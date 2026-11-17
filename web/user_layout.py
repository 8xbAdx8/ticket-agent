"""User workspace presentation only. No model or business writes."""
from pathlib import Path
import json
from web.result_rows import iter_rows
from web.design import escape
from web.presentation import TOOL_LABELS
import sqlite3
import streamlit as st


def styles():
    st.html('<style>'+Path(__file__).with_name('user_layout.css').read_text(encoding='utf-8')+'</style>')
    st.html('<style>'+Path(__file__).with_name('request_motion.css').read_text(encoding='utf-8')+'</style>')


def topbar(sessions, new_session, activate,clock=None,*,test_session=None):
    def create():
        sessions.append(new_session());activate(len(sessions)-1)
    with st.container(key='user_topbar',horizontal=True,vertical_alignment='center'):
        # The simulation clock is an evaluation artifact (fixed dataset anchor,
        # e.g. 2026-10-17 00:00) and must not be shown as a product subtitle;
        # client handover note 2.1 lists "非现实时间" among the wording to drop.
        subtitle='智能购票助手 · 铁路出行服务'
        st.markdown('<div class="ta-product"><span class="ta-product-mark">T</span><div><b>Ticket Agent</b><small>'+subtitle+'</small></div></div>',unsafe_allow_html=True)
        data_source_notice()
        st.button('新会话',key='user_new_top',on_click=create)
        if test_session is not None:
            from web.session_links import open_test_console
            st.button('测试此对话',key='user_open_test_console',on_click=open_test_console,
                      args=(test_session.sid,getattr(test_session,'workbench_source','user')))
        with st.popover('历史会话'):
            for index,session in enumerate(sessions):
                title=(session.history[0]['user_msg'][:24] if session.history else '新对话')
                st.button(title+' · '+str(index+1),key='user_history_top_'+str(index),on_click=activate,args=(index,))


def rail(session):
    from web.user_features import state,open_panel
    s=state(session)
    from web.business_state import current
    view=current(session)
    if view.get('railway') is not None:
        from web.business_panels import summary
        summary(session)
    else:
        selected=s.get('selected_train')
        st.markdown('### 本次行程摘要')
        if selected:
            st.write(selected.get('from_city','')+' → '+selected.get('to_city',''))
            st.caption(' · '.join(str(selected.get(k,'未记录')) for k in ('date','train_no','seat_type')))
        else:
            from web.train_data import selection_mode
            st.caption('选择车次后，在这里查看行程。' if selection_mode(session)=='fixture' else '车次来源见本轮查询标注；快照仅供查看。')
        st.markdown('### 我的订单')
        from web.runtime import CALL_LOCK
        from target.order_read_model import orders
        try:
            rows=orders(session.root/'tickets.db')
            for o in rows[:2]:st.caption(o['order_id']+' · '+o['train_no']+' · '+o['display_status'])
            if not rows:st.caption('尚无订单；可通过“看订单”查询。')
            else:st.caption('当前库只读摘要；操作前仍需在订单面板查询并核对。')
        except (OSError,ValueError,sqlite3.Error):st.caption('当前订单状态无法读取，请在订单面板核对。')
        st.markdown('### 推荐车次')
        trains=s.get('tickets',{}).get('trains',[])
        ticket_result=s.get('tickets',{})
        if getattr(session,'train_source_choice',None) is not None:
            ticket_result=session.last_train_query or {}
            trains=ticket_result.get('trains',[])
        elif not trains:
            for row in reversed(list(iter_rows(session.results))):
                found=row['result'] if row.get('ok') and row.get('tool')=='query_tickets' else None
                if found is not None:ticket_result=found;trains=found.get('trains',[]);break
        price_label='快照票价' if ticket_result.get('data_source',{}).get('mode')=='snapshot' else '参考票价'
        if ticket_result.get('data_source',{}).get('mode')=='live':price_label='查询票价'
        for t in trains[:2]:st.caption(t['train_no']+' · '+str(t.get('seat_type',''))+' · '+price_label+' '+('未提供' if t.get('price') is None else '¥'+str(t['price'])))
        if not trains:st.caption('查询余票后显示已有工具结果，不编造推荐。')
    st.markdown('### 政策速查')
    st.caption('条款编号与原文来源可在政策面板核对。')
    st.button('浏览示例政策',key='rail_policy_'+session.sid,on_click=open_panel,args=(session.sid,'问政策'),width='stretch')


