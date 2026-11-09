"""Versioned deterministic integration plans, separate from AI and formal baselines."""
import copy
import config
DATE = '2026-11-05'
ROUTE = dict(service_date=DATE, origin_stop_id='AOH', destination_stop_id='HGH')

def check(path, value, op='eq'):
    return dict(path=path, op=op, value=value)

def tool(name, args, alias, checks, **extra):
    return dict(kind='tool', tool=name, args=args, **{'as': alias}, checks=checks, **extra)

def confirm(alias, output, status, **extra):
    return dict(kind='confirm', proposal='$' + alias + '.proposal_id', approved=True, actor='test_user', **{'as': output}, checks=[check('result.status', status)], **extra)

def booking():
    selection = dict(ROUTE, trip_id='$trips.data.0.trip_id', seat_class='SECOND')
    return [tool('railway_query_trips', dict(ROUTE, limit=5), 'trips', [check('result.returned_count', 2, 'ge')]), tool('railway_check_inventory', dict(selection, quantity=3), 'inventory', [check('result.available', 3, 'ge')]), tool('railway_quote_fare', dict(selection, passenger_count=3), 'quote', [check('result.quote.total_fen', 1, 'ge')]), tool('railway_create_order', dict(quote_id='$quote.quote.quote_id', passengers=['合成甲', '合成乙', '合成丙'], contact=config.CURRENT_USER_PHONE), 'create', [check('result.status', 'CONFIRMATION_REQUIRED'), check('metrics.order_count', 0), check('metrics.hold_count', 0)]), confirm('create', 'created', 'PENDING_PAYMENT')]

def payment():
    return [tool('railway_pay_order', dict(order_id='$created.order_id', expected_total_fen='$quote.quote.total_fen'), 'pay', [check('result.status', 'CONFIRMATION_REQUIRED'), check('state.orders.0.order_status', 'PENDING_PAYMENT')]), dict(kind='qr', **{'as': 'qr'}, checks=[check('result.payload.demo', True), check('result.payload.currency', 'CNY'), check('result.png_bytes', 100, 'ge')]), confirm('pay', 'paid', 'PAID')]

def lifecycle():
    selection = dict(ROUTE, trip_id='$trips.data.1.trip_id', seat_class='SECOND')
    return booking() + payment() + [tool('railway_get_order', dict(order_id='$created.order_id'), 'order', [check('result.order_status', 'PAID')]), tool('railway_refund_order', dict(order_id='$created.order_id', scope='ITEMS', item_ids=['$order.items.0.item_id']), 'refund', [check('result.status', 'CONFIRMATION_REQUIRED')]), confirm('refund', 'refunded', 'PAID'), tool('railway_quote_fare', dict(selection, passenger_count=2), 'target', [check('result.quote.total_fen', 1, 'ge')]), tool('railway_change_order', dict(order_id='$created.order_id', target_quote_id='$target.quote.quote_id', **{'target_' + k: v for k, v in selection.items()}), 'change', [check('result.status', 'CONFIRMATION_REQUIRED')]), confirm('change', 'changed', 'CHANGED'), tool('railway_get_order', dict(order_id='$created.order_id'), 'changed_order', [check('result.order_status', 'CHANGED'), check('result.active_item_count', 2)]), tool('railway_refund_order', dict(order_id='$created.order_id', scope='ITEMS', item_ids=['$state.orders.0.passenger_ids.0']), 'changed_refund', [check('result.status', 'CONFIRMATION_REQUIRED')]), confirm('changed_refund', 'changed_refunded', 'CHANGED'), tool('railway_refund_order', dict(order_id='$created.order_id', scope='FULL'), 'final_refund', [check('result.status', 'CONFIRMATION_REQUIRED')]), confirm('final_refund', 'final', 'CANCELLED'), tool('railway_get_order', dict(order_id='$created.order_id'), 'final_order', [check('result.order_status', 'CANCELLED'), check('result.active_item_count', 0), check('metrics.held', 0), check('metrics.sold', 0)])]

