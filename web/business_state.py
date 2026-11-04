"""One presentation snapshot shared by chat, rail, order actions and history."""
from pathlib import Path
import copy
import config
from web.result_rows import iter_rows


def query_identity(row):
    """Ignore display-only card IDs; bind to the actual query result payload."""
    from target.v39.context import digest
    return digest(dict(tool=row.get('tool'),result=row.get('result')))


def refresh(session):
    from target.v39.read_model import read
    from target.v39.context import Context
    from target.execution_config import scope
    from target.v39.registry import enabled
    view=dict(session_id=session.sid,railway=None,legacy=[],selected_trip=None,recommendations=[],error=None)
    try:
        ref=getattr(session,'railway_state_reference',None)
        prepared=None
        if enabled() and session.execution_mode!='baseline' and not session.read_only:
            from web.v39_bridge import prepare
            prepared=prepare(session)
        if prepared:
            service,ctx,effective=prepared
            ref=dict(path=str(service.store.path),scenario_id=ctx.scenario_id)
            session.railway_state_reference=ref
            with scope(effective):view['railway']=read(service.store.path,ctx,now=service.now())
        elif ref and enabled() and session.execution_mode!='baseline':
            ctx=Context(session.sid,config.CURRENT_USER_PHONE,ref['scenario_id'],enabled=True)
            with scope(None):view['railway']=read(Path(ref['path']),ctx)
        from target.order_read_model import orders
        view['legacy']=orders(session.root/'tickets.db')
    except (ValueError,OSError,KeyError,__import__('sqlite3').Error) as exc:
        view['error']=type(exc).__name__
    rows=list(iter_rows([getattr(session,'results',[]),getattr(session,'railway_queries',[])]))
    query=next((r for r in reversed(rows) if r.get('ok') and r.get('tool')=='railway_query_trips' and isinstance(r.get('result'),dict)),None)
    if query:
        output=query['result'];params=output.get('query_parameters') or query.get('args') or {}
        if output.get('status')=='FOUND':
            view['recommendations']=[dict(r,**{k:v for k,v in params.items() if k in ('service_date','origin_stop_id','destination_stop_id')}) for r in output.get('data',[]) if isinstance(r,dict)][:3]
    if not query:
        legacy_query=next((r for r in reversed(rows) if r.get('ok') and r.get('tool')=='query_tickets' and isinstance(r.get('result'),dict)),None)
        if legacy_query:
            view['recommendations']=[dict(r,source='LEGACY_DEMO') for r in legacy_query['result'].get('trains',[]) if isinstance(r,dict)][:3]
    rail=view['railway'] or {};orders=rail.get('orders',[])
    selected=getattr(session,'selected_railway_trip',None)
    quote=next((q for q in rail.get('quotes',[]) if q['status']=='ACTIVE' and q['expires_at']>rail['updated_at']),None)
    if selected and (not query or selected.get('query_identity')==query_identity(query)):
        view['selected_trip']=copy.deepcopy(selected)
    elif orders:view['selected_trip']=dict(orders[0],selection_source='committed_order')
    elif quote:view['selected_trip']=dict(quote,selection_source='committed_quote')
    session.business_view=view
    return view


def current(session):
    view=getattr(session,'business_view',None)
    return view if view and view.get('session_id')==session.sid else refresh(session)


def select_trip(session,row,train):
    params=row.get('result',{}).get('query_parameters') or row.get('args') or {}
    previous=getattr(session,'selected_railway_trip',None) or {}
    if previous.get('trip_id')!=train.get('trip_id') or any(previous.get(k)!=params.get(k) for k in ('service_date','origin_stop_id','destination_stop_id')):
        session.booking_passengers=None
    session.selected_railway_trip=dict(train,**{k:v for k,v in params.items() if k in ('service_date','origin_stop_id','destination_stop_id')},query_identity=query_identity(row),selection_source='user_selected_static_result')


def order_for_record(session,record):
    """Current state is a separate projection, never a rewrite of the saved reply."""
    import re
    view=current(session);rows=(view.get('railway') or {}).get('orders',[])
    audit=session._audit_for(record)
    executions=(audit or {}).get('framework_events',[])
    ids=set(re.findall(r'V39-[a-f0-9]{32}',record.get('user_msg','')+' '+record.get('reply','')))
    for event in executions:
        for value in iter_rows([event.get('args'),event.get('result')]):
            if isinstance(value,dict) and value.get('order_id'):ids.add(value['order_id'])
    for receipt in getattr(session,'business_receipts',[]):
        if receipt.get('order_id') and (receipt.get('source_run_id')==(audit or {}).get('trace_id')):ids.add(receipt['order_id'])
    return [o for o in rows if o['order_id'] in ids]


def render_order_status(session,record):
    import streamlit as st
    from target.v39.read_model import status_text
    for order in order_for_record(session,record):
        latest=next((r for r in reversed(session.history) if any(o['order_id']==order['order_id'] for o in order_for_record(session,r))),None)
        if latest is not None and latest!=record:continue
        st.info(status_text(order))
        st.caption('当前已提交状态；上方消息和原始运行记录保留当时结果，不代表本次又执行了交易。')


def orders_for_operation(session,operation):
    audit=next((a for a in session.audits if a.get('trace_id')==operation.get('run_id')),None)
    record=(audit or {}).get('public_trace') or dict(user_msg=operation.get('operation',''),reply='')
    return order_for_record(session,record)
