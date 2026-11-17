"""Current product UI wiring, deterministic agents and MockTransport only."""
import copy,json,threading
from pathlib import Path
import pytest
from tests.v39.test_v394_defaults import session


@pytest.fixture(autouse=True)
def mark_ui_boundary(request):
    if 'session' in request.fixturenames:
        request.getfixturevalue('session')._unified_interaction=True


@pytest.mark.parametrize('entry,message,tool',[
 ('查余票','查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。','railway_query_trips'),
 ('问政策','查询项目示例退改政策。','search_policy'),
 ('看订单','查询我的订单。','railway_get_order'),
 ('退票费率','查询项目示例退票手续费规则。','search_policy'),
 ('行李费用','查询项目示例行李费用规定。','search_policy'),
 ('改签','查看我的订单并查询可改签方案，不要直接执行改签。','railway_get_order')])
def test_six_intents_have_same_agent_trace_history_and_persistence(session,entry,message,tool):
    from web.session_store import restore_session
    result=session.send(message,'request-1',entry='quick:'+entry,defer_followups=True)
    op=session.operations[-1]
    assert tool in result['tool_sequence'] and op['status']=='SUCCEEDED'
    assert op['run_id']==session.audits[-1]['trace_id'] and op['entry']=='quick:'+entry
    assert session.history[-1]==result
    restored=restore_session(session.root,expected_sid=session.sid)
    assert restored.read_only and restored.agent is None
    assert restored.operations[-1]['run_id']==op['run_id'] and restored.history[-1]==result
    assert session.send(message,'request-1',entry='quick:'+entry) is result
    assert len(session.history)==1 and len(session.operations)==1
    with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):session.send('不同参数','request-1')


def test_async_rerun_duplicate_does_not_cancel_or_repeat_real_agent(session,monkeypatch):
    from web import interaction
    from target.v39.planner import RailwayDemoProvider
    started=threading.Event();release=threading.Event();original=RailwayDemoProvider.chat
    def slow(self,messages,tools):
        if not started.is_set():started.set();assert release.wait(10)
        return original(self,messages,tools)
    monkeypatch.setattr(RailwayDemoProvider,'chat',slow)
    text='查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。'
    future=interaction.submit(session,text,'same-click',entry='quick:查余票')
    assert started.wait(10) and interaction.busy(session)
    assert session.operations[-1]['status']=='RUNNING' and session.operations[-1]['run_id']
    assert interaction.submit(session,text,'same-click') is future
    release.set();record=future.result(timeout=15)
    assert record and len(session.history)==1 and len(session.audits)==1
    assert session.operations[-1]['status']=='SUCCEEDED'
    from web.followup_jobs import JOBS
    for (sid,_),job in list(JOBS.items()):
        if sid==session.sid:job.result(timeout=15)


def test_mock_cancel_does_not_claim_creation_id_is_a_fresh_proposal():
    from target.v39.planner import RailwayDemoProvider

    order_id='V39-'+'a'*32
    original_proposal='P'+'b'*32
    messages=[dict(role='user',content=f'取消未支付订单 {order_id}，请生成取消确认提案。'),
              dict(role='tool',name='railway_get_order',content=json.dumps(dict(
                  order_id=order_id,proposal_id=original_proposal,order_status='PENDING_PAYMENT',total_fen=1000)))]
    planner=RailwayDemoProvider()
    call,=planner.chat(messages,[])['tool_calls']
    assert call['name']=='railway_cancel_order' and call['arguments']=={'order_id':order_id}
    messages.append(dict(role='tool',name=call['name'],content=json.dumps(dict(
        proposal_id='P'+'c'*32,status='CONFIRMATION_REQUIRED'))))
    answer=planner.chat(messages,[])
    assert not answer['tool_calls'] and '尚未完成该交易' in answer['content']


def test_failed_request_is_persisted_and_new_request_can_retry(session,monkeypatch):
    from target.v39.planner import RailwayDemoProvider
    original=RailwayDemoProvider.chat
    def fail(*args,**kw):raise TimeoutError('controlled offline timeout')
    monkeypatch.setattr(RailwayDemoProvider,'chat',fail)
    with pytest.raises(Exception):session.send('你好','timeout-id',defer_followups=True)
    assert session.operations[-1]['status']=='FAILED'
    monkeypatch.setattr(RailwayDemoProvider,'chat',original)
    session.send('你好','retry-id',defer_followups=True)
    assert len(session.operations)==2 and session.operations[-1]['status']=='SUCCEEDED'
    assert session.operations[0]['status']=='FAILED'


