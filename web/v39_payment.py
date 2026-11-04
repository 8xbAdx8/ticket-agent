"""V3.10 mock-payment QR projection.

The QR is a deterministic presentation of the committed V3.9 order and an
active PAY proposal. It is never a payment credential and is never stored as
an image: a page refresh regenerates it from SQLite.
"""
from __future__ import annotations

from decimal import Decimal

import streamlit as st

from target.payment_qr import render_qr


def _order_for(snapshot, proposal):
    order_id = (proposal.get("payload") or {}).get("order_id") or proposal.get("order_id")
    return next((o for o in (snapshot or {}).get("orders", []) if o.get("order_id") == order_id), None)


def eligible(snapshot, proposal):
    """Return (order, amount_yuan) only for a live, matching PAY proposal."""
    if not isinstance(proposal, dict) or proposal.get("action") != "PAY":
        return None
    if proposal.get("state") != "PENDING":
        return None
    try:
        if proposal.get("expires_at", "") <= (snapshot or {}).get("updated_at", ""):
            return None
    except (TypeError, ValueError):
        return None
    order = _order_for(snapshot, proposal)
    if not order or order.get("order_status") != "PENDING_PAYMENT":
        return None
    if order.get("payment_status") != "UNPAID" or order.get("hold_expired_at_read"):
        return None
    total = order.get("total_fen")
    expected = (proposal.get("payload") or {}).get("expected_total_fen")
    if type(total) is not int or total <= 0 or expected != total:
        return None
    return order, Decimal(total) / Decimal(100)


def panel(session, snapshot, *, read_only=False):
    """Render the QR for the one active PAY proposal. No business writes."""
    pending = (snapshot or {}).get("pending_proposals") or []
    proposal = next((p for p in pending if p.get("action") == "PAY"), None)
    found = eligible(snapshot, proposal) if proposal else None
    if not found:
        # An order waiting for a fresh payment proposal is actionable through
        # the existing order panel; an expired proposal must not look payable.
        if any(o.get("order_status") == "PENDING_PAYMENT" for o in (snapshot or {}).get("orders", [])):
            st.caption("支付提案尚未生成或已过期；请重新生成模拟支付确认卡。")
        return
    order, amount = found
    st.markdown("### 模拟支付二维码")
    st.caption("订单 " + order["order_id"] + " · ¥" + f"{amount:.2f}" + " · CNY · 本地模拟")
    method = st.selectbox(
        "模拟支付方式",
        ["alipay", "wechat"],
        format_func=lambda v: "支付宝（模拟）" if v == "alipay" else "微信（模拟）",
        key="v39_qr_method_" + order["order_id"],
        disabled=read_only,
    )
    try:
        image = render_qr(order["order_id"], amount, str(amount))
        st.image(image, width=190, caption="本地模拟支付二维码；扫码不会真实扣款")
    except (ValueError, TypeError, OSError):
        st.warning("模拟支付二维码暂时无法生成；订单未支付，请核对订单和支付提案。")
        return
    st.caption("二维码只包含订单号、金额、币种和 demo 标识，不含乘客、证件、手机号或真实支付凭据。")
    st.caption("支付方式：" + ("支付宝（模拟）" if method == "alipay" else "微信（模拟）"))
    if read_only:
        st.info("历史会话只读：可查看二维码和真实订单状态，但不能在历史页确认支付。")
    else:
        st.caption("请在上方/下方“待确认铁路操作”勾选并确认；确认后仍由 V3.10 交易服务提交 PAYMENT。")
