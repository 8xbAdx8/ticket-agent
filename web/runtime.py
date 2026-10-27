"""One UI call path into the existing Agent; per-session business/trace isolation.

The legacy runtime uses module configuration. Serialize UI calls while restoring
that configuration, rather than changing backend interfaces or sharing databases.
"""
import contextlib
import io
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
import config
from target.agent import Agent
from target.deepseek_runtime import safe_error
from web.presentation import collect_results, turn_cursor

CALL_LOCK = threading.RLock()
LIVE_AVAILABLE = config.PROVIDER == "deepseek"
LIVE_MODEL = config.MODEL_NAME
LIVE_URL = config.BASE_URL
LIVE_KEY = config.API_KEY if LIVE_AVAILABLE else ""
ROOT = config.BASE_DIR


def refresh_conversations(sessions):
    """Streamlit retains old class instances on hot reload; keep their data and new methods."""
    for session in sessions:
        old=type(session)
        if old is not Conversation and (old.__module__,old.__qualname__)==(Conversation.__module__,Conversation.__qualname__):
            session.__class__=Conversation


@contextlib.contextmanager
def scoped(values, environment=None):
    """All UI model/business calls hold this lock, including configuration restore."""
    with CALL_LOCK:
        prior = {name: getattr(config, name) for name in values}
        old_env = {name: os.environ.get(name) for name in (environment or {})}
        try:
            for name, value in values.items():
                setattr(config, name, value)
            for name, value in (environment or {}).items():
                os.environ[name] = value
            yield
        finally:
            for name, value in prior.items():
                setattr(config, name, value)
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def live_ready(provider=None):
    if os.getenv("TICKET_WEB_OFFLINE_ONLY") == "1": return False
    if provider is None:
        return LIVE_AVAILABLE and bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
    from target.live_providers import configuration
    return bool(configuration(provider)["configured"])


