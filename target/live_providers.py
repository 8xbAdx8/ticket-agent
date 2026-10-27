"""Small provider registry and unlimited, explicit Live execution. No network on import."""
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


def manual_environment(provider,root,*,model=None):
    """User-authorized daily dialogue; never borrows a frozen acceptance ledger."""
    if provider not in LIVE_PROVIDERS:raise ValueError('unknown_manual_provider')
    root=Path(root).resolve();base=(config.BASE_DIR/'artifacts/runtime').resolve()
    if not root.is_relative_to(base) or root==base:raise ValueError('isolated_manual_runtime_required')
    cfg=configuration(provider);selected=model or cfg['model']
    env={'TICKET_API_VALIDATION_PROFILE':'interactive','TICKET_INITIAL_LIVE_BUDGET':'',
        'TICKET_TOTAL_REQUEST_LIMIT':'','DEEPSEEK_LIVE_TEST_PROFILE':'read_only','DEEPSEEK_THINKING':'disabled',
        'AGENT_PROVIDER':provider,'AGENT_ENGINE':'langchain','AGENT_LC_TOOLSET':'read_only',
        'AGENT_MODEL':selected,'AGENT_BASE_URL':cfg['base_url'],'AGENT_MUTATIONS':'{}',
        'AGENT_DB_PATH':str(root/'tickets.db'),'AGENT_TRACE_DIR':str(root/'traces'),
        'AGENT_USE_HTTP':'0','AGENT_VECTOR_RAG':'0','AGENT_RAG_MODE':os.getenv('AGENT_RAG_MODE') or 'keyword',
        'RAG_QUALITY_PROFILE':'v351','RAG_ALLOW_NETWORK':os.getenv('RAG_ALLOW_NETWORK','0'),
        'DEEPSEEK_MAX_REQUESTS':'0','BAILIAN_MAX_REQUESTS':'0',
        'DEEPSEEK_MAX_MODEL_CALLS':'3','BAILIAN_MAX_MODEL_CALLS':'3','AGENT_MAX_STEPS':'3',
        'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false',
        'DEEPSEEK_BUDGET_PATH':str(base/'manual-live/deepseek/requests.db'),
        'BAILIAN_BUDGET_PATH':str(base/'manual-live/bailian/requests.db')}
    if provider=='bailian':env['DASHSCOPE_MODEL']=selected
    else:env['DEEPSEEK_MODEL']=selected
    return env


def validate_manual_binding(settings, provider):
    """Compatibility check for the retained read-only business boundary only."""
    if provider not in LIVE_PROVIDERS or settings.profile != 'read_only':
        from target.deepseek_runtime import DeepSeekError
        raise DeepSeekError('read_only_tools_required')


def reserve_initial_budget():
    """Deprecated no-op. Shared cumulative budget reservations were removed."""
    return None


def isolated_environment(provider, root, *, profile=None):
    """Lab, CLI and daily dialogue share one unlimited usage-only policy.

    root isolates business state and traces, not a quota or validation batch.
    Existing profile names remain accepted as labels, never as request gates.
    """
    env = manual_environment(provider, root)
    env['TICKET_TEST_PROFILE_LABEL'] = profile or os.getenv('TICKET_API_VALIDATION_PROFILE', 'current')
    return env
