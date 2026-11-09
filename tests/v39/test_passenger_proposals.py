"""Incident regression: actual SQL and both engines; no real model/API calls."""
import json
from dataclasses import replace
import pytest
import config
from tests.v39.test_service import sim
from target.v39.context import scope
from target.execution_config import scope as effective_scope
from target.v39.registry import dispatch,service_scope,NAMES


@pytest.fixture(autouse=True)
def clean_contexts():
    with effective_scope(None),scope(None),service_scope(None):yield


@pytest.fixture
def restore_streamlit_main():
    # Streamlit's script runner replaces __main__. Restore the real runner so
    # later Windows ProcessPool tests do not spawn this transient UI script.
    import sys
    original=sys.modules.get('__main__')
    try:yield
    finally:
        if original is not None:sys.modules['__main__']=original


def quote(s,ctx):
    return s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',
                   destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']


def args(q,ctx,name):
    return dict(quote_id=q['quote_id'],passengers=[name],contact=ctx.owner_phone)


def counts(s):
    with s.store.transaction() as c:
        return {t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
                ('v39_proposals','v39_confirmation_tokens','v39_orders','v39_holds',
                 'v39_inventory_segments','v39_transactions','v39_audit_events')}


def legacy_draft(s,ctx,q,monkeypatch):
    # Reproduce a pre-fix record using the old non-empty-only validation.
    # This bypass exists only in this synthetic test fixture, never production.
    import target.v39.service as module
    with monkeypatch.context() as m:
        m.setattr(module,'require_names',lambda names,count:None)
        return s.propose(ctx,'CREATE_ORDER',args(q,ctx,'请提供乘客姓名'))


@pytest.mark.parametrize('name',['请提供乘客姓名',' 请提供乘客姓名。 ','请输入乘客姓名',
                                '乘客姓名','TBD','unknown','passenger_name'])
def test_placeholder_is_clarification_without_proposal_or_transaction(sim,name):
    s,ctx=sim;ctx=replace(ctx,tool_whitelist=NAMES);q=quote(s,ctx);before=counts(s)
    with scope(ctx),service_scope(s):
        result,ok,_=dispatch('railway_create_order',args(q,ctx,name))
    assert ok and result['status']=='NEEDS_INPUT' and result['missing_fields']==['passengers']
    assert 'proposal_id' not in result and 'order_id' not in result and 'error' not in result
    assert counts(s)==before


@pytest.mark.parametrize('name',['三三','一',"O’Neill",'Anne-Marie','阿布都·热合曼','Demo0'])
def test_valid_names_and_user_confirmation_still_work(sim,name):
    s,ctx=sim;q=quote(s,ctx);p=s.propose(ctx,'CREATE_ORDER',args(q,ctx,name))
    assert counts(s)['v39_orders']==0 and counts(s)['v39_holds']==0
    o=s.confirm(ctx,p['proposal_id']);assert o['status']=='PENDING_PAYMENT'
    assert s.confirm(ctx,p['proposal_id'])==o
    order=s.order(ctx,o['order_id'])
    assert order['items'][0]['passenger_name']==name and order['payment_status']=='UNPAID'
    assert counts(s)['v39_orders']==1 and counts(s)['v39_transactions']==0


def test_legacy_placeholder_cannot_be_confirmed(sim,monkeypatch):
    s,ctx=sim;q=quote(s,ctx);old=legacy_draft(s,ctx,q,monkeypatch);before=counts(s)
    with pytest.raises(ValueError,match='PASSENGER_NAME_REQUIRED'):s.confirm(ctx,old['proposal_id'])
    assert counts(s)==before
    with s.store.transaction() as c:
        assert c.execute('SELECT used_at FROM v39_confirmation_tokens').fetchone()[0] is None
        assert c.execute('SELECT state FROM v39_proposals').fetchone()[0]=='PENDING'


