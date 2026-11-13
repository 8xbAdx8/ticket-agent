from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest

from target.consistency_audit import audit_conversation
from target.scenario_abc_budget import AUTHORIZATION, IntegrationBatch
from target.scenario_workbench import Workbench, load_run_results
from test_scenario_workbench import FixtureModel, candidate, source_session
from web.order_state_evidence import agent_declarations, explicit_declarations, rendered


ORDER = 'V39-' + 'a'*32
FOREIGN = 'V39-' + 'b'*32


def authorized_batch(tmp_path):
    (tmp_path/'authorization.json').write_text(json.dumps(AUTHORIZATION), encoding='utf8')
    batch = IntegrationBatch(tmp_path)
    batch.initialize_authorized()
    return batch


def test_budget_hard_limits_and_unknown_usage_are_independent(tmp_path):
    batch = authorized_batch(tmp_path)
    identity = uuid4().hex
    with batch.scope(identity, 'deepseek', 'agent', scenario_id='case-001', execution_id='execution'):
        with pytest.raises(sqlite3.IntegrityError, match='ABC_OUTPUT_OR_RETRY'):
            batch.reserve(uuid4().hex, 'deepseek', {'max_tokens': 2049}, b'{}')
        with pytest.raises(sqlite3.IntegrityError, match='ABC_TOKEN_LIMIT'):
            batch.reserve(uuid4().hex, 'deepseek', {'max_tokens': 1024}, b'x'*300000)
        for _ in range(8):
            batch.reserve(uuid4().hex, 'deepseek', {'max_tokens': 2048}, b'{}')
        with pytest.raises(sqlite3.IntegrityError, match='ABC_RUN_LIMIT'):
            batch.reserve(uuid4().hex, 'deepseek', {'max_tokens': 1024}, b'{}')
    assert len(batch.ledger()) == 8
    assert batch.snapshot()['observed_tokens'] is None
    assert all(row['execution_id'] == 'execution' for row in batch.ledger())


def test_budget_counts_both_providers_and_closes_on_guard_tampering(tmp_path):
    batch = authorized_batch(tmp_path)
    for provider in ('deepseek', 'bailian'):
        for size in (8, 8, 4):
            with batch.scope(uuid4().hex, provider, 'generate'):
                for _ in range(size):
                    rid = uuid4().hex
                    batch.reserve(rid, provider, {'max_tokens': 4096}, b'{}')
                    batch.settle(rid, {'prompt_tokens': 2, 'completion_tokens': 3}, 'response_received')
        if provider == 'deepseek':
            with batch.scope(uuid4().hex, provider, 'generate'), pytest.raises(sqlite3.IntegrityError, match='ABC_PROVIDER_LIMIT'):
                batch.reserve(uuid4().hex, provider, {'max_tokens': 4096}, b'{}')
    assert batch.snapshot()['http_requests'] == 40
    assert batch.snapshot()['observed_tokens'] == 200
    with batch.scope(uuid4().hex, 'bailian', 'generate'), pytest.raises(Exception, match='acceptance_http_budget_exhausted'):
        batch.reserve(uuid4().hex, 'bailian', {'max_tokens': 4096}, b'{}')
    with closing(sqlite3.connect(batch.path)) as conn:
        conn.execute('DROP TRIGGER abc_guard')
    with pytest.raises(ValueError, match='GUARD_MISSING'):
        batch.snapshot()


def test_review_requires_human_and_current_plan_hash(tmp_path):
    session = source_session(tmp_path/'source')
    model = FixtureModel([candidate()])
    run = Workbench(session.sid)
    assert run.execute(session, model, review_required=True)['status'] == 'AWAITING_REVIEW'
    assert model.calls == ['generate']
    assert not (run.directory/'run_events.jsonl').exists()
    with pytest.raises(ValueError, match='INCOMPLETE'):
        load_run_results(run.run_id, session.sid)
    from target.scenario_workbench import _run_case
    with pytest.raises(ValueError, match='HUMAN_APPROVAL'):
        run.approve_and_execute(['case-001'], model, actor='model', runner=_run_case)
    with pytest.raises(ValueError, match='NOT_ELIGIBLE'):
        run.approve_and_execute(['case-002'], model, actor='human', runner=_run_case)
    assert run.approve_and_execute(['case-001'], model, actor='human', runner=_run_case)['status'] == 'COMPLETED'
    assert load_run_results(run.run_id, session.sid)['executed'] == 1
    assert json.loads((run.directory/'review.json').read_text(encoding='utf8'))['case_ids'] == ['case-001']


