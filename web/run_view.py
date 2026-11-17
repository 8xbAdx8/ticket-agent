"""User-facing run state, derived only from events recorded for one ``run_id``.

Nothing in this module invents a phase, a duration or a tool result. Every value
comes from the rows ``target/run_events.py`` wrote while the run executed, so a
missing phase is shown as 未发生 and a run without events is shown as 未记录.
"""
from pathlib import Path

from web.design import event_label
from web.evidence import read_jsonl
from web.presentation import TOOL_LABELS, escape

PHASES = (("query", "查票"), ("policy", "检索政策"), ("confirm", "等待确认"),
          ("execute", "执行模拟操作"), ("done", "完成"))
QUERY_TOOLS = {"query_tickets","railway_search_stations","railway_query_trips","railway_trip_stops","railway_check_inventory","railway_quote_fare"}
POLICY_TOOLS = {"search_policy"}
WRITE_TOOLS = {"monitor_seat", "lock_seat", "create_order", "pay_order", "cancel_order", "railway_create_order", "railway_pay_order", "railway_cancel_order", "railway_refund_order", "railway_change_order"}

STATUS_TEXT = {"done": "已完成", "failed": "失败", "blocked": "已拦截", "active": "进行中",
               "waiting": "等待确认", "declined": "已取消", "pending": "未发生", "unknown": "未记录"}
RESULT_STATUS = {"succeeded": "done", "failed": "failed", "blocked": "blocked"}


def load_events(trace_dir, run_id, session_id=None):
    """Return the recorded events of one run; never merge a different run_id."""
    if not run_id or trace_dir is None:
        return [], {"missing": True, "invalid": 0, "truncated": False}
    rows, meta = read_jsonl(Path(trace_dir) / "run_events.jsonl", limit=10000)
    selected=[row for row in rows if row.get("run_id") == run_id
              and (session_id is None or row.get('session_id')==session_id)]
    from datetime import datetime
    try:
        selected=sorted(selected,key=lambda e:datetime.fromisoformat(e['timestamp']))
        meta=dict(meta,ordering='recorded_timestamp')
    except (KeyError,ValueError,TypeError):
        meta=dict(meta,ordering='saved_order_timestamp_incomplete')
    return selected, meta


def latest_run(session):
    """The last audit, its run_id, and that run's own events."""
    audit = session.audits[-1] if getattr(session, "audits", None) else None
    run_id = (audit or {}).get("trace_id")
    events, meta = load_events(getattr(session, "trace_dir", None), run_id,session.sid)
    return audit, events, meta


EXECUTION_STAGES=(
    ('用户输入',{'user_input'}),
    ('模型 / 规则与工具选择',{'agent_start','agent_decision','model_start','model_end','model_error','model_tool_proposed'}),
    ('RAG 检索',{'rag_start','rag_result','rag_error'}),
    ('工具与权限',{'tool_proposed','permission_check','parameter_validation','tool_start','tool_result','railway_tool_result','railway_tool_error','tool_message_created','tool_result_in_model_request'}),
    ('用户确认',{'confirmation_requested','user_confirmation','confirmation_declined','operation_resumed'}),
    ('最终回答与结束',{'agent_returned','agent_error','run_finished'}),
)


