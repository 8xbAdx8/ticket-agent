"""Small replay indexes into existing audit JSONL. Never load model checkpoints."""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config

SETTINGS = ('mode','engine','live','live_provider','live_model','case_id','rag_mode',
            'interactive','full_tools','mutations')


def _inside(root):
    root=Path(root).resolve()
    base=(config.BASE_DIR/'artifacts/runtime').resolve()
    if root==base or not root.is_relative_to(base):raise ValueError('历史路径超出本地运行目录')
    return root


def save_session(session):
    """Only the mutable index is replaced; audits/events/Trace are never rewritten."""
    if session.read_only or not session.audits or not session.root.exists():return
    root=_inside(session.root)
    audits={a.get('trace_id'):a for a in session.audits
            if (a.get('public_trace') or {}).get('session_id')==session.sid}
    history=[session._audit_for(record) for record in session.history]
    payload={'schema':'ticket-session-replay/1','session_id':session.sid,
             'settings':{n:getattr(session,n) for n in SETTINGS},
             'run_ids':list(audits),'history_run_ids':[a['trace_id'] for a in history if a],
             'updated_at':datetime.now(timezone.utc).isoformat()}
    from target.diagnostics import sanitize
    payload=sanitize(payload)
    raw=json.dumps(payload,ensure_ascii=False,indent=2)
    if len(raw.encode('utf8'))>256*1024:raise ValueError('会话索引超出读取上限')
    temporary=root/('session-replay-'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(raw,encoding='utf8')
    temporary.replace(root/'session-replay.json')


def restore_session(root, *, expected_sid=None):
    """Read-only restoration: no Agent/Provider construction, no DB or API access."""
    root=_inside(root);path=root/'session-replay.json'
    if path.is_symlink() or path.stat().st_size>256*1024:raise ValueError('会话索引不可用')
    saved=json.loads(path.read_text(encoding='utf8'))
    sid=saved.get('session_id')
    if saved.get('schema')!='ticket-session-replay/1' or not isinstance(sid,str) or not re.fullmatch(r'web-[0-9a-f]{12}',sid):
        raise ValueError('会话索引格式无效')
    if expected_sid is not None and sid!=expected_sid:raise ValueError('会话 ID 不匹配')
    settings=saved.get('settings') or {}
    if set(settings)-set(SETTINGS):raise ValueError('会话包含不支持的配置字段')
    from web.runtime import Conversation
    from web.evidence import read_audit_records
    session=Conversation(**settings,root=root,sid=sid,read_only=True)
    records,errors=read_audit_records(root/'traces/audit_runs.jsonl')
    wanted=saved.get('run_ids') or []
    by_id={r['trace_id']:r for r in records if r.get('trace_id') in wanted
           and (r.get('public_trace') or {}).get('session_id')==sid}
    session.audits=[by_id[rid] for rid in wanted if rid in by_id]
    for rid in saved.get('history_run_ids') or []:
        audit=by_id.get(rid)
        if not audit or audit.get('error') or audit.get('contract_returned') is False:continue
        session.history.append(audit['public_trace'])
        executions=(audit.get('fault_report') or {}).get('executions')
        if executions is None:
            executions=[e for e in audit.get('framework_events') or [] if e.get('event')=='tool_end']
        session.results.append([{'tool':e['tool'],'result':e['result'],'ok':e.get('ok')}
                                for e in executions if isinstance(e,dict) and 'tool' in e and 'result' in e])
    if errors['invalid'] or errors['truncated'] or len(session.audits)!=len(wanted):
        session.persistence_warning='部分历史旁证缺失、损坏或超出读取上限；仅恢复可核验的记录。'
    return session


def restore_by_sid(sid):
    if not isinstance(sid,str) or not re.fullmatch(r'web-[0-9a-f]{12}',sid):raise ValueError('会话 ID 格式无效')
    return restore_session(config.BASE_DIR/'artifacts/runtime/v33/user'/sid,expected_sid=sid)
