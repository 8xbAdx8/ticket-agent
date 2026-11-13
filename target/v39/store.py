"""Independent transactional store; never imports config or the legacy database."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[2]


def utc(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return value.astimezone(timezone.utc)


def integer(value, name, minimum=0, maximum=2**53-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'INVALID_INTEGER:{name}')
    return value


def statements(text):
    """SQLite's parser recognizes trigger BEGIN/END, quoted semicolons and comments."""
    pending = ''
    for line in text.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ''
    if pending.strip() and any(not x.lstrip().startswith('--') for x in pending.splitlines() if x.strip()):
        raise ValueError('INCOMPLETE_MIGRATION')


def safe_path(path):
    p = Path(path).resolve()
    forbidden = [ROOT/'data/tickets.db']
    forbidden += list((ROOT/'artifacts/runtime').glob('railway-static-*/static.sqlite'))
    if any(p == f.resolve() or p.exists() and f.exists() and p.samefile(f) for f in forbidden):
        raise ValueError('PROTECTED_DATABASE')
    if p.name in ('tickets.db', 'static.sqlite') or any(x in p.parts for x in ('traces', 'docs', 'fixtures', 'rag1000')):
        raise ValueError('PROTECTED_DATABASE')
    if p.is_relative_to(ROOT):
        allowed = p.is_relative_to(ROOT/'data/v39')
        runtime = ROOT/'artifacts/runtime'
        if p.is_relative_to(runtime):
            namespace = p.relative_to(runtime).parts[0]
            allowed = namespace in ('v311-abc-integration-20261112','v311-r2-qa09-live-20261112') or namespace.startswith(('v39-implementation-','v391-d9-lifecycle-','v392-','v394-','v310-','full-system-audit-','e2e-user-journey-','v3101-e2e-'))
        if not allowed:
            raise ValueError('PROTECTED_DATABASE_NAMESPACE')
    return p


class Store:
    def __init__(self, path):
        self.path = safe_path(path)

    def connect(self):
        # mode=rw refuses to create an accidental empty database at a bad path.
        c = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=15000')
        if c.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
            c.close()
            raise RuntimeError('FOREIGN_KEYS_DISABLED')
        try:
            row = c.execute('SELECT checksum FROM v39_schema_version WHERE version=1').fetchone()
            if not row or row[0] != self.checksum():
                raise ValueError('SCHEMA_IDENTITY_MISMATCH')
            row=c.execute('SELECT checksum FROM v39_schema_version WHERE version=2').fetchone()
            if not row or row[0]!=self.checksum(2):raise ValueError('V391_MIGRATION_REQUIRED')
        except BaseException:
            c.close()
            raise
        return c

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def initialize(self, *, fail_after=None):
        if self.path.exists():
            with self.transaction() as c:
                row = c.execute('SELECT checksum FROM v39_schema_version WHERE version=1').fetchone()
                if not row or row[0] != self.checksum():
                    raise ValueError('SCHEMA_IDENTITY_MISMATCH')
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects another process or an existing user file.
        with self.path.open('xb'):
            pass
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA foreign_keys=ON')
            assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1
            c.execute('BEGIN IMMEDIATE')
            source = '\n'.join(Path(__file__).with_name(n).read_text(encoding='utf-8') for n in ('schema.sql','hardening.sql'))
            count = 0
            for stmt in statements(source):
                meaningful = '\n'.join(x for x in stmt.splitlines() if not x.lstrip().startswith('--')).strip()
                if not meaningful or meaningful.upper().startswith('PRAGMA'):
                    continue
                c.execute(stmt)
                count += 1
                if fail_after is not None and count == fail_after:
                    raise RuntimeError('MIGRATION_INJECTED_FAILURE')
            c.execute('INSERT INTO v39_schema_version VALUES (1,?,?)', (datetime.now(timezone.utc).isoformat(), self.checksum()))
            for stmt in statements(Path(__file__).with_name('migration_002.sql').read_text(encoding='utf8')):
                c.execute(stmt)
                count+=1
                if fail_after is not None and count==fail_after:raise RuntimeError('MIGRATION_INJECTED_FAILURE')
            c.execute('INSERT INTO v39_schema_version VALUES (2,?,?)',(datetime.now(timezone.utc).isoformat(),self.checksum(2)))
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def checksum(version=1):
        if version==2:return hashlib.sha256(Path(__file__).with_name('migration_002.sql').read_bytes()).hexdigest()
        return hashlib.sha256(b'\0'.join(Path(__file__).with_name(n).read_bytes() for n in ('schema.sql','hardening.sql'))).hexdigest()

    def acquire_worker(self, worker, *, epoch=None, now=None, ttl=60):
        integer(ttl, 'ttl', 1, 3600)
        stamp = utc(now)
        from datetime import timedelta
        expiry = (stamp+timedelta(seconds=ttl)).isoformat()
        epoch = epoch or uuid.uuid4().hex
        with self.transaction() as c:
            row = c.execute('SELECT * FROM v39_worker_lease WHERE slot=1').fetchone()
            if row and row['status']=='ACTIVE' and row['lease_until']>stamp.isoformat() and (row['worker_id'],row['boot_epoch'])!=(worker,epoch):
                raise ValueError('CONFIRMATION_WORKER_BUSY')
            c.execute("INSERT INTO v39_worker_lease(slot,worker_id,boot_epoch,lease_until,status) VALUES(1,?,?,?,'ACTIVE') ON CONFLICT(slot) DO UPDATE SET worker_id=excluded.worker_id,boot_epoch=excluded.boot_epoch,lease_until=excluded.lease_until,status='ACTIVE'", (worker,epoch,expiry))
        return epoch

    def renew_worker(self, worker, epoch, *, now=None, ttl=60):
        from datetime import timedelta
        integer(ttl, 'ttl', 1, 3600)
        stamp = utc(now)
        with self.transaction() as c:
            changed = c.execute("UPDATE v39_worker_lease SET lease_until=? WHERE slot=1 AND worker_id=? AND boot_epoch=? AND status='ACTIVE' AND lease_until>?", ((stamp+timedelta(seconds=ttl)).isoformat(),worker,epoch,stamp.isoformat())).rowcount
            if changed != 1:
                raise ValueError('CONFIRMATION_LEASE_LOST')

    def release_worker(self, worker, epoch):
        with self.transaction() as c:
            return c.execute("UPDATE v39_worker_lease SET status='RELEASED' WHERE slot=1 AND worker_id=? AND boot_epoch=? AND status='ACTIVE'", (worker,epoch)).rowcount == 1
