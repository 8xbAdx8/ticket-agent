"""Atomic cross-ledger reservations and idempotent settlement. No historical guessing."""
import contextvars
import json
import os
import sqlite3
import uuid
import hashlib
from contextlib import contextmanager,closing
from datetime import datetime,timezone
from pathlib import Path

ACTIVE=contextvars.ContextVar("ticket_http_audit",default=None)
SCHEMA="""CREATE TABLE IF NOT EXISTS {db}.requests (
id INTEGER PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, provider TEXT NOT NULL, created TEXT NOT NULL,
status INTEGER, category TEXT, prompt INTEGER, completion INTEGER, model TEXT, phase TEXT NOT NULL,
trace_id TEXT, request_summary TEXT, settled_at TEXT)"""


def now():return datetime.now(timezone.utc).isoformat()


def error(category):
    from target.deepseek_runtime import DeepSeekError
    return DeepSeekError(category)


@contextmanager
def capture(events,trace_id,model_step):
    token=ACTIVE.set((events,trace_id,model_step))
    try:yield
    finally:ACTIVE.reset(token)


def emit(event):
    active=ACTIVE.get()
    if active:active[0].append({**event,"model_step":active[2],"timestamp":now()})


class CoordinatedBudget:
    def __init__(self,settings,provider,shared_path=None,total_limit=None):
        self.settings=settings; self.provider=provider
        self.path=Path(shared_path or os.environ["TICKET_INITIAL_LIVE_BUDGET"]).resolve()
        self.provider_path=Path(settings.ledger_path).resolve()
        self.limit=int(total_limit or os.getenv("TICKET_TOTAL_REQUEST_LIMIT","3"))
        if self.path==self.provider_path or not 1<=self.limit<=4 or not 1<=settings.max_requests<=5:
            raise error("invalid_coordinated_budget")

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);self.provider_path.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None); c.row_factory=sqlite3.Row
        try:
            c.execute("ATTACH DATABASE ? AS provider_db",(str(self.provider_path),))
            for db in ("main","provider_db"):
                columns={r[1] for r in c.execute(f"PRAGMA {db}.table_info(requests)")}
                if columns and "request_id" not in columns:raise error("historical_unlinked_ledger_requires_new_validation_pair")
                if c.execute(f"PRAGMA {db}.journal_mode").fetchone()[0].lower() not in ("delete","truncate","persist"):
                    raise error("atomic_budget_journal_required")
            c.execute("BEGIN IMMEDIATE")
            for db,cap in (("main",self.limit),("provider_db",self.settings.max_requests)):
                c.execute(SCHEMA.format(db=db))
                c.execute(f"CREATE TABLE IF NOT EXISTS {db}.budget_policy (id INTEGER PRIMARY KEY CHECK(id=1), limit_value INTEGER NOT NULL)")
                c.execute(f"INSERT OR IGNORE INTO {db}.budget_policy VALUES(1,?)",(cap,))
                if c.execute(f"SELECT limit_value FROM {db}.budget_policy WHERE id=1").fetchone()[0]!=cap:
                    raise error("persisted_budget_limit_mismatch")
            yield c
            c.execute("COMMIT")
        except Exception:
            if c.in_transaction:c.execute("ROLLBACK")
            raise
        finally:c.close()

    def reserve(self,summary=None,request_id=None):
        identity=request_id or uuid.uuid4().hex
        active=ACTIVE.get(); trace_id=active[1] if active else None
        with self.transaction() as c:
            old=c.execute("SELECT * FROM main.requests WHERE request_id=?",(identity,)).fetchone()
            if old:
                peer=c.execute("SELECT * FROM provider_db.requests WHERE request_id=?",(identity,)).fetchone()
                if not peer or dict(peer)["provider"]!=self.provider:raise error("request_identity_conflict")
                return identity
            if (c.execute("SELECT COUNT(*) FROM main.requests").fetchone()[0]>=self.limit or
                    c.execute("SELECT COUNT(*) FROM provider_db.requests").fetchone()[0]>=self.settings.max_requests):
                raise error("request_budget_exhausted")
            from target.diagnostics import sanitize
            values=(identity,self.provider,now(),"reserved_outcome_unknown","reserved",trace_id,json.dumps(sanitize(summary or {}),ensure_ascii=False))
            for db in ("main","provider_db"):
                c.execute(f"INSERT INTO {db}.requests(request_id,provider,created,category,phase,trace_id,request_summary) VALUES(?,?,?,?,?,?,?)",values)
        return identity

    def record(self,identity,*,status=None,category="response_received",usage=None,model=None,phase="settled"):
        usage=usage if isinstance(usage,dict) else {}
        tokens=[usage.get(k) if type(usage.get(k)) is int and usage[k]>=0 else None for k in ("prompt_tokens","completion_tokens")]
        from target.deepseek_runtime import safe_text
        with self.transaction() as c:
            old=c.execute("SELECT * FROM main.requests WHERE request_id=?",(identity,)).fetchone()
            if not old:raise error("unknown_request_identity")
            # A later SDK/tool failure must never overwrite the observed HTTP response.
            if old["status"] is not None:
                if status is None:return
                if old["status"]!=status:raise error("conflicting_request_settlement")
                return
            settled_at=now() if phase!="dispatch_started" else None
            for db in ("main","provider_db"):
                cur=c.execute(f"UPDATE {db}.requests SET status=?,category=?,prompt=?,completion=?,model=?,phase=?,settled_at=? WHERE request_id=?",
                    (status,category,*tokens,safe_text(model)[:120] if model else None,phase,settled_at,identity))
                if cur.rowcount!=1:raise error("missing_provider_request_mirror")

    def snapshot(self):
        return snapshot(self.provider_path,self.settings.max_requests)


