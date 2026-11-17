"""V3.11 independent oracle and original-Agent integration. No real API requests."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import copy
import json
import uuid
import os
import hashlib
import pytest
import httpx
from target.scenario_live_budget import LiveBatch,ROOT
from target.scenario_business_oracle import p01,invariants,receipt_proof


def batch():
    root=ROOT/'artifacts/runtime'/('v310-v311-test-'+uuid.uuid4().hex)
    root.mkdir()
    (root/'authorization.json').write_text(json.dumps(dict(approved=True,http_limit=50,pilot_http_limit=24,provider_limits=dict(deepseek=25,bailian=25))))
    (root/'test-source.json').write_text(json.dumps(dict(test=os.getenv('PYTEST_CURRENT_TEST'),test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())),encoding='utf8')
    b=LiveBatch(root);b.initialize_authorized();return b


@pytest.fixture
def sdk_env(monkeypatch):
    values=dict(TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='0',DEEPSEEK_API_KEY='v311-sdk-test-key',
                DASHSCOPE_API_KEY='v311-sdk-test-key',DEEPSEEK_MODEL='deepseek-flash',DASHSCOPE_MODEL='qwen3.8-flash',
                DEEPSEEK_BASE_URL='https://api.deepseek.com',DASHSCOPE_BASE_URL='https://cn-beijing.maas.qwencloudapi.com/compatible-mode/v1')
    for k,v in values.items():monkeypatch.setenv(k,v)


class ScriptedSDK:
    """Explicit SDK substitute. Uses real ToolMessages, never calls Registry itself."""
    def __init__(self):self.queue=[];self.names={};self.world={};self.calls=[]
    def tool(self,name,args):self.queue.append((name,args));return self
    def answer(self,text='已读取本地模拟业务结果，请核对确认卡。'):self.queue.append((None,text));return self
    def handle(self,request):
        body=json.loads(request.content);self.calls.append(body)
        for message in body['messages']:
            if message.get('role')=='tool' and message.get('tool_call_id') in self.names:
                payload=json.loads(message['content'])
                if not isinstance(payload,dict) or not payload.get('history_summary'):
                    self.world[self.names[message['tool_call_id']]]=payload
        assert self.queue,'unexpected extra model request'
        name,args=self.queue.pop(0)
        if name:
            args=args(self.world) if callable(args) else args;identity='call-'+uuid.uuid4().hex
            self.names[identity]=name
            message=dict(role='assistant',content=None,tool_calls=[dict(id=identity,type='function',function=dict(name=name,arguments=json.dumps(args,ensure_ascii=False)))])
        else:message=dict(role='assistant',content=args)
        return httpx.Response(200,json=dict(id='sdk-'+uuid.uuid4().hex,object='chat.completion',model=body['model'],choices=[dict(index=0,message=message,finish_reason='tool_calls' if name else 'stop')],usage=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15)),headers={'x-request-id':'sdk-substitute'})


def send(run,script,message,**kwargs):
    # Objective expected tools frozen from the scripted SDK scenario BEFORE send.
    # This helper never inspects actual output to decide what should have happened.
    tools=[name for name,args in script.queue if name]
    spec={'required_tools':tools} if tools else {'reply_contains':[script.queue[-1][1]]} if script.queue else {'replay':True}
    return run.turn(message,expectations=spec,**kwargs)


ROUTE=dict(service_date='2026-11-05',origin_stop_id='AOH',destination_stop_id='HGH')
def selection(w,index=0):return dict(ROUTE,trip_id=w['railway_query_trips']['data'][index]['trip_id'],seat_class='SECOND')


def setup_run(provider='deepseek',scenario='default'):
    from target.scenario_live_agent import AgentRun
    b=batch();script=ScriptedSDK();run=AgentRun(b.root,provider,transport=httpx.MockTransport(script.handle),scenario=scenario)
    return run,script


def create(run,s):
    s.tool('railway_search_stations',dict(name='上海虹桥')).tool('railway_query_trips',dict(ROUTE,limit=3)).tool('railway_trip_stops',lambda w:dict(trip_id=w['railway_query_trips']['data'][0]['trip_id'],service_date=ROUTE['service_date'])).answer()
    assert send(run,s,'查询2026-11-05上海虹桥到杭州东，并查看第一班经停')['passed']
    s.tool('railway_check_inventory',lambda w:dict(selection(w),quantity=3)).tool('railway_quote_fare',lambda w:dict(selection(w),passenger_count=3)).tool('railway_create_order',lambda w:dict(quote_id=w['railway_quote_fare']['quote']['quote_id'],passengers=['合成甲','合成乙','合成丙'],contact=run.context.owner_phone)).answer('已生成建单提案，等待你确认。')
    assert send(run,s,'为三位合成乘客报价并生成建单提案，先不要实际建单')['passed']
    assert not run.read()['tables']['orders']
    preview=run.decision_preview(run.pending()[0]['proposal_id']);row=run.confirm(preview,True,actor='test_user')
    assert row['passed'],row
    return row['result']['order_id'],preview


def pay(run,s,oid):
    total=run.read()['tables']['orders'][0]['total_fen']
    s.tool('railway_pay_order',dict(order_id=oid,expected_total_fen=total)).answer('已生成支付确认卡，尚未支付。')
    assert send(run,s,'为此订单生成模拟支付确认卡')['passed']
    return run.confirm(run.decision_preview(run.pending()[0]['proposal_id']),True,actor='test_user')


@pytest.mark.parametrize('hours,expected',[(48.01,5),(48,10),(24,10),(23.99,20)])
def test_independent_p01_boundaries(hours,expected):
    now=datetime(2026,11,1,tzinfo=timezone.utc)
    assert p01(100,(now+timedelta(hours=hours)).isoformat(),now.isoformat())['fee_fen']==expected


def test_half_up_and_expired_p01():
    assert p01(10,'2026-11-05T00:00:00+00:00','2026-11-01T00:00:00+00:00')['fee_fen']==1
    with pytest.raises(ValueError):p01(100,'2026-11-01T00:00:00+00:00','2026-11-02T00:00:00+00:00')


def test_pilot_and_provider_limits_persist_across_reopen():
    b=batch();body=dict(max_tokens=32,tools=[]);raw=b'{}'
    for i in range(12):b.reserve(str(i),'deepseek',body,raw)
    with pytest.raises(Exception,match='V311_PROVIDER_LIMIT'):b.reserve('blocked','deepseek',body,raw)
    assert LiveBatch(b.root).status()['http_requests']==12
    for i in range(12):b.reserve('q'+str(i),'bailian',body,raw)
    with pytest.raises(Exception,match='V311_PHASE_HTTP_LIMIT'):b.reserve('blocked2','bailian',body,raw)
    assert b.status()['http_requests']==24
    b.release_remaining(dict(pilot_reviewed=True,evidence='test-only no HTTP'))
    for i in range(12,25):b.reserve(str(i),'deepseek',body,raw)
    with pytest.raises(Exception,match='V311_PROVIDER_LIMIT'):b.reserve('blocked3','deepseek',body,raw)


@pytest.mark.parametrize('provider',['deepseek','bailian'])
def test_original_agent_create_pay_and_exact_receipt(provider,sdk_env):
    run,s=setup_run(provider);oid,preview=create(run,s);row=pay(run,s,oid)
    assert row['passed'],row
    view=run.read();assert view['tables']['orders'][0]['order_status']=='PAID'
    assert run.mode=='sdk_stub_agent' and len(view['tables']['transactions'])==1
    assert any(r['kind']=='agent_turn' and r['executed_tools'] for r in run.rows)
    tampered=copy.deepcopy(row['result']);tampered['status']='PENDING_PAYMENT'
    assert not receipt_proof(view,row['proposal']['proposal_id'],tampered)
    assert all(c['passed'] for c in invariants(view))
    before=run.read()['state_sha256'];replayed=run.confirm(preview,True,actor='test_user')
    assert replayed['passed'] and run.read()['state_sha256']==before


def test_oracle_rejects_fake_paid_and_money_drift(sdk_env):
    run,s=setup_run();oid,_=create(run,s);row=pay(run,s,oid);view=run.read()
    bad=copy.deepcopy(view);bad['tables']['transactions']=[]
    assert any(not c['passed'] for c in invariants(bad))
    bad=copy.deepcopy(view);bad['tables']['orders'][0]['net_paid_fen']+=1
    assert any(not c['passed'] for c in invariants(bad))
    with pytest.raises(ValueError,match='ORACLE_TEST_DATABASE_ONLY'):
        from target.scenario_business_oracle import snapshot
        snapshot(ROOT/'data/v39/simulation-v391.sqlite')


def test_reject_confirmation_has_no_order_or_hold(sdk_env):
    run,s=setup_run();s.tool('railway_query_trips',dict(ROUTE,limit=3)).answer()
    assert send(run,s,'查询静态车次')['passed']
    s.tool('railway_quote_fare',lambda w:dict(selection(w),passenger_count=1)).tool('railway_create_order',lambda w:dict(quote_id=w['railway_quote_fare']['quote']['quote_id'],passengers=['合成甲'],contact=run.context.owner_phone)).answer('等待你确认。')
    assert send(run,s,'生成一人建单确认卡')['passed']
    preview=run.decision_preview(run.pending()[0]['proposal_id'])
    with pytest.raises(ValueError):run.confirm(preview,True,actor='model')
    row=run.confirm(preview,False,actor='test_user')
    assert row['passed'] and not run.read()['tables']['orders'] and not run.read()['tables']['holds']


def get_order(run,s,oid):
    s.tool('railway_get_order',dict(order_id=oid)).answer()
    row=send(run,s,'读取我的订单实际状态和乘客明细')
    assert row['passed'],row
    return s.world['railway_get_order']


def refund(run,s,oid,item_ids=None,expected='SUCCEEDED'):
    args=dict(order_id=oid,scope='ITEMS' if item_ids else 'FULL')
    if item_ids:args['item_ids']=item_ids
    s.tool('railway_refund_order',args).answer('退款提案待确认，尚未退款。')
    assert send(run,s,'为选中乘客生成退款确认卡')['passed']
    return run.confirm(run.decision_preview(run.pending()[0]['proposal_id']),True,actor='test_user',expected_outcome=expected)


def test_agent_three_passenger_refund_change_remaining_to_cancelled(sdk_env):
    run,s=setup_run();oid,_=create(run,s);assert pay(run,s,oid)['passed']
    run.batch.release_remaining(dict(pilot_reviewed=True,evidence='SDK-only baseline verified'))
    order=get_order(run,s,oid);first=order['items'][0]
    departure=run.service.static.interval(order['trip_id'],order['service_date'],order['origin_stop_id'],order['destination_stop_id'])['origin']['departure_at']
    expected=p01(first['fare_fen'],departure,run.service.stamp())
    row=refund(run,s,oid,[first['item_id']]);assert row['passed'],row
    assert row['result']['fee_fen']==expected['fee_fen'] and row['result']['refund_fen']==expected['net_fen']
    assert row['after']['tables']['orders'][0]['order_status']=='PAID'
    s.tool('railway_quote_fare',lambda w:dict(selection(w,1),passenger_count=2)).answer()
    assert send(run,s,'给剩余两位乘客查询另一班车的模拟报价')['passed']
    quote=s.world['railway_quote_fare']['quote'];target=selection(s.world,1)
    s.tool('railway_change_order',dict(order_id=oid,target_quote_id=quote['quote_id'],**{'target_'+k:v for k,v in target.items()})).answer('改签确认卡已生成，尚未改签。')
    assert send(run,s,'为剩余两人生成改签确认卡')['passed']
    row=run.confirm(run.decision_preview(run.pending()[0]['proposal_id']),True,actor='test_user');assert row['passed'],row
    state=run.read()['tables'];assert len(state['orders'])==1 and state['orders'][0]['order_status']=='CHANGED'
    assert next(i for i in state['order_items'] if i['item_id']==first['item_id'])['item_status']=='REFUNDED'
    active=[i for i in state['order_items'] if i['item_status']=='ACTIVE']
    assert refund(run,s,oid,[active[0]['item_id']])['passed']
    assert run.read()['tables']['orders'][0]['order_status']=='CHANGED'
    assert refund(run,s,oid)['passed']
    state=run.read()['tables'];assert state['orders'][0]['order_status']=='CANCELLED'
    assert not any(i['held'] or i['sold'] for i in state['inventory_segments'])
    assert all(c['passed'] for c in invariants(run.read()))


def test_agent_cancel_and_clock_expire_preserve_orders(sdk_env):
    run,s=setup_run();oid,_=create(run,s)
    s.tool('railway_cancel_order',dict(order_id=oid)).answer('取消提案待确认。')
    assert send(run,s,'取消这笔未支付模拟订单')['passed']
    assert run.confirm(run.decision_preview(run.pending()[0]['proposal_id']),True,actor='test_user')['passed']
    assert run.read()['tables']['orders'][0]['order_status']=='CANCELLED'
    other,s=setup_run();oid,_=create(other,s)
    row=other.advance(901)
    assert row['passed'] and row['after']['tables']['orders'][0]['order_status']=='EXPIRED'
    assert len(row['after']['tables']['orders'])==1


def test_failed_payment_keeps_failed_transaction_and_releases_inventory(sdk_env):
    run,s=setup_run(scenario='payment_fail');oid,_=create(run,s)
    total=run.read()['tables']['orders'][0]['total_fen']
    s.tool('railway_pay_order',dict(order_id=oid,expected_total_fen=total)).answer('支付仍待确认。')
    assert send(run,s,'生成模拟支付提案')['passed']
    row=run.confirm(run.decision_preview(run.pending()[0]['proposal_id']),True,actor='test_user',expected_outcome='FAILED')
    assert row['passed'],row
    assert row['business_outcome']=='FAILED' and row['after']['tables']['transactions'][0]['status']=='FAILED'
    assert row['after']['tables']['orders'][0]['order_status']=='PAYMENT_FAILED'
    assert not any(x['held'] or x['sold'] for x in row['after']['tables']['inventory_segments'])


def test_database_failure_rolls_back_and_fault_is_observed(sdk_env):
    from target.scenario_faults import inject
    run,s=setup_run();s.tool('railway_query_trips',dict(ROUTE,limit=3)).answer()
    assert send(run,s,'查询静态车次')['passed']
    s.tool('railway_quote_fare',lambda w:dict(selection(w),passenger_count=1)).tool('railway_create_order',lambda w:dict(quote_id=w['railway_quote_fare']['quote']['quote_id'],passengers=['合成甲'],contact=run.context.owner_phone)).answer('等待你确认。')
    assert send(run,s,'生成建单提案')['passed'];preview=run.decision_preview(run.pending()[0]['proposal_id'])
    with inject(run,'database_failure') as events:row=run.confirm(preview,True,actor='test_user')
    assert events and not row['passed']
    assert not run.read()['tables']['orders'] and not run.read()['tables']['holds'] and not run.read()['tables']['transactions']
    run.reconcile(run.read()['state_sha256'],actor='test_user')
    # Original page receipts intentionally retain a failed confirmation. Do not
    # retry it in place: expire the old proposal, then obtain a NEW proposal.
    assert run.advance(301)['passed']
    s.tool('railway_quote_fare',lambda w:dict(selection(w),passenger_count=1)).tool('railway_create_order',lambda w:dict(quote_id=w['railway_quote_fare']['quote']['quote_id'],passengers=['合成甲'],contact=run.context.owner_phone)).answer('新提案等待确认。')
    assert send(run,s,'重新报价并生成新的建单提案，旧失败记录保留')['passed']
    fresh=run.decision_preview(run.pending()[0]['proposal_id'])
    assert fresh['proposal_id']!=preview['proposal_id']
    assert run.confirm(fresh,True,actor='test_user')['passed']


def test_failed_refund_new_proposal_succeeds_old_failure_survives(sdk_env):
    from target.scenario_faults import inject
    run,s=setup_run();oid,_=create(run,s);assert pay(run,s,oid)['passed']
    run.batch.release_remaining(dict(pilot_reviewed=True,evidence='SDK-only baseline'))
    before=run.read()
    with inject(run,'partial_business_failure') as events:
        row=refund(run,s,oid,expected='FAILED')
    assert row['passed'] and events
    assert row['after']['tables']['orders'][0]['net_paid_fen']==before['tables']['orders'][0]['net_paid_fen']
    assert row['after']['tables']['orders'][0]['order_status']=='PAID'
    assert refund(run,s,oid)['passed']
    state=run.read()['tables'];assert {r['status'] for r in state['refund_requests']}=={'FAILED','SUCCEEDED'}
    assert state['orders'][0]['order_status']=='CANCELLED'


@pytest.mark.parametrize('kind',['model_timeout','model_malformed','tool_timeout','tool_error'])
def test_fault_failure_then_safe_readback(kind,sdk_env):
    from target.scenario_faults import inject
    run,s=setup_run();s.tool('railway_query_trips',dict(ROUTE,limit=3)).answer()
    assert send(run,s,'查询车次')['passed']
    if kind.startswith('tool'):
        s.tool('railway_check_inventory',lambda w:dict(selection(w),quantity=1)).answer('操作未成功。')
    with inject(run,kind) as events:row=send(run,s,'查询模拟库存')
    assert events and not row['passed']
    assert not run.read()['tables']['orders']
    s.queue=[];s.tool('railway_query_trips',dict(ROUTE,limit=3)).answer()
    assert send(run,s,'重新进行只读查询，核对实际状态')['passed']
    assert not run.read()['tables']['orders']


def test_duplicate_request_does_not_reexecute_and_disconnect_is_readonly(sdk_env):
    from target.scenario_faults import inject
    run,s=setup_run();s.tool('railway_query_trips',dict(ROUTE,limit=3)).answer()
    first=send(run,s,'查询车次',request_id='stable-user-request');count=len(s.calls)
    with inject(run,'duplicate_request'):
        second=send(run,s,'查询车次',request_id='stable-user-request')
    assert second['passed'] and second['request_replayed'] and not second['model_called'] and not second['executed_tools']
    assert len(s.calls)==count
    with inject(run,'mid_disconnect'):
        from web.session_store import restore_session
        restored=restore_session(run.session.root,expected_sid=run.session.sid)
        assert restored.read_only
        with pytest.raises(ValueError,match='只读'):restored.send('支付','must-not-dispatch')
    assert run.read()['state_sha256']==first['after']['state_sha256']


def test_original_false_success_is_detected_even_if_public_guard_rewrites(sdk_env):
    run,s=setup_run();s.answer('已支付成功。')
    row=send(run,s,'查询我的模拟订单状态')
    assert not row['passed'] and row['reply_assessment']['status']=='FAIL'
    assert row['original_model_reply']=='已支付成功。'
    assert not row['after']['tables']['orders']


def test_budget_missing_guard_and_illegal_phase_fail_closed():
    import sqlite3
    b=batch()
    with sqlite3.connect(b.path) as c:c.execute('DROP TRIGGER v311_admission')
    with pytest.raises(ValueError,match='GUARD_INVALID'):b.reserve('x','deepseek',dict(max_tokens=8),b'{}')
    with pytest.raises(ValueError,match='GUARD_INVALID'):b.initialize_authorized()
    b=batch()
    with sqlite3.connect(b.path) as c:c.execute('UPDATE v311_limits SET provider_limit=25')
    with pytest.raises(ValueError,match='GUARD_INVALID'):b.status()


def test_budget_release_audit_survives_export_error():
    import sqlite3
    b=batch();(b.root/'pilot-release.json').mkdir()
    receipt=b.release_remaining(dict(pilot_reviewed=True,evidence='test-only'))
    assert receipt['export']=='NOT_WRITTEN'
    with sqlite3.connect(b.path) as c:
        assert c.execute('SELECT count(*) FROM v311_release_audit').fetchone()[0]==1
    assert b.status()['phase']['http_limit']==50


def test_no_task_assertions_not_scored_and_stale_audit_not_reused(sdk_env):
    from unittest.mock import patch
    run,s=setup_run();s.answer('请稍等。')
    first=run.turn('查票')
    assert first['task_status']=='NOT_SCORED' and not first['passed']
    with patch.object(run.session,'send',side_effect=ValueError('before audit')):
        row=run.turn('查票',expectations={'required_tools':['railway_query_trips']})
    assert not row['passed'] and not row['events'] and row['trace_id'] is None
    s.answer('请稍等。')
    row=run.turn('查票',expectations={'required_tools':['railway_query_trips']})
    assert row['task_status']=='FAIL' and not row['passed']


def test_oracle_rejects_ghost_sold_even_when_event_balanced(sdk_env):
    run,s=setup_run();oid,_=create(run,s);assert pay(run,s,oid)['passed']
    run.batch.release_remaining(dict(pilot_reviewed=True,evidence='SDK-only'))
    assert refund(run,s,oid)['passed']
    bad=copy.deepcopy(run.read());inv=bad['tables']['inventory_segments'][0];inv['sold']=1
    event=next(e for e in bad['tables']['inventory_events'] if all(e[k]==inv[k] for k in ('scenario_id','dataset_version','trip_id','service_date','seat_class','segment_index')))
    event['delta_sold']+=1
    checks=invariants(bad)
    assert all(c['passed'] for c in checks if c['rule']=='inventory_event_balance')
    assert any(not c['passed'] for c in checks if c['rule']=='inventory_owned_balance')


def test_oracle_rejects_failure_receipt_with_successful_refund_and_wrong_p01(sdk_env):
    run,s=setup_run();oid,_=create(run,s);assert pay(run,s,oid)['passed']
    run.batch.release_remaining(dict(pilot_reviewed=True,evidence='SDK-only'))
    before=run.read();row=refund(run,s,oid);assert row['passed']
    bad=copy.deepcopy(row['after']);result=dict(row['result'],error='SIMULATED_REFUND_FAILURE')
    p=row['proposal'];idem=next(r for r in bad['tables']['idempotency'] if p['proposal_id'] in r['key'])
    idem['status']='FAILED';idem['response_json']=json.dumps(result)
    assert not receipt_proof(bad,p['proposal_id'],result,before=before)
    bad=copy.deepcopy(row['after']);bad['tables']['refund_items'][0]['fee_fen']=0
    assert any(not c['passed'] for c in invariants(bad) if c['rule']=='refund_frozen_price_p01')


@pytest.mark.parametrize('text,expected',[('没有其他问题，已支付成功。','FAIL'),('尚未支付成功。','N/A'),('没有支付成功。','N/A'),('订单已经创建，付款成功。','FAIL')])
def test_positive_claim_negation_is_local(text,expected):
    from target.scenario_business_oracle import reply_claims,TABLES
    empty=dict(tables={t:[] for t in TABLES})
    assert reply_claims(text,empty)['status']==expected


def test_expected_arguments_must_match_the_same_successful_tool_call():
    from target.scenario_live_agent import AgentRun
    events=[dict(tool='railway_query_trips',ok=False,args=dict(service_date='2026-11-05')),dict(tool='railway_query_trips',ok=True,args=dict(service_date='2026-11-06'))]
    checks=AgentRun.task_checks(dict(required_tools=['railway_query_trips'],args=dict(railway_query_trips=dict(service_date='2026-11-05'))),events,'',{}, {},False)
    assert checks and not any(c['passed'] for c in checks)


def test_invalid_task_spec_rejected_before_http(sdk_env):
    run,s=setup_run();s.answer('请稍等')
    with pytest.raises(ValueError,match='INVALID_TASK_EXPECTATIONS'):run.turn('查票',expectations={'arbitrary_sql':'SELECT 1'})
    assert not s.calls and run.batch.status()['http_requests']==0


def test_failed_refund_requires_items_and_failed_transaction(sdk_env):
    from target.scenario_faults import inject
    run,s=setup_run();oid,_=create(run,s);assert pay(run,s,oid)['passed']
    run.batch.release_remaining(dict(pilot_reviewed=True,evidence='SDK-only'))
    with inject(run,'partial_business_failure'):row=refund(run,s,oid,expected='FAILED')
    assert row['passed']
    for table in ('refund_items','transactions'):
        bad=copy.deepcopy(row['after']);bad['tables'][table]=[]
        assert not receipt_proof(bad,row['proposal']['proposal_id'],row['result'],before=row['before'])


def test_hold_cannot_own_a_different_trip(sdk_env):
    run,s=setup_run();create(run,s)
    bad=copy.deepcopy(run.read());bad['tables']['holds'][0]['trip_id']='other-trip'
    assert any(not c['passed'] for c in invariants(bad) if c['rule']=='hold_quote_identity')


def test_decline_proof_rejects_hidden_business_side_effects():
    from target.scenario_business_oracle import decline_proof,TABLES
    before=dict(tables={t:[] for t in TABLES});before['tables']['proposals']=[dict(proposal_id='p',state='PENDING',session_id='s')]
    after=copy.deepcopy(before);after['tables']['proposals'][0]['state']='CANCELLED'
    assert decline_proof(before,after,'p')
    for table in ('orders','holds','transactions','refund_items','inventory_events'):
        bad=copy.deepcopy(after);bad['tables'][table].append(dict(fake_side_effect=True))
        assert not decline_proof(before,bad,'p')


@pytest.mark.parametrize('text,paid,expected',[('已支付 0 分',0,'PASS'),('已支付 0 分',100,'FAIL'),('已支付 1.00 元',100,'PASS'),('已支付 1.00 元',0,'FAIL'),('会明确提示“已支付、本次未重复扣款”',0,'N/A'),('系统提示“已支付成功”',0,'FAIL')])
def test_paid_amount_and_future_message_are_not_completed_payment(text,paid,expected):
    from target.scenario_business_oracle import reply_claims,TABLES
    view=dict(tables={t:[] for t in TABLES})
    view['tables']['orders']=[dict(order_id='example',paid_total_fen=paid)]
    if paid:view['tables']['transactions']=[dict(order_id='example',status='SUCCEEDED',direction='DEBIT',amount_fen=paid)]
    assert reply_claims(text,view)['status']==expected


def test_future_quote_does_not_hide_current_success_or_ledger_drift():
    from target.scenario_business_oracle import reply_claims,TABLES
    view=dict(tables={t:[] for t in TABLES});view['tables']['orders']=[dict(order_id='one',paid_total_fen=0)]
    assert reply_claims('会提示“已支付”，但现在已支付成功。',view)['status']=='FAIL'
    assert reply_claims('已支付1分',view)['status']=='FAIL'
    view['tables']['orders'][0]['paid_total_fen']=9000
    assert reply_claims('已支付9000分',view)['status']=='FAIL'
    view['tables']['transactions']=[dict(order_id='one',status='SUCCEEDED',direction='DEBIT',amount_fen=9000)]
    assert reply_claims('已支付9000分',view)['status']=='PASS'
    assert reply_claims('已支付0分',view)['status']=='FAIL'
    view['tables']['orders'].append(dict(order_id='two',paid_total_fen=9000))
    assert reply_claims('已支付9000分',view)['status']=='FAIL'


from target.v39.registry import TOOLS as RAILWAY_TOOLS
INVALID_SCENARIOS=[]
for definition in RAILWAY_TOOLS:
    f=definition['function'];schema=f['parameters'];props=schema['properties']
    if schema['required']:INVALID_SCENARIOS.append((f['name'],'missing_required',{}))
    field=next(iter(props))
    INVALID_SCENARIOS.append((f['name'],'wrong_type',{field:17}))
    INVALID_SCENARIOS.append((f['name'],'unknown_parameter',{'not_a_registered_field':True}))


@pytest.mark.parametrize('name,variant,args',INVALID_SCENARIOS,ids=[name+'-'+variant for name,variant,args in INVALID_SCENARIOS])
def test_agent_rejects_invalid_tool_arguments_without_transactions(name,variant,args,sdk_env):
    run,s=setup_run();s.tool(name,args).answer('输入不完整或参数无效，操作没有完成。')
    row=run.turn('检查此工具参数；没有确认时不能产生任何交易',expectations=dict(required_tools=[name],unchanged=['orders','order_items','holds','transactions']))
    assert not row['passed']
    assert len(s.calls)>=1
    assert row['before']['tables']['orders']==row['after']['tables']['orders']==[]
    assert not row['after']['tables']['transactions'] and not row['after']['tables']['holds']
    assert not any(e.get('ok') is True for e in row['executed_tools'])


def test_declined_proposal_cannot_later_execute(sdk_env):
    run,s=setup_run();s.tool('railway_query_trips',dict(ROUTE,limit=3)).answer()
    assert send(run,s,'查询静态车次')['passed']
    s.tool('railway_quote_fare',lambda w:dict(selection(w),passenger_count=1)).tool('railway_create_order',lambda w:dict(quote_id=w['railway_quote_fare']['quote']['quote_id'],passengers=['合成甲'],contact=run.context.owner_phone)).answer('待确认')
    assert send(run,s,'生成模拟建单提案')['passed']
    preview=run.decision_preview(run.pending()[0]['proposal_id'])
    assert run.confirm(preview,False,actor='test_user')['passed']
    with pytest.raises(ValueError,match='CURRENT_OWNED_PROPOSAL_REQUIRED'):run.confirm(preview,True,actor='test_user')
    assert not run.read()['tables']['orders']


def test_coverage_original_failures_do_not_disappear_after_reassessment():
    from target.scenario_agent_coverage import coverage
    rows=[dict(kind='agent_turn',passed=False,task_status='PASS',invariant_status='FAIL',error=None),dict(kind='agent_turn',passed=False,task_status='PASS',invariant_status='PASS',error='observed_token_budget_exhausted'),dict(kind='agent_turn',passed=False,task_status='NOT_SCORED',invariant_status='PASS',error=None)]
    report=coverage([dict(mode='live_agent',rows=rows)],'live_agent')
    assert report['tasks']==dict(total=3,pass_count=0,failed=2,not_scored=1)
