from datetime import datetime,timedelta
from unittest.mock import patch
from types import SimpleNamespace
import sqlite3
import pytest
import config
from target.order_refund import calculate
from target.order_read_model import orders,consistent
from tests.test_refund_by_train import db,dump
from web.runtime import Conversation
from streamlit.testing.v1 import AppTest

@pytest.mark.parametrize('hours,rate',[(49,.05),(48,.1),(47,.1),(24,.1),(23,.2)])
def test_shared_calculator_boundaries(hours,rate):
    now=datetime(2026,12,1)
    r=calculate(100,now+timedelta(hours=hours),now=now)
    assert r['fee_rate']==rate and r['fee']==100*rate and r['refund']==100-100*rate

@pytest.mark.parametrize('amount',['',None,'NaN','Infinity',-1,0])
def test_invalid_price(amount):
    with pytest.raises(ValueError):calculate(amount,datetime(2030,1,1))

def test_calculator_restrictions():
    now=datetime(2026,12,1)
    assert calculate(100,now,now=now).get('error')
    assert calculate(100,now,now=now,changed=True).get('error')
    assert calculate(100,now,now=now,status='pending')['refund']==0

@pytest.mark.parametrize('status',['pending','paid','cancelled','refunded','expired'])
def test_owned_projection_permissions_and_readonly(db,status):
    with sqlite3.connect(db) as c:c.execute("UPDATE orders SET status=? WHERE order_id='OD1'",(status,))
    before=dump(db);rows=orders(db);assert len(rows)==3 and not any(o['order_id']=='FOREIGN' for o in rows)
    o=next(o for o in rows if o['order_id']=='OD1')
    assert 'phone' not in o and o['actions']['pay']['allowed']==(status=='pending')
    assert o['actions']['reschedule']['allowed']==(status=='paid')
    assert dump(db)==before

def test_changed_projection_and_inconsistency(db):
    from target.reschedule import preview,confirm
    old=orders(db,'OD1')[0];confirm(db,preview(db,'OD1','G102','2026-12-11','二等座'))
    now=orders(db,'OD1')[0]
    assert now['display_status']=='已改签' and not now['actions']['refund']['allowed']
    assert not consistent(old,now) and now['difference']=='20'

def test_panels_query_uses_actual_agent_and_preserves_trace():
    from web.user_features import query
    s=Conversation('user',engine='legacy')
    with patch('web.runtime.Agent.chat',autospec=True,wraps=None) as fake:
        # No fake success is accepted when a fabricated Agent return lacks tools.
        fake.return_value={}
        with pytest.raises(Exception):query(s,'查询我的订单','query_order')
    s=Conversation('user',engine='legacy')
    with patch.multiple(config,PROVIDER='mock',ENGINE='legacy'):
        result=query(s,'查询我的订单','query_order')
    assert result['orders']==[] and s.history[-1]['tool_sequence']==['query_order']
    assert (s.trace_dir/'traces.jsonl').exists()

def test_policy_uses_existing_sources():
    from target.rag_store import documents
    docs=documents(config.POLICY_PATH)
    assert {'P01','P02','P06','P08','P11'}<={d['doc_id'] for d in docs}
    assert all(d['source'].endswith('#'+d['doc_id']) for d in docs)

def test_expiry_projection_does_not_write_database(db):
    with sqlite3.connect(db) as c:
        c.execute("UPDATE orders SET status='pending' WHERE order_id='OD1'")
        c.execute("UPDATE locks SET expire_at='2000-01-01' WHERE lock_id='LOD1'")
    before=dump(db);o=orders(db,'OD1')[0]
    assert o['status']=='pending' and o['effective_status']=='expired'
    assert not o['actions']['pay']['allowed'] and not o['actions']['refund']['allowed']
    assert dump(db)==before

