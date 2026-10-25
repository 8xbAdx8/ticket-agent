"""DeepSeek 安全边界：官方地址、非思考模式、持久请求预算、脱敏错误。

这里不生成 tool_calls。模型和工具仍由已有 create_agent 调度。
"""
import json
import logging
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

try:
    import httpx
except ImportError:
    httpx = None  # V2 的 Mock 环境不因新增适配器而被迫安装 SDK。
import config

READ_ONLY = frozenset(("query_tickets", "search_policy"))
VALIDATION_NOTICE = ("DeepSeek 已于 2026-10-16 验证 query_tickets、search_policy 两个 Live 工具；"
                     "其余六个工具未开放 Live。该结论来自已保存的历史记录，不表示本轮实时调用或正式测试通过。")
READ_ONLY_PROMPT = """你是只读的模拟出行咨询助手。当前只支持 query_tickets 查询虚构余票和 search_policy 检索政策。
不得执行、承诺或主动邀请锁座、候补、下单、支付、取消或订单查询；即使用户要求，也应明确说明能力边界。
可以说“当前仅支持模拟查票和政策咨询”。政策中可以解释锁座/支付规则，但不代表你能办理。
具体班次、价格和库存必须来自 query_tickets；政策必须来自 search_policy，注明实际返回的 doc_id。
相对日期先换算成 YYYY-MM-DD；明确切换高铁/机票时重置不兼容席别，未指定条件时继承上下文，含糊时澄清。
区分目标席别售罄、存在余票、没有匹配班次；未查询其他席别时不能断言其有票。
工具失败时如实说明，不得编造结果或声称业务成功。不要展示内部推理内容。"""


def validate_read_only_reply(reply):
    """按执行主体识别承诺/邀约；政策和外部渠道说明不是本助手执行。

    这是有限的语言规则，不是通用语义安全判定器；拒绝时不改写原回复。
    """
    action = r"锁座|锁定座位|订票|预订|下单|创建订单|支付|付款|扣款|退票|取消订单|候补|查询订单|查订单"
    # “办理”本身不是承诺。先找助手自身的肯定承诺，再判断用户邀约的执行渠道。
    own_offer = r"(?:我(?:们)?(?:可以|能够|能|来|会|将|要)|本助手(?:可以|能够|会|将)|(?:帮|替|为)(?:您|你))"
    execution = r"(?:(?:现在|直接|马上|立即|继续|先|再|将|会|来|帮|替|为|您|你|办理|执行|完成|操作|进行|提供|成功))*"
    invitation = r"(?:您|你)(?:可以|可)|请(?:您|你)?(?:先)?(?:锁座|下单|订票|付款)|需要.{0,12}(?:吗|么)|是否|要不要|继续.{0,8}(?:吗|么)"
    own_invitation = r"需要(?:我(?:们)?|本助手).{0,60}(?:吗|么)"
    external = r"(?:通过|前往|到|在|联系).{0,24}(?:官方渠道|官方平台|官网|12306|航空公司|航司|铁路|售票窗口)"
    done = r"(?:已经|已|成功).{0,12}(?:" + action + r")|(?:" + action + r").{0,6}成功"
    # 否定只作用于自己的子句，不能豁免后面的“我可以……”肯定承诺。
    clauses = re.split(r"[。！？!?；;,，\n]|但是|不过|但|并且|而且|(?=我(?:们)?(?:可以|能够|将|会|来))", reply)
    for clause in clauses:
        if re.search(r"(?:不支持|不提供|不能|无法|不可|不会|未执行|未办理|没有执行|没有完成|未完成|尚未|不得|禁止|不允许|不能够)", clause):
            continue
        if not re.search(action, clause):
            continue
        if (re.search(done, clause) or re.search(own_invitation, clause)
                or re.search(own_offer + execution + r"(?:" + action + r")", clause)):
            raise DeepSeekError("read_only_capability_violation")
        if re.search(invitation, clause) and not re.search(external, clause):
            raise DeepSeekError("read_only_capability_violation")
    if re.search(r"\b(?:I can|I will|shall I|would you like|let me)\b.{0,60}\b(?:book|reserve|pay|purchase|cancel)\b", reply, re.I):
        raise DeepSeekError("read_only_capability_violation")
