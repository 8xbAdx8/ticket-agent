"""Explicit, isolated offline walkthrough using the existing Agent chat path."""
import uuid
import streamlit as st
from web.runtime import Conversation

STAGES = ['1 / 4 查票', '2 / 4 确认车次并下单', '3 / 4 确认模拟支付', '4 / 4 查询订单', '演示完成']


def start_demo():
    return {'session': Conversation('user', engine='legacy', live=False), 'stage': 0,
            'trains': [], 'order_id': None, 'selected': None, 'error': None}


def run_step(demo, message):
    session=demo['session']
    try:
        record=session.send(message, uuid.uuid4().hex)
        demo['error']=None
        return record, session.results[-1]
    except Exception:
        demo['error']='执行未完成，请检查本次会话的 Trace 和模拟订单状态；没有自动重试。'
        return None, []


def _entry():
    with st.container(key='demo_entry'):
        copy, action = st.columns([3.4, 1], gap='medium')
        copy.markdown(
            '<div class="ta-demo-copy"><span class="ta-eyebrow">60-SECOND WALKTHROUGH</span>'
            '<b>60 秒模拟购票演示</b>'
            '<p>四步离线演示：查票 → 确认车次并下单 → 模拟支付 → 查单。'
            '使用独立的模拟会话与模拟数据库，不产生模型请求、真实购票或扣款。'
            '每一步的按钮只在对应阶段出现，失败时不会自动重试。</p></div>', unsafe_allow_html=True)
        if action.button('开始 60 秒演示', key='demo_start', width='stretch'):
            demo=start_demo()
            st.session_state['guided_demo']=demo
            st.session_state.setdefault('user_sessions',[]).append(demo['session'])
            st.rerun()


def _panel(demo):
    session=demo['session']; stage=demo['stage']
    with st.container(key='demo_panel'):
        head, reset = st.columns([3, 1], gap='medium')
        head.markdown('<div class="ta-rail-head"><b>模拟购票演示</b>'
                      '<span class="ta-demo-badge">演示 · 非真实运行</span></div>', unsafe_allow_html=True)
        if reset.button('结束演示', key='demo_reset', width='stretch'):
            st.session_state.pop('guided_demo', None)
            st.rerun()
        st.progress(stage/4, text='查票 → 确认下单 → 模拟支付 → 查单')
        st.caption('当前进度：' + STAGES[stage])
        if demo['error']:
            st.warning(demo['error'])
        if stage==0 and st.button('查询明天上海到杭州的高铁二等座', key='demo_query'):
            record, results=run_step(demo,'查明天上海到杭州的高铁二等座')
            query=next((x for x in results if x.get('tool')=='query_tickets' and x.get('ok')),None)
            trains=(query or {}).get('result',{}).get('trains',[])
            demo['trains']=[x for x in trains if x.get('seats_left',0)>0]
            if demo['trains']: demo['stage']=1; st.rerun()
            else: demo['error']='未取得可用的模拟余票，请查看执行记录或重新开始。'
        if stage==1:
            st.caption('为保证离线规则模型与所选车次一致，演示选择查询结果中的第一趟有票车次。')
            train=demo['trains'][0]
            st.markdown(
                f'<div class="ticket-card"><div class="tc-train"><strong>{train.get("train_no","")}</strong>'
                f'<div class="muted">演示选中车次</div></div>'
                f'<div class="tc-route"><b>{train.get("depart","—")} <span class="tc-arrow">→</span> {train.get("arrive","—")}</b>'
                f'<div class="muted">{train.get("from_city","—")} → {train.get("to_city","—")}</div></div>'
                f'<div class="tc-seat"><b>{train.get("seat_type","")}</b><div class="muted">{train.get("date","")}</div></div>'
                f'<div class="tc-fare"><b>余票 {train.get("seats_left","未提供")}</b></div></div>',
                unsafe_allow_html=True)
            st.caption('乘客使用虚构姓名张三。点击按钮即确认锁座并创建模拟订单。')
            if st.button('确认选座并创建模拟订单', key='demo_order'):
                message=f"帮我订明天上海到杭州{train['train_no']}二等座，乘客张三"
                record, results=run_step(demo,message)
                order=next((x.get('result',{}) for x in results if x.get('tool')=='create_order' and x.get('ok')),None)
                if order and order.get('order_id') and order.get('train_no')==train['train_no']:
                    demo['order_id']=order['order_id']; demo['selected']=train['train_no']; demo['stage']=2; st.rerun()
                else: demo['error']='未确认创建了所选车次订单；请核查 Trace 和模拟订单状态，勿重复提交。'
        if stage==2:
            st.write('待支付模拟订单：',demo['order_id'])
            if st.button('确认模拟支付',key='demo_pay'):
                record,results=run_step(demo,'支付刚才的订单')
                paid=next((x.get('result',{}) for x in results if x.get('tool')=='pay_order' and x.get('ok')),None)
                if paid and paid.get('order_id')==demo['order_id'] and paid.get('status')=='paid':
                    demo['stage']=3; st.rerun()
                else: demo['error']='未确认支付成功；请先查询订单状态，勿重复提交。'
        if stage==3 and st.button('查询模拟订单',key='demo_order_query'):
            record,results=run_step(demo,'查询我的订单')
            found=next((o for x in results if x.get('tool')=='query_order' and x.get('ok') for o in x.get('result',{}).get('orders',[]) if o.get('order_id')==demo['order_id']),None)
            if found and found.get('status')=='paid':demo['stage']=4;st.rerun()
            else:demo['error']='查询结果未确认目标订单已支付，请查看 Trace。'
        if stage==4:
            st.success('模拟订单已查询，状态为已支付；没有真实购票或扣款。')
        if session.history:
            st.caption('以下为本演示会话的实际 Agent 记录；完整审计可在 Trace 分析中查看。')
            for record in session.history:
                st.write(record['user_msg'], ' → ', ' → '.join(record.get('tool_sequence',[])) or '无工具调用')


def demo_page():
    """Visible entry card, then the step panel once the demo is started."""
    demo=st.session_state.get('guided_demo')
    if demo is None:
        _entry()
        return
    _panel(demo)