@pytest.mark.parametrize('name',['查余票','问政策','看订单','退票费率','行李费用','改签'])
def test_independent_panel_render_and_switch_without_agent(name):
    s=SimpleNamespace(sid='panel',read_only=False,root=config.BASE_DIR/'artifacts/runtime/empty-panel',mode='user',live=False,full_tools=True,pending_action=lambda:None)
    a=AppTest.from_string('import streamlit as st\nfrom web.user_features import render\nrender(st.session_state.s)')
    a.session_state.s=s
    with patch('web.runtime.Agent') as agent:
        a.run();next(b for b in a.button if b.label==name).click().run();assert not a.exception
        next(b for b in a.button if b.label=='关闭面板').click().run();assert not a.exception
        agent.assert_not_called()

def test_center_and_chat_reuse_controls_without_duplicate_keys(db):
    import shutil
    from web.user_features import query
    s=Conversation('user',engine='legacy');s.root.mkdir(parents=True,exist_ok=True)
    shutil.copy2(db,s.root/'tickets.db')
    with sqlite3.connect(s.root/'tickets.db') as c:c.execute("UPDATE orders SET status='pending' WHERE order_id='OD1'")
    result=query(s,'查询我的订单','query_order')
    script="""import streamlit as st
from web.user_features import render
from web.conversation import show_business
s=st.session_state.s
show_business(s.results[-1],s)
render(s)
"""
    a=AppTest.from_string(script,default_timeout=30);a.session_state.s=s
    a.session_state['features_'+s.sid]={'order_result':result}
    a.session_state['feature_panel_'+s.sid]='看订单'
    with patch.object(s.agent,'chat',wraps=s.agent.chat) as spy:
        a.run();a.run();assert not a.exception;spy.assert_not_called()
    next(b for b in a.button if b.label=='去支付').click().run()
    assert not a.exception and any(c.key.endswith('_center') for c in a.checkbox)
    next(c for c in a.checkbox if c.key.endswith('_center')).check().run()
    next(b for b in a.button if b.label=='使用支付宝支付' and b.key.endswith('_center')).click().run()
    assert not a.exception
    with sqlite3.connect(s.root/'tickets.db') as c:
        assert c.execute("SELECT status FROM orders WHERE order_id='OD1'").fetchone()[0]=='paid'
        assert c.execute("SELECT source FROM page_operations WHERE action='payment'").fetchall()==[('page',)]

def test_policy_filter_clear_and_context_has_source():
    from pathlib import Path
    s=SimpleNamespace(sid='policy-test',read_only=False)
    a=AppTest.from_string('import streamlit as st\nfrom web.user_features import policy_browser_panel\npolicy_browser_panel(st.session_state.s)');a.session_state.s=s;a.run()
    a.text_input(key='fp_search').set_value('totallymissing123').run()
    assert any('没有匹配' in i.value for i in a.info)
    a.button(key='fp_clear').click().run();assert not a.exception
    next(b for b in a.button if b.label=='就这条提问').click().run()
    d=a.session_state['features_policy-test']['policy_context']
    assert d['source'].endswith('#'+d['doc_id'])

def test_form_and_results_survive_panel_switch():
    s=SimpleNamespace(sid='forms',read_only=False,root=config.BASE_DIR/'artifacts/runtime/no-forms',mode='user',live=False,full_tools=True,pending_action=lambda:None)
    a=AppTest.from_string('import streamlit as st\nfrom web.user_features import render\nrender(st.session_state.s)');a.session_state.s=s;a.run()
    next(b for b in a.button if b.label=='退票费率').click().run()
    a.text_input(key='fr_amount').set_value('123.45')
    next(b for b in a.button if b.label=='计算退票费用').click().run()
    next(b for b in a.button if b.label=='问政策').click().run()
    next(b for b in a.button if b.label=='退票费率').click().run()
    assert not a.exception and a.text_input(key='fr_amount').value=='123.45'


def ticket_app():
    s=SimpleNamespace(sid='ticket-test',read_only=False)
    a=AppTest.from_string('import streamlit as st\nfrom web.user_features import ticket_search_panel\nticket_search_panel(st.session_state.s)')
    a.session_state.s=s
    a.run()
    return a


