"""Bailian OpenAI-compatible runtime. Reuses existing tools; permanently read-only here."""
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import config
from target.deepseek_runtime import Settings as DeepSeekSettings, RequestBudget, DeepSeekError, ERRORS
from target.live_providers import READ_ONLY, reserve_initial_budget


class BailianError(DeepSeekError):
    def __init__(self, category, status=None):
        self.category, self.status = category, status
        RuntimeError.__init__(self, "Bailian 请求未完成：" + category + (f" (HTTP {status})" if status else ""))


@dataclass(frozen=True)
class Settings(DeepSeekSettings):
    max_requests: int = 3
    ledger_path: Path = config.BASE_DIR / "artifacts/runtime/v33-live-providers/bailian/requests.db"

    @classmethod
    def from_env(cls):
        try:
            settings = cls(timeout=float(os.getenv("BAILIAN_TIMEOUT", "20")),
                max_requests=int(os.getenv("BAILIAN_MAX_REQUESTS", "3")),
                ledger_path=Path(os.getenv("BAILIAN_BUDGET_PATH", str(cls.ledger_path))))
        except ValueError:
            raise BailianError("invalid_safety_limits") from None
        if not 1 <= settings.max_requests <= 3 or not 1 <= settings.timeout <= 60:
            raise BailianError("invalid_safety_limits")
        formal = config.BASE_DIR / "artifacts/runtime/deepseek-budget/requests.db"
        deep = Path(os.getenv("DEEPSEEK_BUDGET_PATH", str(formal)))
        if settings.ledger_path.resolve() in (formal.resolve(), deep.resolve()):
            raise BailianError("provider_budget_must_be_independent")
        return settings


def endpoint():
    url = urlsplit(config.BASE_URL)
    # Accept official regional/workspace HTTPS endpoints, not arbitrary hosts or coding-plan endpoints.
    host = url.hostname or ""
    valid = host in {"dashscope.aliyuncs.com","dashscope-intl.aliyuncs.com","dashscope-us.aliyuncs.com","cn-hongkong.dashscope.aliyuncs.com"} or bool(
        re.fullmatch(r"[a-z0-9-]+\.[a-z]{2}-[a-z0-9-]+\.maas\.aliyuncs\.com",host))
    if (url.scheme != "https" or not valid or url.username or url.password or url.port not in (None, 443)
            or url.query or url.fragment or url.path.rstrip("/") != "/compatible-mode/v1"
            or any(x in host for x in ("coding.", "token-plan."))):
        raise BailianError("invalid_api_address")
    return url


def validate_configuration():
    if not os.getenv("DASHSCOPE_API_KEY", "").strip():
        raise BailianError("missing_DASHSCOPE_API_KEY")
    if not config.BASE_URL.strip():
        raise BailianError("missing_DASHSCOPE_BASE_URL")
    endpoint()
    if not config.MODEL_NAME.strip():
        raise BailianError("missing_DASHSCOPE_MODEL")


def guarded_client(settings, *, transport=None):
    import httpx
    address = endpoint()
    budget = RequestBudget(settings)
    for name in ("httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    def before(request):
        if (request.method != "POST" or request.url.scheme != "https" or request.url.host != address.hostname
                or request.url.port not in (None,443) or request.url.path != address.path.rstrip("/") + "/chat/completions"
                or request.url.query):
            raise BailianError("invalid_api_address")
        body = json.loads(request.content)
        names = {t.get("function",{}).get("name") for t in body.get("tools",[])}
        if not names <= READ_ONLY:
            raise BailianError("read_only_tools_required")
        limit = body.get("max_tokens", body.get("max_completion_tokens"))
        if (body.get("model") != config.MODEL_NAME or body.get("stream")
                or type(limit) is not int or not 1 <= limit <= settings.max_output_tokens):
            raise BailianError("request_configuration_rejected")
        if len(request.content) > settings.max_payload_bytes:
            raise BailianError("request_payload_limit")
        reserve_initial_budget()
        request.extensions["ticket_budget_id"] = budget.reserve()

    def after(response):
        identity = response.request.extensions.get("ticket_budget_id")
        if identity is None: return
        response.read()
        try: body = response.json()
        except ValueError: body = {}
        if not isinstance(body,dict): body = {}
        category = ERRORS.get(response.status_code, "http_error")
        if response.status_code == 404: category = "model_or_endpoint_not_found"
        if response.status_code == 403: category = "permission_denied"
        # Some accounts report Arrearage as HTTP 400, not 402. Inspect only the code, never save body.
        code = str((body.get("error") or {}).get("code", "")).lower() if isinstance(body.get("error"),dict) else ""
        if any(s in code for s in ("arrearage", "insufficient", "balance")): category = "insufficient_balance"
        elif any(s in code for s in ("modelnotfound","invalidmodel","invalidparameter.model")): category = "model_not_found"
        elif "invalidapikey" in code: category = "authentication_failed"
        budget.record(identity,status=response.status_code,category="response_received" if response.is_success else category,
                      usage=body.get("usage"),model=body.get("model"))
        if not response.is_success:
            raise BailianError(category,response.status_code)

    return httpx.Client(timeout=settings.timeout, follow_redirects=False, transport=transport,
                        event_hooks={"request":[before],"response":[after]})


def make_model(settings=None, *, transport=None):
    validate_configuration()
    settings = settings or Settings.from_env()
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=config.MODEL_NAME, api_key=os.environ["DASHSCOPE_API_KEY"].strip(),
        base_url=config.BASE_URL, timeout=settings.timeout, max_retries=0, max_tokens=settings.max_output_tokens,
        streaming=False, use_responses_api=False, http_client=guarded_client(settings,transport=transport),
        extra_body={"enable_thinking":False} if config.MODEL_NAME.lower().startswith("qwen") else None)
