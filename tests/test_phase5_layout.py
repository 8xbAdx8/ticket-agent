"""Interaction checks complement the real Edge geometry acceptance."""
import json
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
import config
from streamlit.testing.v1 import AppTest
from web import scroll_bridge


def app():
    return AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()


def send(a,message):
    a.text_input(key='user_message').set_value(message)
    next(b for b in a.button if b.label=='发送').click().run()
    assert not a.exception


def test_initial_workspace_and_rerun_never_construct_agent():
    with patch('web.runtime.Agent') as agent:
        a=app();sid=a.session_state['user_sessions'][0].sid;a.run()
        assert not a.exception and a.session_state['user_sessions'][0].sid==sid
        agent.assert_not_called()
    labels=[b.label for b in a.button]
    assert '新会话' in labels and all(n in labels for n in ['查余票','问政策','看订单','退票费率','行李费用','改签'])
    assert not any('更多模拟工具' in e.label or '高级设置' in e.label for e in a.expander)


def test_one_send_one_trace_and_plain_rerun_preserves_session():
    a=app();send(a,'查明天上海到杭州的高铁二等座')
    s=a.session_state['user_sessions'][0]
    before=(s.trace_dir/'traces.jsonl').read_bytes()
    assert len(s.history)==1 and s.history[0]['tool_sequence']==['query_tickets']
    a.run();a.run()
    assert not a.exception and len(s.history)==1
    assert (s.trace_dir/'traces.jsonl').read_bytes()==before


def test_multiline_send_and_rerun_do_not_repeat_dispatch():
    a=app();a.toggle(key='user_multiline').set_value(True).run()
    a.text_area(key='user_message').set_value('查明天上海到杭州的高铁\n二等座')
    next(b for b in a.button if b.label=='发送').click().run()
    assert not a.exception
    s=a.session_state['user_sessions'][0];assert len(s.history)==1 and '\n' in s.history[0]['user_msg']
    a.run();assert len(s.history)==1


def test_topbar_new_and_history_activation_no_model_call():
    with patch('web.runtime.Agent') as agent:
        a=app();first=a.session_state['user_sessions'][0].sid
        a.button(key='user_new_top').click().run()
        assert not a.exception and len(a.session_state['user_sessions'])==2
        a.button(key='user_history_top_0').click().run()
        assert not a.exception and a.session_state['user_sessions'][a.session_state['user_session_index']].sid==first
        agent.assert_not_called()


def test_native_mobile_information_toggle_preserves_form_state():
    a=app();a.toggle(key='user_info_open').set_value(True).run()
    next(b for b in a.button if b.label=='退票费率').click().run()
    a.text_input(key='fr_amount').set_value('123.45')
    next(b for b in a.button if b.label=='计算退票费用').click().run()
    a.toggle(key='user_info_open').set_value(False).run()
    a.toggle(key='user_info_open').set_value(True).run()
    assert not a.exception and a.text_input(key='fr_amount').value=='123.45'


@pytest.mark.parametrize('approved',[True,False])
def test_confirmation_readable_details_and_original_authorization(approved):
    s=SimpleNamespace(sid='confirm-phase5',live=False,history=[],results=[],audits=[],confirm_action=Mock())
    a=AppTest.from_string("import streamlit as st\nfrom web.conversation import _confirm_cards\n_confirm_cards(st.session_state.s,{'tool':'lock_seat','args':{'train_no':'G7303','seat_type':'二等座','passengers':['张三']}},None,False)")
    a.session_state.s=s;a.run();s.confirm_action.assert_not_called()
    assert any(e.label=='查看技术细节' and not e.proto.expanded for e in a.expander)
    assert a.code and not a.json
    next(b for b in a.button if b.label==('确认此模拟操作' if approved else '取消此模拟操作')).click().run()
    assert s.confirm_action.call_count==1 and s.confirm_action.call_args.args[0] is approved


@pytest.mark.parametrize('scope',['session-a','session-b'])
def test_scroll_scope_is_explicit_and_sizing_never_mutates_inline_height(scope):
    html=scroll_bridge.bridge_html('user_chat_scroll','0:none:','none','',0,scope=scope)
    cfg=json.loads(html.split('var CFG = ',1)[1].split(';',1)[0])
    assert cfg['scope']==scope and cfg['maxHeight'] is None
    assert "setProperty('height'" not in html and 'window.scrollTo' not in html
