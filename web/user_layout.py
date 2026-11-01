"""User workspace presentation only. No model or business writes."""
from pathlib import Path
import sqlite3
import streamlit as st


def styles():
    st.html('<style>'+Path(__file__).with_name('user_layout.css').read_text(encoding='utf-8')+'</style>')


def topbar(sessions, new_session, activate):
    def create():
        sessions.append(new_session());activate(len(sessions)-1)
    with st.container(key='user_topbar',horizontal=True,vertical_alignment='center'):
        st.markdown('<div class="ta-product"><span class="ta-product-mark">T</span><div><b>Ticket Agent</b><small>智能购票助手 · 演示空间</small></div></div>',unsafe_allow_html=True)
        st.button('新会话',key='user_new_top',on_click=create)
        with st.popover('历史会话'):
            for index,session in enumerate(sessions):
                title=(session.history[0]['user_msg'][:24] if session.history else '新对话')
                st.button(title+' · '+str(index+1),key='user_history_top_'+str(index),on_click=activate,args=(index,))


def rail(session):
    from web.user_features import state,open_panel
    s=state(session)
    selected=s.get('selected_train')
    st.markdown('### 本次行程摘要')
    if selected:
        st.write(selected.get('from_city','')+' → '+selected.get('to_city',''))
        st.caption(' · '.join(str(selected.get(k,'未记录')) for k in ('date','train_no','seat_type')))
    else:
        from web.train_data import selection_mode
        st.caption('选择车次后，在这里查看行程。当前使用演示数据。' if selection_mode(session)=='fixture' else '车次来源见本轮查询标注；快照仅供查看，不办理真实交易。')
    st.markdown('### 我的订单')
    from web.runtime import CALL_LOCK
    from target.order_read_model import orders
    try:
        with CALL_LOCK:rows=orders(session.root/'tickets.db')
        for o in rows[:2]:st.caption(o['order_id']+' · '+o['train_no']+' · '+o['display_status'])
        if not rows:st.caption('尚无演示订单；可通过“看订单”查询。')
        else:st.caption('当前库只读摘要；操作前仍需在订单面板查询并核对。')
    except (OSError,ValueError,sqlite3.Error):st.caption('当前订单状态无法读取，请在订单面板核对。')
    st.markdown('### 推荐车次')
    trains=s.get('tickets',{}).get('trains',[])
    ticket_result=s.get('tickets',{})
    if getattr(session,'train_source_choice',None) is not None:
        ticket_result=session.last_train_query or {}
        trains=ticket_result.get('trains',[])
    elif not trains:
        for batch in reversed(session.results):
            found=next((r['result'] for r in batch if r.get('ok') and r.get('tool')=='query_tickets'),None)
            if found is not None:ticket_result=found;trains=found.get('trains',[]);break
    price_label='快照票价' if ticket_result.get('data_source',{}).get('mode')=='snapshot' else '演示票价'
    for t in trains[:2]:st.caption(t['train_no']+' · '+str(t.get('seat_type',''))+' · '+price_label+' ¥'+str(t.get('price','未提供')))
    if not trains:st.caption('查询余票后显示已有工具结果，不编造推荐。')
    from web.user_features import render
    render(session)
    st.markdown('### 政策速查')
    st.caption('项目内示例政策，保留条款编号和原文来源。')
    st.button('浏览示例政策',key='rail_policy_'+session.sid,on_click=open_panel,args=(session.sid,'问政策'),width='stretch')
