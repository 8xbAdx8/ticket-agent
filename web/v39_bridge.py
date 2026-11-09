"""Bridge the existing Ticket Agent UI/Agent to the existing V3.9 service.

The original user workspace remains authoritative. This module only supplies the
trusted per-session V3.9 context, service scope and a small right-rail fragment.
It never replaces the old eight tools, the original page layout, or D9/P01.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import hashlib
import os
import threading
import time
from contextvars import ContextVar

import streamlit as st

import config
from target.v39.context import Context, CURRENT as V39_CURRENT, digest
from target.v39.policy import Policy, VERSION as POLICY_VERSION
from target.v39.registry import SERVICE, NAMES as RAILWAY_NAMES, enabled, service_scope
from target.v39.service import Service
from target.v39.static import RailwayStatic, VERSION as DATASET_VERSION
from target.v39.store import Store

_SERVICES: dict[str, Service] = {}
_LOCK = threading.RLock()
_ACTIVE_SESSION = None
_SERVICE_CLOCK=ContextVar('railway_service_clock',default=None)


def _db_path() -> Path:
    explicit = os.getenv("RAILWAY_SIM_DB_PATH", "").strip()
    if explicit:
        return Path(explicit).resolve()
    day = date.today().isoformat()
    return (config.BASE_DIR / "artifacts/runtime/v392-user" / day / "simulation.sqlite").resolve()


def _service(path: Path) -> Service:
    key = str(path.resolve())
    with _LOCK:
        service = _SERVICES.get(key)
        if service is None:
            service = Service(Store(path), RailwayStatic(), policy=Policy(),clock=_SERVICE_CLOCK.get())
            service.start()
            service.scenario("railway-demo", DATASET_VERSION)
            _SERVICES[key] = service
        return service


def _default_effective(session):
    from target.execution_config import resolve_effective_config
    engine, live, provider, model = session.baseline_binding
    return resolve_effective_config(
        session.sid, "developer_custom", engine=engine,
        provider=provider if live else "mock", model=model if live else None,
        full_tools=bool(session.full_tools), allow_embedding=bool(session.allow_rag_network),
    )


def _v39_names(session, effective) -> tuple[str, ...]:
    # A feature flag is not a grant of permissions. Match the established
    # original-tool gates, including explicit Developer Override revocations.
    required={n:('query_tickets',) for n in RAILWAY_NAMES[:5]}
    required.update(railway_create_order=('lock_seat','create_order'),
                    railway_get_order=('query_order',),railway_pay_order=('pay_order',),
                    railway_cancel_order=('cancel_order',),railway_refund_order=('cancel_order',),
                    railway_change_order=('lock_seat','create_order','cancel_order'))
    candidates=RAILWAY_NAMES[:5] if effective.provider!='mock' and not session.full_tools else RAILWAY_NAMES
    return tuple(n for n in candidates if all(t in effective.tool_whitelist for t in required[n]))


def prepare(session, effective=None):
    """Create/attach the per-session service and context; no UI side effects."""
    if not enabled() or session.execution_mode == "baseline":
        return None
    from web.simulation_clock import binding
    bound_path,simulation_clock=binding(session)
    if effective is None:
        effective = session.resolve_config() or _default_effective(session)
    names = tuple(dict.fromkeys((*effective.tool_whitelist, *_v39_names(session, effective))))
    suffix = (
        "\n当前会话已接入 V3.9 铁路静态数据与本地模拟交易。"
        "铁路车次/站/经停只能通过 railway_* 工具读取只读 GTFS Adapter；"
        "库存、票价、订单、支付、退款、改签均为本地模拟，不得称为官方实时数据。"
        "高风险操作只能创建 proposal，必须由用户在界面确认；模型不能确认交易。"
        "D9 已批准 CHANGED_REFUND_P01：改签后可退款，部分退款后可改签剩余 ACTIVE，"
        "每乘客最多一次成功退款，每订单最多一次成功改签；P01 为 >48h 5%、24-48h 10%、<24h 20%，整数分 half-up。"
        "只缺日期等一个必要条件时，只追问该条件，并沿用本会话已明确的其他条件；站名歧义要展示工具真实候选。"
        "不要猜测站点ID、日期或车次。查某车经停先用车次号查真实trip_id。"
        "班次总数必须逐字引用total_count，当前页数引用returned_count，不能心算列表长度或编造数量；"
        "has_more为真时说明尚有下一页；默认回答当前页即可，不要为默认查询自动翻完全部分页，只有用户明确要求下一页时才用next_cursor继续，不把当前页称为全部。"
        "不要逐行重复抄长车次表，简洁解释主要结果，完整表格由界面显示。"
        "GTFS是真实来源的静态时刻表；LOCAL_DEMO_ONLY仅为使用范围限制，不表示车次数据由Mock编造。"
        "SHAPE_UNAVAILABLE仅表示线路几何形状缺失，不表示车次停运、经停缺失或无法查询经停。"
        "铁路静态查询（包括连续补充日期）使用railway_*，不要混用旧query_tickets的演示车次；旧工具保留给明确的旧演示业务和航班等原有功能。"
        "V3.10铁路流程没有独立锁座工具，也不存在railway_lock_seat；此前legacy的lock_seat必须先锁座规则不适用于本会话。"
        "正确流程是：查询库存→生成报价→railway_create_order建单提案→用户界面确认→Service自动创建hold并锁座→PENDING_PAYMENT。"
        "用户说锁座时，解释建单确认后自动锁座；不得声称已经锁座，除非工具返回的订单和hold已由用户确认并存在。"
        "建单前必须取得用户明确提供的模拟乘客姓名；缺少姓名先追问，不能把‘请提供乘客姓名’等提示语当作姓名调用工具。"
        "工具返回NEEDS_INPUT时，只询问missing_fields对应信息；不得声称已生成提案、已锁座或已建单。"
    )
    recent=getattr(session,'railway_queries',[])
    if recent and recent[-1]['ok'] and recent[-1]['tool']=='railway_query_trips' and recent[-1]['result'].get('status')=='FOUND':
        import json
        known={k:v for k,v in recent[-1]['args'].items() if k in ('service_date','origin_stop_id','destination_stop_id','train_no')}
        suffix+='\n本会话最近快捷查询的明确条件（仅在用户沿用时参考，新条件覆盖旧条件）：'+json.dumps(known,ensure_ascii=False)
    # Remove the legacy lock-first rule from the V3.10 effective prompt. The
    # original SYSTEM_PROMPT remains untouched for legacy business.
    legacy_lock = "4. 下单前必须先 lock_seat 拿到 lock_id，不可跳过；"
    v310_lock = ("4. 本 V3.10 铁路流程不提供独立锁座工具；"
                 "锁座只能由用户在界面确认 railway_create_order 后，由 Service 自动创建 hold；")
    prompt = effective.prompt.replace(legacy_lock, v310_lock) + suffix
    if simulation_clock:
        import re
        day=simulation_clock.snapshot()['now'][:10]
        prompt=re.sub(r'当前北京时间日期 \d{4}-\d{2}-\d{2}', '当前铁路模拟北京时间日期 '+day,prompt)
        prompt+='\n本会话铁路业务使用独立暂停模拟时钟，clock_id='+simulation_clock.clock_id+'；今天/明天相对于上述模拟日期，确切时间以工具simulation_clock和页面为准。不可将模拟时间说成现实日期；用户只能在页面推进时间。'
    effective = replace(
        effective,
        prompt=prompt,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        tool_whitelist=names,
        config_hash=digest([effective.config_hash, names, prompt, "v393-original-ui"]),
    )
    path = bound_path or _db_path()
    try:
        clock_token=_SERVICE_CLOCK.set(simulation_clock)
        try:service = _service(path)
        finally:_SERVICE_CLOCK.reset(clock_token)
    except Exception:
        # Keep the original page usable; the rail/chat will show the actual
        # service error instead of silently switching to Mock.
        raise
    ctx = Context(
        session.sid, config.CURRENT_USER_PHONE, "railway-demo", enabled=True,
        execution_mode=effective.execution_mode, config_hash=effective.config_hash,
        config_revision=effective.override_revision, provider=effective.provider,
        tool_whitelist=names,
    )
    session._v39_service = service
    session._v39_context = ctx
    session._v39_effective = effective
    if simulation_clock and getattr(session,'root',None) and not (session.root/'session-replay.json').exists():session.save_replay()
    return service, ctx, effective


def activate(session, effective=None):
    """Set trusted ContextVars for the current serialized UI call.

    Original UI calls are serialized by CALL_LOCK. The context is refreshed on
    every Agent construction/chat and cleared between non-V39 sessions.
    """
    global _ACTIVE_SESSION
    prepared = prepare(session, effective)
    if prepared is None:
        deactivate()
        return None
    service, ctx, effective = prepared
    from target.execution_config import CURRENT as EFFECTIVE
    V39_CURRENT.set(ctx)
    SERVICE.set(service)
    EFFECTIVE.set(effective)
    _ACTIVE_SESSION = session.sid
    return effective


def deactivate():
    global _ACTIVE_SESSION
    from target.execution_config import CURRENT as EFFECTIVE
    V39_CURRENT.set(None)
    SERVICE.set(None)
    EFFECTIVE.set(None)
    _ACTIVE_SESSION = None


def current():
    prepared = getattr(_ACTIVE_SESSION, "sid", None)
    return prepared


def _session_context(session):
    prepared = prepare(session)
    if prepared is None:
        return None
    return prepared


def _notice(session, message, kind="success"):
    getattr(st, kind)(message)


def render(session):
    """Right-rail fragment for the original user workspace."""
    if not enabled() or session.read_only:
        return
    try:
        if not enabled():
            return
        prepared=prepare(session)
        if prepared is None:return
        service = getattr(session, "_v39_service", None)
        ctx = getattr(session, "_v39_context", None)
        effective = getattr(session, "_v39_effective", None)
        if service is None or ctx is None or effective is None:
            return
        from web.simulation_clock import controls
        controls(session,service)
        from web.railway_queries import panel
        panel(session,service,ctx,effective)
        from web.business_state import current
        snapshot=current(session).get('railway')
        pending=(snapshot or {}).get('pending_proposals',[]) if not session.read_only else []
        if pending:
            st.markdown("### 待确认铁路操作")
            labels = {"CREATE_ORDER": "锁定模拟座位并建单", "PAY": "模拟支付", "CANCEL": "取消模拟订单", "REFUND": "模拟退票", "CHANGE": "模拟改签"}
            for proposal in pending:
                pid = proposal["proposal_id"]
                st.caption(labels.get(proposal["action"], proposal["action"]) + " · " + pid)
                payload=proposal.get('payload') or {}
                preview=payload.get('_refund_preview') or payload.get('_display_preview') or {}
                if preview:
                    if 'net_fen' in preview:st.info('本次模拟退款 ¥'+f"{preview['net_fen']/100:.2f}"+'；手续费 ¥'+f"{preview['fee_fen']/100:.2f}")
                    elif 'difference_fen' in preview:st.info('改签差价 ¥'+f"{preview['difference_fen']/100:.2f}"+'（正数补款，负数退差）')
                    elif 'total_fen' in preview:st.info('本次模拟金额 ¥'+f"{preview['total_fen']/100:.2f}")
                if payload.get('passengers'):st.write('乘客：'+'、'.join(payload['passengers']))
                if payload.get('item_ids') and snapshot:
                    chosen={i['item_id']:i['passenger_name'] for o in snapshot['orders'] for i in o['items']}
                    st.write('本次乘客：'+'、'.join(chosen.get(i,'无法核验') for i in payload['item_ids']))
                if proposal.get('action')=='PAY' and snapshot:
                    from web.v39_payment import panel as payment_qr
                    payment_qr(session,snapshot,read_only=False)
                from target.v39.passengers import has_placeholders
                invalid_name=proposal['action']=='CREATE_ORDER' and has_placeholders(payload.get('passengers'))
                if invalid_name:st.warning('这张旧确认卡尚未包含有效乘客姓名，不能确认；请补充姓名重新生成，或撤销此卡。')
                ack = st.checkbox("我已核对，确认这次本地模拟操作", key="v39_bridge_ack_" + pid)
                c1, c2 = st.columns(2)
                if c1.button("确认", key="v39_bridge_yes_" + pid, disabled=not ack or invalid_name, type="primary"):
                    try:
                        result = session.confirm_railway_proposal(pid, True)
                        st.session_state["v39_bridge_notice"] = result
                        st.rerun()
                    except Exception as exc:
                        st.error("确认未完成：" + str(exc))
                if c2.button("撤销", key="v39_bridge_no_" + pid):
                    try:
                        session.confirm_railway_proposal(pid, False); st.rerun()
                    except Exception as exc:
                        st.error("撤销未完成：" + str(exc))
        notice = st.session_state.pop("v39_bridge_notice", None)
        if notice:
            if notice.get('error'):st.error('本地模拟操作未完成：'+str(notice['error']))
            else:st.success("本地模拟状态：" + str(notice.get("status", "")))
        st.caption("铁路静态时刻 + 本地模拟库存/价格/订单；不是官方实时数据。D9 B / P01 已批准。")
    except Exception as exc:
        st.caption("铁路模拟服务暂不可用：" + str(exc))