def test_unconfigured_provider_is_blocked_without_fabricated_agent_trace(session,monkeypatch):
    monkeypatch.setattr(session,'_send',lambda *a:(_ for _ in ()).throw(ValueError('Provider未配置，未发送')))
    with pytest.raises(ValueError):session.send('你好','blocked',defer_followups=True)
    op=session.operations[-1]
    assert op['status']=='BLOCKED' and op['run_id'] is None and not op['agent_started']


@pytest.mark.parametrize('entry',['查余票','问政策','看订单','退票费率','行李费用','改签'])
def test_six_shortcut_failures_keep_same_entry_and_failed_audit(session,entry,monkeypatch):
    from target.v39.planner import RailwayDemoProvider
    from web.session_store import restore_session
    def timeout(*args,**kwargs):raise TimeoutError('offline validation only')
    monkeypatch.setattr(RailwayDemoProvider,'chat',timeout)
    with pytest.raises(Exception):session.send('查询项目示例政策','failed-'+entry,entry='quick:'+entry,defer_followups=True)
    op=session.operations[-1];restored=restore_session(session.root,expected_sid=session.sid)
    assert op['status']=='FAILED' and op['run_id']==session.audits[-1]['trace_id']
    assert restored.operations[-1]['entry']=='quick:'+entry and restored.operations[-1]['status']=='FAILED'
    assert not restored.history


def test_budget_block_and_cross_session_history_remain_distinct(session,monkeypatch):
    from target.deepseek_runtime import DeepSeekError
    from web.interaction import history
    def block(*args):raise DeepSeekError('observed_token_budget_exhausted')
    monkeypatch.setattr(session,'_send',block)
    with pytest.raises(DeepSeekError):session.send('查询车次','budget-stop',defer_followups=True)
    assert session.operations[-1]['status']=='BLOCKED'
    session.operations.append(dict(session.operations[-1],session_id='other',run_id='foreign'))
    session.audits.append(dict(trace_id='foreign-audit',public_trace=dict(session_id='other')))
    assert all(row.get('run_id') not in ('foreign','foreign-audit') for row in history(session))


def test_followup_job_does_not_hold_main_answer_or_repeat_generation(session,monkeypatch):
    from web import followup_jobs
    from target import followups
    record=session.send('你好','hello',defer_followups=True)
    entered=threading.Event();release=threading.Event();calls=[]
    original=followups.generate_and_save
    def slow(*args,**kw):calls.append(1);entered.set();assert release.wait(10);return original(*args,**kw)
    monkeypatch.setattr(followups,'generate_and_save',slow)
    before=copy.deepcopy(session.history)
    future=followup_jobs.schedule(session,record)
    assert entered.wait(5) and not future.done() and session.operations[-1]['status']=='SUCCEEDED'
    assert followup_jobs.schedule(session,record) is future
    release.set();saved=future.result(timeout=15)
    assert saved['suggestions'] and len(saved['suggestions'])<=3 and calls==[1]
    assert session.history==before


def test_render_defaults_do_not_read_another_workers_temporary_model_config(monkeypatch):
    import config
    from web.runtime import scoped,render_value,render_environment
    started=threading.Event();release=threading.Event()
    original=config.PROVIDER
    monkeypatch.setenv('DEEPSEEK_MODEL','user-configured-model')
    def worker():
        with scoped(dict(PROVIDER='bailian',ENGINE='langchain'),dict(DEEPSEEK_MODEL='temporary-worker-model')):
            started.set();assert release.wait(10)
    t=threading.Thread(target=worker);t.start()
    try:
        assert started.wait(5)
        assert render_value('PROVIDER')==original
        assert render_environment()['DEEPSEEK_MODEL']=='user-configured-model'
    finally:release.set();t.join(timeout=5)


def test_cancel_only_a_queued_job_creates_no_agent_trace(session,monkeypatch):
    import concurrent.futures
    from web import interaction
    pool=concurrent.futures.ThreadPoolExecutor(max_workers=1)
    entered=threading.Event();release=threading.Event()
    def occupy():entered.set();release.wait(10)
    pool.submit(occupy);assert entered.wait(5)
    monkeypatch.setattr(interaction,'POOL',pool)
    try:
        future=interaction.submit(session,'你好','queue-cancel')
        assert session.operations[-1]['status']=='QUEUED'
        assert interaction.cancel_queued(session) and future.cancelled()
        assert session.operations[-1]['status']=='CANCELLED'
        assert not session.audits and session.agent is None
    finally:release.set();pool.shutdown(wait=True)