def test_valid_name_atomically_replaces_only_legacy_bad_draft(sim,monkeypatch):
    s,ctx=sim;q=quote(s,ctx);old=legacy_draft(s,ctx,q,monkeypatch);pid=old['proposal_id']
    with s.store.transaction() as c:
        original=dict(c.execute('SELECT * FROM v39_proposals WHERE proposal_id=?',(pid,)).fetchone())
    new=s.propose(ctx,'CREATE_ORDER',args(q,ctx,'三三'))
    with s.store.transaction() as c:
        history=dict(c.execute('SELECT * FROM v39_proposals WHERE proposal_id=?',(pid,)).fetchone())
        assert history==dict(original,state='CANCELLED')
        token=c.execute('SELECT * FROM v39_confirmation_tokens WHERE proposal_id=?',(pid,)).fetchone()
        assert token['invalid_reason']=='PASSENGER_NAME_REQUIRED' and token['used_at'] is None
        e=c.execute("SELECT detail_json FROM v39_audit_events WHERE event_type='INVALID_PASSENGER_PROPOSAL_REPLACED'").fetchone()
        assert json.loads(e[0])['replacement_proposal_id']==new['proposal_id']
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
    assert pid not in s._secrets and counts(s)['v39_orders']==0
    result=s.confirm(ctx,new['proposal_id'])
    assert s.order(ctx,result['order_id'])['items'][0]['passenger_name']=='三三'
    old_result=s.confirm(ctx,pid)
    assert old_result.get('status')!='PENDING_PAYMENT' and counts(s)['v39_orders']==1


def test_replacement_failure_rolls_back_draft_token_event_and_secrets(sim,monkeypatch):
    import target.v39.service as module
    s,ctx=sim;q=quote(s,ctx);old=legacy_draft(s,ctx,q,monkeypatch);before=counts(s);secrets=dict(s._secrets)
    real=module.insert
    def fail(c,table,values):
        if table=='v39_confirmation_tokens':raise RuntimeError('injected new token failure')
        return real(c,table,values)
    monkeypatch.setattr(module,'insert',fail)
    with pytest.raises(RuntimeError,match='injected'):s.propose(ctx,'CREATE_ORDER',args(q,ctx,'三三'))
    assert counts(s)==before and s._secrets==secrets
    with s.store.transaction() as c:
        assert c.execute('SELECT state FROM v39_proposals').fetchone()[0]=='PENDING'
        assert c.execute('SELECT invalidated_at FROM v39_confirmation_tokens').fetchone()[0] is None


def test_valid_draft_is_never_automatically_replaced(sim):
    s,ctx=sim;q=quote(s,ctx);old=s.propose(ctx,'CREATE_ORDER',args(q,ctx,'原乘客'));before=counts(s)
    with pytest.raises(ValueError,match='PROPOSAL_ALREADY_PENDING'):
        s.propose(ctx,'CREATE_ORDER',args(q,ctx,'三三'))
    assert counts(s)==before
    assert s.order(ctx,s.confirm(ctx,old['proposal_id'])['order_id'])['items'][0]['passenger_name']=='原乘客'


def test_different_quote_and_permission_cannot_retire_old_draft(sim,monkeypatch):
    s,ctx=sim;q=quote(s,ctx);old=legacy_draft(s,ctx,q,monkeypatch)
    with pytest.raises(ValueError,match='WRITE_POLICY_DENIED'):
        s.propose(replace(ctx,write_policy=(('CREATE_ORDER','deny'),)),'CREATE_ORDER',args(q,ctx,'三三'))
    with pytest.raises(ValueError,match='QUOTE_FORBIDDEN'):
        s.propose(replace(ctx,session_id='other'),'CREATE_ORDER',args(q,ctx,'三三'))
    s.propose(ctx,'CREATE_ORDER',args(quote(s,ctx),ctx,'三三'))
    with s.store.transaction() as c:
        assert c.execute('SELECT state FROM v39_proposals WHERE proposal_id=?',(old['proposal_id'],)).fetchone()[0]=='PENDING'
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==0


class MissingThenProvided:
    name='mock';last_usage={'prompt':0,'completion':0};mutations={}
    def __init__(self,q,ctx):self.q=q;self.ctx=ctx
    def chat(self,messages,tools):
        if messages[-1]['role']=='tool':
            payload=json.loads(messages[-1]['content'])
            text='请提供模拟乘客姓名。' if payload.get('status')=='NEEDS_INPUT' else '已生成三三的建单确认卡，请在页面核对确认；尚未建单。'
            return dict(role='assistant',content=text,tool_calls=[])
        user=next(m['content'] for m in reversed(messages) if m['role']=='user')
        return dict(role='assistant',content='',tool_calls=[dict(id='name-call',name='railway_create_order',arguments=args(self.q,self.ctx,'三三' if user=='三三' else '请提供乘客姓名'))])


