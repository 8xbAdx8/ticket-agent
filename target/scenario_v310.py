"""Declarative, isolated integration adapter over the existing V3.10 UI/Registry/Service."""
import copy
import io
import json
import os
import re
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import config
from target.v39.registry import NAMES, TOOLS
ROOT = Path(__file__).resolve().parents[1]
WORKBENCH_RUN_ROOT = Path(os.getenv('TICKET_WORKBENCH_RUN_ROOT', ROOT / 'artifacts/runtime/v310-c-workbench-runs')).resolve()
if not WORKBENCH_RUN_ROOT.is_relative_to(ROOT / 'artifacts/runtime') or WORKBENCH_RUN_ROOT == ROOT / 'artifacts/runtime':
    raise ValueError('WORKBENCH_RUN_ROOT_MUST_BE_ISOLATED')
KINDS = ('tool', 'confirm', 'advance', 'chat', 'qr', 'history', 'flag', 'foreign_confirm', 'foreign_order')
OPS = ('eq', 'ne', 'ge', 'len', 'contains', 'not_contains')
FLAG_SCHEMA = {'type': 'object', 'required': ['enabled'], 'properties': {'enabled': {'type': 'boolean'}}}
PATH_MAX_LENGTH = 512
PATH_PATTERN = r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*'
CHAT_REFERENCE = re.compile(r'\{\{([A-Za-z0-9_.]+)\}\}')
TABLES = ('v39_orders', 'v39_order_items', 'v39_holds', 'v39_transactions', 'v39_inventory_segments', 'v39_inventory_events', 'v39_refund_requests', 'v39_change_requests', 'v39_proposals', 'v39_idempotency', 'v39_refund_items', 'v39_hold_segments', 'v39_transaction_allocations')

