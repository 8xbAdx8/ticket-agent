"""Trusted page operations use the existing Registry/Service, never model confirmation."""
import copy,json,uuid
from datetime import datetime,timezone
from target.v39.context import scope
from target.v39.registry import service_scope,dispatch,ACTIONS
from target.execution_config import scope as effective_scope
from web.runtime import CALL_LOCK


def _start(session,label,tool=None,call_id=None):
    from web.interaction import begin,now
    identity='page-'+uuid.uuid4().hex
    row,_=begin(session,label,identity,'page_business')
    row.update(kind='page_business',run_id=identity,status='RUNNING',stage='正在核对订单状态',model=None,
        agent_started=False,tools=[dict(tool=tool,call_id=call_id,status='running',executed=False)] if tool else [])
    return row


def _end(session,row,result,*,before=None,after=None,proposal_id=None,call_id=None,error=None,verified=False,cancelled=False,outcome=None):
    from web.interaction import now
    from target.followups import emit_event
    denied=bool(row.get('tools')) and all(t.get('executed') is False for t in row['tools'])
    status='BLOCKED' if denied and (error or result.get('error')) else 'FAILED' if error or result.get('error') else 'CANCELLED' if cancelled else 'BLOCKED' if result.get('status')=='CONFIRMATION_REQUIRED' else 'SUCCEEDED' if verified else 'BLOCKED'
    status=outcome or status
    row.update(status=status,ended_at=now(),stage='已完成' if status=='SUCCEEDED' else '等待你确认' if status=='BLOCKED' and result.get('status')=='CONFIRMATION_REQUIRED' else '未完成，请核对订单状态' if status in ('FAILED','BLOCKED') else '订单状态待核验，请稍后查看' if status=='UNKNOWN' else '订单信息不一致，已暂停' if status=='PARTIAL' else '已撤销',
        error=dict(category=type(error).__name__ if error else result.get('error') or 'awaiting_confirmation') if status in ('FAILED','BLOCKED','UNKNOWN','PARTIAL') else None,
        result_summary=str(result.get('status','UNKNOWN')),tokens=None)
    receipt=dict(operation_id=row['run_id'],session_id=session.sid,order_id=result.get('order_id') or (before or {}).get('order_id') or row.get('order_id'),
        proposal_id=proposal_id or result.get('proposal_id'),tool_call_id=call_id,status=status,actual_result=copy.deepcopy(result),
        database_verified=verified,before=before,after=after,action=row.get('action'),approved=(not cancelled) if row.get('action') else None,source_run_id=row.get('source_run_id'),
        started_at=row['started_at'],finished_at=row['ended_at'],source='trusted_page_operation',model_called=False)
    if not hasattr(session,'business_receipts'):session.business_receipts=[]
    session.business_receipts.append(receipt)
    row['business_operation_id']=receipt['operation_id'];row['order_id']=receipt['order_id']
    try:
        emit_event(session.trace_dir/'run_events.jsonl',row['run_id'],session.sid,'business_operation_completed',
            operation_status=status,business_receipt=receipt,source='trusted_page_operation',model_called=False)
    except OSError:
        session.persistence_warning='业务回执已保留；运行事件写入失败。请核对数据库，不要重复执行交易。'
    session.save_replay()
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx(suppress_warning=True) is not None:
        import streamlit as st
        st.session_state['user_focus_run']=(session.sid,row['run_id'])
    from web.business_state import refresh
    refresh(session)
    return result