@pytest.mark.parametrize('kind,seat',[('高铁','二等座'),('高铁','一等座'),('高铁','商务座'),('机票','经济舱'),('机票','公务舱')])
def test_ticket_submit_once_and_empty_result_without_refresh_resend(kind,seat):
    a=ticket_app()
    a.selectbox(key='ft_kind').select(kind)
    a.selectbox(key='ft_seat').select(seat)
    with patch('web.user_features.query',return_value={'trains':[]}) as q:
        next(b for b in a.button if b.label=='查询车票').click().run()
        a.run()
        assert not a.exception and q.call_count==1
        assert kind in q.call_args.args[1] and seat in q.call_args.args[1]
        assert q.call_args.args[2]=='query_tickets'
        assert any('没有符合条件' in i.value for i in a.info)


@pytest.mark.parametrize('case',['same_city','past_date','wrong_seat'])
def test_invalid_ticket_form_never_sends_agent(case):
    a=ticket_app()
    if case=='same_city':a.selectbox(key='ft_to').select('上海')
    if case=='past_date':
        # Streamlit clamps widget values to min_value. Inject an invalid return
        # to exercise the additional submission guard, independently of that UI.
        with patch('web.user_features.st.date_input',return_value=config.today()-timedelta(days=1)),patch('web.user_features.query') as q:
            next(b for b in a.button if b.label=='查询车票').click().run()
            assert not a.exception and a.warning
            q.assert_not_called()
        return
    if case=='wrong_seat':a.selectbox(key='ft_kind').select('机票')
    with patch('web.user_features.query') as q:
        next(b for b in a.button if b.label=='查询车票').click().run()
        assert not a.exception and a.warning
        q.assert_not_called()


@pytest.mark.parametrize('category,doc_id',[('退票费率','P01'),('改签规则','P02'),('行李限额','P06'),('支付时限','P11'),('候补规则','P08')])
def test_policy_categories_use_real_document_content(category,doc_id):
    from target.rag_store import documents
    s=SimpleNamespace(sid='categories',read_only=False)
    a=AppTest.from_string('import streamlit as st\nfrom web.user_features import policy_browser_panel\npolicy_browser_panel(st.session_state.s)')
    a.session_state.s=s;a.run();a.selectbox(key='fp_category').select(category).run()
    doc=next(d for d in documents(config.POLICY_PATH) if d['doc_id']==doc_id)
    assert not a.exception and any(e.label.startswith(doc_id+' · ') for e in a.expander)
    assert any(m.value==doc['content'] for m in a.markdown)
    assert any(doc['source'] in c.value for c in a.caption)


def test_ticket_agent_real_trace_and_selection_does_not_write(db):
    import shutil
    from web.user_features import query
    s=Conversation('user',engine='legacy');s.root.mkdir(parents=True,exist_ok=True)
    shutil.copy2(db,s.root/'tickets.db')
    before=dump(s.root/'tickets.db')
    result=query(s,'查2026-12-10上海到杭州的高铁二等座','query_tickets')
    assert result['trains'] and s.history[-1]['tool_sequence']==['query_tickets']
    a=ticket_app();a.session_state['features_ticket-test']={'tickets':result}
    a.run();next(b for b in a.button if b.label=='选择这个车次').click().run()
    assert a.session_state['features_ticket-test']['selected_train']['train_no']==result['trains'][0]['train_no']
    assert dump(s.root/'tickets.db')==before


def test_calculator_decimal_precision_and_no_database_access():
    from decimal import Decimal
    with patch('sqlite3.connect',side_effect=AssertionError('calculator must not open DB')):
        r=calculate('123.45',datetime(2026,12,4),now=datetime(2026,12,1))
    assert Decimal(str(r['fee']))==Decimal('6.17') and Decimal(str(r['refund']))==Decimal('117.28')
