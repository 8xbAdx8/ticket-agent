"""Single authoritative navigation contract for the test workbench.

`web.app` must not import this module through a page module; this module has no
Streamlit or target imports, so both navigation and page views can use it.
"""
WORKBENCH_PAGES = (
    "AI 场景总测试",
    "质量分析",
    "RAG / 多轮 / 安全",
    "边界与异常测试",
    "性能测试",
)
