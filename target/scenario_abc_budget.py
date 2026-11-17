"""Durable admission for the separately authorized A/B/C acceptance batch."""
from contextlib import contextmanager, closing
from contextvars import ContextVar
import json
import re
from pathlib import Path
from unittest.mock import patch

from target.acceptance_budget import Batch, RETRY, fail


BATCH_NAME = 'V311-ABC-INTEGRATION-LIVE-20261112'
ROOT = Path(__file__).resolve().parents[1]
BATCH_ROOT = ROOT / 'artifacts/runtime/v311-abc-integration-20261112'
R2_ROOT = ROOT / 'artifacts/runtime/v311-r2-qa09-live-20261112'
AUTHORIZATION = dict(batch=BATCH_NAME, approved=True, http_total=40, http_per_provider=20,
                     tokens=300000, generate_output=4096, execution_output=2048, http_per_run=8, retry=0)
CURRENT = ContextVar('ticket_abc_live_scope', default=None)
PROVIDERS = ('deepseek', 'bailian')
SCHEMA = '''
CREATE TABLE abc_request_scope (
 request_id TEXT PRIMARY KEY REFERENCES requests(request_id), run_id TEXT NOT NULL,
 stage TEXT NOT NULL, scenario_id TEXT, execution_id TEXT
);
CREATE TRIGGER abc_guard BEFORE INSERT ON requests BEGIN
 SELECT RAISE(ABORT, 'ABC_SCOPE_REQUIRED') WHERE abc_run() IS NULL OR NEW.provider != abc_provider();
 SELECT RAISE(ABORT, 'ABC_HTTP_LIMIT') WHERE (SELECT count(*) FROM requests) >= 40;
 SELECT RAISE(ABORT, 'ABC_PROVIDER_LIMIT') WHERE (SELECT count(*) FROM requests WHERE provider=NEW.provider) >= 20;
 SELECT RAISE(ABORT, 'ABC_RUN_LIMIT') WHERE (SELECT count(*) FROM abc_request_scope WHERE run_id=abc_run()) >= 8;
 SELECT RAISE(ABORT, 'ABC_OUTPUT_OR_RETRY') WHERE NEW.output_limit > abc_output() OR NEW.parent_id IS NOT NULL OR NEW.attempt != 0;
 SELECT RAISE(ABORT, 'ABC_TOKEN_LIMIT') WHERE NEW.reserved_tokens + coalesce((
   SELECT sum(CASE WHEN prompt IS NULL OR completion IS NULL THEN reserved_tokens ELSE prompt+completion END) FROM requests
 ), 0) > 300000;
END;
CREATE TRIGGER abc_link AFTER INSERT ON requests BEGIN
 INSERT INTO abc_request_scope VALUES(NEW.request_id, abc_run(), abc_stage(), abc_case(), abc_execution());
END;
'''


