"""Small provider registry and opt-in initial validation ceiling. No network on import."""
import os
from dataclasses import replace
from pathlib import Path
import config

LIVE_PROVIDERS = ("deepseek", "bailian")
READ_ONLY = frozenset(("query_tickets", "search_policy"))


def configuration(provider):
    """Safe configuration summary; deliberately never returns a credential value."""
    if provider == "deepseek":
        return {"provider": provider, "model": "deepseek-flash", "base_url": "https://api.deepseek.com",
                "key_env": "DEEPSEEK_API_KEY", "configured": bool(os.getenv("DEEPSEEK_API_KEY", "").strip())}
    if provider == "bailian":
        return {"provider": provider, "model": os.getenv("DASHSCOPE_MODEL", ""),
                "base_url": os.getenv("DASHSCOPE_BASE_URL", ""), "key_env": "DASHSCOPE_API_KEY",
                "configured": all(os.getenv(n, "").strip() for n in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "DASHSCOPE_MODEL"))}
    raise ValueError("Unknown Live provider")


def reserve_initial_budget():
    """Only new validation/UI entry points opt in. Original DeepSeek ledger is untouched.

    Three total generation attempts across both providers; timeouts/crashes do not refund.
    Local file deletion or other clients are outside this application's protection.
    """
    path = os.getenv("TICKET_INITIAL_LIVE_BUDGET")
    if path:
        from target.deepseek_runtime import Settings, RequestBudget
        RequestBudget(replace(Settings(), max_requests=3, ledger_path=Path(path))).reserve()


def isolated_environment(provider, root):
    """New multi-provider entry: independent provider ledgers + shared first-three ceiling."""
    root = Path(root).resolve()
    base = (config.BASE_DIR / "artifacts/runtime").resolve()
    if not root.is_relative_to(base) or root == base:
        raise ValueError("Live evidence must be isolated under artifacts/runtime")
    cfg = configuration(provider)
    budget_base = config.BASE_DIR / "artifacts/runtime/v33-live-providers"
    env = {"AGENT_PROVIDER": provider, "AGENT_ENGINE": "langchain", "AGENT_LC_TOOLSET": "read_only",
        "AGENT_MODEL": cfg["model"], "AGENT_BASE_URL": cfg["base_url"], "AGENT_MUTATIONS": "{}",
        "AGENT_DB_PATH": str(root / "tickets.db"), "AGENT_TRACE_DIR": str(root / "traces"),
        "AGENT_USE_HTTP": "0", "AGENT_VECTOR_RAG": "0",
        "TICKET_INITIAL_LIVE_BUDGET": str(budget_base / "initial-total.db"),
        "DEEPSEEK_LIVE_TEST_PROFILE": "read_only", "DEEPSEEK_THINKING": "disabled",
        "DEEPSEEK_MAX_REQUESTS": "3", "DEEPSEEK_BUDGET_PATH": str(budget_base / "deepseek/requests.db"),
        "BAILIAN_MAX_REQUESTS": "3", "BAILIAN_BUDGET_PATH": str(budget_base / "bailian/requests.db")}
    return env
