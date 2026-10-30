"""Opt-in events in independent sidecars; never rewrite historical Trace."""
import contextlib
import contextvars
from datetime import datetime, timezone
import json
import uuid
ACTIVE=contextvars.ContextVar('ticket_runtime_events',default=None)

@contextlib.contextmanager
def capture(path, callback=None):
    state={'path':path,'callback':callback,'run_id':None,'last':None}
    token=ACTIVE.set(state)
    try:yield state
    finally:ACTIVE.reset(token)

def bind(trace):
    state=ACTIVE.get()
    if state is None:return
    state.update(run_id=trace.trace_id,session_id=trace.session_id,provider=trace.provider,model=trace.model)
    emit('user_input',input=trace.user_msg);emit('agent_start')

def emit(kind,status='recorded',**fields):
    state=ACTIVE.get()
    if state is None or state['run_id'] is None:return None
    from target.diagnostics import sanitize
    row=sanitize({'schema':'ticket-run-event/1','run_id':state['run_id'],
        'event_id':uuid.uuid4().hex,'previous_event_id':state['last'],
        'event_type':kind,'timestamp':datetime.now(timezone.utc).isoformat(),
        'status':status,'session_id':state.get('session_id'),
        'provider':state.get('provider'),'model':state.get('model'),**fields})
    state['last']=row['event_id'];path=state['path'];path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    if state['callback']:
        try:state['callback'](row)
        except Exception:pass
    return row
