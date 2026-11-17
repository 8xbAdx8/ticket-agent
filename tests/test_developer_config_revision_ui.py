"""Regression for restoring Baseline directly after an in-page override save."""
from streamlit.testing.v1 import AppTest

from target.dev_overrides import Store


def test_save_then_restore_baseline_uses_the_saved_revision(tmp_path, monkeypatch):
    import web.developer_config as view

    store = Store(tmp_path / "overrides")
    monkeypatch.setattr(view, "Store", lambda: store)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from web.runtime import Conversation\n"
        "from web.developer_config import editor\n"
        "if 'test_session' not in st.session_state:\n"
        "    st.session_state.test_session = Conversation('lab', execution_mode='developer_custom')\n"
        "editor(st.session_state.test_session)\n"
    ).run()
    sid = app.session_state["test_session"].sid
    app.text_area(key="dev_suffix_" + sid).set_value("隔离测试附加提示")
    next(item for item in app.button if item.label == "保存会话配置").click().run()
    assert store.load(sid, owner=sid)["revision"] == 1
    app.button(key="dev_restore_" + sid).click().run()
    assert not app.exception
    restored = store.load(sid, owner=sid)
    assert restored["revision"] == 2
    assert restored["config_source"] == "baseline"
    assert app.text_area(key="dev_suffix_" + sid).value == ""
