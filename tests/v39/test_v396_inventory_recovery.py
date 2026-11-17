"""Deterministic regression for the actual G7543 station-name/ID correction."""
import copy,json
from pathlib import Path
import pytest
from target.v39.read_recovery import inventory_recoveries
from tests.v39.test_v394_defaults import session


def incident():return json.loads((Path(__file__).parent/'fixtures/v396-inventory-recovery.json').read_text('utf8'))


def test_original_failure_is_preserved_and_exact_correction_is_proven():
    events=incident();original=copy.deepcopy(events)
    assert inventory_recoveries(events)=={events[0]['call_id']:events[-1]['call_id']}
    assert events==original and events[0]['ok'] is False


@pytest.mark.parametrize('fault',['no_success','different_date','different_train','different_seat','different_quantity','different_destination','ambiguous','failed_lookup','not_executed','permission_error'])
def test_unrelated_or_unproven_attempts_cannot_clear_failure(fault):
    events=incident()
    if fault=='no_success':events.pop()
    elif fault.startswith('different_'):
        field={'different_date':'service_date','different_train':'trip_id','different_seat':'seat_class','different_quantity':'quantity','different_destination':'destination_stop_id'}[fault]
        events[-1]['args'][field]='OTHER'
    elif fault=='ambiguous':events[1]['result']['data'].append(dict(stop_id='OTHER',stop_name=events[1]['args']['name']))
    elif fault=='failed_lookup':events[1]['ok']=False
    elif fault=='not_executed':events[-1]['executed']=False
    elif fault=='permission_error':events[0]['result']['error']='ORDER_FORBIDDEN'
    assert inventory_recoveries(events)=={}


class CorrectionModel:
    name='scripted_mock'
    def __init__(self,correct=True):self.calls=0;self.correct=correct
    def chat(self,messages,tools):
        rows=incident();step=self.calls;self.calls+=1
        if step==0:selected=[rows[0]]
        elif step==1 and self.correct:selected=rows[1:3]
        elif step==2 and self.correct:selected=[rows[-1]]
        else:return dict(role='assistant',content='模拟余票8张，尚未锁座、建单或支付。',tool_calls=[])
        return dict(role='assistant',content='',tool_calls=[dict(id=e['call_id'],name=e['tool'],arguments=e['args']) for e in selected])


@pytest.mark.parametrize('correct',[True,False])
def test_actual_langchain_live_validation_with_offline_model_and_real_gtfs(session,correct,monkeypatch):
    from target.langchain_agent import LangChainAgent
    from target.langchain_model import LangChainMockModel
    from target.deepseek_runtime import Settings,DeepSeekError
    from target.v39.context import scope
    from target.v39.registry import service_scope
    from target.execution_config import scope as effective_scope
    from web.railway_defaults import prepare
    import config
    monkeypatch.setattr(config,'DB_PATH',session.root/'tickets.db')
    monkeypatch.setattr(config,'TRACE_DIR',session.trace_dir)
    monkeypatch.setattr(config,'USE_HTTP_MOCK',False)
    session.root.mkdir(parents=True,exist_ok=True)
    (session.root/'.ticket-agent-sandbox.json').write_text(json.dumps(dict(purpose='ticket-agent-fault-test',version=1,simulated_only=True)),encoding='utf8')
    service,ctx,effective=prepare(session);provider=CorrectionModel(correct)
    with scope(ctx),service_scope(service),effective_scope(effective):
        agent=LangChainAgent('离线确定性测试',model=LangChainMockModel(decision_provider=provider),effective_config=effective)
        # Exercise the production Live reply-validation branch without a Live client.
        agent.deepseek_settings=Settings(profile='full_sandbox',max_model_calls=6,turn_token_budget=32000,sandbox_root=session.root)
        if not correct:
            with pytest.raises(DeepSeekError,match='tool_execution_failed'):agent.chat(session.sid,'查询模拟余票',save_trace=False)
            return
        result=agent.chat(session.sid,'查询模拟余票',save_trace=False)
    assert '8张' in result['reply'] and '尚未锁座' in result['reply']
    calls=[c for s in result['steps'] for c in s['calls']]
    assert calls[0]['ok'] is False and calls[-1]['ok'] is True
    assert len(result)==10 and provider.calls==4
    assert any(e.get('event')=='railway_read_recovered' for e in agent.last_events)
    assert agent.last_audit_report['error'] is None
    import sqlite3
    with sqlite3.connect(service.store.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        for table in ('v39_orders','v39_quotes','v39_proposals','v39_transactions'):
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