def confirmation_proof(pid, output, view):
    """Independently match the committed receipt and concrete business rows."""
    db=view['db']
    proposal=next((p for p in db['v39_proposals'] if p['proposal_id']==pid),None)
    if not proposal or proposal['state']!='CONFIRMED':return False
    receipt=next((r for r in db['v39_idempotency'] if r['scope']=='confirm' and r['key']=='confirm:'+proposal['session_id']+':'+pid+':'+proposal['action']),None)
    if not receipt or receipt['status']!='SUCCEEDED':return False
    payload=json.loads(proposal['payload_json'])
    saved=json.loads(receipt['response_json'])
    if saved!=output:return False
    order=next((o for o in db['v39_orders'] if o['order_id']==output.get('order_id')),None)
    if not order or order['order_status']!=output.get('status'):return False
    if proposal['action']!='CREATE_ORDER' and payload.get('order_id')!=order['order_id']:return False
    hold=next((h for h in db['v39_holds'] if h['hold_id']==order['hold_id'] and h['order_id']==order['order_id']),None)
    if not hold:return False
    items=[i for i in db['v39_order_items'] if i['order_id']==order['order_id'] and i['item_status']=='ACTIVE']
    segments=[s for s in db['v39_hold_segments'] if s['hold_id']==hold['hold_id']]
    if not segments or any(s['quantity']!=hold['remaining_quantity'] for s in segments):return False
    if hold['status'] in ('ACTIVE','CONSUMED') and hold['remaining_quantity']!=len(items):return False
    if proposal['action']=='CREATE_ORDER':
        names=[i['passenger_name'] for i in sorted(items,key=lambda i:i['passenger_index'])]
        return names==payload.get('passengers') and order['quote_id']==payload.get('quote_id') and hold['status']=='ACTIVE' and hold['remaining_quantity']==len(items)
    transactions=[t for t in db['v39_transactions'] if t['order_id']==order['order_id'] and t['status']=='SUCCEEDED']
    if proposal['action']=='PAY':
        paid=[t for t in transactions if t['transaction_type']=='PAYMENT']
        return order['payment_status']=='SUCCEEDED' and hold['status']=='CONSUMED' and len(paid)==1 and paid[0]['amount_fen']==order['paid_total_fen']==payload.get('expected_total_fen')
    if output.get('refund_id'):
        refund=next((r for r in db['v39_refund_requests'] if r['refund_id']==output['refund_id'] and r['order_id']==order['order_id'] and r['status']=='SUCCEEDED'),None)
        credits=[t for t in transactions if t['transaction_type']=='REFUND' and t['refund_id']==output['refund_id']]
        refunded=[i for i in db['v39_refund_items'] if i['refund_id']==output['refund_id']]
        ids={i['item_id'] for i in db['v39_order_items'] if i['order_id']==order['order_id'] and i['item_status']=='REFUNDED'}
        wanted={i['item_id'] for i in payload.get('_refund_preview',{}).get('items',[])}
        if not wanted or {i['order_item_id'] for i in refunded}!=wanted:return False
        return bool(refund and refunded and all(i['status']=='SUCCEEDED' and i['order_item_id'] in ids for i in refunded) and sum(i['net_fen'] for i in refunded)==refund['net_fen'] and sum(i['fee_fen'] for i in refunded)==refund['fee_fen'] and refund['net_fen']==output.get('refund_fen') and refund['fee_fen']==output.get('fee_fen') and len(credits)==1 and credits[0]['amount_fen']==refund['net_fen'])
    if output.get('change_id'):
        change=next((r for r in db['v39_change_requests'] if r['change_id']==output['change_id'] and r['order_id']==order['order_id'] and r['status']=='CONFIRMED'),None)
        differences=[t for t in transactions if t['change_id']==output['change_id'] and t['transaction_type'] in ('CHANGE_REFUND','CHANGE_SUPPLEMENT')]
        if not change or change['target_quote_id']!=payload.get('target_quote_id'):return False
        return bool(change and change['new_hold_id']==hold['hold_id'] and hold['status']=='CONSUMED' and change['difference_fen']==output.get('difference_fen') and sum(t['amount_fen']*(1 if t['direction']=='DEBIT' else -1) for t in differences)==change['difference_fen'] and all(i['price_quote_id']==change['target_quote_id'] for i in items))
    return proposal['action']=='CANCEL' and hold['status']=='RELEASED' and hold['remaining_quantity']==0

def deny_network(*args, **kwargs):
    raise RuntimeError('OFFLINE_ADAPTER_NETWORK_BLOCKED')

def replay_proof(pid, output, before, after):
    """Historical idempotent receipts are not the current order status."""
    proposal=next((p for p in before['db']['v39_proposals'] if p['proposal_id']==pid),None)
    if not proposal or proposal['state']!='CONFIRMED':return False
    key='confirm:'+proposal['session_id']+':'+pid+':'+proposal['action']
    receipt=next((r for r in before['db']['v39_idempotency'] if r['scope']=='confirm' and r['key']==key and r['status']=='SUCCEEDED'),None)
    return bool(receipt and json.loads(receipt['response_json'])==output and before['db']==after['db'])

def valid_path(path):
    return isinstance(path, str) and len(path) <= PATH_MAX_LENGTH and re.fullmatch(PATH_PATTERN, path) is not None


def lookup(value, path):
    for part in path.split('.'):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value

def resolve(value, variables):
    if isinstance(value, str) and value.startswith('$'):
        return copy.deepcopy(lookup(variables, value[1:]))
    if isinstance(value, dict):
        return {key: resolve(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, variables) for item in value]
    return value

