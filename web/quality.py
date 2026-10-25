"""Mutation and specialist analysis preserve their original denominators."""
import streamlit as st
from web.design import header,panel_title,kpis,empty
from web.evidence import MUTATIONS,mutation_rows,read_json,B_SOURCE,AUDIT_SOURCE,export_rows
from web import charts
from web.dashboard import quality_dimensions
from web.trace_view import show_record


def mutation_matrix():
    population=st.radio("变异数据范围",["选定矩阵（69 组合）","额外假车次探测（16 案例）"],horizontal=True)
    rows=[r for r in mutation_rows() if r["origin"]==("选定矩阵" if population.startswith("选定") else "额外探测")]
    case_ids=list(dict.fromkeys(r["case_id"] for r in rows))
    selected=st.multiselect("显示宿主用例",case_ids,default=case_ids[:18])
    lookup={(r["mutation"],r["case_id"]):r for r in rows}
    grid=[dict(lookup.get((m,c),{"mutation":m,"case_id":c,"status":"not_applicable" if m=="concurrent_duplicate_order" else "not_verified","c5":None})) for m in MUTATIONS for c in selected]
    if not grid:
        empty("请选择用例","空选择不会自动显示为全部通过。")
        return
    event=st.altair_chart(charts.heatmap(grid),width="stretch",on_select="rerun",key="mutation_heatmap")
    st.caption("点击热力图可定位记录。detected=任意规则检出；c5=true 才是 C5 命中。未在矩阵内的组合保持未验证；M8 对话单元格不适用。")
    selection=event.selection.get("cell",[]) if hasattr(event,"selection") else []
    selected_cell=selection[0] if selection else None
    defaults=0
    if selected_cell:
        defaults=next((i for i,r in enumerate(grid) if r["case_id"]==selected_cell.get("case_id") and r["mutation"]==selected_cell.get("mutation")),0)
    index=st.selectbox("单元格与原始断言详情",range(len(grid)),index=defaults,format_func=lambda i:grid[i]["mutation"]+" / "+grid[i]["case_id"]+" · "+grid[i]["status"])
    chosen=grid[index]
    st.json(chosen)
    st.info("B 本轮提供的是压缩执行摘要；没有包含对应完整 Trace/临时数据库，不能补造参数与权威快照。请由 B 补充关联证据。")


def hallucination_topic():
    probe=read_json(B_SOURCE/"probe_m6_m8.json")
    kpis([("选定假车次矩阵","14 / 14","其中 12 条命中 C5"),("额外探测判失败","14 / 16","独立分母；保留原结果"),("真实漏检","T04","G9999 已进入回复"),("不适用","R01","未查票、未触发假车次")])
    st.dataframe([{ "用例":r["case_id"],"G9999 进入回复":r["G9999_进入回复"],"任意规则检出":r["killed"],"C5 命中":"C5" in r["failed_rules"],"失败规则":", ".join(r["failed_rules"]),"回复片段":r["reply_片段"]} for r in probe["details"]],hide_index=True,width="stretch")
    st.caption("T04 未配置 C5；R01 不适用。F15/M12 只触发 C1/R1。B 压缩记录未保存数据库权威列表，不能在此复造。")
    panel_title("A 有独立标注的有限规则样本","与上面的 B 正式用例、变异矩阵分别统计；不是通用语义准确率。")
    report=read_json(AUDIT_SOURCE/"report.json")
    samples=report["labelled_samples"]
    counts={"TP":0,"FP":0,"FN":0,"TN":0,"无法判定":0}
    for r in samples:
        expected=r.get("expected_semantic_outcome")
        actual=r["judgement"]["hallucination"].get("hallucination_detected")
        key="无法判定" if expected is None or actual is None else "TP" if expected and actual else "FN" if expected else "FP" if actual else "TN"
        counts[key]+=1
    kpis([(k,v,"6 个可判样本；2 个含糊样本单列") for k,v in counts.items()])
    st.dataframe([{ "样本":r["case_id"],"回复":r["reply"],"标注":r.get("expected_semantic_outcome"),"检测":r["judgement"]["hallucination"].get("hallucination_detected")} for r in samples],hide_index=True,width="stretch")
    paths=sorted((AUDIT_SOURCE/"cases").glob("*m7-mutant/audit_runs.jsonl"))
    if paths:
        from web.evidence import read_jsonl
        records,_=read_jsonl(paths[0])
        if records:
            audit=records[0]
            with st.expander("A 历史离线样本：权威数据库、声称车次与 Trace"):
                st.json({"authority":audit.get("authority"),"reply":audit.get("public_trace",{}).get("reply"),"hallucination":audit.get("judgement",{}).get("hallucination")})
                show_record(audit,key="hallucination_sample")