@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_both_engines_ask_then_continue_without_failed_tool_or_order(sim,monkeypatch,tmp_path,engine):
    from target.agent import Agent
    s,ctx=sim;ctx=replace(ctx,tool_whitelist=NAMES);q=quote(s,ctx)
    monkeypatch.setattr(config,'PROVIDER','mock');monkeypatch.setattr(config,'LC_TOOLSET','all')
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'old-untouched.sqlite')
    monkeypatch.setattr(config,'TRACE_DIR',tmp_path/'traces');monkeypatch.setattr(config,'BASE_DIR',tmp_path)
    with scope(ctx),service_scope(s):
        agent=Agent(engine=engine,provider=MissingThenProvided(q,ctx))
        first=agent.chat(ctx.session_id,'买D3145的票',save_trace=False)
        assert '姓名' in first['reply'] and counts(s)['v39_proposals']==0
        second=agent.chat(ctx.session_id,'三三',save_trace=False)
    for result in (first,second):
        assert all(call['ok'] for step in result['steps'] for call in step['calls'])
        assert len(result)==10
    assert counts(s)['v39_proposals']==1 and counts(s)['v39_orders']==0 and counts(s)['v39_transactions']==0
    assert not config.DB_PATH.exists()


def test_clarification_phase_is_not_completed_transaction():
    from web.run_view import phase_states
    rows=phase_states([dict(event_type='railway_tool_result',tool='railway_create_order',
                           status='succeeded',output=dict(status='NEEDS_INPUT'))])
    execute=next(r for r in rows if r['key']=='execute')
    assert execute['status']=='pending' and '姓名' in execute['detail']


def test_two_name_corrections_cannot_make_duplicate_live_drafts(sim,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    s,ctx=sim;q=quote(s,ctx);old=legacy_draft(s,ctx,q,monkeypatch)
    def attempt(name):
        try:return s.propose(ctx,'CREATE_ORDER',args(q,ctx,name))
        except ValueError as exc:return dict(error=str(exc))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,['三三','四四']))
    assert sum(r.get('status')=='CONFIRMATION_REQUIRED' for r in results)==1
    assert sum(r.get('error')=='PROPOSAL_ALREADY_PENDING' for r in results)==1
    with s.store.transaction() as c:
        assert c.execute("SELECT count(*) FROM v39_proposals WHERE state='PENDING'").fetchone()[0]==1
        assert c.execute("SELECT state FROM v39_proposals WHERE proposal_id=?",(old['proposal_id'],)).fetchone()[0]=='CANCELLED'
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==0


@pytest.mark.parametrize('legacy_bad',[False,True])
def test_real_streamlit_confirm_disabled_for_legacy_placeholder_only(sim,monkeypatch,legacy_bad,restore_streamlit_main):
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    from target.v39.read_model import read
    from web import v39_bridge,railway_queries,business_state
    s,ctx=sim;q=quote(s,ctx)
    p=legacy_draft(s,ctx,q,monkeypatch) if legacy_bad else s.propose(ctx,'CREATE_ORDER',args(q,ctx,'三三'))
    view=dict(railway=read(s.store.path,ctx,now=s.now()))
    session=SimpleNamespace(read_only=False,sid=ctx.session_id,_v39_service=s,
                            _v39_context=ctx,_v39_effective=object())
    monkeypatch.setattr(v39_bridge,'_passenger_test_session',session,raising=False)
    monkeypatch.setattr(v39_bridge,'prepare',lambda _: (s,ctx,session._v39_effective))
    monkeypatch.setattr(railway_queries,'panel',lambda *a:None)
    monkeypatch.setattr(business_state,'current',lambda _:view)
    app=AppTest.from_string('from web import v39_bridge\nv39_bridge.render(v39_bridge._passenger_test_session)',default_timeout=15).run()
    assert not app.exception
    before=counts(s)
    app.checkbox[0].check().run()
    confirm=next(b for b in app.button if b.label=='确认')
    assert confirm.disabled is legacy_bad
    assert next(b for b in app.button if b.label=='撤销').disabled is False
    assert bool(app.warning) is legacy_bad
    assert counts(s)==before and counts(s)['v39_orders']==0
