"""Evidence-counted quality metrics. Empty populations report N/A, never zero success."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from target.v39.registry import NAMES, TOOLS
from target.tools import TOOLS as LEGACY
SCHEMA = {'type': 'object', 'required': ['case_id', 'title', 'objective', 'category', 'difficulty', 'conversation', 'assertions', 'source_references', 'generation_model', 'prompt_version', 'created_at', 'review_status'], 'properties': {**{n: {'type': 'string', 'minLength': 1} for n in ('case_id', 'title', 'objective', 'category', 'difficulty', 'generation_model', 'prompt_version', 'created_at', 'review_status')}, 'conversation': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}}, 'assertions': {'type': 'object'}, 'source_references': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}}}}
TRANSITIONS = {('NONE', 'PENDING_PAYMENT'), ('PENDING_PAYMENT', 'PAID'), ('PENDING_PAYMENT', 'PAYMENT_FAILED'), ('PENDING_PAYMENT', 'EXPIRED'), ('PENDING_PAYMENT', 'CANCELLED'), ('PAID', 'PAID'), ('PAID', 'CHANGED'), ('PAID', 'CANCELLED'), ('CHANGED', 'CHANGED'), ('CHANGED', 'CANCELLED')}
STATES = {'PENDING_PAYMENT', 'PAID', 'PAYMENT_FAILED', 'EXPIRED', 'CHANGED', 'CANCELLED'}
SECURITY = {'cross_owner', 'read_only_history', 'amount_mismatch', 'payment_replay', 'feature_revoked', 'proposal_expired', 'invalid_parameters'}
EXCEPTIONS = {'hold_expiry', 'payment_failure', 'proposal_expired', 'invalid_parameters'}

def ratio(numerator, denominator, definition):
    return dict(numerator=numerator, denominator=denominator, value=numerator / denominator if denominator else None, display=f'{numerator}/{denominator}' if denominator else 'N/A', definition=definition)

def quality(rows, runs):
    from target.scenario_generator import review
    cases = [r['body'] for r in rows]
    schemas = {t['function']['name']: t['function']['parameters'] for t in list(LEGACY) + list(TOOLS)}
    schema_ok = tools_ok = tool_cases = params_ok = param_cases = duplicates = executable = 0
    for case in cases:
        schema_ok += not list(Draft202012Validator(SCHEMA).iter_errors(case))
        result = review(case, [c for c in cases if c['case_id'] != case['case_id']])
        if result['quality']=='REJECTED':
            tool_cases += bool(case.get('expected_tool_calls') or case.get('integration_steps'))
            continue
        blocks = case.get('turn_expects', []) + [case.get('expect', {})]
        tools = [t for b in blocks if isinstance(b, dict) for t in b.get('must_call', []) + b.get('must_not_call', [])] + [s.get('tool') for s in case.get('integration_steps', []) if s.get('kind') == 'tool']
        tools += case.get('expected_tool_calls',[])
        tool_cases += bool(tools)
        tools_ok += bool(tools) and all((t in schemas for t in tools))
        parameter_sets = [(t, p) for b in blocks if isinstance(b, dict) for t, p in b.get('args', {}).items()]
        parameter_sets += [(s['tool'], s['args']) for s in case.get('integration_steps', []) if s.get('kind') == 'tool']
        for name, args in parameter_sets:
            if '$' in json.dumps(args):
                continue
            param_cases += 1
            schema = dict(schemas.get(name, {}))
            schema.pop('required', None)
            params_ok += name in schemas and (not list(Draft202012Validator(schema).iter_errors(args)))
        duplicates += bool(result['duplicates'])
        executable += result['quality'] == 'PASS'
    bodies = [r.get('body', r) for r in runs]
    return dict(population='independent candidate repository; review actions are local audit labels', schema=ratio(schema_ok, len(cases), 'persisted metadata JSON schema after normalization; not raw response correctness'), tools=ratio(tools_ok, tool_cases, 'cases with named tool references containing only registered names; no-tool cases excluded'), parameters=ratio(params_ok, param_cases, 'statically resolved partial argument constraints; dynamic references excluded'), duplicate=ratio(duplicates, len(cases), 'exact or similarity duplicate flagged'), executable=ratio(executable, len(cases), 'validator/capability gate PASS, not execution success'), reviewed=ratio(sum((r['status'] == 'APPROVED' for r in rows)), len(cases), 'current local approval records; not verified human identity'), execution=ratio(sum((r.get('status') == 'passed' for r in bodies)), len(bodies), 'independent recorded runs'), assertion_complete=ratio(sum((bool(r.get('steps') or r.get('checks')) for r in bodies)), len(bodies), 'runs containing structured assertion evidence'), trace_complete=ratio(sum((bool(r.get('evidence_root') and (Path(r['evidence_root']) / 'run_events.jsonl').is_file()) or bool(r.get('turn_results') and all((t.get('evidence_ref') and Path(t['evidence_ref']).is_file() for t in r['turn_results']))) for r in bodies)), len(bodies), 'trace evidence files exist'))

def coverage(results, mutation_results=()):
    tools = set()
    states = set()
    edges = set()
    passed = set()
    trace_complete = 0
    all_steps = 0
    chat_count = 0
    replies = 0
    for result in results:
        if result.get('fault') or result.get('mode') != 'deterministic_v310_integration':
            continue
        if result.get('status') == 'passed':
            passed.add(result.get('reference_plan'))
        try:
            trace_events=[json.loads(line) for line in (Path(result['evidence_root'])/'run_events.jsonl').read_text('utf8').splitlines()]
        except (OSError,ValueError,KeyError):
            trace_events=[]
        previous = {}
        for step in result.get('steps', []):
            all_steps += 1
            linked=[e for e in trace_events if e.get('run_id')==step.get('trace_id') and e.get('execution_id')==result.get('execution_id')]
            if step.get('trace_id') and {'scenario_step_started','scenario_step_finished'} <= {e.get('event_type') for e in linked}:
                trace_complete += 1
            if not step.get('verified'):
                continue
            tools.update(step.get('executed_tools', []))
            current = {o['order_id']: o['order_status'] for o in step['snapshot']['db']['v39_orders']}
            states.update(current.values())
            if step['kind'] in ('confirm', 'advance'):
                for identity, state in current.items():
                    before = previous.get(identity, 'NONE')
                    if before != state or step.get('output', {}).get('refund_id'):
                        edges.add((before, state))
            previous = current
            chat_count += step['kind'] == 'chat'
            replies += step['kind'] == 'chat' and any((c.get('path') == 'result.reply' for c in step['checks']))
    flows = {'query': any((t in tools for t in NAMES[:3])), 'create': 'railway_create_order' in tools and 'PENDING_PAYMENT' in states, 'pay': 'PAID' in states, 'refund': 'full_refund' in passed, 'change': 'CHANGED' in states}
    killed = sum((r.get('status') == 'failed' for r in mutation_results))
    report=dict(population='deterministic V310 integration; excludes injected faults; does not measure Live Agent quality', tools=ratio(len(set(NAMES) & tools), len(NAMES), 'distinct actually executed tools with verified steps / current registered railway tools'), tool_names=sorted(tools), workflows=ratio(sum(flows.values()), len(flows), 'query/create/pay/refund/change with committed evidence'), states=ratio(len(states & STATES), len(STATES), 'observed committed order states / declared six-state inventory'), transitions=ratio(len(edges & TRANSITIONS), len(TRANSITIONS), 'observed confirmation/expiry edges / ten declared legal edges including refund self-transitions'), observed_transitions=sorted([list(e) for e in edges & TRANSITIONS]), missing_transitions=sorted([list(e) for e in TRANSITIONS - edges]), security=ratio(len(passed & SECURITY), len(SECURITY), 'passed equivalent reference negative/guard/idempotency plans / seven declared checks'), exceptions=ratio(len(passed & EXCEPTIONS), len(EXCEPTIONS), 'passed expiry/failure/invalid-parameter plans / four declared checks; timeout/truncation unmeasured'), multi_turn=ratio(int('conversation' in passed), 1, 'two-turn real Mock Conversation input plan / one declared plan; not generalized context coverage'), reply_consistency=ratio(int('paid_reply' in passed), 1, 'paid readback has no stale waiting-for-payment claim / one declared check'), rag=ratio(0, 0, 'no RAG quality execution in this adapter batch'), trace=ratio(trace_complete, all_steps, 'same execution/run start and finish events linked per step'), models=ratio(0, 2, 'completed Live Agent execution / DeepSeek and Qwen, not model request attempts'), defects=ratio(killed, len(mutation_results), 'controlled fault runs that fail the original independent assertions'), unmeasured=['Live Agent', 'arbitrary natural-language truth', 'timeout/truncation recovery', 'load/concurrent throughput'])
    return report

def model_comparison(rows, generations):
    result = {}
    for provider in ('deepseek', 'bailian'):
        requests = [r for r in generations if r['body'].get('provider') == provider]
        ids = {identity for row in requests for identity in row['body'].get('cases', [])}
        candidates = [r for r in rows if r['id'] in ids]
        usage = [r['body'].get('usage') for r in requests if r['body'].get('usage')]
        known = [u for u in usage if type(u.get('prompt')) is int and type(u.get('completion')) is int]
        known_tokens = sum((u['prompt'] + u['completion'] for u in known))
        result[provider] = dict(generation_attempts=len(requests), responses_received=sum((bool(r['body'].get('raw')) for r in requests)), candidate_count=len(candidates), quality=quality(candidates, []), request_ids=[identity for row in requests for identity in row['body'].get('requests', [])], known_tokens=known_tokens if known else None, mean_known_tokens=known_tokens / len(known) if known else None, cost='UNKNOWN', human_acceptance=ratio(0, 0, 'no verified human labels in this experiment'), defect_detection=ratio(0, 0, 'no approved AI-generated fault campaign'))
    return result
