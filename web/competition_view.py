"""Competition coverage landing page, backed only by independent B snapshots."""
import streamlit as st

from web.design import header, kpis, table
from web.evidence import (
    DIMENSIONS, batch, b_aux_batch, cases, dimension_rows, summary, verified_manifest,
)


REQUIREMENTS = {
    "功能准确性": "典型场景下回答是否正确、有用",
    "工具调用": "是否在正确时机调用正确工具",
    "RAG": "知识库召回准确率与回答忠实度",
    "多轮": "上下文记忆与逻辑连贯性",
    "安全": "越狱与角色扮演下的安全护栏",
    "边界": "不完整输入、超长上下文、工具异常",
    "性能": "并发响应速度与资源消耗",
}
ENGINES = {"legacy": "Legacy Mock", "langchain": "LangChain Mock"}
BATCHES = ("B 独立测试", "当前测试实验室（实时）", "A 历史离线自测", "A 当前隔离实验")


def overview_data():
    """Compose existing adapters; do not introduce a second scoring definition."""
    catalog = cases()
    metadata, checks = verified_manifest()
    engines = {}
    for engine in ENGINES:
        data = batch(engine)
        engines[engine] = {
            "data": data, "summary": summary(data["rows"]),
            "dimensions": dimension_rows(data["rows"]),
        }
    mutations = b_aux_batch("选定变异矩阵（69 组合）")
    return {
        "catalog": catalog, "catalog_dimensions": dimension_rows(catalog),
        "engines": engines, "metadata": metadata, "sha256_match": checks,
        "mutations": mutations, "mutation_summary": summary(mutations["rows"]),
    }


def open_dimension(dimension, engine):
    """Widget callback runs before the next render, including sidebar navigation."""
    if dimension not in DIMENSIONS or engine not in ENGINES:
        raise ValueError("未知的证据维度或引擎")
    st.session_state.update(
        workspace_page="质量分析", quality_source="B 历史测试",
        quality_section="七维度", quality_batch=engine, quality_dimension=dimension,
    )
    # Do not reuse a previous dimension's case selection.
    st.session_state.pop("quality_case", None)


def matrix_rows(view):
    rows = []
    for index, dimension in enumerate(DIMENSIONS):
        for engine, label in ENGINES.items():
            result = view["engines"][engine]["dimensions"][index]
            rows.append({
                "维度": dimension, "比赛要求": REQUIREMENTS[dimension], "引擎": label,
                "用例数": view["catalog_dimensions"][index]["defined"],
                **{label: result[key] for key, label in (
                    ("executed", "实际执行"), ("passed", "通过"), ("failed", "失败"),
                    ("not_applicable", "不适用"), ("not_verified", "未验证"),
                    ("indeterminate", "无法判定"), ("skipped", "跳过"), ("missing", "状态缺失"),
                )},
            })
    return rows


def _engine_result(result):
    st.markdown(f"执行 **{result['executed']}** · 通过 **{result['passed']}** · 失败 **{result['failed']}**")
    st.caption(f"不适用 {result['not_applicable']} · 未验证 {result['not_verified']} · 无法判定 {result['indeterminate']}")
    if result["skipped"] or result["missing"]:
        st.caption(f"跳过 {result['skipped']} · 状态缺失 {result['missing']}")


