"""One additive registry for both engines. Original TOOLS is never mutated."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import copy,json,os,time
from functools import wraps
from jsonschema import Draft202012Validator,validators
from target.v39.context import CURRENT

TOOLS=json.loads(Path(__file__).with_name('tool-schemas.json').read_text(encoding='utf-8'))['tools']
NAMES=tuple(t['function']['name'] for t in TOOLS)
ACTIONS=dict(zip(NAMES[5:],('CREATE_ORDER',None,'PAY','CANCEL','REFUND','CHANGE')))
SERVICE=ContextVar('railway_simulation_service',default=None)
BUDGET=ContextVar('railway_simulation_call_budget',default=None)
StrictValidator=validators.extend(Draft202012Validator,type_checker=Draft202012Validator.TYPE_CHECKER.redefine('integer',lambda checker,value:type(value) is int))

def bounded_run(function):
    @wraps(function)
    def call(*args,**kwargs):
        ctx=CURRENT.get()
        if ctx is not None and (kwargs.get('session_id') or args[1])!=ctx.session_id:raise ValueError('V39_SESSION_MISMATCH')
        if ctx is None or BUDGET.get() is not None:return function(*args,**kwargs)
        token=BUDGET.set({'attempts':0})
        try:return function(*args,**kwargs)
        finally:BUDGET.reset(token)
    return call


def enabled():return os.getenv('RAILWAY_SIMULATION_ENABLED','0')=='1'

def denial(name):
    if name not in NAMES:return None
    from target.execution_config import CURRENT as EFFECTIVE
    effective=EFFECTIVE.get();ctx=CURRENT.get()
    if effective and effective.execution_mode=='baseline':return 'V39_BASELINE_DENIED'
    if not enabled() or ctx is None:return 'V39_CONTEXT_REQUIRED'
    try:ctx.require(ACTIONS.get(name))
    except ValueError as exc:return str(exc)
    if ctx.provider not in ('mock','deepseek','bailian'):return 'V39_LIVE_NOT_AUTHORIZED'
    if name not in ctx.tool_whitelist:return 'V39_TOOL_NOT_ALLOWED'
    if effective and (ctx.config_hash!=effective.config_hash or ctx.config_revision!=effective.override_revision or ctx.provider!=effective.provider):return 'V39_CONFIG_MISMATCH'
    if SERVICE.get() is None:return 'V39_SERVICE_UNAVAILABLE'
    return None

def definitions(original):
    additions=[copy.deepcopy(t) for t in TOOLS if denial(t['function']['name']) is None]
    ctx=CURRENT.get()
    if additions and ctx:original=[t for t in original if t['function']['name'] in ctx.tool_whitelist]
    return list(original)+additions

@contextmanager
def service_scope(service):
    token=SERVICE.set(service)
    try:yield
    finally:SERVICE.reset(token)

def dispatch(name,args):
    if name not in NAMES:
        ctx=CURRENT.get()
        if ctx is not None and ctx.enabled and name not in ctx.tool_whitelist:
            return dict(error='V39_TOOL_NOT_ALLOWED'),False,0
        from target.tools import dispatch as legacy
        return legacy(name,args)
    from target.run_events import emit
    from target.tools import DISPATCH_OBSERVER
    start=time.perf_counter();diagnostic=dict(validation=dict(status='unknown'),backend_executed=False)
    context=CURRENT.get()
    if context is not None:
        emit('railway_runtime_configuration',config_source='railway_simulation',session_id=context.session_id,
             actual_tool_whitelist=list(context.tool_whitelist),write_policy=dict(context.write_policy),
             scenario_id=context.scenario_id,provider=context.provider,configuration=context.snapshot())
    emit('tool_proposed',tool=name,args=args)
    try:
        budget=BUDGET.get()
        if budget is not None:
            budget['attempts']+=1
            if budget['attempts']>8:raise ValueError('RAILWAY_TOOL_CALL_LIMIT')
        schema=next(t['function']['parameters'] for t in TOOLS if t['function']['name']==name)
        if not StrictValidator(schema).is_valid(args):raise ValueError('INVALID_RAILWAY_ARGUMENTS')
        diagnostic['validation']=dict(status='valid',validated_args=copy.deepcopy(args))
        reason=denial(name)
        if reason:raise ValueError(reason)
        ctx=CURRENT.get();s=SERVICE.get();diagnostic['backend_executed']=True
        if name=='railway_search_stations':result=s.static.stations(**args)
        elif name=='railway_query_trips':result=s.static.trips(**args)
        elif name=='railway_trip_stops':result=s.static.trip(**args)
        elif name=='railway_check_inventory':result=s.inventory(ctx,**args)
        elif name=='railway_quote_fare':result=s.quote(ctx,**args)
        elif name=='railway_get_order':result=s.order(ctx,**args)
        else:
            if name=='railway_create_order' and args['contact']!=ctx.owner_phone:raise ValueError('ORDER_FORBIDDEN')
            result=s.propose(ctx,ACTIONS[name],args)
        # A proposal is a successful tool operation, never a completed business action.
        ok=not isinstance(result,dict) or 'error' not in result
    except Exception as exc:
        import traceback
        emit('railway_tool_error','failed',tool=name,error_type=type(exc).__name__,
             error_code=str(exc) if isinstance(exc,ValueError) else 'RAILWAY_INTERNAL_ERROR',
             stack=traceback.format_exc(),business_completed=False)
        result=dict(error=str(exc) if isinstance(exc,ValueError) else 'RAILWAY_INTERNAL_ERROR',simulation=True);ok=False
        if diagnostic['validation']['status']=='unknown':diagnostic['validation']=dict(status='invalid')
    elapsed=int((time.perf_counter()-start)*1000)
    emit('railway_tool_result','succeeded' if ok else 'failed' if diagnostic['backend_executed'] else 'blocked',tool=name,executed=diagnostic['backend_executed'],output=result,duration_ms=elapsed,business_completed=False,simulation=True)
    observer=DISPATCH_OBSERVER.get()
    if observer:observer(diagnostic)
    return result,ok,elapsed