ERRORS = {400: "invalid_format", 401: "authentication_failed", 402: "insufficient_balance",
          422: "invalid_parameters", 429: "rate_limited", 500: "server_error", 503: "service_unavailable"}


class DeepSeekError(RuntimeError):
    def __init__(self, category, status=None):
        self.category, self.status = category, status
        super().__init__(f"DeepSeek 请求未完成：{category}" + (f" (HTTP {status})" if status else ""))


def safe_error(exc):
    """不包含 str(exc)、响应正文、请求头或第三方堆栈。"""
    if isinstance(exc, DeepSeekError):
        return {"category": exc.category, "http_status": exc.status}
    cause, seen = exc, set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause,DeepSeekError):
            return {"category":cause.category,"http_status":cause.status}
        cause = cause.__cause__
    status = getattr(exc, "status_code", None)
    if status is None and httpx and isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    if status:
        return {"category": ERRORS.get(status, "http_error"), "http_status": status}
    if isinstance(exc, ImportError):
        return {"category":"dependency_missing","http_status":None}
    name = type(exc).__name__.lower()
    category = "timeout" if (httpx and isinstance(exc, httpx.TimeoutException)) or "timeout" in name else (
        "network_connection" if (httpx and isinstance(exc, httpx.TransportError)) or "connection" in name else "client_error")
    return {"category": category, "http_status": None}


def safe_text(text):
    from target.diagnostics import redact_credentials
    return redact_credentials(str(text))


@dataclass(frozen=True)
class Settings:
    timeout: float = 20
    max_requests: int = 5  # 0：用户手动使用时不限制累计请求数，仍逐次记账。
    max_output_tokens: int = 512
    max_model_calls: int = 3
    max_tool_calls: int = 4
    turn_token_budget: int = 12000
    max_payload_bytes: int = 32000
    ledger_path: Path = config.BASE_DIR / "artifacts/runtime/deepseek-budget/requests.db"
    profile: str = "read_only"
    sandbox_root: Path | None = None

    @classmethod
    def from_env(cls):
        values = dict(timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "20")),
            max_requests=int(os.getenv("DEEPSEEK_MAX_REQUESTS", "5")),
            max_output_tokens=int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "512")),
            max_model_calls=int(os.getenv("DEEPSEEK_MAX_MODEL_CALLS", "3")),
            max_tool_calls=int(os.getenv("DEEPSEEK_MAX_TOOL_CALLS", "4")),
            turn_token_budget=int(os.getenv("DEEPSEEK_TURN_TOKEN_BUDGET", "12000")),
            max_payload_bytes=int(os.getenv("DEEPSEEK_MAX_PAYLOAD_BYTES", "32000")),
            ledger_path=Path(os.getenv("DEEPSEEK_BUDGET_PATH",str(cls.ledger_path))))
        bounds = {"timeout":(1,60),"max_requests":(0,5),"max_output_tokens":(16,1024),
                  "max_model_calls":(1,4),"max_tool_calls":(1,8),"turn_token_budget":(512,32000),
                  "max_payload_bytes":(1000,64000)}
        if any(not low <= values[k] <= high for k,(low,high) in bounds.items()):
            raise DeepSeekError("invalid_safety_limits")
        if os.getenv("DEEPSEEK_THINKING", "disabled") != "disabled":
            raise DeepSeekError("thinking_mode_not_validated")
        profile = os.getenv("DEEPSEEK_LIVE_TEST_PROFILE", "read_only")
        if profile not in ("read_only", "full_sandbox"):
            raise DeepSeekError("invalid_test_profile")
        settings = cls(**values, profile=profile,
                       sandbox_root=Path(os.environ["DEEPSEEK_SANDBOX_DIR"]) if os.getenv("DEEPSEEK_SANDBOX_DIR") else None)
        if profile == "full_sandbox":
            validate_sandbox(settings)
        return settings


