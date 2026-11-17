import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from target import mock_core
from tests.test_refund_by_train import db,rows,dump,count,get_quote
from web.order_actions import execute,replay_order


def session(db):
    return SimpleNamespace(root=db.parent,sid='p3test',read_only=False,mode='user',live=False,full_tools=True,
                           pending_action=lambda:None,persistence_warning=None)


def app(db):
    script="""import streamlit as st
from target import mock_core
from web.order_actions import card_actions,refund_panel,notice
from web.presentation import order_card
s=st.session_state.s
with mock_core.database_scope(s.root/'tickets.db'):o=mock_core.query_order('OD1')
st.markdown(order_card(o),unsafe_allow_html=True)
card_actions(s,o,True)
refund_panel(s)
notice(s)
"""
    a=AppTest.from_string(script,default_timeout=30);a.session_state.s=session(db);a.run();assert not a.exception
    return a


def test_card_auto_binds_id_and_preview_has_no_writes(db):
    a=app(db);next(b for b in a.button if b.label=='改签').click().run();assert not a.exception
    assert not any('订单号' in t.label for t in a.text_input)
    assert any('OD1' in m.value for m in a.markdown)
    next(s for s in a.selectbox if s.label=='目标日期').select('2026-12-11').run()
    before=dump(db);next(b for b in a.button if b.label=='预览差价').click().run()
    assert not a.exception and dump(db)==before and count(db,'reschedules')==0
    next(b for b in a.button if b.label=='确认改签').click().run()
    assert not a.exception and rows(db,"SELECT train_no FROM orders WHERE order_id='OD1'")==[('G102',)]
    assert count(db,'page_operations')==1 and count(db,'reschedules')==1
    assert not any(b.label=='改签' for b in a.button)
    assert any('P02' in w.value for w in a.warning)
    a.text_input(key='p3_refund_train').set_value('G102');a.date_input(key='p3_refund_date').set_value('2026-12-11')
    with patch('target.mock_core.cancel_order') as cancel:
        next(b for b in a.button if b.label=='查找可退订单').click().run()
        next(s for s in a.selectbox if s.label=='选择要退的订单').select('OD1').run()
        assert not any(b.label=='确认退票 / 取消订单' for b in a.button)
        cancel.assert_not_called()


def test_refund_candidates_selection_preview_then_explicit_confirm(db):
    a=app(db);a.text_input(key='p3_refund_train').set_value('G101');a.date_input(key='p3_refund_date').set_value('2026-12-10')
    next(b for b in a.button if b.label=='查找可退订单').click().run();assert not a.exception
    select=next(s for s in a.selectbox if s.label=='选择要退的订单')
    assert len(select.options)==3 and 'FOREIGN' not in str(select.options)
    assert not any(b.label=='确认退票 / 取消订单' for b in a.button)
    select.select('OD1').run();next(b for b in a.button if b.label=='预览退票费用').click().run()
    assert count(db,'refunds')==0
    next(b for b in a.button if b.label=='确认退票 / 取消订单').click().run()
    assert not a.exception and rows(db,"SELECT status FROM orders WHERE order_id='OD1'")==[('refunded',)]
    assert rows(db,"SELECT status FROM orders WHERE order_id='OD2'")==[('paid',)]
    assert count(db,'page_operations')==1 and count(db,'refunds')==1


@pytest.mark.parametrize('kind',['refund','reschedule'])
def test_service_requires_explicit_confirmation(db,kind):
    with pytest.raises(ValueError):execute(session(db),kind,{},confirmed=False)
    assert count(db,'page_operations')==0


@pytest.mark.parametrize('field,value',[('read_only',True),('mode','lab'),('live',True)])
def test_service_permission_guard(db,field,value):
    s=session(db);setattr(s,field,value)
    if field=='live':s.full_tools=False
    with pytest.raises(ValueError):execute(s,'refund',get_quote(db),confirmed=True)
    assert count(db,'refunds')==0


def test_page_action_does_not_invoke_agent_or_forge_trace_and_replays_readonly(db):
    s=session(db)
    with patch('web.runtime.Agent') as agent:
        result=execute(s,'refund',get_quote(db),confirmed=True);agent.assert_not_called()
    assert not (s.root/'traces').exists()
    assert rows(db,'SELECT action,source FROM page_operations')==[('refund','page')]
    s.read_only=True
    with patch('target.mock_core.query_order') as query:
        assert replay_order(s,{'order_id':'OD1','status':'paid'})['status']=='refunded';query.assert_not_called()


@pytest.mark.parametrize('message,expected',[('退票G101 2026-12-10',True),('取消G101',True),('G101退票手续费怎么算？',False),('不要退票G101',False)])
def test_explicit_train_refund_routes_to_selection_not_latest_order_guess(db,message,expected):
    a=AppTest.from_string("import streamlit as st\nfrom web.order_actions import route_refund_request\nst.session_state.result=route_refund_request(st.session_state.s,st.session_state.message)")
    a.session_state.s=session(db);a.session_state.message=message;a.run()
    assert not a.exception and a.session_state.result is expected
    assert count(db,'refunds')==0
    if expected:assert a.session_state['p3_refund_query']['args'][0]=='G101'


@pytest.mark.parametrize('train,text',[('G102','应补差额（仅记录）：¥20'),('G103','应退差额（仅记录）：¥20'),('G104','无差价：¥0')])
def test_ui_difference_matches_fixed_db_values_without_execution(db,train,text):
    a=app(db);next(b for b in a.button if b.label=='改签').click().run()
    if train=='G102':next(s for s in a.selectbox if s.label=='目标日期').select('2026-12-11').run()
    next(s for s in a.selectbox if s.label=='目标车次').select(train).run()
    before=dump(db);next(b for b in a.button if b.label=='预览差价').click().run()
    assert not a.exception and any(text in m.value for m in a.markdown)
    assert dump(db)==before and count(db,'reschedules')==0 and count(db,'demo_payments')==0