def execution_stages(events):
    """Absence is known only for a completed, P1-instrumented run, never old gaps."""
    complete=any(e.get('event_type')=='run_finished' and e.get('coverage_version')=='p1/1' for e in events)
    result=[]
    for label,kinds in EXECUTION_STAGES:
        rows=[e for e in events if e.get('event_type') in kinds]
        # agent_start proves entry, not a model request or a model decision.
        activity=[e for e in rows if e.get('event_type')!='agent_start']
        if not activity:
            status='未发生' if complete else '未记录'
            if label=='RAG 检索' and any(e.get('tool')=='search_policy' and
                e.get('event_type') in ('tool_start','tool_result') and e.get('executed') is not False
                for e in events):status='未记录'
        elif any(e.get('status')=='failed' for e in activity):status='失败'
        elif any(e.get('status')=='blocked' for e in activity):status='已拦截'
        elif label=='用户确认':
            status=('已确认' if any(e.get('event_type')=='user_confirmation' and e.get('approved') is True for e in activity)
                    else '已取消' if any(e.get('status')=='declined' for e in activity) else '等待确认')
        elif label=='RAG 检索':
            status=('没有足够证据' if any(e.get('status')=='insufficient_evidence' for e in activity)
                    else '已返回证据' if any(e.get('event_type')=='rag_result' for e in activity) else '执行中' if not complete else '未记录')
        elif label=='模型 / 规则与工具选择':
            status=('已返回' if any(e.get('event_type')=='model_end' for e in activity)
                    else '已澄清（规则）' if any(e.get('event_type')=='agent_decision' for e in activity)
                    else '执行中' if not complete else '未记录')
        else:status='已记录'
        result.append({'stage':label,'status':status,'event_ids':[e.get('event_id') for e in activity]})
    return result


def _phase_of(tool):
    if tool in QUERY_TOOLS:
        return "query"
    if tool in POLICY_TOOLS:
        return "policy"
    if tool in WRITE_TOOLS:
        return "execute"
    return None


def phase_states(events):
    """Five states in execution order; each one only from what was recorded."""
    state = {key: {"key": key, "label": label, "status": "pending", "detail": ""} for key, label in PHASES}
    if not events:
        for item in state.values():
            item["status"] = "unknown"
        return [state[key] for key, _ in PHASES]

    for event in events:
        kind, status, tool = event.get("event_type"), event.get("status"), event.get("tool")
        phase = _phase_of(tool)
        if kind in ("tool_proposed", "tool_start") and phase and state[phase]["status"] in ("pending", "unknown"):
            state[phase]["status"] = "active"
            state[phase]["detail"] = "已提议 · " + TOOL_LABELS.get(tool, str(tool))
        if kind in ("tool_result","railway_tool_result","railway_tool_error") and phase:
            state[phase]["status"] = RESULT_STATUS.get(status, "unknown")
            duration = event.get("duration_ms")
            detail = TOOL_LABELS.get(tool, str(tool))
            state[phase]["detail"] = detail + (f" · {duration} ms" if isinstance(duration, int) else "")
            if phase=='execute' and isinstance(event.get('output'),dict) and event['output'].get('status')=='CONFIRMATION_REQUIRED':
                state['execute']['status']='pending';state['execute']['detail']='尚未执行交易'
                state['confirm'].update(status='waiting',detail='等待用户核对确认卡')
            if phase=='execute' and isinstance(event.get('output'),dict) and event['output'].get('status')=='NEEDS_INPUT':
                state['execute'].update(status='pending',detail='等待补充乘客姓名；尚未生成提案或执行交易')
        if kind == "confirmation_requested":
            state["confirm"]["status"] = "waiting"
            state["confirm"]["detail"] = TOOL_LABELS.get(tool, str(tool)) + " · 等待用户确认"
        if kind == "operation_resumed":
            approved = status == "approved"
            state["confirm"]["status"] = "done" if approved else "declined"
            state["confirm"]["detail"] = "用户已确认" if approved else "用户已取消"
            if approved:
                state["execute"]["status"] = "active"
                state["execute"]["detail"] = "恢复模拟操作"
        if kind == "confirmation_declined":
            state["confirm"]["status"] = "declined"
            state["confirm"]["detail"] = "用户已取消"
        if kind == "rag_result" and state["policy"]["status"] in ("pending", "unknown"):
            hits = event.get("documents") or []
            state["policy"]["status"] = "active"
            state["policy"]["detail"] = f"{len(hits)} 条检索结果"
        if kind == "agent_returned":
            state["done"]["status"] = "done"
            reason = event.get("finish_reason")
            state["done"]["detail"] = f"结束原因 {reason}" if reason else "Agent 已返回"
        if kind == "agent_error":
            state["done"]["status"] = "failed"
            state["done"]["detail"] = "执行异常 · " + str(event.get("error") or "未记录类别")
        if kind=='business_operation_completed':
            receipt=event.get('business_receipt') or {}
            if receipt.get('action'):
                state['confirm'].update(status='declined' if receipt.get('approved') is False else 'done',detail='实际页面确认记录')
                final='done' if receipt.get('database_verified') and receipt.get('status')=='SUCCEEDED' else 'failed' if receipt.get('status')=='FAILED' else 'declined' if receipt.get('status')=='CANCELLED' else 'blocked'
                state['execute'].update(status=final,detail='SQLite与操作回执核验')
                state['done'].update(status=final,detail='页面业务操作，不是新模型请求')
            elif receipt.get('status')=='BLOCKED':
                state['confirm'].update(status='waiting',detail='已生成确认卡，尚未交易')
                state['execute'].update(status='pending',detail='尚未执行交易')
                state['done'].update(status='waiting',detail='等待用户继续')
            else:state['done'].update(status='done' if receipt.get('status')=='SUCCEEDED' else 'failed',detail='本地页面工具操作')
    failed = any(state[key]["status"] in ("failed", "blocked") for key in ("query", "policy", "execute"))
    if failed and state["done"]["status"] == "done":
        state["done"]["status"] = "failed"
        state["done"]["detail"] = "运行已结束，但存在未成功的模拟操作"
    if state['confirm']['status']=='waiting' and state['done']['status']=='done':
        state['done'].update(status='waiting',detail='等待确认，不代表交易完成')
    return [state[key] for key, _ in PHASES]


