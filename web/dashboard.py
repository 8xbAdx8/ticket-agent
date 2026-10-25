"""Independent B batches and A audit results never share an invented total."""
import streamlit as st
from web.design import header,kpis,empty,panel_title
from web import charts
from web.evidence import batch,summary,dimension_rows,latency_rows,mutation_totals,verified_manifest,export_rows,read_json,B_SOURCE


def choose_batch(key):
    engine=st.selectbox("当前数据源",["legacy","langchain"],format_func=lambda e:"B 独立测试 · "+("Legacy Mock" if e=="legacy" else "LangChain Mock"),key=key)
    data=batch(engine)
    st.caption(f"B 独立测试 · Mock · 执行日期 {data['date']}（精确时间未知） · 代码 {data['commit'][:12]} · {data['source']}")
    return data


def dashboard_page():
    header("测试总览","按批次审阅质量，保留失败、未验证与证据边界。","质量工作台")
    data=choose_batch("dashboard_batch")
    counts=summary(data["rows"])
    kpis([("实际执行",counts["executed"],f"定义用例 {counts['defined']}；不相加其他批次"),
          ("通过",counts["passed"],"当前适用用例"),("失败",counts["failed"],"当前保存结果"),
          ("通过率",f"{counts['rate']:.1%}" if counts["rate"] is not None else None,f"{counts['passed']} / {counts['executed']}；不含不适用")])
    a,b=st.columns([1.2,1],gap="large")
    with a,st.container(border=True):
        panel_title("七维度通过情况","这是已有断言的通过率，不是功能覆盖率或真实模型正确率。")
        st.altair_chart(charts.dimensions(dimension_rows(data["rows"])),width="stretch")
    with b,st.container(border=True):
        panel_title("执行状态分布",f"不适用 {counts['not_applicable']} · 跳过 {counts['skipped']} · 未验证 {counts['not_verified']} · 无法判定 {counts['indeterminate']}")
        st.altair_chart(charts.statuses(counts),width="stretch")
    c,d=st.columns([1.2,1],gap="large")
    with c,st.container(border=True):
        panel_title("单轮执行耗时","Mock 工具与规则耗时；不能当作 DeepSeek API 性能。")
        st.altair_chart(charts.latency(latency_rows(data["rows"])),width="stretch")
    with d,st.container(border=True):
        panel_title("选定七类变异矩阵","69 / 69 个指定组合被任意规则检出。M8 单列；额外探测仍有 T04 漏检。")
        st.altair_chart(charts.mutation_distribution(mutation_totals()),width="stretch")
    st.warning("已知边界：T04 假车次未检出；R01 政策场景不适用；F15、M12 被其他规则检出，不能算 C5 命中。当前 V3.3 真实模型专项未执行。")
    with st.expander("失败、不适用与未验证用例"):
        rows=[{"用例":r["id"],"维度":r["dimension"],"状态":r["status"],"说明":r.get("note","")} for r in data["rows"] if r["status"]!="passed"]
        st.dataframe(rows,hide_index=True,width="stretch")
    with st.expander("来源校验与当前批次下载"):
        meta,checks=verified_manifest()
        st.json({"metadata":meta,"sha256_match":checks})
        st.download_button("下载当前批次脱敏结果",export_rows(data),file_name=data["id"]+".json",mime="application/json")
    empty("历史趋势：暂无足够可比批次","当前接入 B 本轮两个独立引擎批次；未把 A 自测或旧版文字报告拼成趋势线。")


def quality_dimensions():
    data=choose_batch("quality_batch")
    rows=dimension_rows(data["rows"])
    st.altair_chart(charts.dimensions(rows),width="stretch")
    st.dataframe([{ "维度":r["dimension"],"定义用例":r["defined"],"执行":r["executed"],"通过":r["passed"],"失败":r["failed"],"跳过":r["skipped"],"不适用":r["not_applicable"],"未验证":r["not_verified"],"无法判定":r["indeterminate"]} for r in rows],hide_index=True,width="stretch")
    st.caption("来源为 B 原始用例及执行记录；没有以代码覆盖率代替测试维度。RAG 15 条是现有政策断言，不代表已完成 RAGAS/DeepEval 忠实度评测。")