def concurrency_topic():
    data=read_json(B_SOURCE/"m8_idempotent.json")
    st.caption("B 独立后端验证 · 2026-10-20 · Mock · 10 条检查，包含多个断言共享一个场景；不是 10 次模型对话。")
    import json
    st.dataframe([dict(r,expect=json.dumps(r.get("expect"),ensure_ascii=False),actual=json.dumps(r.get("actual"),ensure_ascii=False)) for r in data["records"]],hide_index=True,width="stretch")
    st.info("B 本轮 JSON 未保存锁座 ID 和全部请求明细；这些字段显示为未提供。下面可独立查看 A 保存的正常/影子库对照，不能冒充 B 原始证据。")
    from web.evidence import read_jsonl
    audits=[]
    for pattern in ("concurrency-normal-same_lock_two","concurrency-mutant-two"):
        records,_=read_jsonl(AUDIT_SOURCE/"cases"/pattern/"audit_runs.jsonl")
        audits.extend(records)
    st.dataframe([{ "来源":"A 历史离线自测","组别":r.get("mode"),"并发请求":r.get("concurrency",{}).get("workers"),"落库订单":r.get("judgement",{}).get("actual_behavior",{}).get("orders"),"影子库":r.get("database_isolation",{}).get("shadow_only_mutation"),"资源清理":r.get("resources_cleaned")} for r in audits],hide_index=True,width="stretch")
    for i,r in enumerate(audits):
        with st.expander("正常组" if r.get("mode")=="normal_backend" else "受控影子库缺陷组"):
            show_record(r,key="concurrency_history_"+str(i))
    st.caption("正常库沿用原 UNIQUE 约束；缺陷仅在临时影子库。单进程多线程验证不代表多进程压测。")


def specialist_topics():
    groups={"回答—行为一致性":"已有工具轨迹与明确成功标记；通用语言声明一致性评测规划中。",
            "RAG 忠实度":"已有政策引用用例；逐句支持/无依据标注、RAGAS/DeepEval 暂无本轮记录。",
            "语言扰动":"原用例可查看；尚未形成同意图多表达的成对数据集。",
            "长对话记忆":"B 多轮维度 12 条已执行；长窗口记忆专项暂无记录。",
            "行为边界":"已有授权与流程前置条件测试；允许合理澄清路径。",
            "工具异常与恢复":"已有工具错误用例；通用语义恢复率仍未知，不能以安全停止代替恢复。"}
    choice=st.selectbox("AI 专项分类",list(groups))
    st.info(groups[choice])
    from web.evidence import batch
    ids={"回答—行为一致性":{"F04","F05","F06","T24"},"RAG 忠实度":{"R01","R02","R13"},"语言扰动":set(),
         "长对话记忆":{"M01","M05","M09","M12"},"行为边界":{"X15","X16","X01","X03"},"工具异常与恢复":{"T20","T23","T24"}}
    candidates=[r for r in batch("legacy")["rows"] if r["id"] in ids[choice]]
    if not candidates:
        empty("暂无该专项数据集","分类接口已准备；未执行的测试保持未验证。")
        return
    st.dataframe([{ "用例":r["id"],"维度":r["dimension"],"状态":r["status"],"工具序列":" → ".join(t for turn in r.get("executed",[]) for t in turn.get("tool_sequence",[]))} for r in candidates],hide_index=True,width="stretch")
    st.caption("这是相关原始用例入口，不是上述六类专项全部完成的证明。")


def quality_page():
    header("质量分析","分别检查既有断言、注入检出、事实一致性与并发边界。","Mock / 离线证据")
    section=st.radio("质量专题",["七维度","变异热力图","幻觉检测","并发幂等","AI 专项"],horizontal=True)
    {"七维度":quality_dimensions,"变异热力图":mutation_matrix,"幻觉检测":hallucination_topic,"并发幂等":concurrency_topic,"AI 专项":specialist_topics}[section]()