def phase_strip(states, current=None):
    """Horizontal stepper markup; ``current`` highlights the live phase."""
    parts = []
    for index, item in enumerate(states, 1):
        status = item["status"]
        if current is not None and item["key"] == current and status in ("pending", "unknown"):
            status = "active"
        detail = item.get("detail") or ""
        parts.append(
            f'<div class="ta-phase is-{escape(status)}">'
            f'<span class="ta-phase-dot"></span>'
            f'<span class="ta-phase-body"><b>{index:02} {escape(item["label"])}</b>'
            f'<small>{escape(STATUS_TEXT.get(status, status))}'
            f'{(" · " + escape(detail)) if detail else ""}</small></span></div>')
    return '<div class="ta-phases" role="list">' + "".join(parts) + "</div>"


def call_rows(events):
    """One row per recorded tool_result, in execution order."""
    rows = []
    for event in events:
        if event.get("event_type") != "tool_result":
            continue
        tool = event.get("tool")
        duration = event.get("duration_ms")
        rows.append({
            "tool": tool,
            "label": TOOL_LABELS.get(tool, str(tool)),
            "status": RESULT_STATUS.get(event.get("status"), "unknown"),
            "status_text": STATUS_TEXT.get(RESULT_STATUS.get(event.get("status"), "unknown"), "未记录"),
            "executed": event.get("executed"),
            "duration": f"{duration} ms" if isinstance(duration, int) else "未记录",
        })
    return rows


def call_list(rows):
    if not rows:
        return '<p class="ta-rail-empty">本轮没有记录到工具调用。</p>'
    items = "".join(
        f'<li class="ta-call is-{escape(row["status"])}">'
        f'<span class="ta-call-name">{escape(row["label"])}</span>'
        f'<span class="ta-call-meta">{escape(row["status_text"])} · {escape(row["duration"])}</span></li>'
        for row in rows)
    return f'<ul class="ta-calls">{items}</ul>'


