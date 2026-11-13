import copy
import json
from pathlib import Path

import pytest

from target.scenario_generation_contract import generation_issues
from target.scenario_generator import review
from target.scenario_plans import candidate, plans
from target.scenario_r2_business import BusinessRun
from target.scenario_r2_live import R2Model, example
from target.scenario_workbench import Workbench, _candidate, _generator_prompt
from target.scenario_workbench_evidence import snapshot_conversation
from test_scenario_workbench import FixtureModel, source_session


ROOT = Path(__file__).resolve().parents[1]
RESPONSES = ROOT/'tests/fixtures/v311_r2_qa09'


@pytest.mark.parametrize('provider', ['deepseek', 'bailian'])
def test_provider_prompt_example_is_complete_and_quality_passes(tmp_path, provider):
    snapshot = snapshot_conversation(source_session(tmp_path/'source'))
    model = R2Model.__new__(R2Model)
    model.provider = provider
    system, user = model.prepare_prompt(*_generator_prompt(snapshot), 'generate')
    raw = json.loads(system.split('完整合法示例：', 1)[1])['scenarios'][0]
    assert raw == example(provider) and not generation_issues(raw)
    row, plan = _candidate(raw, 1, 'run', snapshot, dict(generation_model=provider, prompt_sha256='hash'), [])
    assert row['validated'] and plan['integration_steps'] == raw['integration_steps']
    assert json.loads(user)['tool_schema']['required']
    assert json.loads(user)['required_attribution'] == {key: raw[key] for key in ('dimension','source_turn_ids','covered_nodes')}
    assert '任何一个缺失都会拒绝' in system
    assert model.provider_for('judge') != provider
    assert model.provider_for('agent') == provider


@pytest.mark.parametrize('mutation,code', [
    (lambda item: item['integration_steps'][0].pop('message'), 'MESSAGE_INVALID:0'),
    (lambda item: item['integration_steps'][0].pop('checks'), 'CHECKS_REQUIRED:0'),
    (lambda item: item['integration_steps'][0].update(checks=[]), 'CHECKS_REQUIRED:0'),
    (lambda item: item['integration_steps'][0].update(checks={}), 'CHECKS_REQUIRED:0'),
    (lambda item: item.pop('turns'), 'TURNS_NONEMPTY_STRING_ARRAY_REQUIRED'),
    (lambda item: item.update(turns=[{'role':'user','content':'hello'}]), 'TURNS_NONEMPTY_STRING_ARRAY_REQUIRED'),
    (lambda item: item.update(turns='hello'), 'TURNS_NONEMPTY_STRING_ARRAY_REQUIRED'),
    (lambda item: item.update(turns=[' ']), 'TURNS_NONEMPTY_STRING_ARRAY_REQUIRED'),
    (lambda item: item.update(case_id='fabricated', result='PASS', run_id='invented'), 'UNKNOWN_OR_SYSTEM_OWNED_FIELDS'),
    (lambda item: item['integration_steps'][0].update(result={'status':'PAID'}), 'STEP_FIELDS_INVALID:0'),
    (lambda item: item['integration_steps'][0].update(message=' '), 'MESSAGE_INVALID:0'),
    (lambda item: item['integration_steps'][0].update(kind='tool', tool='railway_fake', args={}), 'TOOL_STEP_INVALID:0'),
])
def test_rejects_original_structure_without_normalizing(mutation, code, tmp_path):
    item = example('deepseek')
    mutation(item)
    original = copy.deepcopy(item)
    assert code in generation_issues(item)
    snapshot = snapshot_conversation(source_session(tmp_path/'source'))
    row, plan = _candidate(item, 1, 'run', snapshot, dict(generation_model='model', prompt_sha256='sha'), [])
    assert code in row['errors'] and not row['validated'] and plan is None and item == original


def test_workbench_rejects_duplicate_plan_and_missing_runtime_result_path(tmp_path):
    snapshot = snapshot_conversation(source_session(tmp_path/'source'))
    receipt = dict(generation_model='test', prompt_sha256='sha')
    item = example('deepseek')
    _, valid = _candidate(item, 1, 'run', snapshot, receipt, [])
    duplicate, plan = _candidate(item, 2, 'run', snapshot, receipt, [valid])
    assert not duplicate['validated'] and plan is None
    item['integration_steps'][0]['checks'][0]['path'] = 'result.queries.0.not_a_field'
    invalid, plan = _candidate(item, 3, 'run', snapshot, receipt, [])
    assert not invalid['validated'] and plan is None


def test_write_step_without_trusted_confirmation_is_rejected():
    plan = next(row for row in plans() if row['title'] == 'lifecycle')
    item = candidate(plan)
    item['integration_steps'] = item['integration_steps'][:4]
    assert any(row['code'] == 'TRUSTED_CONFIRMATION_REQUIRED' for row in review(item)['diagnostics'])


@pytest.mark.parametrize('request_id,code', [
    ('5e260b8cf12f4a5b98ffd86b20d222da', 'MESSAGE_INVALID:0'),
    ('c9126f53272641e498cbd32cdfbd95c0', 'TURNS_NONEMPTY_STRING_ARRAY_REQUIRED'),
])
def test_exact_historical_responses_are_still_rejected(request_id, code):
    item = json.loads((RESPONSES/f'{request_id}.json').read_text(encoding='utf8'))['scenarios'][0]
    assert code in generation_issues(item)
    assert 'CHECKS_REQUIRED:0' in generation_issues(item)