def invoke(session,tool,args):
    from web.v39_bridge import prepare
    if session.read_only:raise ValueError('READ_ONLY_HISTORY')
    with CALL_LOCK:
        prepared=prepare(session)
        if not prepared:raise ValueError('V39_CONTEXT_REQUIRED')
        service,ctx,effective=prepared
        call_id='page-call-'+uuid.uuid4().hex
        row=_start(session,{'railway_quote_fare':'生成报价','railway_check_inventory':'查询余票',
                            'railway_create_order':'生成订单'}.get(tool,'生成确认卡'),tool,call_id)
        row['order_id']=args.get('order_id')
        try:
            with effective_scope(effective),scope(ctx),service_scope(service):
                from target.tools import DISPATCH_OBSERVER
                diagnostic={}
                token=DISPATCH_OBSERVER.set(lambda value:diagnostic.update(value))
                try:result,ok,elapsed=dispatch(tool,args)
                finally:DISPATCH_OBSERVER.reset(token)
                row['tools'][0]['executed']=diagnostic.get('backend_executed',False)
                try:service.page_event(ctx,tool,dict(tool_arguments=args,tool_call_id=call_id,operation_id=row['run_id'],scenario_id=ctx.scenario_id),result,ok,elapsed)
                except Exception as exc:session.persistence_warning='工具已返回，页面审计写入失败（'+type(exc).__name__+'）；原工具回执保留，未重试。'
            row['tools'][0]['status']='succeeded' if ok else 'failed'
            verified=ok and (not isinstance(result,dict) or result.get('status')!='CONFIRMATION_REQUIRED')
            return _end(session,row,result if isinstance(result,dict) else dict(data=result),call_id=call_id,verified=verified)
        except Exception as exc:
            _end(session,row,dict(status='FAILED',error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__),call_id=call_id,error=exc)
            raise



def _proposal_origin(session, proposal):
    """Find the executed call that returned this owned proposal."""
    pid = proposal['proposal_id']
    for audit in reversed(session.audits):
        if (audit.get('public_trace') or {}).get('session_id') != session.sid:
            continue
        executions = (audit.get('fault_report') or {}).get('executions', [])
        for entry in (*executions, *audit.get('framework_events', [])):
            if ACTIONS.get(entry.get('tool')) != proposal['action'] or not entry.get('executed') or not entry.get('ok'):
                continue
            result = entry.get('original_result', entry.get('result'))
            if isinstance(result, dict) and result.get('status') == 'CONFIRMATION_REQUIRED' and result.get('proposal_id') == pid and entry.get('call_id'):
                return audit['trace_id'], entry['call_id']
    for receipt in reversed(getattr(session, 'business_receipts', [])):
        if receipt.get('proposal_id') == pid and (receipt.get('actual_result') or {}).get('status') == 'CONFIRMATION_REQUIRED':
            return None, receipt.get('tool_call_id')
    return None, None