def validate(case, diagnostics=None):
    errors = []

    def report(code, message, step=None, path=None):
        errors.append(f'step {step}: {message}' if step is not None else message)
        if diagnostics is not None:
            diagnostic = dict(code=code, step=step, message=errors[-1])
            if path is not None:
                diagnostic['path'] = path
            diagnostics.append(diagnostic)

    steps = case.get('integration_steps')
    if case.get('execution_adapter') != 'v310' or not isinstance(steps, list) or not 1 <= len(steps) <= 40:
        report('PLAN_SIZE_INVALID', 'v310 plan requires 1 to 40 steps')
        return errors
    if case.get('fixture_scenario', 'default') not in ('default', 'sold_out', 'payment_fail'):
        report('FIXTURE_INVALID', 'unknown fixture scenario')
    aliases = {'state', 'metrics', 'ui'}
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get('kind') not in KINDS:
            report('STEP_KIND_INVALID', 'unknown operation', index, 'kind')
            continue
        kind = step['kind']
        allowed = {'kind', 'as', 'args', 'tool', 'checks', 'expected_error', 'proposal', 'approved', 'actor', 'seconds', 'message', 'enabled', 'order'}
        if set(step) - allowed:
            report('STEP_FIELDS_INVALID', 'unknown fields', index)
        if kind == 'tool' and (step.get('tool') not in NAMES or not isinstance(step.get('args'), dict)):
            report('TOOL_STEP_INVALID', 'invalid registry tool', index)
        if kind == 'confirm' and (step.get('actor') != 'test_user' or type(step.get('approved')) is not bool or not isinstance(step.get('proposal'), str)):
            report('CONFIRMATION_INVALID', 'explicit trusted test-user decision required', index)
        if kind in ('foreign_confirm', 'foreign_order'):
            field = 'proposal' if kind == 'foreign_confirm' else 'order'
            if not isinstance(step.get(field), str) or not step[field].strip():
                report('FOREIGN_REFERENCE_REQUIRED', f'{field} must be provided', index, field)
        if 'expected_error' in step and (not isinstance(step['expected_error'], str) or not step['expected_error'].strip()):
            report('EXPECTED_ERROR_INVALID', 'expected error must be a non-empty string', index, 'expected_error')
        if kind == 'advance' and (type(step.get('seconds')) is not int or not 1 <= step['seconds'] <= 86400 * 30):
            report('CLOCK_ADVANCE_INVALID', 'invalid clock advance', index, 'seconds')
        if kind == 'chat' and (not isinstance(step.get('message'), str) or not step['message'].strip() or len(step['message']) > 10000):
            report('MESSAGE_INVALID', 'invalid user message', index, 'message')
        if kind == 'history' and type(step.get('enabled')) is not bool:
            report('HISTORY_ENABLED_REQUIRED', 'invalid read-only toggle', index, 'enabled')
        if kind == 'flag' and ('args' in step or any(type(step.get(field)) is not bool for field in FLAG_SCHEMA['required'])):
            report('FLAG_ENABLED_REQUIRED', 'invalid feature flag, enabled must be an explicit top-level boolean and flag does not accept args', index, 'enabled')
        if 'as' in step:
            alias = step['as']
            if not isinstance(alias, str) or not alias.isidentifier() or not valid_path(alias) or alias in aliases:
                report('ALIAS_INVALID', 'invalid or duplicate alias', index, 'as')
            else:
                aliases.add(alias)
        checks = step.get('checks')
        if not isinstance(checks, list) or not checks:
            report('CHECKS_REQUIRED', 'deterministic checks required', index, 'checks')
        else:
            for check in checks:
                if not isinstance(check, dict) or set(check) != {'path', 'op', 'value'} or check.get('op') not in OPS:
                    report('ASSERTION_INVALID', 'invalid assertion', index, 'checks')
                elif not valid_path(check['path']):
                    report('ASSERTION_PATH_INVALID', 'assertion requires a dot-separated path', index, 'checks.path')
    return errors