def test_r2_first_response_missing_attribution_is_retained_and_rejected(tmp_path):
    raw = json.loads((RESPONSES/'0c91345910d7467f8849691c81665be7.json').read_text(encoding='utf8'))['scenarios'][0]
    assert generation_issues(raw) == []
    snapshot = snapshot_conversation(source_session(tmp_path/'source'))
    row, plan = _candidate(raw, 1, 'run', snapshot, dict(generation_model='deepseek', prompt_sha256='sha'), [])
    assert row['errors'] == ['DIMENSION_INVALID', 'COVERAGE_NODES_INVALID', 'SOURCE_TURNS_INVALID']
    assert not row['validated'] and plan is None


def test_r2_approval_binds_raw_model_and_records_delegation(tmp_path):
    session = source_session(tmp_path/'source')
    model = FixtureModel([example('deepseek')])
    model.source = 'r2_live_model'
    model.provider = 'deepseek'
    run = Workbench(session.sid, root=tmp_path)
    assert run.execute(session, model, review_required=True)['status'] == 'AWAITING_REVIEW'
    with pytest.raises(ValueError, match='HUMAN_APPROVAL_REQUIRED'):
        run.approve(['case-001'], model, actor='human')
    receipt = run.approve(['case-001'], model, actor='test_user', interaction='delegated_browser')
    assert receipt['interaction'] == 'delegated_browser' and receipt['inputs']['raw-candidates.json']
    assert run.manifest['status'] == 'APPROVED' and not (run.directory/'execution-started').exists()


def test_business_entry_rechecks_approval_before_creating_agent(tmp_path, monkeypatch):
    session = source_session(tmp_path/'source')
    model = FixtureModel([example('deepseek')])
    model.source = 'r2_live_model'
    model.provider = 'deepseek'
    run = Workbench(session.sid, root=tmp_path)
    assert run.execute(session, model, review_required=True)['status'] == 'AWAITING_REVIEW'

    def unexpected_agent(*args, **kwargs):
        pytest.fail('Agent was constructed before approval validation')

    monkeypatch.setattr('target.scenario_r2_business.AgentRun', unexpected_agent)
    with pytest.raises(ValueError, match='ABC_VALID_APPROVAL_REQUIRED'):
        BusinessRun(run, model, {'case_ids':['case-001'], 'actor':'test_user','run_id':run.run_id})
    receipt = run.approve(['case-001'], model, actor='test_user', interaction='delegated_browser')
    with pytest.raises(ValueError, match='R2_TRUSTED_APPROVAL_REQUIRED'):
        BusinessRun(run, model, dict(receipt, interaction='changed'))
    (run.directory/'review.json').write_text(json.dumps(dict(receipt, interaction='changed')), encoding='utf8')
    with pytest.raises(ValueError, match='ABC_VALID_APPROVAL_REQUIRED'):
        BusinessRun(run, model, receipt)
    with pytest.raises(ValueError, match='ABC_VALID_APPROVAL_REQUIRED'):
        BusinessRun.recover(run, model, receipt)


@pytest.mark.parametrize('orders,observations,expected', [
    ([], [], 'passed'),
    ([{'order_id':'written'}], [], 'indeterminate'),
    ([{'order_id':'written'}], [{'identity':{'order_id':'other'},'status':'passed'}], 'indeterminate'),
    ([{'order_id':'written'}], [{'identity':{'order_id':'written'},'status':'passed'}], 'passed'),
])
def test_r2_judge_requires_state_evidence_for_each_written_order(tmp_path, orders, observations, expected):
    model = FixtureModel([])
    model.source = 'r2_live_model'
    run = Workbench('test', root=tmp_path)
    case = dict(case_id='case-001', dimension='工具调用', objective='check', conversation=['query'])
    execution = dict(executed=True, ref='executions/case-001.json', agent_trace_refs=['trace#id'],
                     steps=[dict(kind='chat', trace_id='trace', result={'reply':'model reply'}, checks=[],
                                 state={'orders':orders}, db_metrics={})],
                     retrieval_evidence=[], tool_evidence=[], order_observations=observations)
    row, = run._judge([(case, {})], [execution], model)
    assert row['status'] == expected
    if expected == 'indeterminate':
        assert row['model_status'] == 'passed' and row['verdict_constraint'] == 'ORDER_STATE_EVIDENCE_NOT_VERIFIED'


def test_r2_judge_compacts_duplicate_payload_without_dropping_checks_or_provenance():
    payload = dict(evidence=[dict(calls=[{'content':'长'*25000}], checks=[{'path':'metrics.order_count','ok':True}])],
                   tool_events=[dict(tool='railway_query_trips', call_id='real', args={'origin_stop_id':'AOH'},
                                     result=dict(status='FOUND', data=[{'trip_id':'x'}]*900))],
                   order_observations=[{'status':'indeterminate','missing_layers':['Agent']}],
                   refs=['run_events.jsonl#event'], oracle={'state_sha256':'verified'})
    model = R2Model.__new__(R2Model)
    system, user = model.prepare_prompt('judge',json.dumps(payload,ensure_ascii=False),'judge-case-001-revision-2')
    compact = json.loads(user)
    assert len(user.encode('utf8')) < 57000
    assert compact['tool_events'][0]['result']['data_count'] == 900
    assert compact['tool_events'][0]['call_id'] == 'real'
    assert compact['evidence'][0]['checks'] == payload['evidence'][0]['checks']
    assert compact['refs'] == payload['refs'] and compact['oracle'] == payload['oracle']
    assert '四层有缺失' in system
