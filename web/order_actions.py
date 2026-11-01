"""Order-card actions, not an Agent run or a new workspace/order dashboard."""
import json
import re
import sqlite3
import uuid
from decimal import Decimal
from contextlib import closing
import streamlit as st
from target import mock_core, reschedule
from web.runtime import CALL_LOCK
from web.presentation import order_card


def allowed(session):
    return (not session.read_only and session.mode=='user' and not session.pending_action()
            and (not session.live or session.full_tools))


def route_refund_request(session, message):
    """A train reference must not fall through to an Agent's latest-order guess."""
    if not allowed(session) or not re.search('退票|退掉|取消',message):return False
    if re.search('手续费|政策|规则|怎么|如何|[?？]|不要|不想|不退|取消退票|别',message):return False
    train=re.search(r'(?<![A-Za-z0-9])([GDC]\d{1,8})(?!\d)',message,re.I)
    if not train:return False
    day=re.search(r'\d{4}-\d{2}-\d{2}',message)
    st.session_state['p3_refund_query']={'sid':session.sid,'args':(train[1].upper(),day[0] if day else None,None,None)}
    st.session_state['p3_refund_open']=session.sid
    return True


def database(session, *, write=False):
    if session.read_only or (write and not allowed(session)):
        raise ValueError('当前会话没有本次订单操作权限')
    path=session.root/'tickets.db'
    if not path.is_file():raise ValueError('当前会话尚无演示订单')
    return path


def snapshot(session, order):
    path=session.root/'page-order-state.json'
    saved={'session_id':session.sid,'orders':{}}
    if path.is_file():saved=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(saved,dict) or saved.get('session_id')!=session.sid or not isinstance(saved.get('orders'),dict):raise ValueError('订单展示会话不匹配')
    saved['orders'][order['order_id']]={k:v for k,v in order.items() if k not in ('phone','passengers')}
    temporary=path.with_name('page-state-'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(saved,ensure_ascii=False),encoding='utf-8');temporary.replace(path)


def replay_order(session, order):
    if session is None or not session.read_only:return order
    path=session.root/'page-order-state.json'
    try:
        if path.is_symlink() or path.stat().st_size>256*1024:return order
        saved=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved,dict) or not isinstance(saved.get('orders'),dict):return order
        row=saved['orders'].get(order['order_id'])
        if saved['session_id']==session.sid and isinstance(row,dict) and row.get('order_id')==order['order_id']:
            return {**order,**row}
    except (OSError,ValueError,KeyError,TypeError):pass
    return order


def execute(session, kind, proposal, *, confirmed=False):
    if confirmed is not True:raise ValueError('请先明确确认本次操作')
    with CALL_LOCK:
        path=database(session,write=True)
        with mock_core.database_scope(path):
            if kind=='refund':
                result=mock_core.cancel_order(proposal['order_id'],expected=proposal,source='page')
            elif kind=='reschedule':result=reschedule.confirm(path,proposal,source='page')
            else:raise ValueError('不支持的页面操作')
            if result.get('error'):raise ValueError(result['error'])
            current=mock_core.query_order(proposal['order_id'])
            try:snapshot(session,current)
            except (OSError,ValueError,TypeError):
                session.persistence_warning='操作已完成，但刷新展示记录未保存，请保留当前会话核对订单。'
            return current


def _finish(session,kind,proposal):
    try:
        current=execute(session,kind,proposal,confirmed=True)
        st.session_state['p3_notice']={'sid':session.sid,'kind':kind,'order':current}
        st.session_state.pop('p3_reschedule',None)
        st.rerun()
    except ValueError as e:st.warning(str(e))
    except (OSError,sqlite3.Error):st.warning('本次操作未确认完成，请核对订单；没有自动重试。')


def notice(session):
    item=st.session_state.get('p3_notice') or {}
    if item.get('sid')==session.sid:
        st.success('演示退票/取消已完成，不产生真实退款。' if item['kind']=='refund' else '演示改签已完成，差价仅记录，不产生真实收款或退款。')
        st.markdown(order_card(item['order']),unsafe_allow_html=True)


def card_actions(session, order, verified, namespace=""):
    if session is None:return
    if order.get('has_reschedules'):
        st.warning('该订单已办理改签，根据当前示例政策P02，改签后的车票不支持退票。')
        st.caption('每张票仅可改签一次，不能再次改签。')
        return
    if not verified or not allowed(session):return
    if order.get('actions',{}).get('reschedule',{}).get('allowed') is False:
        st.caption(order['actions']['reschedule']['reason']);return
    if order.get('status')=='paid':
        if st.button('改签',key='p3_change_'+session.sid+'_'+order['order_id']+namespace):
            st.session_state['p3_reschedule']={'sid':session.sid,'order_id':order['order_id'],**({'scope':namespace} if namespace else {})}
        pending=st.session_state.get('p3_reschedule') or {}
        if pending=={'sid':session.sid,'order_id':order['order_id'],**({'scope':namespace} if namespace else {})}:
            change_panel(session,order)