class IntegrationBatch(Batch):
    def __init__(self, root=BATCH_ROOT):
        self.root = Path(root).resolve()
        self._check_authorization()
        super().__init__(self.root / 'integration-budget.sqlite', max_http=40)

    def _check_authorization(self):
        auth = json.loads((self.root / 'authorization.json').read_text(encoding='utf8'))
        if auth != AUTHORIZATION:
            raise ValueError('ABC_AUTHORIZATION_MISMATCH')

    def initialize_authorized(self):
        if self.path.exists():
            with closing(self.connect()):
                return
        super().initialize()
        with closing(super().connect()) as conn:
            conn.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')

    def connect(self):
        self._check_authorization()
        conn = super().connect()
        try:
            expected = {part.split()[2]: ' '.join(part.strip().rstrip(';').split())
                        for part in re.split(r'(?=CREATE (?:TABLE|TRIGGER))', SCHEMA) if part.strip()}
            stored = {row['name']: ' '.join(row['sql'].split()) for row in conn.execute(
                "SELECT name,sql FROM sqlite_master WHERE name IN ('abc_request_scope','abc_guard','abc_link')")}
            if expected != stored or conn.execute('SELECT count(*) FROM requests').fetchone()[0] != conn.execute(
                    'SELECT count(*) FROM abc_request_scope').fetchone()[0]:
                raise ValueError('ABC_DURABLE_GUARD_MISSING')
            scope = CURRENT.get() or {}
            for name, key in (('run', 'run_id'), ('provider', 'provider'), ('stage', 'stage'),
                              ('case', 'scenario_id'), ('execution', 'execution_id')):
                conn.create_function('abc_' + name, 0, lambda key=key: scope.get(key))
            conn.create_function('abc_output', 0, lambda: 4096 if scope.get('stage') == 'generate' else 2048)
            return conn
        except Exception:
            conn.close()
            raise

    def reserve(self, request_id, provider, body, raw, **kwargs):
        scope = CURRENT.get()
        if not scope or provider != scope['provider'] or RETRY.get():
            fail('abc_admission_scope_or_retry')
        return super().reserve(request_id, provider, body, raw, **kwargs)

    def ledger(self):
        with closing(self.connect()) as conn:
            return [dict(row) for row in conn.execute('SELECT r.*, s.run_id, s.stage, s.scenario_id, s.execution_id '
                                                       'FROM requests r JOIN abc_request_scope s USING(request_id) ORDER BY r.rowid')]

    @contextmanager
    def scope(self, run_id, provider, stage, *, scenario_id=None, execution_id=None, evidence_root=None):
        from target import acceptance_budget
        from web.runtime import CALL_LOCK
        from contextlib import ExitStack
        import os
        if not re.fullmatch(r'[0-9a-f]{32}', run_id) or provider not in PROVIDERS or stage not in ('generate', 'agent', 'judge'):
            raise ValueError('ABC_INVALID_RUN_SCOPE')
        evidence = Path(evidence_root).resolve() if evidence_root is not None else self.root
        if evidence != self.root and evidence != R2_ROOT:
            raise ValueError('ABC_UNAUTHORIZED_EVIDENCE_NAMESPACE')
        with CALL_LOCK:
            token = CURRENT.set(dict(run_id=run_id, provider=provider, stage=stage,
                                     scenario_id=scenario_id, execution_id=execution_id))
            try:
                with ExitStack() as stack:
                    stack.enter_context(patch.object(acceptance_budget, 'active', lambda: self))
                    stack.enter_context(patch.dict(os.environ, {'TICKET_ACCEPTANCE_BATCH': str(self.path),
                        'TICKET_API_USAGE_DIR': str(evidence/'api-usage'), 'LANGSMITH_TRACING': 'false',
                        'LANGCHAIN_TRACING_V2': 'false'}))
                    stack.enter_context(self._capture_responses(evidence))
                    yield
            finally:
                CURRENT.reset(token)

    @contextmanager
    def _capture_responses(self, evidence):
        from target import request_accounting
        from target.diagnostics import redact_credentials
        original = request_accounting.settle

        def settle(response, category, body):
            original(response, category, body)
            entry = response.request.extensions.get('ticket_acceptance_reservation')
            if not entry or entry[0] is not self:
                return
            response_dir = evidence/'raw-http'
            response_dir.mkdir(exist_ok=True)
            with (response_dir/(entry[1]+'.json')).open('x', encoding='utf8') as stream:
                row = dict(request_id=entry[1], http_status=response.status_code, category=category,
                           scope=CURRENT.get(), response=redact_credentials(body))
                if evidence == R2_ROOT:
                    import hashlib
                    payload = response.request.content
                    row.update(request_messages=redact_credentials(json.loads(payload)['messages']),
                               request_payload_sha256=hashlib.sha256(payload).hexdigest())
                json.dump(row, stream, ensure_ascii=False)

        with patch.object(request_accounting, 'settle', settle):
            yield
