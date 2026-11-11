"""Regressions for V3.10 candidate review and deterministic decline evidence."""
import copy
from uuid import uuid4

import pytest

from target.scenario_generator import ROOT, Store, review
from target.scenario_plans import ROUTE, booking, candidate, check, plans, tool
from target.scenario_v310 import V310Adapter


def plan(steps):
    return dict(title='QA lifecycle', execution_adapter='v310', integration_steps=steps)


@pytest.mark.parametrize('quantity', ['1', 1.0, False])
def test_literal_still_validated_beside_a_reference(quantity):
    steps = [
        booking()[0],
        tool('railway_check_inventory', dict(ROUTE, trip_id='$trips.data.0.trip_id',
             seat_class='SECOND', quantity=quantity), 'available', [check('result.available', 1, 'ge')]),
    ]
    result = review(candidate(plan(steps)))
    assert result['quality'] == 'REJECTED'
    assert any('tool argument schema mismatch' in e for e in result['errors'])


def test_review_requires_decision_for_the_proposal_actually_created():
    steps = booking()
    steps[-1]['proposal'] = '$inventory.proposal_id'
    assert any('confirmation required for proposal' in e for e in review(candidate(plan(steps)))['errors'])


def test_reference_lifecycle_can_be_reviewed_and_executed():
    store = Store(ROOT/'artifacts/runtime'/('qa-scenario-review-'+uuid4().hex))
    case = candidate(next(p for p in plans() if p['title'] == 'lifecycle'))
    duplicate = copy.deepcopy(case)
    duplicate['case_id'] = 'AI-GEN-'+uuid4().hex
    store.save(case, 'test fixture')
    store.save(duplicate, 'test fixture')
    assert store.review_candidate(case)['quality'] == 'NEEDS_REVIEW'
    with pytest.raises(ValueError, match='quality gate'):
        store.decide([(case['case_id'], 1)], 'APPROVED', 'test reviewer')
    store.decide([(duplicate['case_id'], 1)], 'REJECTED', 'test reviewer')
    assert store.review_candidate(case)['quality'] == 'PASS'
    store.decide([(case['case_id'], 1)], 'APPROVED', 'test reviewer')
    run = store.run(case['case_id'], 2)
    assert run['status'] == 'passed'
    assert run['model_requests'] == 0
    assert run['steps'][-1]['snapshot']['db']['v39_orders'][0]['order_status'] == 'CANCELLED'


@pytest.mark.parametrize('fault', [None, 'missing_confirmation'])
def test_decline_verifies_proposal_and_never_requires_order_receipt(fault):
    steps = booking()[:-1]
    steps.append(dict(kind='confirm', proposal='$create.proposal_id', approved=False,
                      actor='test_user', checks=[check('metrics.order_count', 0), check('metrics.hold_count', 0)]))
    result = V310Adapter().run(plan(steps), fault=fault)
    last = result['steps'][-1]
    assert last['snapshot']['db']['v39_orders'] == []
    assert last['snapshot']['db']['v39_holds'] == []
    assert last['snapshot']['db']['v39_transactions'] == []
    assert last['snapshot']['db']['v39_proposals'][0]['state'] == ('CANCELLED' if fault is None else 'PENDING')
    assert {'path':'committed_decline_receipt','ok':fault is None} in last['checks']
    assert result['status'] == ('passed' if fault is None else 'failed')


@pytest.mark.parametrize('status,label', [('CANCELLED','订单已取消'),('EXPIRED','订单已过期'),('PAYMENT_FAILED','支付失败')])
def test_terminal_order_keeps_passenger_record_without_marking_it_valid(status,label):
    from target.v39.read_model import passenger_status_text, status_text
    order = dict(order_id='test-order', order_status=status, payment_status='UNPAID',
                 active_item_count=2, initial_passenger_count=3, hold_status='RELEASED')
    passenger = {'item_status':'ACTIVE'}
    assert '原订单乘客 3 人' in status_text(order)
    assert '有效乘客' not in status_text(order)
    assert passenger_status_text(order,passenger) == label
    assert passenger == {'item_status':'ACTIVE'}
    order['order_status'] = 'PAID'
    assert '有效乘客 2 人' in status_text(order)
    assert passenger_status_text(order,passenger) == '有效'
    assert passenger_status_text(order,{'item_status':'REFUNDED'}) == '已退款'


@pytest.mark.parametrize('evidence_field', ['legacy', 'langchain'])
def test_proposal_origin_binds_the_owned_executed_call(evidence_field):
    from types import SimpleNamespace
    from web.business_actions import _proposal_origin
    proposal = {'proposal_id':'P-example','action':'CREATE_ORDER'}
    result = {'status':'CONFIRMATION_REQUIRED','proposal_id':'P-example'}
    call = dict(tool='railway_create_order', call_id='executed-call', result=result, executed=True, ok=True)
    trace = dict(trace_id='run',public_trace={'session_id':'owner'})
    if evidence_field == 'legacy':
        trace['fault_report'] = {'executions':[call]}
    else:
        trace['framework_events'] = [dict(call,event='tool_end')]
    unrelated = dict(trace,trace_id='wrong-session',public_trace={'session_id':'other'})
    blocked = dict(trace,trace_id='blocked',fault_report={'executions':[dict(call,executed=False)]},framework_events=[])
    session = SimpleNamespace(sid='owner',audits=[trace,unrelated,blocked])
    assert _proposal_origin(session,proposal) == ('run','executed-call')
    assert _proposal_origin(session,dict(proposal,proposal_id='P-other')) == (None,None)


def test_trip_stop_assertion_paths_match_real_tool_shape():
    case = candidate(plans()[0])
    stop_check = case['integration_steps'][-1]['checks']
    stop_check.append(check('result.data.0.stop_id', 'AOH'))
    stop_check.append(check('result.data', 2, 'len'))
    result = review(case)
    assert result['quality'] == 'REJECTED'
    assert any('unsupported output path' in err for err in result['errors'])
    assert any('stop counts' in err for err in result['errors'])
    stop_check[-2:] = [check('result.data.stops.0.stop_id', 'AOH')]
    assert review(case)['quality'] == 'PASS'