def run_summary(session, audit, events, mode_label):
    """Compact description of the run that is actually on screen.

    ``run_id`` is the selected audit's id, never the newest audit of another
    session, so a historical session cannot borrow the latest run's state.
    """
    phases = phase_states(events)
    status_by_key = {phase["key"]: phase["status"] for phase in phases}
    if not audit or not events:
        status = "未记录"
    elif any(value == "failed" for value in status_by_key.values()):
        status = "失败"
    elif any(value == "blocked" for value in status_by_key.values()):
        status = "已拦截"
    elif status_by_key.get("confirm") == "waiting":
        status = "等待确认"
    elif status_by_key.get("done") == "done":
        status = "已完成"
    elif any(value == "active" for value in status_by_key.values()):
        status = "进行中"
    else:
        status = "未完成"
    current = None
    for phase in phases:
        if phase["status"] in ("waiting", "active"):
            current = phase
            break
    if current is None:
        recorded = [phase for phase in phases if phase["status"] not in ("pending", "unknown")]
        current = recorded[-1] if recorded else None
    rows = call_rows(events)
    return {
        "run_id": (audit or {}).get("trace_id"),
        "mode_label": mode_label,
        "status": status,
        "phase_key": (current or {}).get("key"),
        "phase_label": (current or {}).get("label"),
        "phase_status": (current or {}).get("status", "unknown"),
        "last_call": rows[-1] if rows else None,
        "has_events": bool(events),
        "event_count": len(events),
    }


def run_summary_line(summary):
    """One line for the sticky bar; missing pieces say 未记录 instead of guessing."""
    parts = []
    if summary.get("phase_label"):
        parts.append(f"{summary['phase_label']} · {STATUS_TEXT.get(summary.get('phase_status'), '未记录')}")
    else:
        parts.append("阶段未记录")
    call = summary.get("last_call")
    if call:
        parts.append(f"{call['label']} · {call['status_text']} · {call['duration']}")
    else:
        parts.append("工具调用未记录")
    return " ｜ ".join(parts)


def live_phase(event):
    """Phase key for one streaming event, used only to highlight the stepper."""
    return _phase_of(event.get("tool"))


def _preview(value, limit=140):
    """Bounded text for a card; the raw value stays in the collapsed JSON."""
    if value is None or value == "":
        return "未记录"
    if isinstance(value, str):
        text = value
    else:
        try:
            import json
            text = json.dumps(value, ensure_ascii=False, sort_keys=False)
        except (TypeError, ValueError):
            text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def event_headline(event):
    """One line for the event list: name, status, tool and duration first."""
    parts = [event_label(event)]
    tool = event.get("tool")
    if tool:
        parts.append(TOOL_LABELS.get(tool, str(tool)))
    duration = event.get("duration_ms")
    if isinstance(duration, int):
        parts.append(f"{duration} ms")
    return " · ".join(parts)


def event_summary(event):
    """Card rows. Only fields the event actually carries are shown as data."""
    tool = event.get("tool")
    duration = event.get("duration_ms")
    argument = event.get("args") if event.get("args") is not None else event.get("proposal")
    result = event.get("output")
    if result is None:
        result = event.get("documents")
    if result is None:
        result = event.get("reply")
    if result is None:
        result = event.get("error")
    rows = [
        ("事件", event_label(event)),
        ("类型", str(event.get("event_type") or "未记录")),
        ("状态", str(event.get("status") or "未记录")),
    ]
    if tool:
        rows.append(("工具", TOOL_LABELS.get(tool, str(tool))))
    if isinstance(duration, int):
        rows.append(("耗时", f"{duration} ms"))
    else:
        rows.append(("耗时", "未记录"))
    rows.append(("参数摘要", _preview(argument)))
    rows.append(("结果摘要", _preview(result)))
    rows.append(("时间", str(event.get("timestamp") or "未记录")))
    return rows


def event_card(event):
    rows = "".join(f'<div class="ta-kv"><span>{escape(label)}</span><b>{escape(value)}</b></div>'
                   for label, value in event_summary(event))
    return f'<div class="ta-event-card">{rows}</div>'


def phase_at(event, events):
    """Stepper for the events seen so far during one call."""
    return phase_strip(phase_states([*events, event]), current=_phase_of(event.get("tool")))
