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
    row.update(kind='page_business',run_id=identity,status='RUNNING',stage='正在核验本地业务状态',model=None,
        agent_started=False,tools=[dict(tool=tool,call_id=call_id,status='running',executed=False)] if tool else [])
    return row


def _end(session,row,result,*,before=None,after=None,proposal_id=None,call_id=None,error=None,verified=False,cancelled=False):
    from web.interaction import now
    from target.followups import emit_event
    denied=bool(row.get('tools')) and all(t.get('executed') is False for t in row['tools'])
    status='BLOCKED' if denied and (error or result.get('error')) else 'FAILED' if error or result.get('error') else 'CANCELLED' if cancelled else 'BLOCKED' if result.get('status')=='CONFIRMATION_REQUIRED' else 'SUCCEEDED' if verified else 'BLOCKED'
    row.update(status=status,ended_at=now(),stage='本地模拟操作已完成' if status=='SUCCEEDED' else '等待用户确认' if status=='BLOCKED' and result.get('status')=='CONFIRMATION_REQUIRED' else '本地操作未完成' if status in ('FAILED','BLOCKED') else '已撤销确认卡',
        error=dict(category=type(error).__name__ if error else result.get('error') or 'awaiting_confirmation') if status in ('FAILED','BLOCKED') else None,
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
        row=_start(session,{'railway_quote_fare':'生成模拟报价','railway_check_inventory':'查询模拟库存'}.get(tool,'生成本地操作确认卡'),tool,call_id)
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
            existing=next((r for r in getattr(session,'business_receipts',[]) if r.get('proposal_id')==proposal_id and r['status'] in ('SUCCEEDED','FAILED','CANCELLED')),None)
            if existing:return copy.deepcopy(existing['actual_result'])
            source=None;call_id=None
            for audit in reversed(session.audits):
                match=next((e for e in audit.get('framework_events',[]) if isinstance(e.get('result'),dict) and e['result'].get('proposal_id')==proposal_id),None)
                if match:source=audit['trace_id'];call_id=match.get('call_id');break
            if call_id is None:
                receipt=next((r for r in reversed(getattr(session,'business_receipts',[])) if r.get('proposal_id')==proposal_id),None)
                call_id=(receipt or {}).get('tool_call_id')
            before=brief(next((o for o in state['orders'] if o['order_id']==proposal['order_id']),None))
            row=_start(session,'确认本地模拟操作' if approved else '撤销本地确认卡')
            row.update(source_run_id=source,proposal_id=proposal_id,action=proposal['action'])
            try:
                if approved:result=service.confirm(ctx,proposal_id)
                else:
                    if not service.decline(ctx,proposal_id):raise ValueError('PROPOSAL_NOT_PENDING')
                    result=dict(status='CANCELLED',proposal_id=proposal_id,simulation=True)
                updated=read(service.store.path,ctx,now=service.now())
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
                    session.persistence_warning='本地业务已提交，但页面审计辅助事件写入失败（'+type(exc).__name__+'）；以原生交易回执和数据库为准，未自动重试。'
                engine=getattr(session.agent,'langchain_engine',None) if session.agent else None
                # A trusted page action resolves the V3.9 proposal. The model-side
                # LangGraph interrupt is a pause, not the transaction authority;
                # leaving it behind would freeze the composer after the DB commit.
                if engine is not None and (getattr(engine,'pending_actions',{}) or {}).get(session.sid) is not None:
                    engine.pending_actions.pop(session.sid,None)
                    engine.pending_deadlines.pop(session.sid,None)
                    engine.pending_sources.pop(session.sid,None)
                if approved and not result.get('error') and not verified:result=dict(result,error='DATABASE_RECEIPT_NOT_VERIFIED')
                return _end(session,row,result,before=before,after=after,proposal_id=proposal_id,call_id=call_id,verified=verified,cancelled=not approved)
            except Exception as exc:
                _end(session,row,dict(status='FAILED',error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__),before=before,proposal_id=proposal_id,call_id=call_id,error=exc)
                raise
