"""Presentation of the shared read model; all writes use business_actions."""
import re
import sqlite3
import streamlit as st
from target.execution_config import scope
from web.business_state import current


ORDER_STATUS_TEXT={'PENDING_PAYMENT':'待支付','PAID':'已支付','CHANGED':'已改签',
                   'CANCELLED':'已退票','REFUNDED':'已退款','EXPIRED':'已过期','PAYMENT_FAILED':'支付失败'}
LEG_KEYS=('trip_id','service_date','origin_stop_id','destination_stop_id')


def booking_inputs(names_text, doc_no, phone):
    passengers=[part.strip() for part in re.split(r'[、，,；;\r\n]+',names_text) if part.strip()]
    errors=[]
    if not passengers:errors.append('乘客姓名：请至少填写 1 名乘客。')
    elif len(passengers)>6:errors.append('乘客姓名：每次最多报价 6 名乘客。')
    if not doc_no.strip():errors.append('身份证号码：请输入居民身份证号码。')
    elif not re.fullmatch(r'[0-9]{17}[0-9Xx]',doc_no.strip()):
        errors.append('身份证号码：须为 18 位，前 17 位为数字，末位为数字或 X。')
    if not phone.strip():errors.append('手机号码：请输入手机号。')
    elif not re.fullmatch(r'1[0-9]{10}',phone.strip()):
        errors.append('手机号码：须为以 1 开头的 11 位数字。')
    return passengers,errors


def active_booking_quote(session, selected):
    rail=current(session).get('railway') or {}
    booking=getattr(session,'booking_passengers',None) or {}
    return next((q for q in rail.get('quotes',[]) if q['quote_id']==booking.get('quote_id')
                 and q['status']=='ACTIVE' and q['expires_at']>rail['updated_at']
                 and all(q.get(k)==selected.get(k) for k in LEG_KEYS)),None)


def _request_booking_quote(session, selected, seat, passengers):
    from web.business_actions import invoke
    from web.railway_simulation import ERRORS
    from web.runtime import CALL_LOCK

    args={key:selected[key] for key in LEG_KEYS}
    with CALL_LOCK:
        previous=active_booking_quote(session,selected)
        booking=getattr(session,'booking_passengers',None) or {}
        if previous and previous['seat_class']==seat and booking.get('names')==passengers:
            return None
        session.booking_passengers=None
        stage='查询余票'
        try:
            inventory=invoke(session,'railway_check_inventory',dict(args,seat_class=seat,quantity=len(passengers)))
            status=inventory.get('status')
            if status in ('INVENTORY_SOLD_OUT','INVENTORY_INSUFFICIENT'):
                return f"当前席别模拟余票 {inventory['available']} 张，本次需要 {len(passengers)} 张。请更换车次或席别。"
            if status!='SIMULATED_AVAILABLE':
                return ERRORS.get(inventory.get('error'),'当前席别的模拟库存不可用，请更换车次或席别。')
            stage='计算报价'
            price=invoke(session,'railway_quote_fare',dict(args,seat_class=seat,passenger_count=len(passengers)))
        except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as exc:
            return ERRORS.get(str(exc),f'{stage}未完成，请查看本次工具执行记录。')
        quote=price.get('quote') or {}
        if price.get('status')!='QUOTED' or not quote.get('quote_id'):
            return ERRORS.get(price.get('error'),'报价工具未返回有效报价，请查看本次工具执行记录。')
        session.selected_railway_trip=dict(selected,seat_class=seat)
        session.booking_passengers=dict(quote_id=quote['quote_id'],names=passengers,available=inventory['available'])
    return None


