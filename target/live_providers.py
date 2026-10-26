"""Small provider registry and opt-in initial validation ceiling. No network on import."""
import os
from dataclasses import replace
from pathlib import Path
import config

LIVE_PROVIDERS = ("deepseek", "bailian")
READ_ONLY = frozenset(("query_tickets", "search_policy"))


def configuration(provider):
    """Safe configuration summary; deliberately never returns a credential value."""
    from target.api_config import model_config
    return model_config(provider,active=os.getenv("AGENT_PROVIDER")==provider)


def reserve_initial_budget():
    """Only new validation/UI entry points opt in. Original DeepSeek ledger is untouched.

    Three total generation attempts across both providers; timeouts/crashes do not refund.
    Local file deletion or other clients are outside this application's protection.
    """
    if os.getenv("TICKET_INITIAL_LIVE_BUDGET"):
        from target.deepseek_runtime import DeepSeekError
        raise DeepSeekError("unpaired_reservation_disabled_use_request_accounting")


def isolated_environment(provider, root, *, profile=None):
    """New multi-provider entry: independent provider ledgers + shared first-three ceiling."""
    root = Path(root).resolve()
    base = (config.BASE_DIR / "artifacts/runtime").resolve()
    if not root.is_relative_to(base) or root == base:
        raise ValueError("Live evidence must be isolated under artifacts/runtime")
    cfg = configuration(provider)
    budget_base = config.BASE_DIR / "artifacts/runtime/v33-live-providers"
    selected=profile or os.getenv("TICKET_API_VALIDATION_PROFILE")
    v34=selected=="v34"
    if v34:budget_base=config.BASE_DIR/"artifacts/runtime/v34-api-audit/authorization-20261025"
    env = {"AGENT_PROVIDER": provider, "AGENT_ENGINE": "langchain", "AGENT_LC_TOOLSET": "read_only",
        "AGENT_MODEL": cfg["model"], "AGENT_BASE_URL": cfg["base_url"], "AGENT_MUTATIONS": "{}",
        "AGENT_DB_PATH": str(root / "tickets.db"), "AGENT_TRACE_DIR": str(root / "traces"),
        "AGENT_USE_HTTP": "0", "AGENT_VECTOR_RAG": "0",
        "AGENT_RAG_MODE":os.getenv("AGENT_RAG_MODE") or "hybrid","RAG_QUALITY_PROFILE":"v351","RAG_ALLOW_NETWORK":"0",
        "TICKET_INITIAL_LIVE_BUDGET": str(budget_base / "initial-total.db"),
        "DEEPSEEK_LIVE_TEST_PROFILE": "read_only", "DEEPSEEK_THINKING": "disabled",
        "DEEPSEEK_MAX_REQUESTS": "2" if v34 else "3", "DEEPSEEK_BUDGET_PATH": str(budget_base / "deepseek/requests.db"),
        "BAILIAN_MAX_REQUESTS": "2" if v34 else "3", "BAILIAN_BUDGET_PATH": str(budget_base / "bailian/requests.db"),
        "TICKET_TOTAL_REQUEST_LIMIT":"4" if v34 else "3"}
    if v34:env.update(DEEPSEEK_MAX_MODEL_CALLS="2",BAILIAN_MAX_MODEL_CALLS="2",AGENT_MAX_STEPS="2")
    if selected=="v35":
        if provider!="bailian":raise ValueError("V3.5 has no new DeepSeek generation authorization")
        from target.embeddings import AUTH
        env.update(TICKET_API_VALIDATION_PROFILE="v35",AGENT_MODEL="qwen3.8-flash",DASHSCOPE_MODEL="qwen3.8-flash",
            BAILIAN_MAX_REQUESTS="4",BAILIAN_BUDGET_PATH=str(AUTH/"generation.db"),
            TICKET_INITIAL_LIVE_BUDGET=str(AUTH/"generation-total.db"),TICKET_TOTAL_REQUEST_LIMIT="4",
            BAILIAN_MAX_MODEL_CALLS="2",AGENT_MAX_STEPS="2",AGENT_RAG_MODE=os.getenv("AGENT_RAG_MODE") or "hybrid",
            RAG_ALLOW_NETWORK=os.getenv("RAG_ALLOW_NETWORK","0"))
    if selected=='v352':
        from target.v352_validation import AUTH
        env.update(TICKET_API_VALIDATION_PROFILE='v352',DEEPSEEK_MAX_REQUESTS='2',BAILIAN_MAX_REQUESTS='2',
            DEEPSEEK_MAX_MODEL_CALLS='2',BAILIAN_MAX_MODEL_CALLS='2',AGENT_MAX_STEPS='2',
            DEEPSEEK_BUDGET_PATH=str(AUTH/'deepseek-generation.db'),BAILIAN_BUDGET_PATH=str(AUTH/'bailian-generation.db'),
            TICKET_INITIAL_LIVE_BUDGET=str(AUTH/'generation-total.db'),TICKET_TOTAL_REQUEST_LIMIT='4',
            AGENT_MODEL='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash',
            AGENT_RAG_MODE='hybrid',RAG_QUALITY_PROFILE='v351',RAG_TOP_K='3',RAG_VECTOR_THRESHOLD='0.35',RAG_ALLOW_NETWORK='0',
            LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false')
        if provider=='bailian':env['DASHSCOPE_MODEL']='qwen3.8-flash'
    return env
