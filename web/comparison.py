import streamlit as st
from web.design import header, kpis, empty
from web.evidence import batch, historical_live
from web.trace_view import safe_json


def comparison_page(runtime_dirs=()):
    header("模型与引擎对比", "先确认相同用例，再比较可核对的行为。", "已有证据")
    mode = st.radio("对比范围", ["Legacy / LangChain Mock", "历史 DeepSeek 证据", "当前多模型 Live"], horizontal=True)
    if mode=="当前多模型 Live":
        from pathlib import Path
        import config
        from web.evidence import read_jsonl
        roots=list(runtime_dirs)+list((config.BASE_DIR/"artifacts/runtime/v33-live-providers").glob("*/traces"))
        rows=[]
        for root in roots[:100]:
            path=Path(root)/"provider_runs.jsonl"
            if path.is_file():
                records,_=read_jsonl(path)
                rows.extend({"source":str(path.relative_to(config.BASE_DIR)),"run":r} for r in records if r.get("mode")=="live")
        if not rows:
            empty("暂无本轮多模型 Live 记录","请先获授权，使用独立命令或页面实际运行；不会借用历史 DeepSeek 或 Mock 代替。")
            return
        left,right=st.columns(2)
        for col,provider in ((left,"deepseek_live"),(right,"bailian_live")):
            with col:
                st.markdown("### "+provider)
                subset=[r for r in rows if r["run"].get("provider")==provider]
                if not subset:
                    st.info("该 Provider 本轮暂无记录。")
                    continue
                index=st.selectbox("选择独立运行",range(len(subset)),format_func=lambda i:str(subset[i]["run"].get("case_id"))+" · "+str(subset[i]["run"].get("requested_at")),key="live_compare_"+provider)
                item=subset[index]
                st.caption("来源："+item["source"]+"；完整参数、结果、模型及 Git SHA 见 JSON。")
                safe_json(item["run"],"live_compare_json_"+provider)
        st.caption("同一 case ID 仍须核对输入、日期、工具集及配置一致；这只是原始记录对照，未自动判定正确率/费用。")
        return
    if mode.startswith("Legacy"):
        a, b = batch("legacy"), batch("langchain")
        aa = {r["id"]: r for r in a["rows"] if r["status"] in ("passed", "failed")}
        bb = {r["id"]: r for r in b["rows"] if r["status"] in ("passed", "failed")}
        common = sorted(set(aa) & set(bb))
        kpis([("共同执行用例", len(common), "比较交集，不将101与100相加"), ("数据模式", "Mock", "两种引擎，非两个真实大模型"),
            ("执行日期", a["date"], "精确时间未提供"), ("代码版本", a["commit"][:7], "同一 B 被测基线")])
        selected = st.selectbox("同一用例", common, index=common.index("F01") if "F01" in common else 0, key="compare_case")
        for col, label, row in zip(st.columns(2), ["Legacy Mock", "LangChain Mock"], [aa[selected], bb[selected]]):
            with col, st.container(border=True):
                st.markdown("### " + label)
                st.caption("B 独立测试 · Mock · " + row["status"])
                for t in row.get("executed", []):
                    st.write(t.get("reply", "未提供"))
                    st.caption(" → ".join(t.get("tool_sequence", [])) + " · " + str(t.get("total_latency_ms", "未知")) + " ms")
                with st.expander("原始判定与执行摘要"):
                    st.json(row)
        seq_a = [t for turn in aa[selected].get("executed", []) for t in turn.get("tool_sequence", [])]
        seq_b = [t for turn in bb[selected].get("executed", []) for t in turn.get("tool_sequence", [])]
        st.info("工具序列相同。" if seq_a == seq_b else "工具序列存在差异；合理澄清路径与业务约束须独立核对，不能只因序列不同判错。")
        st.caption("Token 与 API 成本：Mock 不适用。B 压缩摘要未含完整工具参数与 Trace；RAG 忠实度、语义恢复与回答—行为一致性没有统一标注，保持未验证。")
    else:
        records = historical_live()
        if not records:
            empty("没有可用历史 Live 文件", "不会用 Mock 替代第二个真实模型。")
            return
        i = st.selectbox("历史真实运行", range(len(records)), format_func=lambda i: str(records[i]["path"].parent.name))
        r = records[i]
        st.warning("历史真实 DeepSeek，仅供只读审阅；不是 V3.3 新验证，不与当前 Mock 延迟合并。V3.1 full_sandbox 历史写操作也不代表默认 Live 已开放。")
        st.caption("来源：" + str(r["path"].relative_to(__import__('config').BASE_DIR)) + " · 实际费用未知。")
        safe_json(r["data"], "historical_live")
    empty("V3.5 同证据双模型对照尚未执行", "Qwen3.8-Flash已有真实FC与RAG记录，见RAG知识库；DeepSeek仅保留历史证据。未新增DeepSeek请求，不混成双模型排名。")