def _auto_create_order(session, selected, quote, passengers):
    """Submit the quote and auto-confirm the simulated order in one page action."""
    from web.railway_simulation import SEATS, _call
    from web import scroll_bridge
    result = _call(session._v39_service, session._v39_context, 'railway_create_order',
                   dict(quote_id=quote['quote_id'], passengers=passengers,
                        contact=session._v39_context.owner_phone), session)
    proposal_id = str((result or {}).get('proposal_id') or '')
    if not proposal_id:
        st.error('订单生成未完成：建单工具没有返回待确认提案，请查看本次工具执行记录。')
        return
    try:
        confirmed = session.confirm_railway_proposal(proposal_id, True) or {}
    except Exception as exc:
        st.error('订单生成未完成：' + (str(exc) if isinstance(exc, ValueError) else '请查看执行记录与订单状态。'))
        return
    order_id = str(confirmed.get('order_id') or (result or {}).get('order_id') or '待核验')
    st.session_state['last_order_card_' + session.sid] = dict(
        order_id=order_id,
        proposal_id=proposal_id,
        train=str(selected.get('trip_short_name') or selected.get('trip_id') or '所选车次'),
        date=str(selected.get('service_date') or ''),
        seat=SEATS.get(quote['seat_class'], quote['seat_class']),
        passengers=list(passengers),
        amount=int(quote.get('total_fen') or 0) / 100,
        origin=str(selected.get('origin_stop_id') or ''),
        destination=str(selected.get('destination_stop_id') or ''),
    )
    scroll_bridge.request('run', 'action_dock', scope=session.sid)
    st.rerun()


def order_confirm_card(session):
    """Read-only receipt shown in the right tool-execution panel."""
    key = 'last_order_card_' + session.sid
    card = st.session_state.get(key)
    if not card:
        return
    with st.container(border=True, key='order_confirm_card'):
        st.markdown('**订单确认卡（只读）**')
        st.caption('本次模拟订单已直接生成；这里只用于核对，不会重复交易。')
        st.write('订单：' + card['order_id'])
        st.write(card['train'] + ' · ' + card['date'] + ' · ' + card['seat'])
        st.write(card['origin'] + ' → ' + card['destination'])
        st.write('乘客：' + '、'.join(card['passengers']))
        st.write('金额：¥' + f"{card['amount']:.2f}")
        st.caption('对应提案：' + card['proposal_id'])
        if st.button('知道了', key='order_card_ack_' + session.sid):
            st.session_state.pop(key, None)
            st.rerun()


def order_in_progress(session, order):
    """What this train's order is doing now, in place of the booking form.

    After 建单 the customer's next step is paying (then refund/change), never
    "choose a seat and retype the passenger"; leaving the form on screen made
    the page look stuck on the previous screen.
    """
    from web.railway_simulation import SEATS
    oid=str(order['order_id'])
    status=ORDER_STATUS_TEXT.get(order.get('order_status'),'处理中')
    seat=SEATS.get(order.get('seat_class'),order.get('seat_class') or '所选席别')
    items=[i for i in (order.get('items') or []) if isinstance(i,dict)
           and i.get('item_status','ACTIVE')=='ACTIVE']
    names=[str(i.get('passenger_name')) for i in items if i.get('passenger_name')]
    amount=(order.get('total_fen') or 0)/100
    st.markdown('**订单 '+oid+' · '+status+'**')
    facts=['票面 ¥'+f'{amount:.2f}',seat]
    if names:facts.append('乘客 '+'、'.join(names))
    st.caption(' · '.join(facts))
    if order.get('order_status')=='PENDING_PAYMENT':
        st.caption('座位已锁定，支付完成后出票。')
        if st.button('继续完成支付',key='inline_pay_'+oid,width='stretch'):
            from web.railway_queries import open_payment_card
            if open_payment_card(session,order,'继续完成支付'):
                st.session_state['a_pay_turn_'+session.sid]=dict(
                    message='继续完成支付',order_id=oid,
                    reply=('已为订单 '+oid+' 生成支付确认卡，¥'+f'{amount:.2f}'+
                           '。请在主对话里核对支付二维码并完成支付。'))
                st.rerun()
    else:
        st.caption('退票或改签在下方订单卡片办理。')


def order_for_trip(session, selected):
    """The live order this selected train already produced, if any.

    A refunded / expired order no longer owns the train: leaving its status
    block here would keep the booking form away and make the train look
    unbookable, so only orders that are still in force count.
    """
    rail=(current(session).get('railway') or {})
    return next((o for o in (rail.get('orders') or [])
                 if isinstance(o,dict) and o.get('order_id')
                 and o.get('order_status') in ('PENDING_PAYMENT','PAID','CHANGED')
                 and o.get('trip_id')==(selected or {}).get('trip_id')
                 and str(o.get('service_date'))==str((selected or {}).get('service_date'))),None)