def confirm(session,proposal_id,approved):
    from web.v39_bridge import prepare
    from target.v39.read_model import read,brief
    if session.read_only:raise ValueError('历史回放不能确认旧操作')
    if type(approved) is not bool:raise ValueError('确认决定必须为布尔值')
    with CALL_LOCK:
        prepared=prepare(session)
        if not prepared:raise ValueError('V39_CONTEXT_REQUIRED')
        service,ctx,effective=prepared
        with effective_scope(effective),scope(ctx):
            state=read(service.store.path,ctx,now=service.now())
            proposal=next((p for p in state['proposals'] if p['proposal_id']==proposal_id),None)
            if not proposal:raise ValueError('PROPOSAL_NOT_FOUND')
            ctx.require(proposal['action'] if approved else None)
            if approved and proposal['action'] not in ('CREATE_ORDER',) and proposal['order_id'] not in {o['order_id'] for o in state['orders']}:raise ValueError('ORDER_FORBIDDEN')
            latest_receipts={r.get('proposal_id'):r for r in getattr(session,'business_receipts',[]) if r.get('proposal_id')}
            for other_pid,receipt in latest_receipts.items():
                if other_pid==proposal_id or receipt.get('status') not in ('UNKNOWN','PARTIAL'):continue
                proof=next((o for o in state['operations'] if o['proposal_id']==other_pid),None)
                if proof and proof['database_verified']:continue
                if approved and (proposal['action']=='CREATE_ORDER' or receipt.get('order_id')==proposal['order_id']):
                    raise ValueError('PREVIOUS_BUSINESS_RESULT_UNRESOLVED')
            existing=next((r for r in getattr(session,'business_receipts',[]) if r.get('proposal_id')==proposal_id and r['status'] in ('SUCCEEDED','FAILED','CANCELLED') and r.get('actual_result',{}).get('error')!='DATABASE_RECEIPT_NOT_VERIFIED'),None)
            if existing:return copy.deepcopy(existing['actual_result'])
            source,call_id=_proposal_origin(session,proposal)
            before=brief(next((o for o in state['orders'] if o['order_id']==proposal['order_id']),None))
            row=_start(session,'确认操作' if approved else '撤销确认卡')
            row.update(source_run_id=source,proposal_id=proposal_id,action=proposal['action'])
            try:
                uncertain=next((r for r in reversed(getattr(session,'business_receipts',[])) if r.get('proposal_id')==proposal_id and (r.get('status') in ('UNKNOWN','PARTIAL') or r.get('actual_result',{}).get('error')=='DATABASE_RECEIPT_NOT_VERIFIED')),None)
                if approved and uncertain:
                    # Re-read only: never repeat a potentially committed write.
                    from web.receipt_verification import assess
                    result,outcome,verified=assess(proposal,state,uncertain['actual_result'])
                    reconciled=brief(next((o for o in state['orders'] if o['order_id']==result.get('order_id')),None))
                    return _end(session,row,result,before=before,after=reconciled,proposal_id=proposal_id,call_id=call_id,verified=verified,outcome=outcome)
                if approved:result=service.confirm(ctx,proposal_id)
                else:
                    if not service.decline(ctx,proposal_id):raise ValueError('PROPOSAL_NOT_PENDING')
                    result=dict(status='CANCELLED',proposal_id=proposal_id,simulation=True)
                try:updated=read(service.store.path,ctx,now=service.now())
                except Exception as read_error:
                    # Service may already have committed. Preserve the native receipt.
                    result=dict(result,error='DATABASE_RECEIPT_NOT_VERIFIED',verification_status='UNKNOWN',verification_error=type(read_error).__name__)
                    return _end(session,row,result,before=before,proposal_id=proposal_id,call_id=call_id,outcome='UNKNOWN')
                operation=next((o for o in updated['operations'] if o['proposal_id']==proposal_id),None)
                row['business_native_operation_id']=(operation or {}).get('operation_id')
                verified=bool(operation and operation['database_verified']) if approved else True
                after=brief(next((o for o in updated['orders'] if o['order_id']==result.get('order_id',proposal['order_id'])),None))
                if approved and verified and proposal['action']=='CHANGE' and after:
                    session.selected_railway_trip=dict(after,selection_source='committed_order')
                try:
                    service.page_event(ctx,'UI_CONFIRMED_PROPOSAL' if approved else 'UI_DECLINED_PROPOSAL',
                        dict(proposal_id=proposal_id,operation_id=row['run_id'],tool_call_id=call_id,before=before,scenario_id=ctx.scenario_id),dict(result,after=after),verified,0)
                except Exception as exc:
                    # The native transaction and idempotency receipt are already
                    # committed. An auxiliary audit failure cannot undo payment.
                    session.persistence_warning='本页业务已提交，但页面审计辅助事件写入失败（'+type(exc).__name__+'）；以原生交易回执和数据库为准，未自动重试。'
                engine=getattr(session.agent,'langchain_engine',None) if session.agent else None
                # A trusted page action resolves the V3.9 proposal. The model-side
                # LangGraph interrupt is a pause, not the transaction authority;
                # leaving it behind would freeze the composer after the DB commit.
                if engine is not None and (getattr(engine,'pending_actions',{}) or {}).get(session.sid) is not None:
                    engine.pending_actions.pop(session.sid,None)
                    engine.pending_deadlines.pop(session.sid,None)
                    engine.pending_sources.pop(session.sid,None)
                outcome=None
                if approved:
                    from web.receipt_verification import assess
                    result,outcome,verified=assess(proposal,updated,result)
                return _end(session,row,result,before=before,after=after,proposal_id=proposal_id,call_id=call_id,verified=verified,cancelled=not approved,outcome=outcome)
            except Exception as exc:
                # Technical exceptions are not proof that a transaction rolled back.
                from web.receipt_verification import assess
                failure=dict(status='FAILED',error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
                try:
                    latest=read(service.store.path,ctx,now=service.now())
                    result,outcome,verified=assess(proposal,latest,failure,exception=True,before=state)
                except Exception as read_error:
                    result=dict(failure,verification_status='UNKNOWN',verification_error=type(read_error).__name__)
                    outcome,verified='UNKNOWN',False
                final=_end(session,row,result,before=before,proposal_id=proposal_id,call_id=call_id,verified=verified,outcome=outcome)
                if outcome=='FAILED':raise
                return final
