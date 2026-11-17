"""Frozen per-run configuration and a shared execution boundary."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,asdict
from functools import wraps
from pathlib import Path
import hashlib
import json
import os
import uuid
import config
from target.dev_overrides import Store,PROFILE,TOOLS,WRITES,defaults,digest

CURRENT=ContextVar('ticket_effective_config',default=None)
CONFIRMED=ContextVar('ticket_effective_confirmed',default=False)


@dataclass(frozen=True)
class EffectiveConfig:
    baseline_id:str
    execution_mode:str
    override_revision:int
    config_source:str
    prompt:str
    prompt_sha256:str
    tool_whitelist:tuple
    write_policy:tuple
    provider:str
    model:str
    temperature:float|None
    temperature_applicable:bool
    rag_mode:str
    allow_embedding:bool
    fixture_id:str
    policy_version:str
    engine:str
    config_hash:str

    def payload(self):return asdict(self)


def resolve_effective_config(session_id,execution_mode,*,engine='legacy',provider='mock',model=None,full_tools=True,allow_embedding=False,store=None):
    if execution_mode not in ('baseline','developer_custom'):raise ValueError('未知执行模式')
    if engine not in ('legacy','langchain'):raise ValueError('未知执行引擎')
    from target.agent import SYSTEM_PROMPT
    from target.prompt_config import compose
    settings=defaults(engine,provider,model);revision=0;source='baseline'
    if execution_mode=='baseline':
        settings=defaults(engine);full_tools=True;allow_embedding=False
        for n,h in PROFILE['fixture_sources'].items():
            if hashlib.sha256((config.BASE_DIR/n).read_bytes()).hexdigest()!=h:raise ValueError('正式Baseline来源与冻结身份不一致')
    else:
        saved=(store or Store()).load(session_id,owner=session_id)
        if saved:
            revision=saved['revision'];source=saved['config_source']
            if source=='developer_override':settings=saved['settings']
    effective_engine='langchain' if settings['provider']!='mock' or settings['model']=='langchain-mock' else 'legacy'
    safety=set(TOOLS) if full_tools or settings['provider']=='mock' else {'query_tickets','search_policy'}
    names=tuple(n for n in TOOLS if n in settings['tool_whitelist'] and n in safety)
    policy=tuple((n,'deny' if n not in names else settings['write_policy'][n]) for n in WRITES)
    day=PROFILE['clock'][:10] if execution_mode=='baseline' else config.today().isoformat()
    prompt=compose(SYSTEM_PROMPT,effective_engine,read_only=settings['provider']!='mock' and not full_tools,
                   suffix=settings['system_prompt_suffix'],day=day,
                   phone='13800000001' if execution_mode=='baseline' else None,
                   validation=execution_mode!='baseline' and os.getenv('TICKET_API_VALIDATION_PROFILE')=='v352')
    values=dict(baseline_id=PROFILE['baseline_id'],execution_mode=execution_mode,override_revision=revision,config_source=source,
                prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),tool_whitelist=names,write_policy=policy,
                provider=settings['provider'],model=settings['model'],temperature=settings['temperature'],temperature_applicable=settings['provider']!='mock',
                rag_mode=settings['rag_mode'],allow_embedding=bool(settings['allow_embedding'] and allow_embedding and execution_mode!='baseline'),
                fixture_id=digest(PROFILE['fixture_sources']),policy_version=PROFILE['policy_version'],engine=effective_engine)
    return EffectiveConfig(**values,config_hash=digest(values))


@contextmanager
def scope(effective,*,confirmed=False):
    t=CURRENT.set(effective);a=CONFIRMED.set(bool(confirmed))
    try:yield
    finally:CONFIRMED.reset(a);CURRENT.reset(t)


@contextmanager
def approved(value):
    t=CONFIRMED.set(CONFIRMED.get() or value is True)
    try:yield
    finally:CONFIRMED.reset(t)


def tool_denial(name,*,check_confirmation=True):
    current=CURRENT.get()
    if current is None:return None  # Existing trusted offline harness remains compatible.
    if name in ('railway_lock_seat','railway_lock'):
        return '当前版本没有独立锁座操作。请先完成报价并创建建单提案，用户确认后系统会自动创建限时座位占用。'
    if name not in current.tool_whitelist:return '当前冻结配置禁止工具 '+name
    if name in WRITES:
        if dict(current.write_policy)[name]=='deny':return '当前冻结配置禁止写操作 '+name
        if check_confirmation and current.execution_mode=='developer_custom' and not CONFIRMED.get():return '需要当前用户明确确认当前操作，开发者配置不构成确认'
    return None


def bound_run(function):
    @wraps(function)
    def call(self,session_id,message,*args,**kwargs):
        effective=getattr(self,'effective_config',None)
        from target.run_events import ACTIVE
        confirmation=(ACTIVE.get() or {}).get('confirmation') or {}
        valid=confirmation.get('approved') is True and confirmation.get('proposal')=={'message':message}
        with scope(effective,confirmed=valid):return function(self,session_id,message,*args,**kwargs)
    return call


def snapshot(trace,prompt=None):
    """Sidecar is independent from public Trace and includes the exact prompt."""
    from datetime import datetime,timezone
    effective=CURRENT.get()
    if effective:record=effective.payload()
    else:
        names=list(getattr(trace,'runtime_tool_names',TOOLS if config.LC_TOOLSET=='all' or config.ENGINE=='legacy' else ('query_tickets','search_policy')))
        record=dict(baseline_id=PROFILE['baseline_id'],execution_mode='legacy_runtime',config_source='legacy_runtime',
                    override_revision=0,provider=trace.provider,model=trace.model,tool_whitelist=names,
                    write_policy={n:'confirm' if n in names else 'deny' for n in WRITES},temperature=None,temperature_applicable=trace.provider not in ('mock','langchain_mock'),fixture_id='runtime-unpinned',policy_version=hashlib.sha256(config.POLICY_PATH.read_bytes()).hexdigest())
    if prompt is not None:
        if effective and prompt!=effective.prompt:raise ValueError('实际Prompt与冻结配置不一致')
        record.update(prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
    elif not effective:record.update(prompt=None,prompt_sha256=None)
    record['prompt_status']='submitted_to_model_adapter' if prompt is not None else 'frozen_not_submitted' if effective else 'not_recorded'
    record.update(session_id=trace.session_id,run_id=trace.trace_id,batch_id=os.getenv('TICKET_PROFILE_BATCH_ID') or None,created_at=datetime.now(timezone.utc).isoformat(),schema_version=1)
    record.setdefault('config_hash',digest(record))
    directory=config.TRACE_DIR/'config-events';directory.mkdir(parents=True,exist_ok=True)
    p=directory/(trace.trace_id+('-prompt-'+uuid.uuid4().hex if prompt is not None else '')+'.json')
    if prompt is None and p.exists():
        previous=json.loads(p.read_text(encoding='utf-8'))
        if previous.get('session_id')!=trace.session_id or effective and previous.get('config_hash')!=effective.config_hash:
            raise ValueError('同一run_id不能绑定另一配置或会话')
        return previous  # An auxiliary lifecycle capture may rebind this saved run.
    from target.diagnostics import sanitize
    with p.open('x',encoding='utf-8') as f:json.dump(sanitize(record),f,ensure_ascii=False,indent=2)
    global_dir=config.BASE_DIR/'artifacts/runtime/config-events';global_dir.mkdir(parents=True,exist_ok=True)
    with (global_dir/p.name).open('x',encoding='utf-8') as f:json.dump(sanitize(record),f,ensure_ascii=False,indent=2)
    return record


def run_identity(run_id,session_id):
    import re
    if not isinstance(run_id,str) or not re.fullmatch(r'[a-f0-9]{32}',run_id):return None
    path=config.BASE_DIR/'artifacts/runtime/config-events'/(run_id+'.json')
    if not path.is_file() or path.is_symlink():return None
    d=json.loads(path.read_text(encoding='utf-8'))
    if d.get('session_id')!=session_id:raise ValueError('配置旁证会话不匹配')
    return d