def test_restore_interrupted_run_is_blocked_and_never_reexecuted(session):
    from web import interaction
    from web.session_store import restore_session
    interaction.begin(session,'你好','interrupted','chat')
    restored=restore_session(session.root,expected_sid=session.sid)
    assert restored.read_only and restored.agent is None
    assert restored.operations[-1]['status']=='BLOCKED'
    assert restored.operations[-1]['error']['category']=='interrupted_without_final_receipt'


@pytest.mark.parametrize('provider',['deepseek','bailian'])
@pytest.mark.parametrize('output',['valid','malformed','ungrounded'])
def test_contextual_followup_uses_same_sdk_provider_usage_and_safe_fallback(provider,output):
    from tests.test_followups_mvp import FollowupMVPTests
    from target.followups import generate_and_save
    from target.run_events import capture,bind
    from target.trace import Trace
    from web.runtime import scoped
    case=FollowupMVPTests();case.setUp()
    try:
        raw={'valid':'valid','malformed':'bad-json','ungrounded':'{"suggestions":[{"id":"invented","question":"G999999已经支付"},{"id":"fake","question":"假车次"}]}'}[output]
        model,settings=case.sdk(provider,output=raw)
        trace=Trace('offline-context','你好，我第一次使用这个助手');trace.provider=provider+'_live'
        trace.model='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash';trace.finish('可以查询铁路时刻和示例政策，所有交易均为本地模拟。')
        record=trace.to_dict();before=copy.deepcopy(record);audit=dict(trace_id=trace.trace_id,public_trace=record)
        directory=case.root/trace.trace_id
        with scoped({'PROVIDER':provider,'MODEL_NAME':trace.model}),capture(directory/'run_events.jsonl'):
            bind(trace)
            saved=generate_and_save(record,audit,directory,live=True,authorized=True,network_ready=True,
                model=model,settings=settings,enhanced=True)
        assert len(case.calls)==1 and saved['http_requests']==1
        assert saved['tokens']==dict(prompt=20,completion=10) and record==before
        assert saved['generation_source']==('model' if output=='valid' else 'rule_fallback')
        assert 2<=len(saved['suggestions'])<=3 and all('G999999' not in q for q in saved['suggestions'])
        assert saved['provider']==provider+'_live' and saved['model']==trace.model
        import os
        output_root=Path(os.environ['RAILWAY_SIM_DB_PATH']).parent
        (output_root/f'sdk-followup-{provider}-{output}.json').write_text(json.dumps(dict(
            fixture_only=True,real_api_requests=0,request_bodies=case.calls,result=saved,main_trace_unchanged=record==before),ensure_ascii=False,indent=2),encoding='utf8')
    finally:case.doCleanups()


def test_railway_suggestions_only_reference_current_real_records():
    from target.followups import contextual_candidates
    from tests.v39.test_v396_paging_context import incident
    source=incident()[0];rid='run-current';sid='session-current'
    event=dict(event_type='tool_result',run_id=rid,session_id=sid,event_id='actual-event',status='succeeded',executed=True,
        tool='railway_query_trips',args=source['args'],output=source['result'])
    trace=dict(session_id=sid,user_msg='查询车次',reply='真实静态查询完成')
    options,facts=contextual_candidates(trace,[event],dict(trace_id=rid))
    assert len(options)>=2 and all(r['source_event_ids']==['actual-event'] for r in options)
    assert all('2026-11-05' in r['question'] for r in options)
    assert facts['intent']=='railway_query'
    other=dict(event,session_id='other')
    changed,_=contextual_candidates(trace,[other],dict(trace_id=rid))
    assert all('G7541' not in r['question'] for r in changed)


def test_order_followups_use_owned_executed_record_without_confirm_commands():
    from target.followups import contextual_candidates
    trace=dict(session_id='current',user_msg='查看我的订单',reply='已读取订单')
    event=dict(event_type='tool_result',status='succeeded',executed=True,tool='railway_get_order',
        run_id='r',session_id='current',event_id='real-order-read',output=dict(order_id='V39-owned',order_status='CHANGED',active_item_count=2))
    options,facts=contextual_candidates(trace,[event],dict(trace_id='r'))
    assert len(options)==3 and all('V39-owned' in r['question'] for r in options)
    assert all(r['source_event_ids']==['real-order-read'] for r in options)
    assert all('确认支付' not in r['question'] and '确认改签' not in r['question'] for r in options)
