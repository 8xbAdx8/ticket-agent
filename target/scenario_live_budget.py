"""V3.11 authorization limits over the existing durable /3 budget, no API on import."""
from contextlib import closing
from pathlib import Path
import json
from target.acceptance_budget import Batch

ROOT = Path(__file__).resolve().parents[1]

GUARD = '''CREATE TRIGGER v311_admission BEFORE INSERT ON requests BEGIN
 SELECT RAISE(ABORT,'V311_PROVIDER_NOT_AUTHORIZED') WHERE NEW.provider NOT IN ('deepseek','bailian');
 SELECT RAISE(ABORT,'V311_PHASE_HTTP_LIMIT') WHERE (SELECT count(*) FROM requests)>=(SELECT http_limit FROM v311_limits WHERE id=1);
 SELECT RAISE(ABORT,'V311_PROVIDER_LIMIT') WHERE (SELECT count(*) FROM requests WHERE provider=NEW.provider)>=(SELECT provider_limit FROM v311_limits WHERE id=1);
END'''


def validate_guard(c):
    try:
        rows = c.execute('SELECT * FROM v311_limits').fetchall()
        guard = c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='v311_admission'").fetchone()
        valid = len(rows) == 1 and tuple(rows[0]) in ((1, 'pilot', 24, 12), (1, 'remaining_authorized', 50, 25))
        valid = valid and guard and ' '.join(guard[0].split()) == ' '.join(GUARD.split())
        if valid and rows[0]['phase'] == 'remaining_authorized':
            valid = c.execute('SELECT count(*) FROM v311_release_audit WHERE id=1').fetchone()[0] == 1
    except Exception as exc:
        raise ValueError('V311_BUDGET_GUARD_INVALID') from exc
    if not valid:
        raise ValueError('V311_BUDGET_GUARD_INVALID')


class GuardedConnection:
    def __init__(self, connection): self.connection = connection
    def __getattr__(self, name): return getattr(self.connection, name)
    def execute(self, sql, *args):
        result = self.connection.execute(sql, *args)
        if sql.strip().upper().startswith('BEGIN'):
            try: validate_guard(self.connection)
            except Exception:
                self.connection.rollback()
                raise
        return result


class LiveBatch(Batch):
    def __init__(self, root):
        self.root = Path(root).resolve()
        runtime = ROOT / 'artifacts/runtime'
        if not self.root.is_relative_to(runtime) or not self.root.relative_to(runtime).parts[0].startswith('v310-v311-'):
            raise ValueError('V311_ISOLATED_BATCH_REQUIRED')
        super().__init__(self.root / 'live-budget.sqlite')

    def connect(self):
        c = super().connect()
        try: validate_guard(c)
        except Exception:
            c.close()
            raise
        return GuardedConnection(c)

    def initialize_authorized(self):
        auth = json.loads((self.root / 'authorization.json').read_text('utf8'))
        if auth.get('approved') is not True or auth.get('http_limit') != 50 or auth.get('pilot_http_limit') != 24 or auth.get('provider_limits') != {'deepseek': 25, 'bailian': 25}:
            raise ValueError('V311_AUTHORIZATION_REQUIRED')
        if self.path.exists():
            with closing(self.connect()): pass
            return
        self.initialize()
        # An interrupted bootstrap leaves a closed, unusable batch. Never repair
        # missing guards or reopen its quota automatically.
        with closing(super().connect()) as c:
            c.executescript('BEGIN IMMEDIATE;\n'
                'CREATE TABLE v311_limits(id INTEGER PRIMARY KEY CHECK(id=1), phase TEXT NOT NULL, http_limit INTEGER NOT NULL, provider_limit INTEGER NOT NULL);\n'
                "INSERT INTO v311_limits VALUES(1,'pilot',24,12);\n"
                'CREATE TABLE v311_release_audit(id INTEGER PRIMARY KEY CHECK(id=1), review_json TEXT NOT NULL);\n'
                + GUARD + ';\nCOMMIT;')

    def release_remaining(self, review):
        """Trusted operator action after reviewing the pilot; never a model tool."""
        if not isinstance(review, dict) or review.get('pilot_reviewed') is not True or not review.get('evidence'):
            raise ValueError('V311_PILOT_REVIEW_REQUIRED')
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            encoded=json.dumps(review,ensure_ascii=False,sort_keys=True)
            existing=c.execute('SELECT review_json FROM v311_release_audit WHERE id=1').fetchone()
            if existing and existing[0]!=encoded:
                raise ValueError('V311_RELEASE_REVIEW_CONFLICT')
            c.execute('INSERT OR IGNORE INTO v311_release_audit VALUES(1,?)',(encoded,))
            c.execute("UPDATE v311_limits SET phase='remaining_authorized',http_limit=50,provider_limit=25 WHERE id=1")
            c.commit()
        # The transaction above is the authoritative audit; export is optional.
        try:
            with (self.root / 'pilot-release.json').open('x', encoding='utf8') as f:
                json.dump(review, f, ensure_ascii=False, indent=2)
        except OSError:
            return dict(status='RELEASED',export='NOT_WRITTEN',audit='v311_release_audit:1')
        return dict(status='RELEASED',export='WRITTEN',audit='v311_release_audit:1')

    def status(self):
        with closing(self.connect()) as c:
            c.execute('BEGIN')
            result = self._summary(c)
            result['phase'] = dict(c.execute('SELECT * FROM v311_limits WHERE id=1').fetchone())
            result['providers'] = {p: c.execute('SELECT count(*) FROM requests WHERE provider=?', (p,)).fetchone()[0] for p in ('deepseek', 'bailian')}
            return result
