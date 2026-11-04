"""Presentation of the shared read model; all writes use business_actions."""
import streamlit as st
from target.execution_config import scope
from web.business_state import current


def summary(session):
    view=current(session);rail=view.get('railway') or {};selected=view.get('selected_trip')
    names={}
    from web.railway_cards import names_for
    names.update(names_for(session))
    if selected:
        st.markdown('### 本次行程摘要')
        origin=names.get(selected.get('origin_stop_id'),selected.get('origin_stop_id',''))
        destination=names.get(selected.get('destination_stop_id'),selected.get('destination_stop_id',''))
        st.write(origin+' → '+destination)
        from web.railway_simulation import SEATS
        st.caption(' · '.join(str(v) for v in (selected.get('trip_short_name') or selected.get('trip_id'),selected.get('service_date'),SEATS.get(selected.get('seat_class'),'席别待选择')) if v))
        if not session.read_only and selected.get('selection_source')=='user_selected_static_result':
            with st.expander('模拟余票与报价',expanded=True):
                with st.form('business_booking_form_'+session.sid):
                    seat=st.selectbox('选择模拟席别',list(SEATS),format_func=SEATS.get,key='business_seat_'+session.sid)
                    names_text=st.text_input('合成乘客（顿号分隔）',key='business_passengers_'+session.sid,placeholder='例如：测试甲、测试乙、测试丙')
                    submitted=st.form_submit_button('查询模拟库存并报价')
                passengers=[n.strip() for n in names_text.replace('，','、').replace(',','、').split('、') if n.strip()]
                disabled=not 1<=len(passengers)<=6
                if disabled:st.caption('请填写1至6名合成乘客；不会读取真实乘客系统。')
                if submitted and disabled:st.warning('请先填写1至6名合成乘客；尚未调用工具或创建交易。')
                if submitted and not disabled:
                    from web.railway_simulation import _call
                    service=session._v39_service;ctx=session._v39_context
                    args={k:selected[k] for k in ('trip_id','service_date','origin_stop_id','destination_stop_id')}
                    inventory=_call(service,ctx,'railway_check_inventory',dict(args,seat_class=seat,quantity=len(passengers)),session)
                    if inventory and inventory.get('status')=='SIMULATED_AVAILABLE':
                        quote=_call(service,ctx,'railway_quote_fare',dict(args,seat_class=seat,passenger_count=len(passengers)),session)
                        if quote:
                            session.selected_railway_trip=dict(selected,seat_class=seat)
                            session.booking_passengers=dict(quote_id=quote['quote']['quote_id'],names=passengers)
                    elif inventory:st.warning('模拟库存不足或未知，没有生成可建单报价。')
                    st.rerun()
                booking=getattr(session,'booking_passengers',None) or {}
                q=next((q for q in rail.get('quotes',[]) if q['quote_id']==booking.get('quote_id') and q['status']=='ACTIVE' and q['expires_at']>rail['updated_at'] and all(q.get(k)==selected.get(k) for k in ('trip_id','service_date','origin_stop_id','destination_stop_id'))),None)
                if q:
                    st.info('模拟总价 ¥'+f"{q['total_fen']/100:.2f}"+' · '+str(q['passenger_count'])+' 人；建单确认后才锁定模拟座位。')
                    matches=passengers==booking.get('names') and seat==q['seat_class']
                    if not matches:st.caption('乘客或席别已变化，请重新查询报价。')
                    if st.button('生成建单确认卡',key='business_create_'+session.sid,disabled=not matches):
                        from web.railway_simulation import _call
                        _call(session._v39_service,session._v39_context,'railway_create_order',dict(quote_id=q['quote_id'],passengers=passengers,contact=session._v39_context.owner_phone),session);st.rerun()
    if rail.get('orders'):
        st.markdown('### 我的订单')
        if session.read_only:
            from target.v39.read_model import status_text
            for o in rail['orders']:
                with st.container(border=True):
                    st.write(status_text(o));st.caption('票面 ¥'+f"{o['total_fen']/100:.2f}"+'；净支付 ¥'+f"{o['net_paid_fen']/100:.2f}")
                    with st.expander('乘客与交易'):
                        st.dataframe([dict(乘客=i['passenger_name'],状态=i['item_status']) for i in o['items']],hide_index=True)
                        st.json(o['transactions'],expanded=False)
            st.caption('历史会话只读；不会恢复确认令牌或自动继续旧交易。')
        elif not rail.get('pending_proposals'):
            from web.railway_simulation import _orders
            with scope(session._v39_effective):_orders(session._v39_service,session._v39_context,rail,session)
        else:
            for o in rail['orders']:st.caption(o['order_id']+' · '+o['order_status']+' · 有效乘客'+str(o['active_item_count'])+'人')
    if view.get('legacy'):
        with st.expander('原演示订单',expanded=not bool(rail.get('orders'))):
            for order in view['legacy']:st.caption(order['order_id']+' · '+order['train_no']+' · '+order['display_status'])
            st.caption('原演示票务数据；与GTFS铁路模拟订单独立，操作入口保留在原订单面板。')
    if view.get('error'):st.warning('当前业务状态读取未完成，请核对数据库与会话；未使用旧缓存代替。')
    if view.get('recommendations'):
        st.markdown('### 推荐车次')
        legacy=all(t.get('source')=='LEGACY_DEMO' for t in view['recommendations'])
        st.caption('来自本会话原演示查询，不是真实余票。' if legacy else '来自本会话已完成的静态查询，不表示实时余票。')
        for train in view['recommendations']:
            st.caption(str(train.get('trip_short_name') or train.get('trip_id') or train.get('train_no'))+' · '+str(train.get('departure_at') or train.get('depart') or '时刻未提供')+' → '+str(train.get('arrival_at') or train.get('arrive') or '时刻未提供'))


