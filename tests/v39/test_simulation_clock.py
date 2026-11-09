"""Two time domains, persistent ownership, actual SQLite and unchanged policy."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import pytest
from target.v39.simulation_clock import SimulationClock,LOCAL,dataset_anchor,real_now
from target.v39.service import Service
from target.v39.store import Store
from tests.v39.test_service import SyntheticStatic,sim
from target.v39.context import Context


@pytest.fixture
def clock_sim(tmp_path,monkeypatch):
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','1')
    clock=SimulationClock.create(tmp_path/'clock.sqlite','S',datetime(2026,11,3,tzinfo=LOCAL),'SYNTHETIC_TEST_FIXTURE/v39')
    s=Service(Store(tmp_path/'business.sqlite'),SyntheticStatic(),clock=clock)
    s.start();s.scenario('demo','SYNTHETIC_TEST_FIXTURE/v39')
    return s,Context('S','U','demo',enabled=True),clock


def create(s,ctx):
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['三三'],contact=ctx.owner_phone))
    return q,p


def test_pause_persist_scope_and_revision(clock_sim):
    s,ctx,clock=clock_sim;before=clock.snapshot()
    opened=SimulationClock(clock.path,ctx.session_id,clock.clock_id)
    assert opened.snapshot()==before
    with pytest.raises(ValueError,match='SCOPE_MISMATCH'):SimulationClock(clock.path,'other',clock.clock_id)
    clock.advance(60,revision=0)
    assert opened()==datetime.fromisoformat(before['now'])+timedelta(minutes=1)
    with pytest.raises(ValueError,match='STALE'):opened.advance(60,revision=0)
    with pytest.raises(ValueError,match='INVALID_CLOCK_ADVANCE'):opened.advance(-60,revision=1)
    assert opened.snapshot()['revision']==1


def test_lost_clock_is_not_recreated(clock_sim):
    import sqlite3
    s,ctx,clock=clock_sim
    with pytest.raises(sqlite3.OperationalError):SimulationClock(clock.path.with_name('missing.sqlite'),ctx.session_id,clock.clock_id)
    assert not clock.path.with_name('missing.sqlite').exists()


def test_advances_are_atomic_between_two_clients(clock_sim):
    from concurrent.futures import ThreadPoolExecutor
    s,ctx,clock=clock_sim
    def attempt(_):
        try:return clock.advance(60,revision=0)['revision']
        except ValueError as exc:return str(exc)
    with ThreadPoolExecutor(2) as p:results=list(p.map(attempt,range(2)))
    assert sorted(map(str,results))==['1','SIMULATION_CLOCK_STALE']


def test_no_wall_clock_expiry_and_manual_proposal_expiry(clock_sim):
    s,ctx,clock=clock_sim;q,p=create(s,ctx)
    assert s.now().year==2026 and s.now()!=real_now()
    assert (real_now()-datetime.fromisoformat(p['expires_at'])).total_seconds()>0
    assert s.confirm(ctx,p['proposal_id'])['status']=='PENDING_PAYMENT'
    q,p=create(s,ctx);clock.advance(301,revision=0)
    assert s.confirm(ctx,p['proposal_id'])['status']=='PROPOSAL_EXPIRED'


def test_manual_hold_expiry_releases_stock_once(clock_sim):
    s,ctx,clock=clock_sim;q,p=create(s,ctx);o=s.confirm(ctx,p['proposal_id'])
    clock.advance(900,revision=0)
    assert s.expire(ctx)==1 and s.expire(ctx)==0
    assert s.order(ctx,o['order_id'])['order_status']=='EXPIRED'
    with s.store.transaction() as c:
        assert all(tuple(r)==(0,0) for r in c.execute('SELECT held,sold FROM v39_inventory_segments'))
        assert c.execute('SELECT remaining_quantity FROM v39_holds').fetchone()[0]==0


def test_quote_expiry_and_departure_still_enforced(clock_sim):
    s,ctx,clock=clock_sim;q,p=create(s,ctx)
    clock.advance(601,revision=0)
    with pytest.raises(ValueError,match='QUOTE_EXPIRED'):s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['三三']))
    clock.advance(4*86400,revision=1)
    q,p=create(s,ctx)
    with pytest.raises(ValueError,match='DEPARTURE_ALREADY_PASSED'):s.confirm(ctx,p['proposal_id'])


@pytest.mark.parametrize('hours,rate',[(49,500),(48,1000),(24,1000),(23,2000)])
def test_p01_uses_simulation_clock_without_policy_changes(clock_sim,hours,rate):
    from target.v39.policy import Policy
    s,ctx,clock=clock_sim
    departure=s.now()+timedelta(days=4)
    clock.advance(4*86400-hours*3600,revision=0)
    fee=Policy().refund([10000],departure.isoformat(),s.stamp())[0]['fee_fen']
    assert fee==rate


def test_worker_lease_uses_real_time_even_when_simulation_advanced(clock_sim):
    s,ctx,clock=clock_sim
    with s.store.transaction() as c:initial=datetime.fromisoformat(c.execute('SELECT lease_until FROM v39_worker_lease').fetchone()[0])
    assert abs((initial-real_now()).total_seconds()-60)<5
    clock.advance(6*86400,revision=0)
    with s.store.transaction() as c:s._lease(c)
    with s.store.transaction() as c:expiry=datetime.fromisoformat(c.execute('SELECT lease_until FROM v39_worker_lease').fetchone()[0])
    assert abs((expiry-real_now()).total_seconds()-60)<5
    other=Service(s.store,s.static,clock=clock)
    with pytest.raises(ValueError,match='WORKER_BUSY'):other.start()


def test_existing_injected_clocks_remain_compatible(sim):
    s,ctx=sim
    assert s.infrastructure_now()==s.now() and not getattr(s.clock,'simulation',False)


def test_real_gtfs_anchor_and_early_train_are_reusable_past_wall_time(tmp_path,monkeypatch):
    from target.v39.static import RailwayStatic,VERSION
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','1');static=RailwayStatic();anchor=dataset_anchor(static)
    clock=SimulationClock.create(tmp_path/'clock.sqlite','S',anchor,VERSION)
    s=Service(Store(tmp_path/'business.sqlite'),static,clock=clock);s.start();s.scenario('demo',VERSION)
    ctx=Context('S','U','demo',enabled=True)
    q=s.quote(ctx,trip_id='5l000G733102',service_date='2026-11-05',origin_stop_id='AOH',destination_stop_id='HGH',seat_class='SECOND',passenger_count=1)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['三三']))
    assert s.confirm(ctx,p['proposal_id'])['status']=='PENDING_PAYMENT'
    assert s.now()<datetime.fromisoformat('2026-11-05T06:13:00+08:00')


def test_web_binding_keeps_old_ref_and_persists_new_demo(session,monkeypatch):
    from web import v39_bridge,business_state
    from web.session_store import restore_session
    monkeypatch.setenv('RAILWAY_SIM_CLOCK_MODE','demo')
    v=business_state.refresh(session);assert v['simulation_clock']['mode']=='PAUSED'
    ref=dict(session.railway_state_reference);s=session._v39_service
    s.clock.advance(60,revision=0);session.save_replay()
    s2,ctx,effective=v39_bridge.prepare(session);assert s2.store.path==s.store.path
    restored=restore_session(session.root,expected_sid=session.sid)
    assert restored.read_only and restored.railway_state_reference==ref
    value=business_state.refresh(restored)
    assert value['simulation_clock']['revision']==1
    assert value['simulation_clock']['now']==s.clock.snapshot()['now']
    assert '当前铁路模拟北京时间日期' in effective.prompt


def test_baseline_never_creates_demo_clock(session,monkeypatch):
    from web.v39_bridge import prepare
    monkeypatch.setenv('RAILWAY_SIM_CLOCK_MODE','demo');session.execution_mode='baseline'
    assert prepare(session) is None and not getattr(session,'railway_state_reference',None)


def test_launcher_defaults_demo_with_explicit_real_override(tmp_path):
    from scripts.launch_app import build_environment
    for mode in ('offline','live'):
        assert build_environment(mode,tmp_path,inherited={})['RAILWAY_SIM_CLOCK_MODE']=='demo'
        assert build_environment(mode,tmp_path,inherited={'RAILWAY_SIM_CLOCK_MODE':'real'})['RAILWAY_SIM_CLOCK_MODE']=='real'


def test_old_scene_is_never_retimed_by_new_default(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from web.simulation_clock import binding
    ref=dict(path=str(tmp_path/'existing.sqlite'),scenario_id='old')
    session=SimpleNamespace(sid='old',railway_state_reference=ref)
    monkeypatch.setenv('RAILWAY_SIM_CLOCK_MODE','demo')
    path,clock=binding(session)
    assert path==tmp_path/'existing.sqlite' and clock is None and session.railway_state_reference==ref
    assert not path.exists() and not (tmp_path/'clock.sqlite').exists()


def test_clock_day_config_and_existing_profile_cannot_be_switched_back(session,monkeypatch):
    from web.v39_bridge import prepare
    from target.execution_config import scope
    monkeypatch.setenv('RAILWAY_SIM_CLOCK_MODE','demo')
    s,ctx,first=prepare(session);clock=s.clock
    clock.advance(60,revision=0)
    assert prepare(session)[2].config_hash==first.config_hash
    clock.advance(86400,revision=1)
    s,new_ctx,second=prepare(session)
    assert second.config_hash!=first.config_hash and second.prompt_sha256!=first.prompt_sha256
    monkeypatch.setenv('RAILWAY_SIM_CLOCK_MODE','real')
    assert prepare(session)[0].clock.clock_id==clock.clock_id


from tests.v39.test_v394_defaults import session
