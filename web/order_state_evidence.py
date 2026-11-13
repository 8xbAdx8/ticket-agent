"""Capture an explicit Agent declaration and an actual order widget emission."""
import re

from target.consistency_audit import IDENTITY, STATES
from target.diagnostics import digest


DECLARATION = re.compile(
    r'订单\s+(V39-[a-f0-9]{32})\s*(?:当前(?:已提交)?状态|状态)\s*[:：]\s*'
    r'(' + '|'.join(sorted(STATES)) + r')[。.]?'
)


def explicit_declarations(reply):
    matches = {}
    fence = None
    for line in reply.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker and (fence is None or marker[1][0] == fence[0] and len(marker[1]) >= len(fence)):
            fence = marker[1] if fence is None else None
            continue
        if fence or line.startswith(('    ', '\t')):
            continue
        match = DECLARATION.fullmatch(line.replace('**', '').strip().strip('`'))
        if match:
            matches.setdefault(match[1], set()).add(match[2])
    return {order: next(iter(states)) for order, states in matches.items() if len(states) == 1}


def binding(session, order_id):
    receipts = [row for row in getattr(session, 'business_receipts', [])
                if row.get('session_id') == session.sid and row.get('order_id') == order_id
                and row.get('action') and row.get('approved') is True]
    if not receipts:
        return None
    receipt = receipts[-1]
    if (receipt.get('database_verified') is not True or not receipt.get('source_run_id')
            or not all(isinstance(receipt.get(key), str) and receipt[key] for key in IDENTITY)):
        return None
    return {key: receipt[key] for key in (*IDENTITY, 'source_run_id')}


def agent_declarations(session, record):
    from target.run_events import emit, identity
    current = identity()
    reply = record.get('reply')
    if (not isinstance(reply, str) or record.get('session_id') != session.sid
            or current.get('session_id') != session.sid):
        return
    for order_id, status in explicit_declarations(reply).items():
        fields = binding(session, order_id)
        if fields:
            fields.pop('session_id')
            try:
                emit('agent_order_state_declared', **fields, order_status=status,
                     declaration_sha256=digest(reply), source='agent_returned_reply')
            except OSError:
                session.persistence_warning = '订单状态声明的 Trace 写入失败，状态一致性将保留为未知。'


def rendered(session, text, order_id, display_run_id):
    from target.followups import emit_event
    if session.read_only or not display_run_id:
        return
    # The status is extracted from the text sent to the widget, preserving drift.
    status = explicit_declarations(text.split('；', 1)[0]).get(order_id)
    fields = binding(session, order_id)
    if not status or not fields:
        return
    operation_id = fields['operation_id']
    key = (operation_id, display_run_id, digest(text))
    recorded = getattr(session, '_recorded_order_widgets', set())
    if key in recorded:
        return
    fields.pop('session_id')
    try:
        event = emit_event(session.trace_dir/'run_events.jsonl', operation_id, session.sid, 'ui_order_state_rendered',
                           **fields, order_status=status, rendered_from_run_id=display_run_id,
                           render_text_sha256=key[-1], source='streamlit_info_widget')
    except OSError:
        return
    if event:
        recorded.add(key)
        session._recorded_order_widgets = recorded