def snapshot(path,limit):
    path=Path(path)
    if not path.exists():return {"reserved_requests":0,"limit":limit,"requests":[],"unsettled_ids":[]}
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)) as c:
        c.row_factory=sqlite3.Row
        rows=[dict(r) for r in c.execute("SELECT * FROM requests ORDER BY id")]
    return {"reserved_requests":len(rows),"limit":limit,"requests":rows,
            "unsettled_ids":[r.get("request_id",f"legacy-row:{r['id']}") for r in rows if r.get("status") is None],
            "historical_unlinked":bool(rows and "request_id" not in rows[0])}


def budget_for(settings,provider):
    if os.getenv("TICKET_INITIAL_LIVE_BUDGET"):return CoordinatedBudget(settings,provider)
    from target.deepseek_runtime import RequestBudget
    return RequestBudget(settings)


def reserve(request,budget,provider,body):
    if "ticket_reservation" in request.extensions:raise error("duplicate_request_dispatch")
    summary={"model":body.get("model"),"message_roles":[m.get("role") for m in body.get("messages",[])],
             "returned_tool_call_ids":[m.get("tool_call_id") for m in body.get("messages",[]) if m.get("role")=="tool"]}
    try:identity=budget.reserve(summary) if isinstance(budget,CoordinatedBudget) else budget.reserve()
    except Exception:
        emit({"event":"http_budget_blocked","provider":provider});raise
    uid=identity if isinstance(budget,CoordinatedBudget) else f"legacy-{hashlib.sha256(str(budget.settings.ledger_path.resolve()).encode()).hexdigest()[:16]}-{identity}"
    request.extensions["ticket_reservation"]=(budget,identity,uid,provider)
    request.extensions["ticket_budget_id"]=identity
    if isinstance(budget,CoordinatedBudget):budget.record(identity,category="dispatched_outcome_unknown",phase="dispatch_started")
    emit({"event":"http_request","request_id":uid,"provider":provider,"summary":summary})


def settle(response,category,body):
    entry=response.request.extensions.get("ticket_reservation")
    if not entry:return
    budget,identity,uid,provider=entry
    budget.record(identity,status=response.status_code,category=category,
                  usage=body.get("usage") if isinstance(body,dict) else None,model=body.get("model") if isinstance(body,dict) else None)
    response.request.extensions["ticket_response_settled"]=True
    emit({"event":"http_response","request_id":uid,"provider":provider,"http_status":response.status_code,
          "category":category,"usage":body.get("usage") if isinstance(body,dict) else None})


def client_class():
    import httpx
    class AuditedClient(httpx.Client):
        def send(self,request,*args,**kwargs):
            try:return super().send(request,*args,**kwargs)
            except Exception as exc:
                entry=request.extensions.get("ticket_reservation")
                if entry:
                    from target.deepseek_runtime import safe_error
                    budget,identity,uid,provider=entry; category=safe_error(exc)["category"]
                    if not request.extensions.get("ticket_response_settled") and isinstance(budget,CoordinatedBudget):
                        budget.record(identity,category=category+"_outcome_unknown")
                    emit({"event":"http_error","request_id":uid,"provider":provider,"error":safe_error(exc)})
                raise
    return AuditedClient