def receipts(session):
    """Page confirmation results are system receipts, never fictional AI messages."""
    view=current(session);rail=view.get('railway') or {}
    rows=getattr(session,'business_receipts',[])
    if not rows:return
    last=rows[-1]
    if last.get('session_id')!=session.sid:return
    action=last.get('actual_result') or {}
    with st.container(border=True,key='business_receipt_'+last['operation_id']):
        st.markdown('**本地业务操作回执**')
        st.caption('页面操作 · 未因此调用模型 · '+last['status'])
        o=next((o for o in rail.get('orders',[]) if o['order_id']==last.get('order_id')),None)
        if last['status']=='FAILED':st.error('本次操作未完成：'+str(action.get('error') or '请核对回执'))
        elif last['status']=='BLOCKED':
            if action.get('status')=='CONFIRMATION_REQUIRED':st.info('已生成确认卡；尚未执行交易。')
            else:st.warning('本次操作已拦截，未能完成：'+str(action.get('error') or '请核对权限与参数'))
        elif last['status']=='CANCELLED':st.info('已撤销待确认操作，没有因此执行交易。')
        if o:
            before=last.get('before') or {};after=last.get('after') or {}
            st.write('本次订单变化：'+str(before.get('order_status') or '尚未建单')+' → '+str(after.get('order_status') or o['order_status']))
            if action.get('refund_fen') is not None:st.write('本次净退款 ¥'+f"{action['refund_fen']/100:.2f}"+'；手续费 ¥'+f"{action['fee_fen']/100:.2f}")
            if action.get('difference_fen') is not None:st.write('本次改签差价 ¥'+f"{action['difference_fen']/100:.2f}"+'（正数补款，负数退差）')
            st.caption('当时操作回执保留；订单当前状态以本轮共享数据库快照为准。')
        elif last['status']=='SUCCEEDED':st.write('已取得本地工具结果：'+str(action.get('status','已记录')))
