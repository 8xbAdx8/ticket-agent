"""Generate exactly one R2 candidate per provider against the retained ABC budget."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    from target.api_config import bootstrap, model_config
    from target.scenario_abc_budget import AUTHORIZATION, BATCH_ROOT, R2_ROOT, IntegrationBatch
    from target.scenario_abc_live import configured_provider
    from target.scenario_r2_live import R2Model
    from target.scenario_workbench import Workbench
    from web.session_store import restore_session
    parser = argparse.ArgumentParser()
    parser.add_argument('provider', choices=('deepseek', 'bailian'))
    parser.add_argument('--revision', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    gate = read(R2_ROOT/'qa09-results'/('offline-gate.json' if args.revision == 1 and args.provider == 'deepseek' else 'offline-gate-revision-2.json'))
    evidence = R2_ROOT/gate['junit']
    if gate.get('status') != 'PASS' or hashlib.sha256(evidence.read_bytes()).hexdigest() != gate['junit_sha256']:
        raise ValueError('R2_OFFLINE_QUALITY_GATE_REQUIRED')
    for filename, digest in gate['tested_sources'].items():
        if hashlib.sha256((ROOT/filename).read_bytes()).hexdigest() != digest:
            raise ValueError('R2_OFFLINE_QUALITY_SOURCE_CHANGED')
    prior_pilot = R2_ROOT/'qa09-results/deepseek.json'
    prior = read(prior_pilot) if prior_pilot.is_file() else {}
    if args.revision == 2 and (args.provider != 'deepseek' or prior.get('quality') != 'REJECTED'
            or not prior.get('wire_prompt_verified') or gate.get('addresses_request_id') != prior.get('request_id')):
        raise ValueError('R2_REVISED_PILOT_EVIDENCE_REQUIRED')
    if args.provider == 'bailian':
        if prior.get('quality') != 'PASS':
            prior = read(R2_ROOT/'qa09-results/deepseek-revision-2.json')
        if prior.get('quality') != 'PASS':
            raise ValueError('R2_DEEPSEEK_PILOT_REQUIRED')
    suffix = '-revision-2' if args.revision == 2 else ''
    if (R2_ROOT/f'pilot-{args.provider}{suffix}.json').exists():
        raise ValueError('R2_PILOT_ALREADY_STARTED')
    prior_auth = read(BATCH_ROOT/'authorization.json')
    prior_final = read(BATCH_ROOT/'budget-final.json')
    prior_preflight = read(BATCH_ROOT/'budget-preflight.json')
    prior_rows = [json.loads(line) for line in (BATCH_ROOT/'request-ledger.jsonl').read_text(encoding='utf8').splitlines()]
    batch = IntegrationBatch()
    before = batch.snapshot()
    if (prior_auth != AUTHORIZATION or prior_final['batch_id'] != before['batch_id']
            or prior_preflight['budget']['batch_id'] != before['batch_id']
            or not {row['request_id'] for row in prior_rows} <= {row['request_id'] for row in batch.ledger()}):
        raise ValueError('R2_RETAINED_BUDGET_NOT_VERIFIED')
    bootstrap(ROOT)
    with configured_provider(args.provider) as model:
        host = urlsplit(model_config(args.provider)['base_url']).hostname
    receipt = dict(provider=args.provider, model=model, host=host, key_present=True, effective_policy=AUTHORIZATION,
                   budget=before, verified_offline_gate=gate, historical_request_count=len(prior_rows))
    path = R2_ROOT/(f'budget-preflight{suffix}.json' if args.provider == 'deepseek' else 'budget-preflight-bailian.json')
    write(path, receipt)
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = f'127.0.0.1,localhost,{host}'
    source = read(BATCH_ROOT/'source.json')
    if not (R2_ROOT/'source.json').exists():
        write(R2_ROOT/'source.json', source | {'source_area': BATCH_ROOT.name, 'mode': 'OFFLINE_SYNTHETIC_INPUT'})
    session = restore_session(BATCH_ROOT/source['directory'], expected_sid=source['session_id'])
    run = Workbench(session.sid, root=R2_ROOT/'generated-cases')
    result = run.execute(session, R2Model(args.provider, batch=batch, revision=args.revision), review_required=True)
    ledger = [row for row in batch.ledger() if row['run_id'] == run.run_id]
    request = ledger[0] if len(ledger) == 1 else None
    wire = R2_ROOT/'raw-http'/f"{request['request_id']}.json" if request else None
    prompt = run.directory/'prompts/generate.json'
    prompt_sha = read(prompt).get('prompt_sha256') if prompt.is_file() else None
    wire_ok = False
    if wire and wire.is_file():
        response = read(wire)
        messages = response.get('request_messages', [])
        if len(messages) == 2 and [m.get('role') for m in messages] == ['system', 'user']:
            sent = '\n'.join(m['content'] for m in messages)
            wire_ok = hashlib.sha256(sent.encode('utf8')).hexdigest() == prompt_sha and request['payload_sha256'] == response['request_payload_sha256']
    candidates = [json.loads(line) for line in (run.directory/'cases.jsonl').read_text(encoding='utf8').splitlines()] if (run.directory/'cases.jsonl').is_file() else []
    eligible = result['status'] == 'AWAITING_REVIEW' and wire_ok and len(candidates) == 1 and candidates[0]['validated']
    info = dict(provider=args.provider, model=model, run_id=run.run_id, session_id=session.sid,
                quality='PASS' if eligible else 'REJECTED', status=result['status'], wire_prompt_verified=wire_ok,
                prompt_sha256=prompt_sha, request_id=request['request_id'] if request else None, candidates=candidates)
    write(R2_ROOT/'qa09-results'/f'{args.provider}{suffix}.json', info)
    print(json.dumps({k: v for k, v in info.items() if k != 'candidates'}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
