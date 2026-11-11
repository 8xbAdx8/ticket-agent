"""V3.11-R1 test-only 96 HTTP batch; persists in the existing /3 budget schema.

This module is intentionally test-side. It does not alter Agent, Service, D9/P01,
the historical V311 batch, or the old 11 remaining requests.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import json

from target.acceptance_budget import Batch

ROOT = Path(__file__).resolve().parents[1]
GUARD = '''CREATE TRIGGER v311_r1_admission BEFORE INSERT ON requests BEGIN
 SELECT RAISE(ABORT,'R1_PROVIDER_NOT_AUTHORIZED') WHERE NEW.provider NOT IN ('deepseek','bailian');
 SELECT RAISE(ABORT,'R1_HTTP_LIMIT') WHERE (SELECT count(*) FROM requests)>=(SELECT http_limit FROM r1_limits WHERE id=1);
 SELECT RAISE(ABORT,'R1_PROVIDER_LIMIT') WHERE (SELECT count(*) FROM requests WHERE provider=NEW.provider)>=(SELECT provider_limit FROM r1_limits WHERE id=1);
 SELECT RAISE(ABORT,'R1_PILOT_LIMIT') WHERE (SELECT phase FROM r1_limits WHERE id=1)='pilot' AND (SELECT count(*) FROM requests)>=(SELECT pilot_limit FROM r1_limits WHERE id=1);
END'''


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class R1Batch(Batch):
    def __init__(self, root, *, http_limit=96, provider_limit=48, pilot_limit=24):
        self.root = Path(root).resolve()
        self.http_limit=int(http_limit);self.provider_limit=int(provider_limit);self.pilot_limit=int(pilot_limit)
        runtime = ROOT / 'artifacts/runtime'
        if not self.root.is_relative_to(runtime) or not self.root.relative_to(runtime).parts[0].startswith('v310-v311-r1-'):
            raise ValueError('R1_ISOLATED_BATCH_REQUIRED')
        super().__init__(self.root / 'r1-budget.sqlite', max_http=self.http_limit)

    def connect(self):
        c = super().connect()
        try:
            row = c.execute('SELECT * FROM r1_limits WHERE id=1').fetchone()
            guard = c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='v311_r1_admission'").fetchone()
            allowed=((1,'pilot',self.pilot_limit,min(12,self.provider_limit),self.pilot_limit),(1,'released',self.http_limit,self.provider_limit,self.pilot_limit))
            if not row or tuple(row) not in allowed:
                raise ValueError('R1_BUDGET_GUARD_INVALID')
            if not guard or ' '.join(guard[0].split()) != ' '.join(GUARD.split()):
                raise ValueError('R1_BUDGET_GUARD_INVALID')
        except Exception:
            c.close()
            raise
        return _Guarded(c)

    def initialize_authorized(self, authorization):
        required = {'approved': True, 'http_limit': self.http_limit, 'provider_limits': {'deepseek': self.provider_limit, 'bailian': self.provider_limit}, 'pilot_http_limit': self.pilot_limit}
        if not isinstance(authorization, dict) or any(authorization.get(k) != v for k, v in required.items()):
            raise ValueError('R1_AUTHORIZATION_REQUIRED')
        if self.path.exists():
            with closing(self.connect()):
                pass
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self.initialize()
        with closing(super().connect()) as c:
            c.executescript('BEGIN IMMEDIATE;\n'
                'CREATE TABLE IF NOT EXISTS r1_limits(id INTEGER PRIMARY KEY CHECK(id=1), phase TEXT NOT NULL, http_limit INTEGER NOT NULL, provider_limit INTEGER NOT NULL, pilot_limit INTEGER NOT NULL);\n'
                f"INSERT OR REPLACE INTO r1_limits VALUES(1,'pilot',{self.pilot_limit},{min(12,self.provider_limit)},{self.pilot_limit});\n"
                'CREATE VIEW IF NOT EXISTS v311_limits AS SELECT id,phase,http_limit,provider_limit,NULL AS pilot_limit FROM r1_limits;\n'
                'CREATE TABLE IF NOT EXISTS r1_release_audit(id INTEGER PRIMARY KEY CHECK(id=1), review_json TEXT NOT NULL);\n'
                + GUARD + ';\nCOMMIT;')

    def release_remaining(self, review):
        if not isinstance(review, dict) or review.get('pilot_reviewed') is not True or not review.get('evidence'):
            raise ValueError('R1_PILOT_REVIEW_REQUIRED')
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            encoded = json.dumps(review, ensure_ascii=False, sort_keys=True)
            old = c.execute('SELECT review_json FROM r1_release_audit WHERE id=1').fetchone()
            if old and old[0] != encoded:
                raise ValueError('R1_RELEASE_REVIEW_CONFLICT')
            c.execute('INSERT OR IGNORE INTO r1_release_audit VALUES(1,?)', (encoded,))
            c.execute("UPDATE r1_limits SET phase='released',http_limit=?,provider_limit=? WHERE id=1",(self.http_limit,self.provider_limit))
            c.commit()
        return {'status': 'RELEASED', 'phase': 'released'}

    def status(self):
        with closing(self.connect()) as c:
            c.execute('BEGIN')
            out = self._summary(c)
            out['r1_limits'] = dict(c.execute('SELECT * FROM r1_limits WHERE id=1').fetchone())
            out['providers'] = {p: c.execute('SELECT count(*) FROM requests WHERE provider=?', (p,)).fetchone()[0] for p in ('deepseek', 'bailian')}
            limit=out['r1_limits']['http_limit']
            out['remaining_http_requests']=max(0,limit-out['http_requests'])
            out['remaining_provider_requests']={p:max(0,out['r1_limits']['provider_limit']-n) for p,n in out['providers'].items()}
            return out


class _Guarded:
    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def execute(self, sql, *args):
        result = self._connection.execute(sql, *args)
        if sql.strip().upper().startswith('BEGIN'):
            # Guard validation is repeated transactionally before any request.
            row = self._connection.execute('SELECT * FROM r1_limits WHERE id=1').fetchone()
            if not row:
                self._connection.rollback()
                raise ValueError('R1_BUDGET_GUARD_INVALID')
        return result