def validate_sandbox(settings):
    """全工具仅在显式创建的新本地沙箱；不允许HTTP后端或原始库。"""
    root = settings.sandbox_root.resolve() if settings.sandbox_root else None
    base = (config.BASE_DIR / "artifacts/runtime").resolve()
    if (root is None or not root.is_relative_to(base) or root == base or config.USE_HTTP_MOCK
            or config.DB_PATH.resolve() != root / "tickets.db"
            or config.TRACE_DIR.resolve() != root / "traces"
            or settings.ledger_path.resolve() != root / "requests.db" or settings.max_requests == 0):
        raise DeepSeekError("isolated_sandbox_required")
    try:
        marker = json.loads((root / ".ticket-agent-sandbox.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise DeepSeekError("sandbox_marker_required") from None
    if marker != {"purpose":"ticket-agent-fault-test","version":1,"simulated_only":True}:
        raise DeepSeekError("sandbox_marker_required")


def allowed_tools(settings):
    if settings.profile == "full_sandbox":
        validate_sandbox(settings)  # 发送HTTP请求前也重新验证，防止运行中改变配置。
        from target.tools import TOOL_NAMES
        return frozenset(TOOL_NAMES)
    return READ_ONLY


def validate_configuration():
    address = urlsplit(config.BASE_URL)
    if address.scheme != "https" or address.netloc != "api.deepseek.com" or address.path not in ("", "/", "/v1", "/v1/") or address.query or address.fragment:
        raise DeepSeekError("official_endpoint_required")
    if config.MODEL_NAME != "deepseek-flash":
        raise DeepSeekError("deepseek_flash_required")
    if not config.API_KEY.strip():
        raise DeepSeekError("missing_DEEPSEEK_API_KEY")


class RequestBudget:
    """SQLite 事务先占预算再发送；崩溃/超时不退还，防止自动重发。

    同一 ledger 的进程共享上限；max_requests=0 显式关闭累计上限，但保留账本。
    人为删除/改路径、其他客户端不受此限制。
    """
    def __init__(self, settings):
        self.settings = settings

    def _connect(self):
        self.settings.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.settings.ledger_path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, created TEXT, status INTEGER, category TEXT, prompt INTEGER, completion INTEGER, model TEXT)")
        return c

    def reserve(self):
        c = self._connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            count = c.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            if self.settings.max_requests != 0 and count >= min(5,self.settings.max_requests):
                raise DeepSeekError("request_budget_exhausted")
            row = c.execute("INSERT INTO requests(created,category) VALUES (?,?)",
                            (datetime.now(timezone.utc).isoformat(), "reserved_outcome_unknown"))
            c.commit()
            return row.lastrowid
        finally:
            c.close()

    def record(self, identity, *, status=None, category="response_received", usage=None, model=None):
        usage = usage or {}
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        prompt = prompt if type(prompt) is int and prompt >= 0 else None
        completion = completion if type(completion) is int and completion >= 0 else None
        with closing(self._connect()) as c:
            c.execute("UPDATE requests SET status=?,category=?,prompt=?,completion=?,model=? WHERE id=?",
                      (status,category,prompt,completion,safe_text(model)[:100] if model else None,identity))
            c.commit()

    def snapshot(self):
        # 没有请求时不创建 ledger，也不会为“检查密钥”消耗预算。
        if not self.settings.ledger_path.exists():
            return {"reserved_requests":0,"limit":self.settings.max_requests,"requests":[]}
        with closing(self._connect()) as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM requests ORDER BY id")]
        return {"reserved_requests":len(rows),"limit":self.settings.max_requests,"requests":rows}


def guarded_client(settings, *, transport=None):
    if httpx is None:
        raise DeepSeekError("dependency_missing")
    for name in ("httpx","httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    budget = RequestBudget(settings)

    def before(request):
        if request.url.scheme != "https" or request.url.host != "api.deepseek.com" or request.url.port not in (None,443):
            raise DeepSeekError("official_endpoint_required")
        if request.method == "GET" and request.url.path in ("/user/balance","/v1/user/balance"):
            return
        if request.method != "POST" or request.url.path not in ("/chat/completions","/v1/chat/completions"):
            raise DeepSeekError("endpoint_not_allowed")
        body = json.loads(request.content)
        names = {t.get("function",{}).get("name") for t in body.get("tools",[])}
        if body.get("model") != "deepseek-flash" or body.get("thinking") != {"type":"disabled"}:
            raise DeepSeekError("request_configuration_rejected")
        if not names <= allowed_tools(settings):
            raise DeepSeekError("read_only_tools_required")
        if body.get("stream"):
            raise DeepSeekError("streaming_not_validated")
        output_limit = body.get("max_tokens",body.get("max_completion_tokens"))
        if type(output_limit) is not int or not 1 <= output_limit <= settings.max_output_tokens:
            raise DeepSeekError("output_token_limit_required")
        if len(request.content) > settings.max_payload_bytes:
            raise DeepSeekError("request_payload_limit")
        from target.live_providers import reserve_initial_budget
        reserve_initial_budget()
        request.extensions["ticket_budget_id"] = budget.reserve()

    def after(response):
        identity = response.request.extensions.get("ticket_budget_id")
        if identity is None:
            return
        response.read()
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = {}
        if not isinstance(body,dict):
            body = {}
        budget.record(identity,status=response.status_code,
                      category="response_received" if response.is_success else ERRORS.get(response.status_code,"http_error"),
                      usage=body.get("usage"),model=body.get("model"))

    return httpx.Client(timeout=settings.timeout,follow_redirects=False,transport=transport,
                        event_hooks={"request":[before],"response":[after]})


def make_model(settings=None, *, transport=None):
    validate_configuration()
    settings = settings or Settings.from_env()
    from langchain_deepseek import ChatDeepSeek
    # 不开启 SDK debug 日志或外部 LangSmith 观测。
    logging.getLogger("openai").setLevel(logging.WARNING)
    client = guarded_client(settings,transport=transport)
    return ChatDeepSeek(model=config.MODEL_NAME,api_key=config.API_KEY,base_url=config.BASE_URL,
        timeout=settings.timeout,max_retries=0,max_tokens=settings.max_output_tokens,
        extra_body={"thinking":{"type":"disabled"}},http_client=client,streaming=False,
        use_responses_api=False)


def save_run_evidence(trace, events, error=None):
    """只存模型元数据、真实 tool_calls/工具结果与最终文字，不序列化 AIMessage。"""
    output = {"provider":"deepseek_live","model":config.MODEL_NAME,"session_id":trace.session_id,
              "user_msg":safe_text(trace.user_msg),"events":events,"error":error,
              "tokens":None if error else trace.tokens,"latency_ms":trace.total_latency_ms,
              "reply":None if error else safe_text(trace.reply),"finish_reason":trace.finish_reason,
              "thinking":"disabled"}
    if error:
        # 错误不伪装为正常契约 Trace；保留真实失败工具及已确认的部分用量。
        output["tool_attempts"] = trace.steps
        output["tool_sequence"] = trace.tool_names
        output["observed_tokens"] = trace.tokens if any(
            e["event"] == "model_response" and all(type(e.get("usage",{}).get(k)) is int and e["usage"][k] >= 0
                                                  for k in ("input_tokens","output_tokens")) for e in events) else None
    path = config.TRACE_DIR / "deepseek_runs.jsonl"
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:
        f.write(safe_text(json.dumps(output,ensure_ascii=False))+"\n")
