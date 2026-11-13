"""One explicit Judge-only continuation after the evidenced local payload refusal."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from target.api_config import bootstrap
    from target.scenario_abc_budget import R2_ROOT, IntegrationBatch
    from target.scenario_r2_live import R2Model
    from target.scenario_business_oracle import snapshot
    from target.scenario_workbench import Workbench, JUDGE_PROMPT, _judge_prompt, _allowed_judge_refs, _file_sha, _utc, _write
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf8'))
    pilot = read(R2_ROOT/'qa09-results/deepseek-revision-2.json')
    run = Workbench.reopen(pilot['run_id'], pilot['session_id'], root=R2_ROOT/'generated-cases')
    previous = run.manifest
    if (pilot['quality'] != 'PASS' or previous['status'] != 'FAILED' or previous['stages'][3]['error'] != 'BailianError'
            or previous['stages'][2]['status'] != 'COMPLETED' or (run.directory/'judgements.jsonl').stat().st_size != 0):
        raise ValueError('R2_JUDGE_RECOVERY_STATE_INVALID')
    batch = IntegrationBatch()
    own = [row for row in batch.ledger() if row['run_id'] == run.run_id]
    if len(own) != 7 or any(row['stage'] == 'judge' for row in own):
        raise ValueError('R2_JUDGE_ALREADY_DISPATCHED_OR_BUDGET_CHANGED')
    approval = read(run.directory/'review.json')
    if (approval['interaction'] != 'delegated_browser' or approval['actor'] != 'test_user'
            or approval['case_ids'] != ['case-001'] or approval['run_id'] != run.run_id
            or _file_sha(run.directory/'review.json') != previous['review_sha256']
            or any(_file_sha(run.directory/name) != value for name,value in previous['review_inputs'].items())):
        raise ValueError('R2_JUDGE_REVIEW_IDENTITY_CHANGED')
    execution_file = run.directory/'executions/case-001.json'
    execution = read(execution_file)
    dom = read(R2_ROOT/'browser/deepseek-recovery-result.json')
    if (execution['run_id'] != run.run_id or execution['execution_id'] != dom['execution_id']
            or dom['steps'][0]['database_receipt_verified'] is not True):
        raise ValueError('R2_JUDGE_EXECUTION_IDENTITY_CHANGED')
    db = R2_ROOT/'agent-executions'/execution['execution_id']/'simulation.sqlite'
    state = snapshot(db)
    if state['state_sha256'] != execution['oracle_evidence']['state_sha256']:
        raise ValueError('R2_JUDGE_ORACLE_CHANGED')
    plans = read(run.directory/'review-plans.json')
    model = R2Model('deepseek', batch=batch, revision=2)
    prior_prompt = read(run.directory/'prompts/judge-case-001.json')['prompt']
    system,user = _judge_prompt(plans[0][0], execution, _allowed_judge_refs(execution))
    revised_system,revised_user = model.prepare_prompt(system,user,'judge-case-001-revision-2')
    info = dict(previous_prompt_bytes=len(prior_prompt.encode('utf8')),
                revised_prompt_bytes=len((revised_system+'\n'+revised_user).encode('utf8')),
                original_judge_http=0, stage='judge', run_id=run.run_id, execution_sha256=_file_sha(execution_file),
                database_state_sha256=state['state_sha256'])
    if not info['previous_prompt_bytes'] > 64000 or not info['revised_prompt_bytes'] < 57000:
        raise ValueError('R2_JUDGE_PAYLOAD_DIAGNOSIS_NOT_VERIFIED')
    print(json.dumps(info), flush=True)
    if args.check_only:
        return
    bootstrap(ROOT)
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = 'localhost,127.0.0.1,api.deepseek.com,cn-beijing.maas.qwencloudapi.com'
    start_file = run.directory/'judge-revision-2-start.json'
    with start_file.open('x', encoding='utf8') as stream:
        json.dump(info, stream)
    _write(run.directory/'judge-initial-manifest.json', previous)
    started, clock = _utc(), time.monotonic()
    revised = run._judge(plans, [execution], model, revision=2)
    stage = previous['stages'][3]
    stage.update(status='COMPLETED', error=None, started_at=started, finished_at=_utc(),
                 duration_ms=round((time.monotonic()-clock)*1000,2), evidence=['judgements-revision-2.jsonl'])
    snapshot_source = read(run.directory/'conversation.json')
    candidates = [json.loads(line) for line in (run.directory/'cases.jsonl').read_text(encoding='utf8').splitlines()]
    started, clock = _utc(), time.monotonic()
    run._summarize(snapshot_source, candidates, [execution], revised)
    previous['stages'][4].update(status='COMPLETED', error=None, started_at=started, finished_at=_utc(),
                                duration_ms=round((time.monotonic()-clock)*1000,2), evidence=['summary.json','sha256.txt'])
    previous.update(status='COMPLETED', finished_at=_utc(), judgements_file='judgements-revision-2.jsonl')
    run._manifest()
    run._seal()
    print(json.dumps(dict(judge_status=revised[0]['status'], request_id=revised[0]['request_id']), ensure_ascii=True))


if __name__ == '__main__':
    main()
