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

    def send(self, message, request_id):
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
        env={"LANGSMITH_TRACING":"false", "LANGCHAIN_TRACING_V2":"false", "AGENT_MUTATIONS":"{}"}
        if self.live:
            # Preserve the launcher's real budget path and limits. Never enable live writes.
            env["DEEPSEEK_LIVE_TEST_PROFILE"]="read_only"
            # New provider selector gets separate ledgers and a shared initial-three ceiling.
            # Keep existing explicit DeepSeek launcher settings for compatibility tests/entry.
            if self.initial_budget or self.live_provider=="bailian":
                from target.live_providers import isolated_environment
                env.update(isolated_environment(self.live_provider,self.root,
                    profile="v35" if self.live_model=="qwen3.8-flash" else None))
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
                full=collect_results(self.agent,self.sid,cursor,record)
                self.history.append(record)
                self.results.append(full)
                if self.agent.last_audit_report:
                    self.audits.append(self.agent.last_audit_report)
                self.receipts[request_id]=record
                return record
            except Exception as exc:
                self.error={"type":type(exc).__name__,**safe_error(exc)}
                if self.agent and self.agent.last_audit_report:
                    self.audits.append(self.agent.last_audit_report)
                raise

    def export_last(self, *, consent=False, transport=None):
        if not self.agent or not self.agent.langchain_engine or not self.agent.langchain_engine.last_live_run:
            raise ValueError("No saved Live run available")
        from target.observability import export_run
        receipt=export_run(self.agent.langchain_engine.last_live_run,consent=consent,trace_dir=self.trace_dir,transport=transport)
        self.remote_receipts.append(receipt)
        return receipt

    def concurrency(self, scenario="same_lock_two"):
        if self.mode != "lab":
            raise ValueError("Only the test lab can run concurrency probes")
        from target.concurrency_probe import probe
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        with scoped(self._values(), {"LANGSMITH_TRACING":"false","LANGCHAIN_TRACING_V2":"false"}):
            records=[probe(scenario, save=True, trace_dir=self.trace_dir), probe(scenario, mutant=True, save=True, trace_dir=self.trace_dir)]
        self.audits.extend(records)
        return records


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
