"""Shared API configuration bootstrap; never prints or persists secret values."""
import os
from pathlib import Path
from urllib.parse import urlsplit

NAMES = ("DEEPSEEK_API_KEY","DEEPSEEK_MODEL","DEEPSEEK_BASE_URL","DASHSCOPE_API_KEY","DASHSCOPE_MODEL","DASHSCOPE_BASE_URL",
         "DASHSCOPE_EMBEDDING_BASE_URL","RAG_EMBEDDING_MODEL","RAG_EMBEDDING_DIMENSIONS",
         "LANGCHAIN_API_KEY","LANGCHAIN_TRACING_V2","LANGCHAIN_PROJECT","LANGCHAIN_ENDPOINT","LANGCHAIN_WORKSPACE_ID",
         "LANGSMITH_API_KEY","LANGSMITH_TRACING","LANGSMITH_PROJECT","LANGSMITH_ENDPOINT","LANGSMITH_WORKSPACE_ID")


def bootstrap(root=None):
    """Process (including explicit empty) > project .env > Windows user environment.

    Offline review guards prohibit local secret discovery; explicit fake env remains usable.
    Only documented API variables are read; no shell expansion/execution or arbitrary files.
    """
    if os.getenv("TICKET_OFFLINE_GUARD_LOG") or os.getenv("TICKET_WEB_OFFLINE_ONLY")=="1" or os.getenv("TICKET_DISABLE_LOCAL_SECRETS")=="1":
        return {"local_secret_discovery":"disabled"}
    root=Path(root or Path(__file__).resolve().parent.parent).resolve()
    sources={name:"process" for name in NAMES if name in os.environ}
    path=Path(os.getenv("TICKET_ENV_FILE",str(root/".env"))).resolve()
    if not path.is_relative_to(root): raise ValueError("project_env_file_required")
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line=line.strip()
            if not line or line.startswith("#"): continue
            name,separator,value=line.partition("=")
            name=name.strip()
            if not separator or name not in NAMES: continue
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in "\"'": value=value[1:-1]
            if name not in os.environ: os.environ[name]=value; sources[name]="project_env"
    if os.name=="nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,"Environment") as key:
                for name in NAMES:
                    if name in os.environ: continue
                    try: value,_=winreg.QueryValueEx(key,name)
                    except OSError: continue
                    if isinstance(value,str): os.environ[name]=value; sources[name]="windows_user"
        except OSError: pass
    return sources


def alias(old,new,default=""):
    left,right=os.getenv(old,"").strip(),os.getenv(new,"").strip()
    if left and right and left!=right: raise ValueError("conflicting_api_configuration")
    return left or right or default


def model_config(provider,*,active=False,environment=None):
    getenv=os.getenv if environment is None else environment.get
    if provider=="deepseek":
        model=getenv("DEEPSEEK_MODEL",getenv("AGENT_MODEL","deepseek-flash") if active else "deepseek-flash")
        endpoint=getenv("DEEPSEEK_BASE_URL",getenv("AGENT_BASE_URL","https://api.deepseek.com") if active else "https://api.deepseek.com")
        key_env="DEEPSEEK_API_KEY"
    elif provider=="bailian":
        model=getenv("DASHSCOPE_MODEL","qwen3.8-flash"); endpoint=getenv("DASHSCOPE_BASE_URL",""); key_env="DASHSCOPE_API_KEY"
    else: raise ValueError("unknown_api_provider")
    return {"provider":provider,"model":model,"base_url":endpoint,"key_env":key_env,
            "configured":all((getenv(key_env,"").strip(),model.strip(),endpoint.strip()))}


def safe_endpoint(value):
    try:
        url=urlsplit(value)
        if url.username or url.password or url.query or url.fragment or not url.hostname: return "<invalid endpoint>"
        port=url.port
        return f"{url.scheme}://{url.hostname}"+(f":{port}" if port else "")+url.path
    except ValueError: return "<invalid endpoint>"


def status(provider):
    row=model_config(provider,active=os.getenv("AGENT_PROVIDER")==provider)
    row["base_url"]=safe_endpoint(row["base_url"])
    from target.diagnostics import redact_credentials
    return redact_credentials({**row,"state":"configured_unverified" if row["configured"] else "not_configured",
            "connection_verified":None,"tool_calling_verified":None,"business_verified":None})