def _quote_preview(session, selected):
    """Show a real, one-passenger local quote before the passenger form."""
    from web.railway_simulation import SEATS, _call
    from web.railway_cards import names_for
    seat = selected.get('seat_class') or 'SECOND'
    key = 'business_quote_preview_' + '_'.join((session.sid, *(str(selected[k]) for k in LEG_KEYS), seat))
    quote = st.session_state.get(key)
    if quote is None:
        # A refresh can restore the same active session. Reuse its existing
        # preview instead of writing another quote just to paint the page.
        snapshot=(current(session).get('railway') or {})
        saved=next((q for q in snapshot.get('quotes',[]) if q['status']=='ACTIVE'
                    and q['expires_at']>snapshot['updated_at'] and q['passenger_count']==1
                    and q['seat_class']==seat and all(q[k]==selected[k] for k in LEG_KEYS)),None)
        if saved:quote=st.session_state[key]={'quote':saved}
    if quote is None:
        try:
            args = {k: selected[k] for k in ('trip_id','service_date','origin_stop_id','destination_stop_id')}
            inventory = _call(session._v39_service, session._v39_context, 'railway_check_inventory',
                              dict(args, seat_class=seat, quantity=1), session)
            if inventory and inventory.get('status') == 'SIMULATED_AVAILABLE':
                quote = _call(session._v39_service, session._v39_context, 'railway_quote_fare',
                              dict(args, seat_class=seat, passenger_count=1), session) or {'status': 'UNAVAILABLE'}
            else:
                quote = {'status': 'UNAVAILABLE'}
        except (OSError, ValueError, KeyError, TypeError):
            quote = {'status': 'UNAVAILABLE'}
        st.session_state[key] = quote
    q = (quote or {}).get('quote') or {}
    names = names_for(session)
    st.markdown('**已选车次报价**')
    st.caption(str(selected.get('trip_short_name') or selected.get('trip_id') or '车次') + ' · ' +
               str(SEATS.get(seat, seat)) + ' · ' + str(selected.get('service_date') or ''))
    if q.get('quote_id') and q.get('total_fen') is not None:
        st.markdown('**模拟票价 ¥' + f"{q['total_fen']/100:.2f}" + '** · 1 人')
        st.caption('价格来自本地模拟库存/报价工具；选乘客后会在下方重新报价。')
    else:
        st.caption('当前席别暂无可报价库存；不会编造价格。')


