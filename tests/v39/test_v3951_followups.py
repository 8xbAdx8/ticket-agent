from copy import deepcopy
from types import SimpleNamespace
import pytest
from web.railway_followups import build,identity,consume,register
from tests.v39.test_v394_defaults import session


def row(day='2026-11-05',origin='A',destination='B',cursor=None):
    return dict(ok=True,tool='railway_query_trips',id='query-'+day+origin+destination+str(cursor),args={},result=dict(query_parameters=dict(service_date=day,origin_stop_id=origin,destination_stop_id=destination,cursor=cursor),data=[dict(trip_id='T'+str(i),trip_short_name='G'+str(i+1),departure_at=day+'T'+t+':00+08:00',arrival_at=day+'T'+a+':00+08:00') for i,(t,a) in enumerate([('07:00','08:00'),('13:00','13:45'),('19:43','20:45')])]))


def test_route_questions_are_bounded_deduplicated_and_grounded():
    r=row();before=deepcopy(r);q=build('S',r,{'A':'出发站甲','B':'到达站乙'})
    assert len(q)==4 and len({x['label'] for x in q})==4
    assert all(x['service_date']=='2026-11-05' and x['origin_stop_id']=='A' and '出发站甲' in x['message'] for x in q)
    assert r==before and all(x['context_id']==identity('S',r) for x in q)


def test_focused_times_and_next_train_are_from_records():
    q=build('S',row(),{'A':'甲','B':'乙'},'T1')
    assert any('13:00' in x['label'] for x in q) and any('13:45' in x['label'] for x in q)
    assert any('G2 和 G3' in x['label'] for x in q)
    assert all(x['train_id']=='T1' for x in q)


def test_missing_times_do_not_create_time_questions():
    r=row()
    for t in r['result']['data']:t.pop('departure_at');t.pop('arrival_at')
    q=build('S',r,{},'T0')
    assert len(q)==2 and not any('更早' in x['label'] for x in q)


def test_stops_questions_require_real_detail():
    detail=dict(ok=True,result=dict(data=dict(stops=[dict(stop_id='X',arrival_time='25:00:00',departure_time='25:03:00'),dict(stop_id='B',arrival_time='26:00:00',departure_time='26:00:00')])))
    q=build('S',row(),{},'T0',detail)
    assert any('停留时间最长' in x['label'] for x in q) and any('最后一站' in x['label'] for x in q)
    assert not any('停留时间最长' in x['label'] for x in build('S',row(),{},'T0'))


@pytest.mark.parametrize('change',[dict(day='2026-11-06'),dict(origin='C'),dict(destination='C'),dict(cursor='20')])
def test_context_change_rejects_old_requests(change):
    old=row();q=build('S',old,{})[0];request=dict(q,sid='S')
    assert consume(SimpleNamespace(sid='S',read_only=False),request,build('S',row(**change),{})) is None


def test_session_and_read_only_isolation():
    q=build('A',row(),{})[0];request=dict(q,sid='A')
    assert consume(SimpleNamespace(sid='B',read_only=False),request,build('B',row(),{})) is None
    assert consume(SimpleNamespace(sid='A',read_only=True),request,[q]) is None
    assert consume(SimpleNamespace(sid='A',read_only=False),request,[q])['question']==q['message']


def test_empty_and_failure_clear_questions():
    r=row();r['result']['data']=[];assert build('S',r,{})==[]
    r['ok']=False;s=SimpleNamespace();register(s,r)
    assert s.railway_followup_row is None and build('S',r,{})==[]


def test_runtime_rail_generation_never_calls_auxiliary_model(monkeypatch):
    from web.runtime import Conversation
    import target.followups
    monkeypatch.setattr(target.followups,'generate_and_save',lambda *a,**k:pytest.fail('auxiliary API generation called'))
    s=SimpleNamespace(mode='user',results=[[row()]])
    Conversation._record_followups(s,{'tool_sequence':['railway_query_trips']},True)
    assert s.railway_followup_row==row()


def test_rail_chip_sends_real_conversation_without_transactions(session):
    import os,sqlite3
    from web import railway_defaults
    from web.railway_cards import names_for
    railway_defaults.default_demo(session)
    r=session.railway_followup_row
    questions=build(session.sid,r,names_for(session))
    request=consume(session,dict(questions[0],sid=session.sid),questions)
    assert request
    session._rail_followup_dispatch=True
    record=session.send(request['question'],'v3951-local-chip',followup_authorized=False)
    assert record['session_id']==session.sid and 'railway_query_trips' in record['tool_sequence']
    assert session.history[-1]['user_msg']==request['question']
    with sqlite3.connect(os.environ['RAILWAY_SIM_DB_PATH']) as db:
        for t in ('v39_orders','v39_quotes','v39_proposals','v39_transactions'):
            assert db.execute('SELECT count(*) FROM '+t).fetchone()[0]==0


def test_draft_route_date_session_changes_have_distinct_signatures():
    from web.railway_followups import draft
    a={'ft_date':'2026-11-05','ft_from':'上海'}
    assert draft(a,'S')!=draft(dict(a,ft_date='2026-11-06'),'S')
    assert draft(a,'S')!=draft(dict(a,ft_from='北京'),'S')


def test_clarification_from_rail_chip_skips_model_suggestion_generation(monkeypatch):
    from web.runtime import Conversation
    import target.followups
    monkeypatch.setattr(target.followups,'generate_and_save',lambda *a,**k:pytest.fail('auxiliary API generation called'))
    s=SimpleNamespace(mode='user',_rail_followup_dispatch=True)
    Conversation._record_followups(s,{'tool_sequence':[]},True)


def test_identical_agent_requery_gets_new_context_without_mutating_trace():
    r=row();r.pop('id');before=deepcopy(r);s=SimpleNamespace()
    register(s,r);first=identity('S',s.railway_followup_row)
    register(s,r);second=identity('S',s.railway_followup_row)
    assert first!=second and r==before
