"""Opt-in, durable validation batch. Separate from unlimited daily usage logs.

Reserve an upper bound before HTTP, settle observed usage once. Unknown outcomes
retain their entire reservation. SQLite serializes providers and processes.
"""
from contextlib import closing,contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,sqlite3,uuid

POLICY=dict(schema='ticket-acceptance-budget/3',max_http_requests=50,max_total_tokens=None,
    warning_tokens=320000,max_output_tokens=4096,max_read_retries=2,max_transaction_retries=0)
RETRY=ContextVar('ticket_acceptance_retry',default=None)
WRITE={'lock_seat','create_order','pay_order','cancel_order','monitor_seat','railway_create_order','railway_pay_order','railway_refund_order','railway_change_order','railway_cancel_order'}
def now():return datetime.now(timezone.utc).isoformat()
def fail(category):
    from target.deepseek_runtime import DeepSeekError
    raise DeepSeekError(category)


class Batch:
    def __init__(self,path,*,max_http=None):
        self.path=Path(path).resolve()
        self.max_http=int(max_http) if max_http is not None else POLICY['max_http_requests']
        root=Path(__file__).resolve().parents[1]
        if self.path.is_relative_to(root) and not self.path.is_relative_to(root/'artifacts/runtime'):
            raise ValueError('ACCEPTANCE_BUDGET_PATH_REQUIRED')
        if self.path.suffix!='.sqlite' or self.path.name in ('simulation.sqlite','static.sqlite','tickets.db','simulation-v391.sqlite'):
            raise ValueError('ACCEPTANCE_BUDGET_PATH_REQUIRED')

    def connect(self):
        # An opt-in batch must be initialized explicitly. Never recreate a lost
        # ledger while HTTP is being dispatched.
        c=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=10,isolation_level=None)
        c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=10000')
        row=c.execute('SELECT policy FROM batch WHERE id=1').fetchone()
        if not row:
            c.close();raise ValueError('ACCEPTANCE_BATCH_POLICY_MISMATCH')
        old=json.loads(row[0])
        if old!=POLICY:
            # In-place audit-preserving migration: retain every request row,
            # unknown reservation and batch id; only remove the obsolete
            # project-wide token ceiling policy.
            if old.get('max_total_tokens')==400000 and old.get('max_http_requests')==50:
                c.execute('UPDATE batch SET policy=? WHERE id=1',(json.dumps(POLICY,sort_keys=True),));c.commit();return c
            c.close();raise ValueError('ACCEPTANCE_BATCH_POLICY_MISMATCH')
        return c

    def initialize(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with self.path.open('xb'):pass
        except FileExistsError:
            with closing(self.connect()):pass
            return
        with closing(sqlite3.connect(self.path)) as c:
            c.executescript('''CREATE TABLE batch(id INTEGER PRIMARY KEY CHECK(id=1),batch_id TEXT NOT NULL,policy TEXT NOT NULL,created_at TEXT NOT NULL,halt_reason TEXT);
CREATE TABLE requests(request_id TEXT PRIMARY KEY,provider TEXT NOT NULL,trace_id TEXT,model_step TEXT,payload_sha256 TEXT NOT NULL,reserved_tokens INTEGER NOT NULL CHECK(reserved_tokens>0),output_limit INTEGER NOT NULL,transactional INTEGER NOT NULL,parent_id TEXT,attempt INTEGER NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,prompt INTEGER,completion INTEGER,category TEXT,cost REAL,cost_basis TEXT NOT NULL DEFAULT 'UNKNOWN');''')
            c.execute('INSERT INTO batch VALUES(1,?,?,?,NULL)',(uuid.uuid4().hex,json.dumps(POLICY,sort_keys=True),now()));c.commit()

    @staticmethod
    def _summary(c,max_http=50):
        rows=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY rowid')]
        known=[r for r in rows if type(r['prompt']) is int and type(r['completion']) is int]
        observed=sum(r['prompt']+r['completion'] for r in known)
        committed=observed+sum(r['reserved_tokens'] for r in rows if r not in known)
        return dict(batch_id=c.execute('SELECT batch_id FROM batch WHERE id=1').fetchone()[0],policy=POLICY,
            http_requests=len(rows),observed_tokens=observed if len(known)==len(rows) else None,
            known_observed_tokens=observed,charged_or_reserved_tokens=committed,
            remaining_http_requests=max(0,int(max_http)-len(rows)),remaining_tokens=None,
            warning=committed>=320000,halt_reason=c.execute('SELECT halt_reason FROM batch WHERE id=1').fetchone()[0],
            unresolved_request_ids=[r['request_id'] for r in rows if r not in known],requests=rows,cost=None,cost_basis='UNKNOWN')

    def snapshot(self):
        with closing(self.connect()) as c:
            c.execute('BEGIN');return self._summary(c,self.max_http)

    def reserve(self,request_id,provider,body,raw,*,trace_id=None,model_step=None):
        output=body.get('max_tokens',body.get('max_completion_tokens'))
        if type(output) is not int or not 1<=output<=4096:fail('acceptance_output_limit')
        # UTF-8 payload bytes dominate supported tokenizer text pieces. Add a
        # separate 4096-token framing allowance and maximum possible completion.
        # Never release an unknown reservation based on this estimate.
        bound=len(raw)+4096+output
        payload_hash=hashlib.sha256(raw).hexdigest()
        names={t.get('function',{}).get('name') for t in body.get('tools',[]) if isinstance(t,dict)}
        transactional=bool(names&WRITE) or any(m.get('role')=='tool' and m.get('name') in WRITE for m in body.get('messages',[]) if isinstance(m,dict))
        retry=RETRY.get()
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            state=self._summary(c,self.max_http)
            if state['halt_reason']:fail('acceptance_batch_halted')
            if state['http_requests']>=self.max_http:fail('acceptance_http_budget_exhausted')
            # Token accounting is observability/audit only. Provider quotas, HTTP
            # admission and output limits remain enforced; no project-wide token cap.
            parent=None;attempt=0
            if retry:
                parent=retry
                original=c.execute('SELECT * FROM requests WHERE request_id=?',(parent,)).fetchone()
                if not original or original['parent_id'] or original['finished_at'] is None:fail('acceptance_retry_not_allowed')
                if original['transactional'] or transactional:fail('acceptance_transaction_retry_forbidden')
                if original['payload_sha256']!=payload_hash or original['provider']!=provider:fail('acceptance_retry_payload_conflict')
                attempt=c.execute('SELECT count(*) FROM requests WHERE parent_id=?',(parent,)).fetchone()[0]+1
                if attempt>2:fail('acceptance_retry_limit')
                if original['category'] not in ('rate_limited','server_error','service_unavailable'):fail('acceptance_retry_not_allowed')
            c.execute('INSERT INTO requests(request_id,provider,trace_id,model_step,payload_sha256,reserved_tokens,output_limit,transactional,parent_id,attempt,started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (request_id,provider,trace_id,str(model_step) if model_step is not None else None,payload_hash,bound,output,int(transactional),parent,attempt,now()))
            c.commit()
        return bound

    def settle(self,identity,usage,category):
        usage=usage if isinstance(usage,dict) else {}
        valid=lambda x:type(x) is int and x>=0
        prompt=usage.get('prompt_tokens');completion=usage.get('completion_tokens')
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM requests WHERE request_id=?',(identity,)).fetchone()
            if not row:fail('acceptance_unknown_reservation')
            if row['finished_at'] is not None:return
            observed=valid(prompt) and valid(completion)
            c.execute('UPDATE requests SET prompt=?,completion=?,category=?,finished_at=? WHERE request_id=?',
                (prompt if valid(prompt) else None,completion if valid(completion) else None,category,now(),identity))
            if observed and (prompt+completion>row['reserved_tokens'] or completion>row['output_limit']):
                c.execute("UPDATE batch SET halt_reason='PROVIDER_USAGE_EXCEEDS_RESERVED_BOUND' WHERE id=1")
            c.commit()


def active():
    value=os.getenv('TICKET_ACCEPTANCE_BATCH','').strip()
    if not value:
        return None
    limit = os.getenv('TICKET_ACCEPTANCE_HTTP_LIMIT')
    return Batch(value, max_http=int(limit) if limit is not None else None)


@contextmanager
def controlled_read_retry(original_request_id):
    """Explicit opt-in only. SDK retries remain zero; writes never use this."""
    token=RETRY.set(original_request_id)
    try:yield
    finally:RETRY.reset(token)
