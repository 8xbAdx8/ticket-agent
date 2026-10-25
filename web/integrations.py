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
    from target.observability import configuration_status
    from target.live_providers import configuration
    ls = configuration_status()
    bailian=configuration("bailian")
    from target.tools import TOOL_NAMES
    return [ProviderCapability("Legacy Mock", True, True, "离线可用", "A 基线 / B 独立测试", tuple(TOOL_NAMES), "规则模型，不是自主大模型"),
        ProviderCapability("LangChain Mock", True, lc, "依赖已安装" if lc else "缺少依赖", "B 双引擎独立回归", tuple(TOOL_NAMES), "Mock 模型经真实 create_agent 框架执行"),
        ProviderCapability("DeepSeek Live", True, key, "已配置但本轮未联网" if key else "未配置", "历史真实证据；V3.3 尚未验证", ("query_tickets", "search_policy"), "默认只读；打开本页不会发送请求"),
        ProviderCapability("LangGraph 执行增强", True, graph, "已有 create_agent 图执行与 InMemorySaver", "本地 Mock 运行路径已验证", (), "自定义图、持久化 checkpoint、人工 interrupt、失败恢复尚未实现"),
        ProviderCapability("LangSmith", True, ls["key_configured"],
            {"user_disabled":"用户主动关闭","not_configured":"未配置","configured_unverified":"已配置但未验证"}.get(ls["state"],"配置错误"),
            "以单次导出回执为准；未自动验证", (), "显式确认后仅导出白名单记录，POST + GET 回读验证；本地审计独立保留"),
        ProviderCapability("阿里云百炼", True, bailian["configured"], "已配置但未验证" if bailian["configured"] else "未配置",
            "代码/离线 SDK 桩已验证；本轮真实请求未执行", ("query_tickets","search_policy"), "独立 ChatOpenAI 适配器、地址/模型必填；只读、独立预算、无 Mock 回退")]


def observation_envelope(audit):
    from target.diagnostics import sanitize
    return sanitize({"version": "ticket-agent-ui-observation/1", "trace_id": audit.get("trace_id"),
        "events": (audit.get("fault_report") or {}).get("executions", []), "graph": None,
        "graph_status": "尚未启用显式状态图输出", "remote_run_id": None, "external_export_enabled": False})


def integrations_page():
    header("集成中心", "检查已有能力与未来边界。配置存在不等于真实验证通过。", "远端追踪须显式确认")
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
        from target.observability import configuration_status,UPLOAD_SCOPE
        from target.live_providers import configuration
        from target.diagnostics import sanitize
        st.json(sanitize({"installed_versions":versions,"bailian":configuration("bailian"),"langsmith":configuration_status()}))
        st.caption(UPLOAD_SCOPE+" 自由文本中的任意姓名等不能保证自动识别，导出前必须人工检查预览。")
    receipts=[r for session in st.session_state.get("user_sessions",[])+st.session_state.get("lab_archives",[]) for r in session.remote_receipts]
    if receipts:
        latest=receipts[-1]
        st.markdown("**最近远端回执："+{"verified":"已验证","failed":"运行失败","user_disabled":"用户主动关闭"}.get(latest["remote_status"],latest["remote_status"])+"**")
        st.json(latest)
    empty("执行图：尚未启用", "当前没有输出显式节点与条件边的完整状态图。保留真实事件时间线，不随机绘制 DAG。")
    st.download_button("下载集成能力声明", export_rows([asdict(r) for r in registry()]), file_name="integration-capabilities.json", mime="application/json")
    st.caption("实施说明：docs/architecture/V3.3_Provider与LangSmith架构.md。新增模型仍须独立真实验证；没有自动在线健康探测。")