def plans():
    paid = booking() + payment()
    query = [tool('railway_search_stations', dict(name='上海虹桥'), 'stations', [check('result.returned_count', 1, 'ge')]), tool('railway_query_trips', dict(ROUTE, limit=3), 'trips', [check('result.returned_count', 1, 'ge')]), tool('railway_trip_stops', dict(trip_id='$trips.data.0.trip_id', service_date=DATE), 'stops', [check('result.status', 'FOUND')])]
    expiry = booking() + [dict(kind='advance', seconds=901, checks=[check('state.orders.0.order_status', 'EXPIRED'), check('metrics.held', 0)])]
    cancel = booking() + [tool('railway_cancel_order', dict(order_id='$created.order_id'), 'cancel', [check('result.status', 'CONFIRMATION_REQUIRED')]), confirm('cancel', 'cancelled', 'CANCELLED')]
    mismatch = booking() + [tool('railway_pay_order', dict(order_id='$created.order_id', expected_total_fen=1), 'wrong_pay', [check('result.error', 'AMOUNT_MISMATCH')], expected_error='AMOUNT_MISMATCH')]
    malformed = [tool('railway_query_trips', {}, 'invalid', [check('result.error', 'INVALID_RAILWAY_ARGUMENTS')], expected_error='INVALID_RAILWAY_ARGUMENTS')]
    no_result = [tool('railway_search_stations', dict(name='不存在的合成车站'), 'none', [check('result.returned_count', 0)])]
    history = booking() + [dict(kind='history', enabled=True, checks=[check('result.read_only', True)]), tool('railway_pay_order', dict(order_id='$created.order_id', expected_total_fen='$quote.quote.total_fen'), 'readonly', [check('metrics.transaction_count', 0)], expected_error='READ_ONLY_HISTORY')]
    repeat = paid + [confirm('pay', 'replayed', 'PAID'), tool('railway_get_order', dict(order_id='$created.order_id'), 'verified', [check('metrics.transaction_count', 1), check('state.orders.0.hold_status', 'CONSUMED')])]
    flag = booking() + [dict(kind='flag', enabled=False, checks=[check('result.enabled', False)]), dict(kind='confirm', proposal='$create.proposal_id', approved=True, actor='test_user', checks=[check('state.orders.0.order_status', 'PENDING_PAYMENT')], expected_error='V39_CONTEXT_REQUIRED')]
    expired = booking()[:-1] + [dict(kind='advance', seconds=901, checks=[check('metrics.order_count', 0)]), dict(kind='confirm', proposal='$create.proposal_id', approved=True, actor='test_user', checks=[check('metrics.order_count', 0)], expected_error='DATABASE_RECEIPT_NOT_VERIFIED')]
    groups = [('railway_queries', query), ('lifecycle', lifecycle()), ('hold_expiry', expiry), ('cancel', cancel), ('amount_mismatch', mismatch), ('invalid_parameters', malformed), ('no_match', no_result), ('read_only_history', history), ('payment_replay', repeat), ('feature_revoked', flag), ('proposal_expired', expired)]
    other = booking() + [dict(kind='foreign_confirm', proposal='$create.proposal_id', checks=[check('metrics.order_count', 1)], expected_error='PROPOSAL_NOT_FOUND'), dict(kind='foreign_order', order='$created.order_id', checks=[check('metrics.order_count', 1)], expected_error='ORDER_FORBIDDEN')]
    failed = booking() + payment()[:-1] + [dict(kind='confirm', proposal='$pay.proposal_id', approved=True, actor='test_user', checks=[check('state.orders.0.order_status', 'PAYMENT_FAILED'), check('metrics.held', 0), check('metrics.sold', 0)], expected_error='PAYMENT_FAILED')]
    conversation = [dict(kind='chat', message='查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。', checks=[check('result.queries.0.args.service_date', DATE), check('result.queries.0.args.origin_stop_id', 'AOH'), check('metrics.order_count', 0)]), dict(kind='chat', message='继续查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。', checks=[check('result.queries.0.args.destination_stop_id', 'HGH'), check('metrics.order_count', 0)])]
    chat_paid = booking() + payment() + [dict(kind='chat', message='查询我的铁路模拟订单 {{created.order_id}}', checks=[check('result.public_result.tool_sequence', 'railway_get_order', 'contains'), check('state.orders.0.order_status', 'PAID'), check('result.reply', '等待支付', 'not_contains')])]
    full_refund = paid + [tool('railway_refund_order', dict(order_id='$created.order_id', scope='FULL'), 'full_refund', [check('result.status', 'CONFIRMATION_REQUIRED')]), confirm('full_refund', 'fully_refunded', 'CANCELLED')]
    groups += [('full_refund', full_refund), ('paid_reply', chat_paid), ('cross_owner', other), ('payment_failure', failed), ('conversation', conversation)]
    result = [dict(case_id='V310-INTEGRATION-' + name, title=name, execution_adapter='v310', plan_version='1', tags=[name], integration_steps=copy.deepcopy(steps)) for name, steps in groups]
    next((c for c in result if c['title'] == 'payment_failure'))['fixture_scenario'] = 'payment_fail'
    return result

def candidate(plan):
    from target.scenario_generator import normalize, evidence
    item = dict(title=plan['title'], turns=['执行经人工审核的独立V3.10集成计划'], expected_behavior='answer', expect={'must_call': []}, difficulty='medium', forbidden_claims=['真实扣款'], execution_adapter='v310', integration_steps=plan['integration_steps'], fixture_scenario=plan.get('fixture_scenario', 'default'))
    category = '业务状态一致性'
    case = normalize([item], category, 'deterministic_reference_plan', 'reference-plan-v1', list(evidence(category)['references']))[0]
    case['expected_state_changes'] = [c for step in plan['integration_steps'] for c in step['checks'] if c['path'].startswith('state.')]
    case['expected_tool_calls'] = list(dict.fromkeys(s['tool'] for s in plan['integration_steps'] if s['kind']=='tool'))
    return case
