"""Presentation-only state mapping. No model, business or database execution."""
import copy
import pytest
from web.request_motion import state,tools,markup,tool_markup
from web.user_copy import phase_markup

def event(kind,**fields):return dict(event_type=kind,**fields)

@pytest.mark.parametrize('status,category,expected',[('QUEUED',None,'PENDING'),('SUCCEEDED',None,'SUCCEEDED'),('FAILED','timeout','FAILED'),('FAILED','tool_execution_failed','FAILED'),('BLOCKED','permission_denied','BLOCKED'),('BLOCKED','awaiting_confirmation','WAITING'),('CANCELLED',None,'CANCELLED')])
def test_lifecycle_states(status,category,expected):
    op=dict(status=status,error=dict(category=category));old=copy.deepcopy(op)
    view=state(op,[],active=status in ('QUEUED','RUNNING'))
    assert view['state']==expected and not view['moving'] and op==old

def test_waiting_model_and_real_generation_are_distinct():
    assert state({'status':'RUNNING'},[event('model_start')],active=True)['text']=='AI 正在思考'
    assert state({'status':'RUNNING'},[event('model_start'),event('model_end')],active=True)['text']=='正在处理请求'
    assert state({'status':'RUNNING'},[event('model_start'),event('model_delta')],active=True)['text']=='AI 正在生成回复'

def test_tool_proposal_never_claims_execution():
    events=[event('model_end'),event('tool_proposed',tool='railway_query_trips')]
    assert tools(events,True)==[] and '调用' not in state({'status':'RUNNING'},events,active=True)['text']

def test_real_tool_start_result_and_next_model_wait():
    events=[event('tool_start',tool='query_tickets',call_id='one')]
    assert state({'status':'RUNNING'},events,active=True)['text']=='正在调用 query_tickets'
    events+=[event('tool_result',tool='query_tickets',call_id='one',status='succeeded',executed=True),event('model_start')]
    assert tools(events,True)[0]['status']=='SUCCEEDED'
    assert state({'status':'RUNNING'},events,active=True)['text']=='AI 正在思考'

def test_parallel_tool_results_do_not_finish_other_calls():
    events=[event('tool_start',tool='query_tickets',call_id='a'),event('tool_start',tool='query_tickets',call_id='b'),event('tool_result',tool='query_tickets',call_id='a',status='failed')]
    assert [r['status'] for r in tools(events,True)]==['FAILED','RUNNING']
    assert [r['status'] for r in tools(events,False)]==['FAILED','UNKNOWN']

def test_railway_result_without_start_stays_honest():
    e=[event('railway_tool_result',tool='railway_query_trips',call_id='a',status='succeeded',executed=True)]
    assert tools(e,True)==[dict(tool='railway_query_trips',call_id='a',status='SUCCEEDED')]

def test_blocked_and_failed_tools_are_distinct_and_duplicate_results_join():
    e=[event('tool_start',tool='x',call_id='a'),event('railway_tool_result',tool='x',call_id='a',status='succeeded'),event('tool_result',tool='x',call_id='a',status='blocked',executed=False)]
    assert len(tools(e,True))==1 and tools(e,True)[0]['status']=='BLOCKED'

def test_readonly_restore_never_plays_an_old_running_animation():
    op={'status':'RUNNING'};events=[event('model_start')]
    assert not state(op,events,active=False)['moving']
    assert 'ta-motion-active' not in phase_markup([dict(key='query',status='active')])

def test_completed_steps_static_and_only_current_step_animates():
    html=phase_markup([dict(key='query',status='done'),dict(key='policy',status='active')],animate=True)
    assert html.count('ta-motion-active')==1 and '✓' in html and 'role="listitem"' in html

def test_markup_escapes_names_and_has_accessible_dots():
    html=markup(dict(state='RUNNING',text='<script>bad</script>',moving=True))
    assert html.count('<i>')==3 and '<script>' not in html and 'aria-live="polite"' in html
    assert '<script>' not in tool_markup([dict(tool='<script>',status='FAILED')])
