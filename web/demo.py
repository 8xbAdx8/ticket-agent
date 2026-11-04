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

STAGES = ['1 / 4 查票', '2 / 4 确认车次并下单', '3 / 4 确认模拟支付', '4 / 4 查询订单', '演示完成']


def start_demo():
    from web import v39_bridge
    if not v39_bridge.enabled():
        from web.demo_legacy import start_demo as legacy_start
        demo = legacy_start()
        demo['legacy'] = True
        return demo
    session = Conversation('user', engine='legacy', live=False)
    demo = {'session': session, 'stage': 0, 'result': None, 'trip': None,
            'order_id': None, 'error': None, 'log': []}
    try:
        demo['service'], demo['ctx'], demo['effective'] = defaults.prepare(session)
    except defaults.DefaultQueryError:
        demo['error'] = '铁路模拟服务未就绪；没有自动重试，也没有创建订单。'
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
        demo['error'] = '默认路线没有静态车次；没有编造车次。'
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
            service_date=defaults.DEMO_SERVICE_DATE,
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
        demo['error'] = '创建模拟订单未完成：' + type(exc).__name__ + '；未自动重试。'


def _step_pay(demo):
    service, ctx, oid = demo['service'], demo['ctx'], demo['order_id']
    try:
        order = service.order(ctx, oid)
        proposal = service.propose(ctx, 'PAY', {
            'order_id': oid, 'expected_total_fen': order['total_fen'],
        })
        paid = service.confirm(ctx, proposal['proposal_id'])
        if paid.get('order_id') != oid or paid.get('status') not in ('PAID', 'SUCCEEDED'):
            demo['error'] = '模拟支付未确认成功：' + str(paid.get('status') or 'NO_RESULT') + '；未自动重试。'
            return
        demo['stage'] = 3
        demo['error'] = None
        demo['log'].append({'step': 'PAY', 'proposal': proposal['proposal_id'], 'order': oid})
    except Exception as exc:
        demo['error'] = '模拟支付未完成：' + type(exc).__name__ + '；未自动重试。'


def _step_order_query(demo):
    service, ctx, oid = demo['service'], demo['ctx'], demo['order_id']
    try:
        order = service.order(ctx, oid)
        if order.get('order_status') != 'PAID':
            demo['error'] = '订单查询结果不是已支付，未标记演示完成。'
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
            '<div class="ta-demo-copy"><span class="ta-eyebrow">快速体验</span>'
            '<b>四步了解购票流程</b>'
            '<p>查票 → 确认车次并下单 → 模拟支付 → 查单。'
            '使用独立的演示会话和隔离模拟库，不产生模型费用，不会真实出票或扣款。'
            '静态车次来自本地 GTFS；每一步仍需你点击确认。</p></div>', unsafe_allow_html=True)
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
    with st.container(key='demo_panel'):
        head, reset = st.columns([3, 1], gap='medium')
        head.markdown('<div class="ta-rail-head"><b>模拟购票演示</b>'
                      '<span class="ta-demo-badge">本地静态时刻 + 模拟交易 · 不真实出票或扣款</span></div>',
                      unsafe_allow_html=True)
        if reset.button('结束演示', key='demo_reset', width='stretch'):
            st.session_state.pop('guided_demo', None)
            st.rerun()
        st.progress(stage / 4, text='查票 → 确认下单 → 模拟支付 → 查单')
        st.caption('当前进度：' + STAGES[stage])
        if demo.get('error'):
            st.warning(demo['error'])
        if stage == 0:
            st.caption('默认路线：' + defaults.DEMO_ORIGIN + ' → ' + defaults.DEMO_DESTINATION +
                       ' · ' + defaults.DEMO_SERVICE_DATE + ' · ' + defaults.DEMO_SEAT_LABEL)
            if st.button('查询默认演示车次', key='demo_query'):
                _step_query(demo)
                st.rerun()
        if stage == 1:
            result, trip = demo['result'], demo['trip']
            st.caption('真实静态数据：' + str(result['trips'].get('dataset_version', '')) +
                       '；共 ' + str(result['trips'].get('total_count', len(result['rows']))) + ' 班。')
            st.markdown(
                f'<div class="ticket-card"><div class="tc-train"><strong>{trip.get("trip_short_name", "")}</strong>'
                f'<div class="muted">选定静态车次</div></div>'
                f'<div class="tc-route"><b>{trip.get("departure_at", "—")} <span class="tc-arrow">→</span> '
                f'{trip.get("arrival_at", "—")}</b><div class="muted">'
                f'{defaults.DEMO_ORIGIN} → {defaults.DEMO_DESTINATION}</div></div>'
                f'<div class="tc-seat"><b>{defaults.DEMO_SEAT_LABEL}</b>'
                f'<div class="muted">{defaults.DEMO_SERVICE_DATE}</div></div>'
                f'<div class="tc-fare"><b>乘客 {defaults.DEMO_PASSENGER}</b></div></div>',
                unsafe_allow_html=True)
            inv = (result.get('inventory') or {})
            if inv.get('status'):
                st.caption('首班模拟库存：' + str(inv.get('status')) + '；静态车次存在不代表真实有票。')
            ack = st.checkbox('我已核对车次，确认创建本地模拟订单', key='demo_order_ack')
            if st.button('确认选座并创建模拟订单', key='demo_order', disabled=not ack):
                _step_order(demo)
                st.rerun()
        if stage == 2:
            st.write('待支付模拟订单：', demo['order_id'])
            ack = st.checkbox('我已核对金额，确认进行本地模拟支付', key='demo_pay_ack')
            if st.button('确认模拟支付', key='demo_pay', disabled=not ack):
                _step_pay(demo)
                st.rerun()
        if stage == 3:
            st.write('已支付模拟订单：', demo['order_id'])
            if st.button('查询模拟订单', key='demo_order_query'):
                _step_order_query(demo)
                st.rerun()
        if stage == 4:
            st.success('模拟订单已查询，状态为已支付；没有真实购票或扣款。')
            st.caption('新会话或“结束演示”可从干净状态重新开始。')
        if demo.get('log'):
            with st.expander('本次本地交易审计', expanded=False):
                st.json(demo['log'], expanded=False)


def demo_page():
    """Visible entry card, then the step panel once the demo is started."""
    demo = st.session_state.get('guided_demo')
    if demo is None:
        _entry()
        return
    _panel(demo)
