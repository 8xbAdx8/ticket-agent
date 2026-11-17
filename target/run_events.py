"""Additive events for saved Agent calls and UI captures; historical Trace stays intact."""
import contextlib
import contextvars
from datetime import datetime, timezone
import json
import uuid
from pathlib import Path
from functools import wraps
from inspect import signature
ACTIVE=contextvars.ContextVar('ticket_runtime_events',default=None)

@contextlib.contextmanager
def capture(path, callback=None, *, confirmation=None):
    state={'path':Path(path),'callback':callback,'run_id':None,'last':None,
           'confirmation':confirmation,'sequence':0,'ids':set(),'proposals':{},
           'tools':{},'retrievals':{},'current_tool':None,'tool_failed':False}
    token=ACTIVE.set(state)
    try:yield state
    finally:ACTIVE.reset(token)

def bind(trace):
    state=ACTIVE.get()
    if state is None:return
    state.update(run_id=trace.trace_id,session_id=trace.session_id,provider=trace.provider,model=trace.model,
                 last=None,sequence=0,ids=set(),proposals={},tools={},retrievals={},current_tool=None,
                 tool_failed=False)
    state['_trace']=trace
    from target.execution_config import snapshot
    snapshot(trace)
    emit('user_input',input=trace.user_msg);emit('agent_start')
    if state.get('confirmation'):
        emit('user_confirmation','approved' if state['confirmation']['approved'] else 'declined',
             **state['confirmation'])


def identity():
    state=ACTIVE.get()
    return {key:state.get(key) for key in ('run_id','session_id','provider','model')} if state and state.get('run_id') else {}


def finish(record=None,error=None):
    state=ACTIVE.get()
    if not state or not state.get('run_id'):return
    failed=bool(error) or state['tool_failed']
    emit('run_finished','failed' if failed else 'succeeded',coverage_version='p1/1',
         error=error,business_success=None,finish_reason=(record or {}).get('finish_reason'))


def recorded_run(function):
    """The public Agent entry records directly too; UI capture remains the owner."""
    sig=signature(function)
    @wraps(function)
    def wrapped(self,*args,**kwargs):
        values=sig.bind(self,*args,**kwargs).arguments
        if ACTIVE.get() is not None or values.get('save_trace',True) is False and getattr(self,'effective_config',None) is None:
            return function(self,*args,**kwargs)
        import config
        with capture(config.TRACE_DIR/'run_events.jsonl'):
            try:
                record=function(self,*args,**kwargs)
                finish(record,(getattr(self,'last_audit_report',None) or {}).get('error'))
                emit('agent_returned',reply=record.get('reply'),finish_reason=record.get('finish_reason'))
                return record
            except Exception as exc:
                finish(error={'type':type(exc).__name__})
                emit('agent_error','failed',error=type(exc).__name__)
                raise
    return wrapped

def emit(kind,status='recorded',**fields):
    state=ACTIVE.get()
    if state is None or state['run_id'] is None:return None
    if kind=='model_start' and isinstance(fields.get('system_prompt'),str):
        from target.execution_config import snapshot
        snapshot(state['_trace'],fields['system_prompt'])
    from target.diagnostics import sanitize
    call_id=fields.get('call_id')
    tool=fields.get('tool')
    proposal_key=json.dumps([tool,fields.get('args')],sort_keys=True,ensure_ascii=False,default=str)
    if kind=='tool_proposed' and not call_id:
        proposal=state['proposals'].get(proposal_key)
        if proposal:call_id=proposal.get('call_id')
    parent=fields.pop('parent_event_id',None)
    if parent is None:
        if kind=='agent_start':parent=state.get('input_event')
        elif kind in ('model_start','agent_decision'):parent=state.get('agent_event')
        elif kind in ('model_end','model_error'):parent=state.get('model_event')
        elif kind=='model_tool_proposed':parent=state.get('model_response')
        elif kind in ('permission_check','confirmation_requested','confirmation_declined'):
            parent=(state['tools'].get(call_id) or {}).get('proposal')
        elif kind=='tool_proposed':
            parent=(state['tools'].get(call_id) or state['proposals'].get(proposal_key) or {}).get('proposal')
        elif kind in ('parameter_validation','tool_start','tool_result'):
            entry=state['tools'].get(call_id or state.get('current_tool'),{})
            parent=entry.get('start') or entry.get('dispatch') or entry.get('permission')
            call_id=call_id or entry.get('call_id')
        elif kind=='rag_start':parent=(state['tools'].get(state.get('current_tool')) or {}).get('start')
        elif kind in ('rag_result','rag_error'):parent=state['retrievals'].get(fields.get('retrieval_id'))
        elif kind in ('tool_message_created','tool_result_in_model_request'):
            parent=(state['tools'].get(call_id) or {}).get('result')
        elif kind in ('run_finished','agent_returned','agent_error','user_confirmation'):
            parent=state.get('agent_event')
    if parent not in state['ids']:parent=None
    if call_id is None and kind.startswith('rag_'):call_id=state.get('current_tool')
    if kind in ('tool_proposed','tool_start','tool_result'):
        entry=state['tools'].get(call_id) or {}
        fields.setdefault('requires_confirmation',entry.get('requires_confirmation'))
        fields.setdefault('user_confirmed',entry.get('user_confirmed'))
        if kind=='tool_result':
            fields.setdefault('args',entry.get('args'))
            fields.setdefault('started_at',entry.get('started_at'))
    state['sequence']+=1
    row=sanitize({'schema':'ticket-run-event/1',
        'event_id':uuid.uuid4().hex,'previous_event_id':state['last'],
        'parent_event_id':parent,'sequence':state['sequence'],
        'event_type':kind,'timestamp':datetime.now(timezone.utc).isoformat(),
        'status':status,'provider':state.get('provider'),'model':state.get('model'),
        **fields,'run_id':state['run_id'],'session_id':state.get('session_id')})
    if call_id is not None:row['call_id']=call_id
    eid=row['event_id'];state['ids'].add(eid)
    if kind=='user_input':state['input_event']=eid
    elif kind=='agent_start':state['agent_event']=eid
    elif kind=='model_start':state['model_event']=eid
    elif kind=='model_end':state['model_response']=eid
    elif kind=='model_tool_proposed':
        entry={'proposal':eid,'call_id':call_id};state['proposals'][proposal_key]=entry
        if call_id:state['tools'][call_id]=entry
    elif kind=='tool_proposed':
        # Direct dispatch also has an execution identity, distinct from a model call ID.
        call_id=call_id or eid;row['call_id']=call_id;state['current_tool']=call_id
        state['tools'].setdefault(call_id,{'call_id':call_id}).update(dispatch=eid,args=fields.get('args'))
    elif kind=='tool_start':
        state['tools'].setdefault(call_id,{}).update(start=eid,started_at=row['timestamp'])
    elif kind=='permission_check' and call_id:
        state['tools'].setdefault(call_id,{}).update(permission=eid,
            requires_confirmation=fields.get('requires_confirmation'),user_confirmed=fields.get('user_confirmed'))
    elif kind=='tool_result':
        state['tools'].setdefault(call_id,{})['result']=eid
        if status in ('failed','blocked'):state['tool_failed']=True
    elif kind=='rag_start':state['retrievals'][fields.get('retrieval_id')]=eid
    state['last']=row['event_id'];path=state['path'];path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    if state['callback']:
        try:state['callback'](row)
        except Exception:pass
    return row