def test_review_rejects_candidate_modified_after_generation(tmp_path):
    session = source_session(tmp_path/'source')
    run = Workbench(session.sid, root=tmp_path)
    run.execute(session, FixtureModel([candidate()]), review_required=True)
    (run.directory/'review-plans.json').write_text('[]', encoding='utf8')
    with pytest.raises(ValueError, match='INPUT_CHANGED'):
        run.review_candidates()


def test_real_event_hooks_keep_agent_ui_and_database_observations_distinct(tmp_path):
    from target.followups import emit_event
    from target.run_events import capture
    receipt = dict(session_id='own', operation_id='op', order_id=ORDER, proposal_id='pid',
                   action='CREATE_ORDER', approved=True, database_verified=True, source_run_id='proposal',
                   finished_at='2000-01-01T00:00:00+00:00',
                   after=dict(order_id=ORDER, order_status='PENDING_PAYMENT'),
                   actual_result=dict(order_id=ORDER, status='PENDING_PAYMENT'))
    history = [dict(session_id='own', user_msg='提案轮', reply='确认请求', steps=[]),
               dict(session_id='own', user_msg='状态轮', reply=f'订单 {ORDER} 当前状态：PAID', steps=[])]
    session = SimpleNamespace(sid='own', mode='user', engine='legacy', live=False,
                              trace_dir=tmp_path, read_only=False, business_receipts=[receipt], history=history,
                              audits=[dict(trace_id=rid, public_trace=record)
                                      for rid, record in zip(('proposal', 'report'), history)])
    log = tmp_path/'run_events.jsonl'
    emit_event(log, 'op', 'own', 'business_operation_completed', business_receipt=receipt)
    with capture(log) as state:
        state.update(run_id='report', session_id='own')
        agent_declarations(session, dict(session_id='own', reply=f'订单 {ORDER} 当前状态：PAID'))
        agent_declarations(session, dict(session_id='own', reply=f'订单 {FOREIGN} 当前状态：PAID'))
        agent_declarations(session, dict(session_id='own', reply=f'订单 {ORDER} 可以是 PAID'))
    def audit():
        from target.scenario_workbench_evidence import snapshot_conversation
        return audit_conversation(snapshot_conversation(session))[0]
    before_ui = audit()
    assert before_ui['status'] == 'failed' and before_ui['missing_layers'] == ['UI']
    assert len(before_ui['layers']['Agent']) == 1
    rendered(session, f'订单 {ORDER} 当前已提交状态：PENDING_PAYMENT；模拟支付 PENDING。', ORDER, 'report')
    after_ui = audit()
    assert after_ui['status'] == 'failed' and not after_ui['missing_layers']
    assert after_ui['layers']['UI'][0]['status'] == 'PENDING_PAYMENT'
    assert explicit_declarations(f'若订单 {ORDER} 当前状态：PAID') == {}
    assert explicit_declarations(f'格式示例：\n```text\n订单 {ORDER} 当前状态：PAID\n```') == {}


def test_workbench_has_all_new_and_historical_routes(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    monkeypatch.setenv('TICKET_WEB_OFFLINE_ONLY', '1')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'web/app.py')).run()
    app.radio(key='workspace_mode').set_value('测试工作台').run()
    expected = ('AI 场景总测试', '质量分析', 'RAG / 多轮 / 安全', '边界与异常测试', '性能测试')
    assert tuple(app.radio(key='workspace_page').options) == expected
    for page in expected:
        app.radio(key='workspace_page').set_value(page).run()
        assert not app.exception
    assert 'Trace 分析' not in app.radio(key='workspace_page').options
