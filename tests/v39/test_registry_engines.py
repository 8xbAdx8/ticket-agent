from contextlib import ExitStack
from dataclasses import replace
import json
import pytest
import config
from target.v39.context import scope
from target.v39.registry import service_scope,definitions,dispatch,NAMES,TOOLS
from tests.v39.test_service import sim

class ScriptedProvider:
    """Controlled model, actual registered ToolNode/Legacy execution, no API."""
    name='mock'
    last_usage={'prompt':0,'completion':0}
    mutations={}
    def __init__(self,tool,args):self.tool=tool;self.args=args
    def chat(self,messages,tools):
        if messages[-1]['role']=='tool':return dict(role='assistant',content='已收到工具实际结果，交易仍需页面确认。',tool_calls=[])
        return dict(role='assistant',content='',tool_calls=[dict(id='rail-call',name=self.tool,arguments=self.args)])

def bound(sim):
    s,ctx=sim
    return s,replace(ctx,tool_whitelist=NAMES)

def test_registered_definitions_schema_and_no_secret(sim,monkeypatch):
    from target.tools import TOOLS as OLD
    s,ctx=bound(sim)
    assert len(TOOLS)==11 and len(OLD)==8
    assert 'token' not in json.dumps(TOOLS).lower()
    assert len(definitions(OLD))==8
    with scope(ctx),service_scope(s):
        assert len(definitions(OLD))==11
        result,ok,_=dispatch('railway_check_inventory',dict(trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',quantity=True))
        assert not ok and result['error']=='INVALID_RAILWAY_ARGUMENTS'
        monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','0')
        assert len(definitions(OLD))==8
        assert not dispatch('railway_get_order',{})[1]
    assert len(OLD)==8

@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_actual_engine_proposal_cannot_confirm(sim,monkeypatch,tmp_path,engine):
    from target.agent import Agent
    s,ctx=bound(sim)
    monkeypatch.setattr(config,'PROVIDER','mock');monkeypatch.setattr(config,'LC_TOOLSET','all')
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'old-untouched.sqlite')
    monkeypatch.setattr(config,'TRACE_DIR',tmp_path/'traces')
    monkeypatch.setattr(config,'BASE_DIR',tmp_path)
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    with scope(ctx),service_scope(s):
        a=Agent(engine=engine,provider=ScriptedProvider('railway_create_order',dict(quote_id=q['quote_id'],passengers=['演示乘客'],contact=ctx.owner_phone)))
        result=a.chat(ctx.session_id,'为已有报价创建铁路模拟购票提案',save_trace=False)
    calls=[c for step in result['steps'] for c in step['calls']]
    assert len(calls)==1 and calls[0]['tool']=='railway_create_order' and calls[0]['ok'] is True
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_proposals').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM v39_transactions').fetchone()[0]==0
    assert not config.DB_PATH.exists()
    assert set(result)=={'session_id','provider','model','user_msg','steps','tool_sequence','reply','finish_reason','tokens','total_latency_ms'}

def test_baseline_and_revocation_block_even_old_proposals(sim,monkeypatch):
    from types import SimpleNamespace
    from target.execution_config import scope as effective_scope
    from tests.v39.test_service import create
    s,ctx=bound(sim)
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['A']))
    for value in (replace(ctx,enabled=False),replace(ctx,execution_mode='baseline'),replace(ctx,write_policy=(('CREATE_ORDER','deny'),))):
        with pytest.raises(ValueError):s.confirm(value,p['proposal_id'])
    with effective_scope(SimpleNamespace(execution_mode='baseline')):
        with scope(ctx),service_scope(s):
            assert definitions([])==[]
            with pytest.raises(ValueError):s.confirm(ctx,p['proposal_id'])
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','0')
    with pytest.raises(ValueError):s.confirm(ctx,p['proposal_id'])
    with s.store.transaction() as c:assert c.execute('SELECT used_at FROM v39_confirmation_tokens').fetchone()[0] is None
