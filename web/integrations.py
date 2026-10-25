"""Capability declarations; not a second model runtime or an upload client."""
import importlib.util
import importlib.metadata
import os
from dataclasses import asdict, dataclass
import streamlit as st
from web.design import header, empty
from web.evidence import export_rows


@dataclass(frozen=True)
class ProviderCapability:
    id: str
    implemented: bool
    configured: bool
    availability: str
    verification: str
    tools: tuple[str, ...]
    limits: str


@dataclass(frozen=True)
class FutureModelConfig:
    """Reserved configuration shape. No credentials, defaults or network method."""
    provider: str = "bailian"
    api_key_env: str = "DASHSCOPE_API_KEY"
    base_url_env: str = "BAILIAN_BASE_URL"
    region_env: str = "BAILIAN_REGION"
    workspace_env: str = "BAILIAN_WORKSPACE_ID"
    model_env: str = "BAILIAN_MODEL"
    budget_env: str = "BAILIAN_MAX_REQUESTS"
    tool_calling: str = "待按具体模型验证"


def registry():
    lc = importlib.util.find_spec("langchain") is not None
    graph = importlib.util.find_spec("langgraph") is not None
    key = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
    ls = bool(os.getenv("LANGSMITH_API_KEY", "").strip())
    from target.tools import TOOL_NAMES
    return [ProviderCapability("Legacy Mock", True, True, "离线可用", "A 基线 / B 独立测试", tuple(TOOL_NAMES), "规则模型，不是自主大模型"),
        ProviderCapability("LangChain Mock", True, lc, "依赖已安装" if lc else "缺少依赖", "B 双引擎独立回归", tuple(TOOL_NAMES), "Mock 模型经真实 create_agent 框架执行"),
        ProviderCapability("DeepSeek Live", True, key, "已配置但本轮未联网" if key else "未配置", "历史真实证据；V3.3 尚未验证", ("query_tickets", "search_policy"), "默认只读；打开本页不会发送请求"),
        ProviderCapability("LangGraph 执行增强", True, graph, "已有 create_agent 图执行与 InMemorySaver", "本地 Mock 运行路径已验证", (), "自定义图、持久化 checkpoint、人工 interrupt、失败恢复尚未实现"),
        ProviderCapability("LangSmith", False, ls, "已配置但未验证" if ls else "未配置", "未验证", (), "SDK 已存在；前端关闭外传；远端关联尚未实现"),
        ProviderCapability("阿里云百炼", False, bool(os.getenv("DASHSCOPE_API_KEY")), "待集成", "尚未验证", (), "仅配置字段和能力声明；没有模型适配器，不可发起请求")]


def observation_envelope(audit):
    from target.diagnostics import sanitize
    return sanitize({"version": "ticket-agent-ui-observation/1", "trace_id": audit.get("trace_id"),
        "events": (audit.get("fault_report") or {}).get("executions", []), "graph": None,
        "graph_status": "尚未启用显式状态图输出", "remote_run_id": None, "external_export_enabled": False})


def integrations_page():
    header("集成中心", "检查已有能力与未来边界。配置存在不等于真实验证通过。", "外部 Trace 上报关闭")
    for row in registry():
        with st.container(border=True):
            left, right = st.columns([1, 3])
            left.markdown("**" + row.id + "**")
            left.caption(row.availability)
            right.write(row.limits)
            right.caption("验证：" + row.verification + " · 工具：" + (" / ".join(row.tools) or "不适用 / 未开放"))
    with st.expander("安装版本与未来配置接口"):
        versions = {}
        for name in ("streamlit", "altair", "langchain", "langgraph", "langchain-deepseek", "langsmith"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = "未安装"
        st.json({"installed_versions": versions, "future_bailian_config": asdict(FutureModelConfig()),
            "langsmith": {"upload_enabled": False, "remote_run_link": "尚未实现", "redaction": "复用 sanitize；不保留凭据、个人字段或 reasoning_content"}})
    empty("执行图：尚未启用", "当前没有输出显式节点与条件边的完整状态图。保留真实事件时间线，不随机绘制 DAG。")
    st.download_button("下载集成能力声明", export_rows([asdict(r) for r in registry()]), file_name="integration-capabilities.json", mime="application/json")
    st.caption("设计说明：docs/architecture/V3.3_未来框架与模型集成设计.md。新增 Provider 须独立验证工具协议、预算与脱敏；没有自动在线健康探测。")
