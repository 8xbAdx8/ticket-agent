"""Deterministic local four-step walkthrough (V3.9.4).

Uses the same real GTFS static adapter and V3.9 simulation service as the
original chat, but never calls a model and never touches an external railway
or payment service.  Each transactional step still goes through the V3.9
proposal/confirmation path.
"""
import streamlit as st
import config
from web.runtime import Conversation
from web import railway_defaults as defaults

STAGES = ['1 / 4 查票', '2 / 4 确认车次并下单', '3 / 4 确认支付', '4 / 4 查询订单', '流程完成']


def start_demo():
    from web import v39_bridge
    if not v39_bridge.enabled():
        from web.demo_legacy import start_demo as legacy_start
        demo = legacy_start()
        demo['legacy'] = True
        return demo
    session = Conversation('user', engine='legacy', live=False)
    demo = {'session': session, 'stage': 0, 'result': None, 'trip': None,
            'order_id': None, 'error': None, 'log': [],
            'service_date': defaults.default_service_date().isoformat()}
    try:
        demo['service'], demo['ctx'], demo['effective'] = defaults.prepare(session)
    except defaults.DefaultQueryError:
        demo['error'] = '铁路查询服务未就绪；没有自动重试，也没有创建订单。'
    return demo


def _step_query(demo):
    try:
        result = defaults.default_demo(demo['session'])
    except defaults.DefaultQueryError as exc:
        demo['error'] = '查询未完成：' + str(exc.code) + '；请核对站点或日期。'
        return
    except Exception:
        demo['error'] = '查询未完成：内部错误；没有自动重试。'
        return
    demo['result'] = result
    rows = result.get('rows') or []
    if not rows:
        demo['error'] = '默认路线没有车次；没有编造车次。'
        return
    demo['trip'] = rows[0]
    demo['stage'] = 1
    demo['error'] = None


def _step_order(demo):
    service, ctx, trip = demo['service'], demo['ctx'], demo['trip']
    result = demo['result']
    try:
        quote = service.quote(
            ctx, trip_id=trip['trip_id'],
            service_date=demo['service_date'],
            origin_stop_id=result['origin']['stop_id'],
            destination_stop_id=result['destination']['stop_id'],
            seat_class=defaults.DEMO_SEAT_CLASS, passenger_count=1)
        proposal = service.propose(ctx, 'CREATE_ORDER', {
            'quote_id': quote['quote']['quote_id'],
            'passengers': [defaults.DEMO_PASSENGER],
            'contact': config.CURRENT_USER_PHONE,
        })
        confirmed = service.confirm(ctx, proposal['proposal_id'])
        order_id = confirmed.get('order_id')
        if not order_id:
            demo['error'] = '订单提案未确认成功：' + str(confirmed.get('status') or 'NO_ORDER') + '；未自动重试。'
            return
        demo['order_id'] = order_id
        demo['stage'] = 2
        demo['error'] = None
        demo['log'].append({'step': 'CREATE_ORDER', 'proposal': proposal['proposal_id'], 'order': order_id})
    except Exception as exc:
        demo['error'] = '创建订单未完成：' + type(exc).__name__ + '；未自动重试。'


def _step_pay(demo):
    service, ctx, oid = demo['service'], demo['ctx'], demo['order_id']
    try:
        order = service.order(ctx, oid)
        proposal = service.propose(ctx, 'PAY', {
            'order_id': oid, 'expected_total_fen': order['total_fen'],
        })
        paid = service.confirm(ctx, proposal['proposal_id'])
        if paid.get('order_id') != oid or paid.get('status') not in ('PAID', 'SUCCEEDED'):
            demo['error'] = '支付未确认成功：' + str(paid.get('status') or 'NO_RESULT') + '；未自动重试。'
            return
        demo['stage'] = 3
        demo['error'] = None
        demo['log'].append({'step': 'PAY', 'proposal': proposal['proposal_id'], 'order': oid})
    except Exception as exc:
        demo['error'] = '支付未完成：' + type(exc).__name__ + '；未自动重试。'


def _step_order_query(demo):
    service, ctx, oid = demo['service'], demo['ctx'], demo['order_id']
    try:
        order = service.order(ctx, oid)
        if order.get('order_status') != 'PAID':
            demo['error'] = '订单查询结果不是已支付，未标记流程完成。'
            return
        demo['stage'] = 4
        demo['error'] = None
        demo['log'].append({'step': 'QUERY_ORDER', 'order': oid, 'status': order.get('order_status')})
    except Exception as exc:
        demo['error'] = '订单查询未完成：' + type(exc).__name__ + '；未自动重试。'


