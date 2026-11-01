"""Scheme B: informational QR, followed by explicit in-app confirmation."""
import json
import sqlite3
import uuid
import streamlit as st
from target.payment_qr import render_qr, yuan


def _receipts(session):
    path = session.root/'demo-payment-receipts.json'
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 256*1024:
        raise ValueError('演示支付展示记录不可用')
    saved = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(saved, dict) or saved.get('schema') != 'ticket-demo-payments/1' or saved.get('session_id') != session.sid:
        raise ValueError('演示支付会话不匹配')
    orders = saved.get('orders')
    if not isinstance(orders, dict) or any(not isinstance(k,str) or not isinstance(v,dict) for k,v in orders.items()):
        raise ValueError('演示支付展示记录格式无效')
    return orders


def save_receipt(session, order):
    """New display evidence only, for the existing read-only page-reload path."""
    if order.get('status') != 'paid':
        raise ValueError('未确认演示支付成功')
    orders = _receipts(session)
    orders[order['order_id']] = {k:order[k] for k in ('order_id','amount','status','pay_type','paid_at') if k in order}
    raw = json.dumps({'schema':'ticket-demo-payments/1','session_id':session.sid,'orders':orders},ensure_ascii=False)
    if len(raw.encode('utf-8')) > 256*1024:
        raise ValueError('演示支付展示记录已达上限')
    temporary = session.root/('demo-payment-'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(raw,encoding='utf-8')
    temporary.replace(session.root/'demo-payment-receipts.json')


def current_order(session, recorded):
    if session is None:
        return recorded, False
    if session.read_only:
        # Restoring history remains DB/model/API-free and never restores consent.
        try:
            receipt = _receipts(session).get(recorded['order_id']) or {}
            if (recorded.get('status') in ('pending','paid') and receipt.get('status')=='paid'
                    and receipt.get('order_id')==recorded['order_id']
                    and yuan(recorded.get('amount'))==yuan(receipt.get('amount'))):
                return {**recorded, **receipt}, False
        except (OSError, ValueError, TypeError):
            pass
        return recorded, False
    try:
        from target.order_read_model import orders
        from web.runtime import CALL_LOCK
        with CALL_LOCK:rows=orders(session.root/'tickets.db',recorded['order_id'])
        current=rows[0] if rows else {'error':'订单不可核验'}
    except (OSError, sqlite3.Error):
        return recorded, False
    if current.get('error'):
        return recorded, False
    return current, True


def controls(session, order, *, verified=False, namespace=""):
    if not verified or session is None or session.read_only:
        return
    if order.get('status') == 'paid':
        st.success('演示支付成功，订单已标记为已支付；不会真实扣款或出票。')
        return
    if order.get('status')=='pending' and order.get('actions',{}).get('pay',{}).get('allowed') is False:
        st.info(order['actions']['pay']['reason']);return
    if order.get('status') != 'pending':
        return
    if getattr(session, 'live', False) and not getattr(session, 'full_tools', False):
        st.info('当前在线会话仅支持查询，没有演示支付入口。')
        return
    with st.container(key='demo_payment_'+order['order_id']+namespace):
        st.caption('以下为当前演示订单状态；对话保留当时记录。')
        try:
            qr_bytes = render_qr(order['order_id'], order['amount'], order['amount'])
            st.image(qr_bytes, width=180)
        except Exception:
            st.warning('演示二维码暂时无法生成，订单未支付；仍可在下方确认演示支付。')
        st.warning('演示二维码，扫码不会真实扣款。')
        st.caption('扫码只显示订单识别信息，不会通知本应用。请回到这里确认演示支付；无需连接支付宝或微信。')
        key = session.sid+'_'+order['order_id']+'_'+str(order['amount'])+namespace
        consent = st.checkbox('我确认仅演示支付，不会真实扣款', key='payment_consent_'+key)
        selected = st.selectbox('扫码后的演示支付方式', ['alipay','wechat'],
                               format_func=lambda x: '支付宝' if x=='alipay' else '微信',
                               key='payment_method_'+key)
        pending = st.session_state.get('pending_operation') or {}
        disabled = not consent or bool(session.pending_action()) or pending.get('sid') == session.sid
        alipay = st.button('使用支付宝支付', key='payment_alipay_'+key, disabled=disabled)
        wechat = st.button('使用微信支付', key='payment_wechat_'+key, disabled=disabled)
        scanned = st.button('我已扫码，确认演示支付', key='payment_scan_'+key, disabled=disabled)
        if alipay or wechat or scanned:
            method = 'alipay' if alipay else 'wechat' if wechat else selected
            try:
                result = session.confirm_demo_payment(order['order_id'], order['amount'], method,
                                                      confirmed=consent is True)
                if result.get('error'):
                    st.warning('演示支付未完成：'+result['error'])
                else:
                    if not result.get('duplicate_pay') and hasattr(session,'root'):
                        try:
                            from target.order_refund import page_event
                            with sqlite3.connect(session.root/'tickets.db') as audit_db:
                                page_event(audit_db,'payment',order['order_id'],result)
                        except (OSError,sqlite3.Error):
                            session.persistence_warning='演示支付已记录，页面审计保存失败；请核对订单，不要重复支付。'
                    st.rerun()
            except (ValueError, OSError, sqlite3.Error):
                st.warning('演示支付未完成，请核对当前订单及权限后再确认。')
