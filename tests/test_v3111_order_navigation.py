from streamlit.testing.v1 import AppTest


SOURCE = """
from types import SimpleNamespace
import streamlit as st
from web.proposal_navigation import prepare
sid=st.session_state['test_sid']
prepare(SimpleNamespace(sid=sid,business_view={'railway':st.session_state['test_view']},save_replay=lambda:None))
orders=[order['order_id'] for order in st.session_state['test_view']['orders']]
if orders:
    st.selectbox('选择本人订单',orders,key='railway_order_widget_'+sid)
"""


def test_navigation_selects_verified_order_before_widget_and_preserves_pending():
    app=AppTest.from_string(SOURCE)
    app.session_state['test_sid']='a'
    view={'orders':[{'order_id':'old'},{'order_id':'new'}], 'pending_proposals':[{'proposal_id':'pending'}]}
    app.session_state['test_view']=view
    app.run()
    assert app.selectbox[0].value=='old'
    app.session_state['railway_created_order_a']='new'
    app.run()
    assert not app.exception and app.selectbox[0].value=='new'
    assert app.session_state['railway_order_focus_a']=='new'
    assert app.session_state['user_info_open']
    assert app.session_state['test_view']['pending_proposals']==[{'proposal_id':'pending'}]
    app.run()
    assert app.selectbox[0].value=='new'
    app.session_state['test_sid']='b'
    app.session_state['test_view']={'orders':[{'order_id':'foreign'}]}
    app.run()
    assert app.selectbox[0].value=='foreign'
    assert 'railway_order_focus_b' not in app.session_state


def test_navigation_ignores_order_absent_from_owned_database_view():
    app=AppTest.from_string(SOURCE)
    app.session_state['test_sid']='a'
    app.session_state['test_view']={'orders':[{'order_id':'old'}]}
    app.session_state['railway_created_order_a']='unverified'
    app.run()
    assert not app.exception and app.selectbox[0].value=='old'
    assert 'railway_order_focus_a' not in app.session_state