@dataclass
class Conversation:
    mode: str
    engine: str = "legacy"
    live: bool = False
    live_provider: str = "deepseek"
    live_model: str | None = None
    case_id: str | None = None
    initial_budget: bool = False
    rag_mode: str | None = None
    allow_rag_network: bool = False
    interactive: bool = False
    mutations: dict = field(default_factory=dict)
    root: Path | None = None
    sid: str = field(default_factory=lambda: "web-"+uuid.uuid4().hex[:12])
    history: list = field(default_factory=list)
    results: list = field(default_factory=list)
    audits: list = field(default_factory=list)
    agent: object = None
    error: dict | None = None
    receipts: dict = field(default_factory=dict)
    remote_receipts: list = field(default_factory=list)

    def __post_init__(self):
        if self.mode not in ("user", "lab"):
            raise ValueError("Unknown UI mode")
        if self.mode == "user" and self.mutations:
            raise ValueError("普通用户模式不能注入变异")
        if self.live and self.engine != "langchain":
            raise ValueError("Live requires LangChain")
        if self.live and self.live_provider not in ("deepseek","bailian"):
            raise ValueError("Unknown Live provider")
        self.root = Path(self.root) if self.root else ROOT/"artifacts/runtime/v33"/self.mode/self.sid
        base=(ROOT/"artifacts/runtime").resolve()
        if not self.root.resolve().is_relative_to(base) or self.root.resolve()==base:
            raise ValueError("UI runtime must stay in isolated artifacts/runtime")

    @property
    def trace_dir(self):
        return self.root/"traces"

    def _values(self):
        from target.live_providers import configuration
        cfg=configuration(self.live_provider) if self.live else {}
        model=LIVE_MODEL if self.live_provider=="deepseek" and LIVE_AVAILABLE else cfg.get("model")
        if self.live and self.live_model:model=self.live_model
        address=LIVE_URL if self.live_provider=="deepseek" and LIVE_AVAILABLE else cfg.get("base_url")
        return dict(DB_PATH=self.root/"tickets.db", TRACE_DIR=self.trace_dir, PROVIDER=self.live_provider if self.live else "mock",
                    ENGINE=self.engine, LC_TOOLSET="read_only" if self.live else "all", USE_HTTP_MOCK=False, USE_VECTOR_RAG=False,
                    MODEL_NAME=model if self.live else "langchain-mock" if self.engine=="langchain" else "mock-offline",
                    BASE_URL=address if self.live else "https://api.deepseek.com", API_KEY=os.getenv(cfg["key_env"],"") if self.live else "")

    def send(self,message,request_id):
        self.error=None
        try:return self._send(message,request_id)
        except Exception as exc:
            if self.error is None:self.error={'type':type(exc).__name__,**safe_error(exc)}
            raise

    def _send(self, message, request_id):
        if request_id in self.receipts:
            return self.receipts[request_id]
        if self.live and not live_ready(self.live_provider):
            raise ValueError("Live 未配置或本轮已禁止联网；没有发送请求")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("消息不能为空")
        from target.fault_injection import normalize
        normalize(self.mutations)
        if self.mutations.get("concurrent_duplicate_order"):
            raise ValueError("M8 不适用于普通对话，请运行并发对照")
        env={"LANGSMITH_TRACING":"false", "LANGCHAIN_TRACING_V2":"false", "AGENT_MUTATIONS":"{}",
             "TICKET_CASE_ID":self.case_id or "interactive"}
        if self.live:
            env["DEEPSEEK_LIVE_TEST_PROFILE"]="read_only"
            from target.live_providers import manual_environment
            env.update(manual_environment(self.live_provider,self.root,model=self.live_model))
            if self.rag_mode is not None:env['AGENT_RAG_MODE']=self.rag_mode
            env['RAG_ALLOW_NETWORK']='1' if self.allow_rag_network else '0'
            env["TICKET_CASE_ID"]=self.case_id or "interactive"
        elif self.engine=="langchain" and any(self.mutations.get(k) for k in ("skip_lock","infinite_loop")):
            # Existing sandbox guard, only for the offline Mock test environment.
            env.update(DEEPSEEK_LIVE_TEST_PROFILE="full_sandbox", DEEPSEEK_SANDBOX_DIR=str(self.root),
                       DEEPSEEK_BUDGET_PATH=str(self.root/"requests.db"), DEEPSEEK_MAX_REQUESTS="5")
        self.error=None
        with scoped(self._values(),env):
            try:
                self.root.mkdir(parents=True,exist_ok=True)
                self.trace_dir.mkdir(exist_ok=True)
                if not self.live and env.get("DEEPSEEK_LIVE_TEST_PROFILE")=="full_sandbox":
                    (self.root/".ticket-agent-sandbox.json").write_text(json.dumps({"purpose":"ticket-agent-fault-test","version":1,"simulated_only":True}),encoding="utf-8")
                if not config.DB_PATH.exists():
                    from data.seed import build_db
                    with contextlib.redirect_stdout(io.StringIO()):
                        build_db(config.DB_PATH)
                if self.agent is None:
                    kwargs={"engine":self.engine,"mutations":dict(self.mutations)}
                    if not self.live and self.engine=="legacy":
                        from target.providers import MockProvider
                        kwargs["provider"]=MockProvider(mutations=dict(self.mutations))
                    self.agent=Agent(**kwargs)
                cursor=turn_cursor(self.agent,self.sid)
                record=self.agent.chat(self.sid,message)
                audit_error=(self.agent.last_audit_report or {}).get('error')
                if audit_error:
                    self.error={'type':'AgentError',**audit_error}
                    raise RuntimeError('agent_recorded_execution_error')
                full=collect_results(self.agent,self.sid,cursor,record)
                self.history.append(record)
                self.results.append(full)
                if self.agent.last_audit_report:
                    self.audits.append(self.agent.last_audit_report)
                self.receipts[request_id]=record
                return record
            except Exception as exc:
                if self.error is None:self.error={"type":type(exc).__name__,**safe_error(exc)}
                if self.agent and self.agent.last_audit_report:
                    self.audits.append(self.agent.last_audit_report)
                raise


    def export_last(self, *, consent=False, transport=None):
        if not self.agent or not self.agent.langchain_engine or not self.agent.langchain_engine.last_live_run:
            raise ValueError("No saved Live run available")
        if self.latest_remote_receipt():
            raise ValueError("An existing export must be read back, never automatically reposted")
        from target.observability import export_run
        receipt=export_run(self.agent.langchain_engine.last_live_run,consent=consent,trace_dir=self.trace_dir,transport=transport)
        self.remote_receipts.append(receipt)
        return receipt

    def latest_remote_receipt(self):
        run=self.agent.langchain_engine.last_live_run if self.agent and self.agent.langchain_engine else None
        if not run:return None
        from web.evidence import read_jsonl
        saved,_=read_jsonl(self.trace_dir/'langsmith_readbacks.jsonl')
        rows=[r for r in [*self.remote_receipts,*saved] if isinstance(r,dict)
              and r.get('local_trace_id')==run.get('trace_id') and r.get('remote_run_id')
              and (r.get('post_http_status') in (200,201,202) or r.get('remote_status')=='upload_outcome_unknown'
                   or r.get('upload_outcome_unknown'))]
        return max(rows,key=lambda r:r.get('timestamp','')) if rows else None

    def recheck_export(self, *, consent=False, transport=None):
        receipt=self.latest_remote_receipt()
        if not receipt:raise ValueError('No existing remote run available')
        from target.observability import verify_existing,export_payload
        run=self.agent.langchain_engine.last_live_run
        payload=export_payload(run)
        if receipt.get('payload_file'):
            expected='langsmith_payloads/'+str(uuid.UUID(receipt['remote_run_id']))+'.json'
            if receipt['payload_file']!=expected:raise ValueError('Invalid frozen export path')
            payload=json.loads((self.trace_dir/expected).read_text(encoding='utf-8'))
        result=verify_existing(receipt,payload,consent=consent,transport=transport,
                               max_read_attempts=3,trace_dir=self.trace_dir)
        self.remote_receipts.append(result)
        return result

    def concurrency(self, scenario="same_lock_two"):
        if self.mode != "lab":
            raise ValueError("Only the test lab can run concurrency probes")
        from target.concurrency_probe import probe
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        with scoped(self._values(), {"LANGSMITH_TRACING":"false","LANGCHAIN_TRACING_V2":"false"}):
            records=[probe(scenario, save=True, trace_dir=self.trace_dir)]
            self.audits.extend(records)  # Retain a saved baseline even if the next probe fails.
            if scenario not in ("expired_lock","worker_failure"):
                mutant=probe(scenario, mutant=True, save=True, trace_dir=self.trace_dir)
                records.append(mutant)
                self.audits.append(mutant)
        return records