def assert_value(check, view, variables):
    expected = resolve(check['value'], variables)
    try:
        actual = lookup(view, check['path'])
        if check['op'] == 'eq':
            ok = type(actual) is type(expected) and actual == expected
        elif check['op'] == 'ne':
            ok = actual != expected
        elif check['op'] == 'ge':
            ok = type(actual) in (int, float) and type(expected) in (int, float) and (actual >= expected)
        elif check['op'] == 'len':
            ok = type(expected) is int and len(actual) == expected
        elif check['op'] == 'not_contains':
            ok = expected not in actual
        else:
            ok = expected in actual
        return dict(path=check['path'], op=check['op'], expected=expected, actual=actual, ok=ok)
    except (KeyError, IndexError, TypeError, ValueError):
        return dict(path=check['path'], op=check['op'], expected=expected, actual=None, ok=False, error='MISSING_OR_INVALID_EVIDENCE')

def snapshot(session, service, context, effective):
    from target.execution_config import scope
    from target.v39.read_model import read
    from web.business_state import refresh
    with scope(effective):
        state = read(service.store.path, context, now=service.now())
    ui = refresh(session)['railway']
    with service.store.transaction() as connection:
        tables = {table: [dict(row) for row in connection.execute('SELECT * FROM ' + table)] for table in TABLES}
        foreign_keys = [tuple(row) for row in connection.execute('PRAGMA foreign_key_check')]
    inventory = tables['v39_inventory_segments']
    events = tables['v39_inventory_events']
    inventory_ok = True
    identity = ('scenario_id', 'dataset_version', 'trip_id', 'service_date', 'seat_class', 'segment_index')
    for segment in inventory:
        matching = [event for event in events if all((event[k] == segment[k] for k in identity))]
        inventory_ok &= sum((e['delta_held'] for e in matching)) == segment['held'] and sum((e['delta_sold'] for e in matching)) == segment['sold'] and (0 <= segment['held'] + segment['sold'] <= segment['capacity'])
    money_ok = True
    for order in tables['v39_orders']:
        transactions = [t for t in tables['v39_transactions'] if t['order_id'] == order['order_id'] and t['status'] == 'SUCCEEDED']
        net = sum((t['amount_fen'] * (1 if t['direction'] == 'DEBIT' else -1) for t in transactions))
        money_ok &= net == order['net_paid_fen']
        if order['payment_status'] == 'SUCCEEDED':
            active = sum((i['fare_fen'] for i in tables['v39_order_items'] if i['order_id'] == order['order_id'] and i['item_status'] == 'ACTIVE'))
            money_ok &= net == active + order['fee_total_fen']
    statuses = lambda data: {o['order_id']: (o['order_status'], o['payment_status'], o['net_paid_fen']) for o in data or []}
    consistent = statuses(state['orders']) == statuses((ui or {}).get('orders')) == statuses(tables['v39_orders'])
    metrics = dict(order_count=len(tables['v39_orders']), hold_count=len(tables['v39_holds']), transaction_count=len(tables['v39_transactions']), held=sum((s['held'] for s in inventory)), sold=sum((s['sold'] for s in inventory)), foreign_keys_ok=not foreign_keys, inventory_conserved=bool(inventory_ok), money_conserved=bool(money_ok), ui_consistent=consistent)
    return dict(state=state, ui=ui, db=tables, metrics=metrics)