def _entry():
    with st.container(key='demo_entry'):
        copy, action = st.columns([3.4, 1], gap='medium')
        copy.markdown(
            '<div class="ta-demo-copy"><span class="ta-eyebrow">快速购票</span>'
            '<b>四步完成一次购票</b>'
            '<p>查票 → 下单 → 支付 → 查单，每一步由你确认。</p></div>', unsafe_allow_html=True)
        if action.button('开始快速体验', key='demo_start', width='stretch'):
            demo = start_demo()
            st.session_state['guided_demo'] = demo
            st.session_state.setdefault('user_sessions', []).append(demo['session'])
            st.rerun()


def _panel(demo):
    if demo.get('legacy'):
        from web.demo_legacy import _panel as legacy_panel
        legacy_panel(demo)
        return
    stage = demo['stage']
    service_day = demo.get('service_date') or defaults.default_service_date().isoformat()
    with st.container(key='demo_panel'):
        head, reset = st.columns([3, 1], gap='medium')
        head.markdown('<div class="ta-rail-head"><b>购票流程引导</b>'
                      '<span class="ta-demo-badge">四步流程 · 每一步由你确认</span></div>',
                      unsafe_allow_html=True)
        if reset.button('结束体验', key='demo_reset', width='stretch'):
            st.session_state.pop('guided_demo', None)
            st.rerun()
        st.progress(stage / 4, text='查票 → 确认下单 → 支付 → 查单')
        st.caption('当前进度：' + STAGES[stage])
        if demo.get('error'):
            st.warning(demo['error'])
        if stage == 0:
            st.caption('默认路线：' + defaults.DEMO_ORIGIN + ' → ' + defaults.DEMO_DESTINATION +
                       ' · ' + service_day + ' · ' + defaults.DEMO_SEAT_LABEL)
            if st.button('查询默认路线车次', key='demo_query'):
                _step_query(demo)
                st.rerun()
        if stage == 1:
            result, trip = demo['result'], demo['trip']
            st.caption('车次时刻版本：' + str(result['trips'].get('dataset_version', '')) +
                       '；共 ' + str(result['trips'].get('total_count', len(result['rows']))) + ' 班。')
            st.markdown(
                f'<div class="ticket-card"><div class="tc-train"><strong>{trip.get("trip_short_name", "")}</strong>'
                f'<div class="muted">选定车次</div></div>'
                f'<div class="tc-route"><b>{trip.get("departure_at", "—")} <span class="tc-arrow">→</span> '
                f'{trip.get("arrival_at", "—")}</b><div class="muted">'
                f'{defaults.DEMO_ORIGIN} → {defaults.DEMO_DESTINATION}</div></div>'
                f'<div class="tc-seat"><b>{defaults.DEMO_SEAT_LABEL}</b>'
                f'<div class="muted">{service_day}</div></div>'
                f'<div class="tc-fare"><b>乘客 {defaults.DEMO_PASSENGER}</b></div></div>',
                unsafe_allow_html=True)
            inv = (result.get('inventory') or {})
            if inv.get('status'):
                st.caption('首班余票状态：' + str(inv.get('status')) + '；有余票记录不等于可真实出票。')
            ack = st.checkbox('我已核对车次，确认创建订单', key='demo_order_ack')
            if st.button('确认选座并创建订单', key='demo_order', disabled=not ack):
                _step_order(demo)
                st.rerun()
        if stage == 2:
            st.write('待支付订单：', demo['order_id'])
            ack = st.checkbox('我已核对金额，确认进行支付', key='demo_pay_ack')
            if st.button('确认支付', key='demo_pay', disabled=not ack):
                _step_pay(demo)
                st.rerun()
        if stage == 3:
            st.write('已支付订单：', demo['order_id'])
            if st.button('查询订单', key='demo_order_query'):
                _step_order_query(demo)
                st.rerun()
        if stage == 4:
            st.success('订单已查询，状态为已支付；本次流程没有真实购票或扣款。')
            st.caption('新会话或“结束体验”可从干净状态重新开始。')
        if demo.get('log'):
            with st.expander('本次交易记录', expanded=False):
                st.json(demo['log'], expanded=False)


def demo_page():
    """Visible entry card, then the step panel once the demo is started."""
    demo = st.session_state.get('guided_demo')
    if demo is None:
        _entry()
        return
    _panel(demo)