def failure_hint(category):
    messages={
        'historical_unlinked_ledger_requires_new_validation_pair':'这是旧版本保存的账本错误。当前Live已移除该拦截，旧记录保持原样。',
        'request_budget_exhausted':'这是旧版本保存的本地预算错误。当前Live累计请求数不限，旧记录保持原样。',
        'missing_DEEPSEEK_API_KEY':'未读取到DeepSeek Key，请重新启动在线入口。',
        'missing_DASHSCOPE_API_KEY':'未读取到千问Key，请核对DASHSCOPE_API_KEY后重新启动。',
        'authentication_failed':'模型服务拒绝了Key，请检查有效性。',
        'permission_denied':'服务商拒绝访问，请检查模型、地域和账号权限。',
        'rate_limited':'服务商限流（HTTP 429），本次未自动重试，请稍后手动发送。',
        'server_error':'模型服务端错误（HTTP 500），本次未自动重试。',
        'service_unavailable':'模型服务暂不可用（HTTP 503），本次未自动重试。',
        'insufficient_balance':'模型账户余额或可用额度不足。',
        'timeout':'模型请求超时，本次未自动重试。',
        'network_connection':'模型网络连接失败，请检查本机网络或代理。',
        'reply_data_indeterminate':'模型已返回，但回答与工具数据的自动核对未能确定通过；请在Trace查看证据。这不是联网失败。',
        'reply_tool_mismatch':'模型回答与工具数据不一致，已拦截该回答；请在Trace查看具体字段。',
        'token_usage_unknown':'模型未提供可核对的Token用量，原始旁证已保留。'}
    return messages.get(category,'请求未完成，本次未自动重试；可在Trace中查看详细旁证。')


def operation_kind(message):
    """UI confirmation aid only. Existing backend authorization remains authoritative."""
    import re
    if re.search(r"[?？]|多久|政策|规则|怎么|如何|是否|会不会", message):
        return None
    if re.search(r"不要|别|不想|不能|不需要", message):
        return None
    if re.search(r"支付|付款|退票|退掉|取消订单|候补|抢票|监控|锁座|下单|订票|我要买|帮我订|^(?:请)?订|购买",message):
        return "模拟业务操作"
    return None