class V310Adapter:
    mode = 'deterministic_v310_integration'

    def run(self, case, *, fault=None):
        return self._run(case, fault=fault)

    def run_workbench(self, case, *, directory, engine, mutation=None):
        from target.diagnostics import IDS
        directory = Path(directory).resolve()
        if (directory.parent.name != 'executions' or directory.parents[2] != WORKBENCH_RUN_ROOT
                or not re.fullmatch(r'[0-9a-f]{32}', directory.parents[1].name)
                or not re.fullmatch(r'case-[0-9]{3}', directory.name)):
            raise ValueError('C_WORKBENCH_ISOLATED_EXECUTION_REQUIRED')
        if engine not in ('legacy', 'langchain') or mutation not in (None, *tuple(IDS)[:-1]):
            raise ValueError('C_WORKBENCH_INVALID_ENGINE_OR_MUTATION')
        return self._run(case, root=directory, engine=engine, mutation=mutation)

    def _run(self, case, *, fault=None, root=None, engine='legacy', mutation=None):
        workbench = root is not None
        errors = validate(case)
        if errors:
            return dict(status='NOT_EXECUTABLE', mode=self.mode, errors=errors, steps=[], model_requests=0)
        if fault not in (None, 'wrong_arguments', 'missing_confirmation', 'fake_payment_success', 'missing_expiry', 'ui_drift'):
            raise ValueError('unknown trusted fault')
        from web.runtime import CALL_LOCK, Conversation
        from web.v39_bridge import prepare
        from web.business_actions import invoke
        from target.run_events import capture, emit
        from target.execution_config import scope as effective_scope
        from target.v39.context import scope
        run_id = uuid.uuid4().hex
        root = root if root is not None else ROOT / 'artifacts/runtime/v310-ai-executions' / run_id
        root.mkdir(parents=True, exist_ok=False)
        variables = {}
        rows = []
        started = time.time()
        from target.scenario_plans import plans
        reference = next((p['title'] for p in plans() if p['integration_steps'] == case['integration_steps'] and p.get('fixture_scenario', 'default') == case.get('fixture_scenario', 'default')), None)
        result = dict(reference_plan=reference, case_id=case.get('case_id'), execution_id=run_id, status='error', mode=self.mode, model_requests=0, fault=fault, steps=rows, started_at=started, evidence_root=str(root), agent_invoked=False)
        environment = dict(RAILWAY_SIMULATION_ENABLED='1', RAILWAY_SIM_CLOCK_MODE='demo', RAILWAY_SIM_DB_PATH=str(root / 'simulation.sqlite'), TICKET_DISABLE_LOCAL_SECRETS='1', TICKET_WEB_OFFLINE_ONLY='1', RAG_ALLOW_NETWORK='0', TICKET_API_USAGE_DIR=str(root / 'api-usage'), TICKET_TEST_MODE='1', TICKET_DATA_MODE='fixture', TICKET_RAILWAY_QUERY_ENABLED='0')
        with CALL_LOCK, patch.dict(os.environ, environment), patch('socket.socket.connect',deny_network), patch('socket.socket.connect_ex',deny_network), patch('socket.create_connection',deny_network), patch('socket.getaddrinfo',deny_network):
            if mutation:
                session = Conversation('lab', engine=engine, live=False, full_tools=True,
                                       mutations={mutation: 1 if mutation == 'date_offset' else True}, root=root / 'session')
            else:
                session = Conversation('user', engine=engine, live=False, full_tools=True, root=root / 'session')
            session._unified_interaction = True
            from target.v39.service import Service
            original_scenario = Service.scenario

            def scenario_setup(instance, identity, dataset, **kwargs):
                return original_scenario(instance, identity, dataset, name=case.get('fixture_scenario', 'default'))
            with patch.object(Service, 'scenario', scenario_setup):
                service, context, effective = prepare(session)
            with ExitStack() as stack:
                if fault == 'missing_expiry':
                    stack.enter_context(patch.object(service, 'expire', return_value=None))
                if fault == 'ui_drift':
                    from web.business_state import refresh as original_refresh

                    def drift(current_session):
                        value = copy.deepcopy(original_refresh(current_session))
                        if value.get('railway') is not None:
                            value['railway']['orders'] = [{'order_id': 'injected-wrong-order', 'order_status': 'PAID', 'payment_status': 'SUCCEEDED', 'net_paid_fen': 1}]
                        return value
                    stack.enter_context(patch('web.business_state.refresh', drift))
                try:
                    for index, step in enumerate(case['integration_steps']):
                        output = {}
                        error = None
                        events = []
                        kind = step['kind']
                        with capture(root / 'run_events.jsonl', callback=events.append) as trace:
                            trace.update(run_id=run_id + '-' + str(index), session_id=session.sid, provider='deterministic_integration')
                            emit('scenario_step_started', operation_kind=kind, case_id=case.get('case_id'), execution_id=run_id)
                            audit_count = len(session.audits) if workbench and kind == 'chat' else None
                            try:
                                if kind == 'tool':
                                    args = resolve(step['args'], variables)
                                    if fault == 'wrong_arguments' and 'seat_class' in args:
                                        args['seat_class'] = 'INVALID'
                                    output = invoke(session, step['tool'], args)
                                elif kind in ('foreign_confirm', 'foreign_order'):
                                    from dataclasses import replace
                                    foreign = replace(context, session_id='other-synthetic-session', owner_phone=config.OTHER_USER_PHONE)
                                    with effective_scope(effective), scope(foreign):
                                        output = service.confirm(foreign, resolve(step['proposal'], variables)) if kind == 'foreign_confirm' else service.order(foreign, resolve(step['order'], variables))
                                elif kind == 'confirm':
                                    pid = resolve(step['proposal'], variables)
                                    if step['approved']:
                                        before_confirmation=snapshot(session,service,context,effective)
                                    else:
                                        from target.scenario_business_oracle import snapshot as oracle_snapshot, decline_proof
                                        before_decline=oracle_snapshot(service.store.path)
                                    if fault=='fake_payment_success' and any(p['proposal_id']==pid and p['action']=='PAY' for p in snapshot(session,service,context,effective)['db']['v39_proposals']):
                                        output={'status':'PAID','order_id':variables['created']['order_id'],'simulation':True}
                                    else:
                                        output = {'status': 'PAID'} if fault == 'missing_confirmation' else session.confirm_railway_proposal(pid, step['approved'])
                                elif kind == 'advance':
                                    clock = service.clock.snapshot()
                                    service.clock.advance(step['seconds'], revision=clock['revision'])
                                    with effective_scope(effective), scope(context):
                                        service.expire(context)
                                    output = {'advanced': step['seconds']}
                                elif kind == 'chat':
                                    message = CHAT_REFERENCE.sub(lambda match: str(lookup(variables, match.group(1))), step['message'])
                                    public = session.send(message, uuid.uuid4().hex, defer_followups=True)
                                    output = {'public_result': copy.deepcopy(public), 'reply': public.get('reply', ''), 'queries': [copy.deepcopy(call) for turn in public.get('steps', []) for call in turn.get('calls', []) if call.get('tool', '').startswith('railway_')]}
                                    if workbench:
                                        from target.diagnostics import digest
                                        audit = next((item for item in reversed(session.audits)
                                                      if item.get('public_trace_sha256') == digest(public)
                                                      or item.get('public_trace') == public), {})
                                        output['agent_trace_id'] = audit.get('trace_id')
                                        output['agent_audit'] = {key: audit[key] for key in ('mutation_events', 'judgement')
                                                                 if key in audit}
                                    result['agent_invoked'] = True
                                elif kind == 'history':
                                    session.read_only = step['enabled']
                                    output = {'read_only': session.read_only}
                                elif kind == 'flag':
                                    os.environ['RAILWAY_SIMULATION_ENABLED'] = '1' if step['enabled'] else '0'
                                    output = {'enabled': step['enabled']}
                                elif kind == 'qr':
                                    from web.v39_payment import eligible
                                    from target.payment_qr import payment_payload, render_qr
                                    from PIL import Image
                                    view = snapshot(session, service, context, effective)
                                    proposal = next((p for p in view['state']['pending_proposals'] if p['action'] == 'PAY'))
                                    found = eligible(view['state'], proposal)
                                    if not found:
                                        raise ValueError('QR_NOT_ELIGIBLE')
                                    order, amount = found
                                    png = render_qr(order['order_id'], amount, str(amount))
                                    decoded = json.loads(Image.open(io.BytesIO(png)).info['ticket_demo_payment'])
                                    assert decoded == payment_payload(order['order_id'], amount, str(amount))
                                    (root / f'payment-{index}.png').write_bytes(png)
                                    output = dict(payload=decoded, expected_fen=order['total_fen'], png_bytes=len(png))
                            except Exception as exc:
                                error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                                output = {'error': error}
                                if audit_count is not None and len(session.audits) > audit_count:
                                    audit = session.audits[-1]
                                    output['agent_trace_id'] = audit.get('trace_id')
                                    output['agent_audit'] = {key: audit[key] for key in ('mutation_events', 'judgement')
                                                             if key in audit}
                            with patch.dict(os.environ, {'RAILWAY_SIMULATION_ENABLED': '1'}):
                                view = snapshot(session, service, context, effective)
                            variables['state'] = copy.deepcopy(view['state'])
                            view['result'] = output
                            if step.get('as'):
                                variables[step['as']] = copy.deepcopy(output)
                            checks = [assert_value(check, view, variables) for check in step['checks']]
                            if kind=='confirm' and not error and not output.get('error'):
                                if not step['approved']:
                                    declined=(output.get('status')=='CANCELLED' and output.get('proposal_id')==pid
                                              and decline_proof(before_decline,oracle_snapshot(service.store.path),pid))
                                    checks.append(dict(path='committed_decline_receipt',ok=declined))
                                elif output.get('status') in ('PENDING_PAYMENT','PAID','CHANGED','CANCELLED'):
                                    previously_confirmed=any(p['proposal_id']==pid and p['state']=='CONFIRMED' for p in before_confirmation['db']['v39_proposals'])
                                    checks.append(dict(path='committed_confirmation_receipt',ok=replay_proof(pid,output,before_confirmation,view) if previously_confirmed else confirmation_proof(pid,output,view),replay=previously_confirmed))
                            if step.get('expected_error'):
                                checks.append(dict(path='expected_error', ok=(error or output.get('error')) == step['expected_error'], actual=error or output.get('error'), expected=step['expected_error']))
                            elif error or output.get('error'):
                                checks.append(dict(path='unexpected_error', ok=False, actual=error or output.get('error')))
                            for name in ('foreign_keys_ok', 'inventory_conserved', 'money_conserved', 'ui_consistent'):
                                checks.append(dict(path='metrics.' + name, ok=view['metrics'][name], actual=view['metrics'][name]))
                            executed_tools = [e['tool'] for e in events if e.get('event_type') == 'railway_tool_result' and e.get('executed')]
                            executed = any((e.get('event_type') == 'railway_tool_result' and e.get('executed') for e in events))
                            row = dict(index=index, kind=kind, tool=step.get('tool'), args=resolve(step.get('args', {}), variables), output=output, error=error, checks=checks, snapshot=view, trace_id=trace['run_id'], executed_tools=executed_tools, executed=executed, verified=all((c['ok'] for c in checks)))
                            if workbench and kind == 'chat' and 'agent_trace_id' in output:
                                row['input_message'] = message
                            rows.append(row)
                            emit('scenario_step_finished', 'succeeded' if row['verified'] else 'failed', assertions=checks, execution_id=run_id)
                        if not row['verified']:
                            break
                    result['status'] = 'passed' if len(rows) == len(case['integration_steps']) and all((r['verified'] for r in rows)) else 'failed'
                except Exception as exc:
                    import traceback
                    result['error'] = type(exc).__name__
                    result['error_stack'] = traceback.format_exc()
                finally:
                    result['finished_at'] = time.time()
                    result['duration_s'] = result['finished_at'] - started
                    saved = result
                    if workbench:
                        from target.scenario_workbench_evidence import private_evidence
                        saved = private_evidence(result)
                    (root / 'result.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf8')
        return result