def competition_page(sessions):
    # Keep existing batch views reachable, while the default is always independent B.
    source = st.session_state.get("competition_source", BATCHES[0])
    if source != "B 独立测试":
        with st.expander("其他批次与实时实验", expanded=True):
            st.selectbox("证据批次", BATCHES, key="competition_source")
        from web.dashboard import dashboard_page
        dashboard_page(
            [s.trace_dir for s in sessions],
            [s.trace_dir for s in sessions if s.mode == "lab"], source=source,
        )
        return

    try:
        view = overview_data()
    except (OSError, ValueError, KeyError) as exc:
        header("比赛七维度覆盖总览", "独立测试证据暂不可读", "Mock · B 独立测试")
        st.error("无法读取独立测试数据或 manifest，请检查交接包中的 web/datasets；未生成成绩。")
        st.caption("错误类型：" + type(exc).__name__)
        return

    header("比赛七维度覆盖总览",
           f"{len(view['catalog'])} 条测试用例 · 七维度覆盖 · 双引擎执行 · 全程证据可追溯",
           "Mock · B 独立测试")
    meta = view["metadata"]
    st.caption(f"独立测试记录 · Mock 引擎 · 实际执行日期 {meta.get('execution_date') or '未记录'}"
               f" · 代码 SHA {meta.get('code_commit') or '未记录'}")
    if not view["sha256_match"] or not all(view["sha256_match"].values()):
        st.error("原始测试文件与 manifest 哈希不一致，以下为当前可读记录，证据完整性待核验。")
    for engine, item in view["engines"].items():
        errors = item["data"]["read_errors"]
        if errors["missing"] or errors["invalid"] or errors["truncated"]:
            st.warning(ENGINES[engine] + " 记录不完整：" + str(errors))

    totals = {key: sum(item["summary"][key] for item in view["engines"].values())
              for key in ("executed", "passed")}
    mutant = view["mutation_summary"]
    kpis([
        ("测试用例总数", len(view["catalog"]), "来源：独立测试用例目录；不是执行次数"),
        ("双引擎实际执行次数", totals["executed"],
         "Legacy " + str(view["engines"]["legacy"]["summary"]["executed"])
         + " / LangChain " + str(view["engines"]["langchain"]["summary"]["executed"])),
        ("实际通过数量", totals["passed"], "两个引擎分别执行的通过记录之和"),
        ("缺陷注入检出情况", f"{mutant['passed']} / {mutant['defined']}", "选定变异组合；独立于七维度成绩"),
    ])
    st.subheader("七维度成绩矩阵")
    with st.container(key="competition_matrix_heading"):
        headings = st.columns([1.5, 1.8, 1.8, 1.3], gap="small")
        for col, text in zip(headings, ("维度 / 比赛要求", "Legacy Mock", "LangChain Mock", "查看原始证据")):
            col.markdown("**" + text + "**")
    for index, dimension in enumerate(DIMENSIONS):
        columns = st.columns([1.5, 1.8, 1.8, 1.3], gap="small")
        with columns[0]:
            st.markdown(f"**{dimension}** · {view['catalog_dimensions'][index]['defined']} 用例")
            st.caption(REQUIREMENTS[dimension])
        for col, engine in zip(columns[1:3], ENGINES):
            with col:
                with st.container(key=f"competition_engine_label_{engine}_{index}"):
                    st.caption(ENGINES[engine])
                _engine_result(view["engines"][engine]["dimensions"][index])
        with columns[3], st.container(key=f"competition_links_{index}"):
            a, b = st.columns(2, gap="small")
            for col, engine, label in ((a, "legacy", "Legacy"), (b, "langchain", "LangChain")):
                col.button(label, key=f"competition_evidence_{engine}_{index}",
                           help=f"{dimension} · {ENGINES[engine]}：用例、原始断言与执行记录",
                           on_click=open_dimension, args=(dimension, engine), width="stretch")

    with st.expander("完整矩阵与 CSV"):
        table(matrix_rows(view), "competition_matrix", search=False)
    with st.expander("口径与边界"):
        st.write("这是 B 保存的独立 Mock 测试快照，执行版本见上方 SHA；不是当前工作区重跑成绩，也不是 Live 模型成绩。")
        st.write("用例数来自 case_catalog；执行与通过数量复用现有 summary/dimension_rows。执行口径为通过＋失败；跳过、不适用、未验证、无法判定与状态缺失分别列出，不计入通过率。多轮用例仍按用例计数，不按对话轮数或 HTTP 请求计数。")
        st.write("缺陷检出使用 mutation.json 的选定组合，未混入额外探测或 M8 专项。检出不等于 Agent 已识别或恢复，也不等于业务成功。")
        st.write("比赛要求摘要依据本轮提供的对接说明；原始比赛条款仍需对照原件。RAG 用例成绩不代表完整回答忠实度已通过；性能用例成绩不代表已验证全部吞吐量与资源指标。")
        st.caption("精确执行时间：" + (str(meta.get("execution_time")) if meta.get("execution_time") else "未记录"))
        st.json({"metadata": meta, "sha256_match": view["sha256_match"],
                 "sources": {e: item["data"]["source"] for e, item in view["engines"].items()},
                 "mutation_source": view["mutations"]["source"]})
    with st.expander("其他批次与实时实验"):
        st.selectbox("证据批次", BATCHES, key="competition_source")
        st.caption("实时实验、A 自测与 B 的独立成绩分开查看，不合并统计。")