def booking_panel(session, selected, suffix=''):
    """余票与报价：选席别 + 填乘客 → 真实库存/报价工具 → 直接生成模拟订单。

    Rendered in the foot-of-page dock (conversation._action_dock), so picking a
    train never opens a form in the middle of the timetable.  A valid submit
    creates and confirms the order in one step; the read-only confirmation card
    is shown in the right「本次工具执行」panel instead of blocking the chat.
    """
    from web.railway_simulation import SEATS
    # A committed order moves this block on to the order itself (pay now, or
    # refund/change later) instead of asking for the same train a second time.
    committed=order_for_trip(session,selected)
    if committed is not None:
        order_in_progress(session,committed)
        return
    if getattr(session,'_v39_service',None) is None:
        from web.railway_defaults import prepare
        prepare(session)
    saved_quote=active_booking_quote(session,selected)
    if not saved_quote:
        _quote_preview(session, selected)
    booking=getattr(session,'booking_passengers',None) or {}
    hint='、'.join(booking.get('names',[])) if saved_quote else getattr(session,'passenger_hint',None) or ''
    initial=[part.strip() for part in re.split(r'[、，,；;\r\n]+',hint) if part.strip()][:6]
    rows_key='business_passengers_'+session.sid+suffix+'_rows'
    rows=st.session_state.get(rows_key)
    if type(rows) is not int or not 1<=rows<=6:
        rows=max(1,len(initial))
        st.session_state[rows_key]=rows
    with st.form('business_booking_form_'+session.sid+suffix):
        seats=list(SEATS)
        seat=st.selectbox('选择席别',seats,index=seats.index(selected.get('seat_class') or seats[0]),
                          format_func=SEATS.get,key='business_seat_'+session.sid+suffix)
        heading,add_col=st.columns([5,1.7])
        with heading:
            st.markdown('**乘车人信息**')
            st.caption('逐个添加，最多 6 名；一栏里也可粘贴「张三、李四」。')
        with add_col:
            add_clicked=st.form_submit_button('＋ 添加乘车人',width='stretch',
                                              disabled=rows>=6,help='每单最多 6 名乘车人')
        entered=[]
        for index in range(rows):
            default=initial[index] if index<len(initial) else ''
            entered.append(st.text_input('乘车人 '+str(index+1),value=default,
                                         key='business_passengers_'+session.sid+suffix+'_'+str(index+1),
                                         placeholder='姓名，例如：张三'))
        st.selectbox('证件类型',['居民身份证'],key='business_doc_type_'+session.sid+suffix)
        doc_no=st.text_input('身份证号码（仅本地校验）',type='password',key='business_doc_'+session.sid+suffix,
                             placeholder='18 位；不写入订单数据库')
        phone=st.text_input('手机号码（仅本地校验）',type='password',key='business_phone_'+session.sid+suffix,
                            placeholder='11 位；不写入订单数据库')
        st.selectbox('乘客类型',['成人','儿童','学生'],key='business_ptype_'+session.sid+suffix)
        st.caption('证件号与手机号仅在本页做格式校验，不写入订单数据库、Trace 或普通日志。')
        submitted=st.form_submit_button('提交并生成订单',type='primary',width='stretch')
    if add_clicked:
        st.session_state[rows_key]=min(6,rows+1)
        st.rerun()
    names_text='、'.join(value.strip() for value in entered if isinstance(value,str) and value.strip())
    passengers,errors=booking_inputs(names_text,doc_no,phone)
    failure=None
    if submitted:
        if errors:
            for error in errors:st.warning(error)
        else:
            with st.spinner('正在查询余票并生成模拟订单'):
                failure=_request_booking_quote(session,selected,seat,passengers)
            if failure:st.error(failure)
    booking=getattr(session,'booking_passengers',None) or {}
    q=active_booking_quote(session,selected)
    if q and not (submitted and (errors or failure)):
        st.caption(f"{selected.get('trip_short_name') or selected['trip_id']} · {SEATS[q['seat_class']]}"
                   + (f" · 查询时模拟余票 {booking['available']} 张" if type(booking.get('available')) is int else ''))
        st.info('总价 ¥'+f"{q['total_fen']/100:.2f}"+' · '+str(q['passenger_count'])+' 人；提交后直接生成模拟订单，订单卡片显示在主对话，右栏只留只读凭证供讲解。')
        matches=passengers==booking.get('names') and seat==q['seat_class']
        if not matches:st.caption('乘客或席别已变化，请重新查询报价。')
        elif submitted and not errors and not failure:
            _auto_create_order(session,selected,q,passengers)


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
            with st.expander('余票与报价',expanded=True):
                booking_panel(session,selected)
    if rail.get('orders'):
        st.markdown('### 我的订单')
        if session.read_only:
            from target.v39.read_model import passenger_status_text
            from web.business_state import customer_status_text
            for o in rail['orders']:
                with st.container(border=True):
                    st.write(customer_status_text(o));st.caption('已支付 ¥'+f"{o['net_paid_fen']/100:.2f}")
                    with st.expander('乘客与交易'):
                        st.dataframe([dict(乘客=i['passenger_name'],状态=passenger_status_text(o,i)) for i in o['items']],hide_index=True)
                        st.json(o['transactions'],expanded=False)
            st.caption('历史会话只读；不会恢复确认令牌或自动继续旧交易。')
            try:
                from web.v39_payment import panel as payment_qr
                payment_qr(session,rail,read_only=True)
            except (ValueError,TypeError):
                st.caption('支付二维码状态暂不可读取；未执行支付。')
        elif not rail.get('pending_proposals'):
            from web.railway_simulation import _orders
            with scope(session._v39_effective):_orders(session._v39_service,session._v39_context,rail,session)
        else:
            from target.v39.read_model import passenger_summary
            for o in rail['orders']:st.caption(o['order_id']+' · '+o['order_status']+' · '+passenger_summary(o))
    if view.get('legacy'):
        with st.expander('原订单',expanded=not bool(rail.get('orders'))):
            for order in view['legacy']:st.caption(order['order_id']+' · '+order['train_no']+' · '+order['display_status'])
            st.caption('原票务数据；与GTFS铁路订单独立，操作入口保留在原订单面板。')
    if view.get('error'):st.warning('当前业务状态读取未完成，请核对数据库与会话；未使用旧缓存代替。')
    if view.get('recommendations'):
        st.markdown('### 推荐车次')
        legacy=all(t.get('source')=='LEGACY_DEMO' for t in view['recommendations'])
        st.caption('数据来源与口径见右上角「数据来源说明」。')
        for train in view['recommendations']:
            st.caption(str(train.get('trip_short_name') or train.get('trip_id') or train.get('train_no'))+' · '+str(train.get('departure_at') or train.get('depart') or '时刻未提供')+' → '+str(train.get('arrival_at') or train.get('arrive') or '时刻未提供'))