def quick_actions(session):
    """Six customer entry points; kept outside the collapsed related-info area."""
    from web.user_features import render
    render(session)


def execution_details(operation, events, action, page_events=()):
    """Summarize evidence for the selected run without exposing raw payloads."""
    rows={}
    recorded=operation or {}
    occurrence={}
    for event in events:
        tool=event.get('tool')
        if not tool or event.get('event_type') not in ('tool_result','railway_tool_result','railway_tool_error'):
            continue
        call_id=event.get('call_id')
        if not call_id:
            # Some legacy events lack a call ID. Keep consecutive calls to the
            # same tool distinct, and pair relay events only by occurrence.
            source=(tool,event['event_type'].startswith('railway_'))
            occurrence[source]=occurrence.get(source,0)+1
            call_id=(tool,occurrence[source])
        elif event['event_type']=='tool_result':
            source=(tool,False)
            occurrence[source]=occurrence.get(source,0)+1
            if (tool,occurrence[source]) in rows:
                call_id=(tool,occurrence[source])
        rows[call_id]=event
    if not rows:
        rows={index:tool for index,tool in enumerate(recorded.get('tools') or []) if tool.get('tool')}
        if rows and recorded.get('run_id'):
            for saved in page_events:
                detail=json.loads(saved['detail_json'])
                args=detail.get('args') or {}
                if args.get('operation_id')!=recorded['run_id']:continue
                for index,row in rows.items():
                    if row.get('call_id')==args.get('tool_call_id'):
                        rows[index]=dict(row,duration_ms=detail.get('elapsed_ms'),output=detail.get('result'))
    status_names={'succeeded':'已返回','failed':'失败','blocked':'已拦截','running':'进行中'}
    focus=(action or {}).get('call_id')
    items=[]
    for row in rows.values():
        name=TOOL_LABELS.get(row['tool'],row['tool'])
        status=str(row.get('status') or '').lower()
        output=row.get('output')
        duration=row.get('duration_ms')
        detail=''
        if isinstance(output,dict):
            if output.get('status')=='CONFIRMATION_REQUIRED':detail='等待确认'
            elif type(output.get('total_count')) is int:detail=f"匹配 {output['total_count']} 条"
            elif type(output.get('available')) is int:detail=f"模拟余票 {output['available']} 张"
        if focus and row.get('call_id')==focus:detail='待确认提案对应调用'
        metrics=f'{duration:g} ms' if type(duration) in (int,float) else '耗时未记录'
        items.append(f'<li class="ta-exec-row"><span><b>{escape(name)}</b>'
                     f'{f"<small>{escape(detail)}</small>" if detail else ""}</span>'
                     f'<span><b>{escape(status_names.get(status,"状态未记录"))}</b><small>{escape(metrics)}</small></span></li>')
    if items:
        st.html('<ul class="ta-exec-list" aria-label="本次工具调用">'+''.join(items)+'</ul>')
    elif not action:
        st.caption('本轮没有可显示的工具调用。')


def data_source_notice():
    """Single provenance statement for the whole workspace (handover note 2.1).

    The declaration is never removed: it is relocated into the topbar as one
    collapsed popover, instead of being repeated on every card, button and
    disclaimer or sitting as a permanent rail expander.
    """
    with st.popover('数据来源说明'):
        st.write('车次、站点与时刻来自第三方整理的静态时刻表（GTFS，CC BY 4.0；坐标数据来自 OSM/ODbL），'
                 '不含实时开行状态，也不是 12306 实时数据。')
        st.write('余票、票价与订单为本会话内的参考数据；不连接 12306，不产生真实车票或实际扣款，'
                 '每次交易仍需你在页面确认。')
        st.write('退改与行李规则为本服务收录的条款，保留条款编号与原文；实际规定以承运方公告为准。')
        st.caption('可查询的出行日期以时刻表服务日为准；静态库整库校验，未作裁剪。')