def change_panel(session, order):
    with st.container(border=True,key='p3_change_panel'):
        st.markdown('**订单改签 · 自动带入当前订单**')
        st.write('原订单号：'+order['order_id'])
        st.write('原车次：'+order['train_no']+' · '+order['date']+' · '+order['seat_type'])
        st.write('原票价：¥'+str(order['amount']))
        st.caption('仅当前用户已支付高铁订单可改签一次；差价仅记录，不会真实收款或退款。')
        with closing(sqlite3.connect(database(session).resolve().as_uri()+'?mode=ro',uri=True)) as c:
            c.row_factory=sqlite3.Row
            old=c.execute('SELECT * FROM inventory WHERE train_no=? AND date=? AND seat_type=?',(order['train_no'],order['date'],order['seat_type'])).fetchone()
            if not old or old['kind']!='高铁':st.info('当前改签仅支持已支付的高铁订单。');return
            rows=[dict(r) for r in c.execute("SELECT * FROM inventory WHERE kind='高铁' ORDER BY date,train_no,seat_type")]
        rows=[r for r in rows if (r.get('from_city'),r.get('to_city'))==(dict(old).get('from_city'),dict(old).get('to_city'))]
        dates=sorted({r['date'] for r in rows})
        if not dates:st.info('没有可选目标车次。');return
        key=session.sid+'_'+order['order_id']
        day=st.selectbox('目标日期',dates,index=dates.index(order['date']) if order['date'] in dates else 0,key='p3_date_'+key)
        trains=sorted({r['train_no'] for r in rows if r['date']==day and (r['train_no'],r['date'],r['seat_type'])!=(order['train_no'],order['date'],order['seat_type'])})
        if not trains:st.info('没有其他目标车次。');return
        train=st.selectbox('目标车次',trains,key='p3_train_'+key)
        seats=sorted({r['seat_type'] for r in rows if r['date']==day and r['train_no']==train and (train,day,r['seat_type'])!=(order['train_no'],order['date'],order['seat_type'])})
        seat=st.selectbox('目标席别',seats,key='p3_seat_'+key)
        signature=(session.sid,order['order_id'],train,day,seat)
        if st.button('预览差价',key='p3_preview_'+key):
            st.session_state.pop('p3_proposal',None)
            try:
                with CALL_LOCK:p=reschedule.preview(database(session),order['order_id'],train,day,seat)
                st.session_state['p3_proposal']={'signature':signature,'value':p}
            except ValueError as e:st.warning(str(e))
        saved=st.session_state.get('p3_proposal') or {}
        if saved.get('signature')==signature:
            p=saved['value'];difference=Decimal(p['difference'])
            st.write('新票价：¥'+p['new_amount'])
            st.write(('应补差额（仅记录）：¥' if difference>0 else '应退差额（仅记录）：¥' if difference<0 else '无差价：¥')+str(abs(difference)))
            st.caption('预览未改变订单和库存。确认时将重新校验，改签后不支持退票（P02）。')
            if st.button('确认改签',key='p3_confirm_'+key):_finish(session,'reschedule',p)


def refund_panel(session):
    if not allowed(session):return
    with st.expander('按车次退票 / 取消演示订单',expanded=st.session_state.get('p3_refund_open')==session.sid):
        st.caption('只查当前会话中本人的订单。请输入准确日期；不会按车次批量取消。')
        with st.form('p3_refund_search'):
            train=st.text_input('退票车次',key='p3_refund_train')
            day=st.date_input('出行日期',value=None,key='p3_refund_date')
            seat=st.text_input('席别（可选）',key='p3_refund_seat')
            passenger=st.text_input('乘客（可选）',key='p3_refund_passenger')
            search=st.form_submit_button('查找可退订单')
        if search:
            st.session_state['p3_refund_query']={'sid':session.sid,'args':(train.strip(),day.isoformat() if day else None,seat.strip() or None,passenger.strip() or None)}
        request=st.session_state.get('p3_refund_query') or {}
        if request.get('sid')!=session.sid:return
        st.caption('当前匹配：'+str(request['args'][0])+' · '+str(request['args'][1] or '请补充日期'))
        try:
            with CALL_LOCK,mock_core.database_scope(database(session)):
                matched=mock_core.cancel_order_by_train(*request['args'])
        except ValueError as e:st.warning(str(e));return
        if matched.get('error'):st.info(matched['error']);return
        rows=matched['orders']
        if not rows:st.info(matched['message']);return
        by_id={r['order_id']:r for r in rows}
        selected=st.selectbox('选择要退的订单',list(by_id),index=None,
            format_func=lambda oid:oid+' · '+by_id[oid]['train_no']+' · '+by_id[oid]['date']+' · '+by_id[oid]['seat_type']+' · '+','.join(by_id[oid]['passengers']),key='p3_refund_selected_'+session.sid)
        if not selected:return
        row=by_id[selected];st.markdown(order_card(row),unsafe_allow_html=True)
        st.write(row['from_city']+' → '+row['to_city']+' · 乘客：'+','.join(row['passengers']))
        st.write('是否已改签：'+('是' if row['has_reschedules'] else '否'))
        q=row['quote']
        if q.get('error'):st.warning(q['error']);return
        signature=(session.sid,selected,request['args'])
        if st.button('预览退票费用',key='p3_refund_preview_'+session.sid):
            st.session_state['p3_refund_quote']={'signature':signature,'value':q}
        saved=st.session_state.get('p3_refund_quote') or {}
        if saved.get('signature')!=signature:return
        q=saved['value']
        st.write('预计手续费：¥'+str(q['fee'])+' · 费率 '+str(int(q['fee_rate']*100))+'% · 预计退款：¥'+str(q['refund']))
        st.caption('来源：'+q['policy_ref']+'，仅本地演示，不产生真实退款。')
        if st.button('确认退票 / 取消订单',key='p3_refund_confirm_'+session.sid):_finish(session,'refund',q)