def money(fen):
    """RMB amount with an explicit 元 unit (never a bare symbol)."""
    try:value=int(fen or 0)/100
    except (TypeError,ValueError):return '金额待核验'
    return f'{value:,.2f} 元'


def receipts(session):
    """What this page operation just did, once.

    Internal operation kinds, status codes, model-call notes and simulation
    disclaimers belong in the developer workspace, not on a booking receipt.
    The line is labelled as this step's result and can be dismissed, so a green
    bar never reads like an old success that is still true.
    """
    view=current(session);rail=view.get('railway') or {}
    rows=getattr(session,'business_receipts',[])
    if not rows:return
    last=rows[-1]
    if last.get('session_id')!=session.sid:return
    action=last.get('actual_result') or {}
    status=last['status']
    o=next((o for o in rail.get('orders',[]) if o['order_id']==last.get('order_id')),None)
    operation=str(last.get('operation_id') or last.get('order_id') or '')
    ack='receipt_ack_'+str(session.sid)
    if operation and st.session_state.get(ack)==operation:return
    after=last.get('after') if isinstance(last.get('after'),dict) else {}
    oid=str(last.get('order_id') or (o or {}).get('order_id') or '')
    text=None
    if status=='UNKNOWN':
        text=('warning','订单状态待核验，请稍后查看，暂不要重复操作。')
    elif status=='PARTIAL':
        text=('error','订单信息不一致，已暂停后续操作，请稍后再试。')
    elif status=='FAILED':
        text=('error','本次操作未完成，请核对订单状态后再试。')
    elif status=='BLOCKED' and action.get('status')!='CONFIRMATION_REQUIRED':
        text=('warning','本次操作未完成，请核对订单状态后再试。')
    elif status=='SUCCEEDED' and last.get('action')=='PAY' and o:
        text=('success','支付成功 · 实付 '+money(o.get('net_paid_fen') if o.get('net_paid_fen') is not None else o.get('total_fen'))+
              ' · 订单 '+oid)
    elif status=='SUCCEEDED' and last.get('action')=='REFUND':
        refunded=after.get('refunded_total_fen')
        text=('success','退票已完成'+((' · 已退 '+money(refunded)) if type(refunded) is int and refunded>0 else ' · 退款按原支付渠道退回')+
              ' · 订单 '+oid)
    elif status=='SUCCEEDED' and last.get('action')=='CHANGE':
        text=('success','改签已完成 · 新车票已生效，差价多退少补 · 订单 '+oid)
    elif status=='SUCCEEDED' and last.get('action')=='CANCEL':
        text=('success','订单已取消 · 订单 '+oid)
    if text is None:return
    kind,message=text
    close_key='receipt_close_'+(operation or str(session.sid))
    body,close=st.columns([8,1.1],vertical_alignment='center')
    getattr(body,kind)(message)
    if close.button('知道了',key=close_key,width='stretch'):
        if operation:st.session_state[ack]=operation
        st.rerun()
    body.caption('本次操作结果；关闭后不再显示。')
