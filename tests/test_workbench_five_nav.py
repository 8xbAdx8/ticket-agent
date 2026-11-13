"""Navigation contract for the five-page test workbench (no model/API)."""
import os
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import config


from web.workbench_config import WORKBENCH_PAGES

EXPECTED = list(WORKBENCH_PAGES)


def test_workbench_has_exactly_five_navigation_entries():
    env = {
        "TICKET_WEB_OFFLINE_ONLY": "1",
        "TICKET_DISABLE_LOCAL_SECRETS": "1",
        "DEEPSEEK_API_KEY": "",
        "DASHSCOPE_API_KEY": "",
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
    }
    with patch.dict(os.environ, env), patch.multiple(config, PROVIDER="mock", ENGINE="legacy",
                                                    LC_TOOLSET="all", USE_HTTP_MOCK=False,
                                                    USE_VECTOR_RAG=False):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "web/app.py"),
                                default_timeout=30).run()
        app.radio(key="workspace_mode").set_value("测试工作台").run()
        assert not [item for item in app.exception], [item.message for item in app.exception]
        page = app.radio(key="workspace_page")
        assert list(page.options) == EXPECTED
        assert page.value == EXPECTED[0]
        # User and developer workspaces remain available on the top-level switch.
        assert list(app.radio(key="workspace_mode").options) == ["用户工作空间", "开发者工作空间", "测试控制台"]
