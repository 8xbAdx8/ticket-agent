"""Declarative, isolated integration adapter over the existing V3.10 UI/Registry/Service."""
import copy
import io
import json
import os
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import config
from target.v39.registry import NAMES, TOOLS
ROOT = Path(__file__).resolve().parents[1]
KINDS = ('tool', 'confirm', 'advance', 'chat', 'qr', 'history', 'flag', 'foreign_confirm', 'foreign_order')
OPS = ('eq', 'ne', 'ge', 'len', 'contains', 'not_contains')
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

def validate(case):
    errors = []
    steps = case.get('integration_steps')
    if case.get('execution_adapter') != 'v310' or not isinstance(steps, list) or (not 1 <= len(steps) <= 40):
        return ['v310 plan requires 1 to 40 steps']
    if case.get('fixture_scenario', 'default') not in ('default', 'sold_out', 'payment_fail'):
        errors.append('unknown fixture scenario')
    aliases = {'state', 'metrics', 'ui'}
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get('kind') not in KINDS:
            errors.append(f'step {index}: unknown operation')
            continue
        allowed = {'kind', 'as', 'args', 'tool', 'checks', 'expected_error', 'proposal', 'approved', 'actor', 'seconds', 'message', 'enabled', 'order'}
        if set(step) - allowed:
            errors.append(f'step {index}: unknown fields')
        if step.get('kind') == 'tool' and (step.get('tool') not in NAMES or not isinstance(step.get('args'), dict)):
            errors.append(f'step {index}: invalid registry tool')
        if step.get('kind') == 'confirm' and (step.get('actor') != 'test_user' or type(step.get('approved')) is not bool or (not isinstance(step.get('proposal'), str))):
            errors.append(f'step {index}: explicit trusted test-user decision required')
        if step.get('kind') == 'advance' and (type(step.get('seconds')) is not int or not 1 <= step['seconds'] <= 86400 * 30):
            errors.append(f'step {index}: invalid clock advance')
        if step.get('kind') == 'chat' and (not isinstance(step.get('message'), str) or len(step['message']) > 10000):
            errors.append(f'step {index}: invalid user message')
        if step.get('kind') == 'history' and type(step.get('enabled')) is not bool:
            errors.append('invalid read-only toggle')
        if step.get('kind') == 'flag' and type(step.get('enabled')) is not bool:
            errors.append('invalid feature flag')
        alias = step.get('as')
        if alias:
            if not isinstance(alias, str) or not alias.isidentifier() or alias in aliases:
                errors.append('invalid or duplicate alias')
            if isinstance(alias,str):aliases.add(alias)
        checks = step.get('checks')
        if not isinstance(checks, list) or not checks:
            errors.append(f'step {index}: deterministic checks required')
        else:
            for check in checks:
                if not isinstance(check, dict) or set(check) != {'path', 'op', 'value'} or check.get('op') not in OPS or (not isinstance(check.get('path'), str)):
                    errors.append(f'step {index}: invalid assertion')
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
        root = ROOT / 'artifacts/runtime/v310-ai-executions' / run_id
        root.mkdir(parents=True, exist_ok=False)
        variables = {}
        rows = []
        started = time.time()
        from target.scenario_plans import plans
        reference = next((p['title'] for p in plans() if p['integration_steps'] == case['integration_steps'] and p.get('fixture_scenario', 'default') == case.get('fixture_scenario', 'default')), None)
        result = dict(reference_plan=reference, case_id=case.get('case_id'), execution_id=run_id, status='error', mode=self.mode, model_requests=0, fault=fault, steps=rows, started_at=started, evidence_root=str(root), agent_invoked=False)
        environment = dict(RAILWAY_SIMULATION_ENABLED='1', RAILWAY_SIM_CLOCK_MODE='demo', RAILWAY_SIM_DB_PATH=str(root / 'simulation.sqlite'), TICKET_DISABLE_LOCAL_SECRETS='1', TICKET_WEB_OFFLINE_ONLY='1', RAG_ALLOW_NETWORK='0', TICKET_API_USAGE_DIR=str(root / 'api-usage'), TICKET_TEST_MODE='1', TICKET_DATA_MODE='fixture', TICKET_RAILWAY_QUERY_ENABLED='0')
        with CALL_LOCK, patch.dict(os.environ, environment), patch('socket.socket.connect',deny_network), patch('socket.socket.connect_ex',deny_network), patch('socket.create_connection',deny_network), patch('socket.getaddrinfo',deny_network):
            session = Conversation('user', engine='legacy', live=False, full_tools=True, root=root / 'session')
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
                                    before_confirmation=snapshot(session,service,context,effective)
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
                                    import re
                                    message = re.sub('\\{\\{([A-Za-z0-9_.]+)\\}\\}', lambda match: str(lookup(variables, match.group(1))), step['message'])
                                    public = session.send(message, uuid.uuid4().hex, defer_followups=True)
                                    output = {'public_result': copy.deepcopy(public), 'reply': public.get('reply', ''), 'queries': [copy.deepcopy(call) for turn in public.get('steps', []) for call in turn.get('calls', []) if call.get('tool', '').startswith('railway_')]}
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
                            with patch.dict(os.environ, {'RAILWAY_SIMULATION_ENABLED': '1'}):
                                view = snapshot(session, service, context, effective)
                            variables['state'] = copy.deepcopy(view['state'])
                            view['result'] = output
                            if step.get('as'):
                                variables[step['as']] = copy.deepcopy(output)
                            checks = [assert_value(check, view, variables) for check in step['checks']]
                            if kind=='confirm' and not error and not output.get('error') and output.get('status') in ('PENDING_PAYMENT','PAID','CHANGED','CANCELLED'):
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
                    (root / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        return result
