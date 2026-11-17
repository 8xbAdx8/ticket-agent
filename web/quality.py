"""Mutation and specialist analysis preserve their original denominators."""
import streamlit as st
from web.design import header,panel_title,kpis,empty,table
from web.evidence import (
    MUTATIONS, MUTATION_SOURCES, STATUS_LABELS, mutation_group, mutation_summary,
    read_json, B_SOURCE, AUDIT_SOURCE, export_rows,
)
from web import charts
from web.dashboard import quality_dimensions
from web.trace_view import show_record


MUTATION_DETAILS = {
    "date_offset": ("M1 日期偏移", "让查票使用偏移后的日期"),
    "skip_lock": ("M2 跳过锁座", "跳过订单流程中的锁座步骤"),
    "repeat_call": ("M3 重复调用", "让同一工具被重复调用"),
    "infinite_loop": ("M4 无限循环", "让 Agent 反复监控余票，验证工具轮数上限能否拦截"),
    "route_error": ("M5 线路错误", "把原请求导向错误的查询或线路"),
    "no_citation": ("M6 缺少政策引用", "去掉回答中的政策依据"),
    "hallucinated_train": ("M7 虚构车次", "向查票工具结果注入假车次"),
    "concurrent_duplicate_order": ("M8 并发重复订单", "让并发请求绕过防重复建单检查"),
}


def mutation_metrics_row(label, group, rows=None):
    whole_group = rows is None
    if whole_group:
        rows = group["rows"]
        absent = group["missing_records"]
    else:
        absent = 0
    counts = mutation_summary(rows, absent)
    rate_known = absent is not None and (whole_group or group["missing_records"] == 0)
    return {"范围": label, "记录总数": counts["total"] if absent is not None else "未知",
            "适用分母": counts["applicable"] if absent is not None else "未知",
            **{text: counts[key] if absent is not None else "未知" for key, text in STATUS_LABELS.items()},
            "适用项检出率": f"{counts['rate']:.1%}" if rate_known and counts["rate"] is not None else "—"}


def _select_mutation_cell():
    event = st.session_state.get("mutation_heatmap") or {}
    selection = event.get("selection", {}).get("cell", [])
    if selection:
        cell = selection[0]
        st.session_state["mutation_case"] = (cell["mutation"], cell["case_id"])


def _show_mutation_case(row, source):
    from target.diagnostics import sanitize
    label, fault = MUTATION_DETAILS[row["mutation"]]
    state = row["status"]
    st.markdown(f"**{label} · {row['case_id']} · {STATUS_LABELS[state]}**")
    original = row.get("original")
    if original is None:
        st.info("该组合没有对应的执行证据。M8 并发幂等使用独立后端证据。")
        return
    original = sanitize(original)
    st.write(f"故障注入会{fault}。")
    st.write("预期是故障触发后由评测断言识别异常。")
    if original.get("reply_片段"):
        st.caption("实际回复片段")
        st.text(original["reply_片段"])
    else:
        st.caption("原记录未保存实际回复片段或完整工具轨迹。")
    if state == "detected":
        st.success("至少一条评测断言记录了异常。" if row["failed_rules"] else "原记录标记已检出，未提供具体断言。")
    elif state == "missed":
        st.warning("原记录明确标记未检出；该项计为漏检。")
    elif state == "not_applicable":
        st.info("该场景不适用此类故障注入，未进入适用分母。")
    else:
        st.info("现有记录无法确认这项故障是否被检出。")
    if original.get("G9999_进入回复") is True:
        st.caption("原记录确认注入的假车次 G9999 进入了回复。")
    if row["failed_rules"]:
        st.caption("触发断言：" + "、".join(str(rule) for rule in row["failed_rules"]))
    st.caption(f"原始证据 · {source} · {row['case_id']}")
    with st.expander("查看原始变异记录"):
        st.json(original)


def mutation_matrix(*, on_m8=None):
    groups = {origin: mutation_group(origin) for origin in MUTATION_SOURCES}
    panel_title("缺陷注入统计", "B 历史 Mock / TEST_ONLY。选定矩阵与额外探测各自统计。")
    table([mutation_metrics_row(origin, group) for origin, group in groups.items()], "mutation_population", search=False)
    st.caption("适用项检出率 = 已检出 / 适用分母。仅扣除明确不适用的记录；未执行、未知、缺失保留。B 原始记录未单独标注误报。")
    origin = st.radio("变异数据范围", list(groups), horizontal=True, key="mutation_population")
    group = groups[origin]
    if group["missing_records"] is None:
        st.warning(f"{origin}的原始证据不可读，记录总数未知。来源 {group['source']}")
        return
    if group["missing_records"]:
        st.warning(f"{origin}有 {group['missing_records']} 条应有记录缺失或不可读，尚无法分配到具体变异类型。")
    rows = group["rows"]
    if not rows:
        empty("暂无可读取的变异记录", f"当前范围 · {group['source']}")
        return

    panel_title("按变异类型查看", "分布仅涵盖可读记录。缺失项无法归类时，各类型检出率暂不显示。"
                if group["missing_records"] else None)
    by_type = {kind: [row for row in rows if row["mutation"] == kind] for kind in MUTATIONS}
    table([mutation_metrics_row(MUTATION_DETAILS[kind][0], group, subset) for kind, subset in by_type.items()],
          "mutation_types", search=False)
    if on_m8 is None:
        def on_m8():
            st.session_state["quality_section"] = "并发幂等"
    st.button("查看 M8 并发幂等原始证据", key="mutation_m8_evidence", on_click=on_m8)
    mutation = st.selectbox("变异类型", [None, *MUTATIONS], key="mutation_type",
                            format_func=lambda key: MUTATION_DETAILS[key][0] if key else "全部类型")
    displayed = by_type[mutation] if mutation else rows
    if not displayed:
        detail = "M8 的并发幂等记录在独立证据入口中。" if mutation == MUTATIONS[-1] else "当前范围没有保存该类型的结果。"
        empty("该类型没有执行记录", detail)
        return

    case_ids = list(dict.fromkeys(row["case_id"] for row in displayed))
    selected = st.multiselect("热力图宿主用例", case_ids, default=case_ids[:18],
                              key=f"mutation_cases_{origin}_{mutation}")
    lookup = {(row["mutation"], row["case_id"]): row for row in displayed}
    grid = [lookup.get((kind, case), {"mutation": kind, "case_id": case,
                                     "status": "not_applicable" if kind == MUTATIONS[-1] else "not_verified", "c5": None})
            for kind in ([mutation] if mutation else MUTATIONS) for case in selected]
    if grid:
        st.altair_chart(charts.heatmap(grid), width="stretch", on_select=_select_mutation_cell, key="mutation_heatmap")
        st.caption("点击热力图查看对应证据。空白组合仅用于导航，统计来自原始记录。")
    else:
        empty("请选择宿主用例", "可继续使用下方选择器查阅原始记录。")

    lookup.update({(row["mutation"], row["case_id"]): row for row in grid})
    misses = [key for key, row in lookup.items() if row["status"] == "missed"]
    if misses:
        st.button("定位首条漏检", key="mutation_first_miss",
                  on_click=st.session_state.update, args=({"mutation_case": misses[0]},))
    if st.session_state.get("mutation_case") not in lookup:
        st.session_state.pop("mutation_case", None)
    key = st.selectbox("查看变异证据", list(lookup), key="mutation_case",
                       format_func=lambda pair: f"{MUTATION_DETAILS[pair[0]][0]} / {pair[1]} · "
                                                f"{STATUS_LABELS[lookup[pair]['status']]}")
    _show_mutation_case(lookup[key], group["source"])


def render_injection_compact(height=360):
    """Compact M1-M8 fault-injection matrix for the boundary/exception page.

    The full ``mutation_matrix`` page carries population tables, per-type
    tables and a drill-down selector.  The boundary page only needs the matrix
    itself plus one short verdict, so this keeps it small on screen while the
    raw evidence stays reachable in a folded drawer.
    """
    groups = {origin: mutation_group(origin) for origin in MUTATION_SOURCES}
    origin = next((name for name in MUTATION_SOURCES if groups[name]["rows"]),
                  next(iter(MUTATION_SOURCES)))
    group = groups[origin]
    # Keep the y axis in M1..M8 order instead of first-seen order.
    order = {name: index for index, name in enumerate(MUTATIONS)}
    rows = sorted(group["rows"],
                  key=lambda row: (order.get(row.get("mutation"), 99), str(row.get("case_id"))))
    if not rows:
        empty("异常注入器还没有记录", "先在测试实验室跑一轮 M1–M8 缺陷注入，这里才会出现热力图。")
        return
    counts = mutation_summary(rows, group["missing_records"])
    kpis([("注入记录", counts["total"], "M1–M8 × 宿主用例 · 2026-10-20 历史批次"),
          ("已检出", counts["detected"], "断言捕获了注入缺陷"),
          ("漏检", counts["missed"], "未捕获，需要补断言"),
          ("无法判定", counts["indeterminate"], "证据不足，不折算为通过")])
    st.altair_chart(charts.heatmap(rows).properties(height=height), width="stretch")
    st.caption("一行一种注入类型，一列一个宿主用例；颜色即判定结果。")
    missed = counts["missed"]
    if missed:
        verdict = ("异常注入器在 " + str(counts["total"]) + " 个「注入类型 × 宿主用例」组合里检出 "
                   + str(counts["detected"]) + " 个、漏检 " + str(missed) + " 个。"
                   "漏检说明断言没盖住这类缺陷，应按漏检格补断言后复测。")
    else:
        verdict = ("异常注入器在 " + str(counts["total"]) + " 个「注入类型 × 宿主用例」组合里检出 "
                   + str(counts["detected"]) + " 个，没有漏检；"
                   "这只证明已有断言能抓住这八类缺陷，不等于 Agent 在所有异常下都不会出错。")
    st.markdown('<div class="ta-guide-note"><b>异常注入结论</b><br>' + verdict + '</div>',
                unsafe_allow_html=True)
    with st.expander("查看原始变异证据", expanded=False):
        mutation = st.selectbox("变异类型", [None, *MUTATIONS], key="lab_mutation_type",
                                format_func=lambda key: MUTATION_DETAILS[key][0] if key else "全部类型")
        displayed = [row for row in rows if mutation is None or row["mutation"] == mutation][:60]
        lookup = {(row["mutation"], row["case_id"]): row for row in displayed}
        if not lookup:
            empty("该类型没有执行记录", "换一个变异类型，或先在测试实验室跑一轮注入。")
            return
        key = st.selectbox("查看变异证据", list(lookup), key="lab_mutation_case",
                           format_func=lambda pair: f"{MUTATION_DETAILS[pair[0]][0]} / {pair[1]} · "
                                                    f"{STATUS_LABELS[lookup[pair]['status']]}")
        _show_mutation_case(lookup[key], group["source"])


def hallucination_topic():
    selected = mutation_group("选定矩阵")
    probe = mutation_group("额外探测")
    selected_m7 = [row for row in selected["rows"] if row["mutation"] == "hallucinated_train"]
    if selected["missing_records"] == 0:
        selected = {"rows": selected_m7, "missing_records": 0}
        label = "选定假车次矩阵"
    else:
        label = "选定假车次矩阵（分母待核对）"
        selected = {"rows": selected_m7, "missing_records": None}
    table([mutation_metrics_row(label, selected), mutation_metrics_row("额外探测", probe)],
          "hallucination_counts", search=False)
    table([{"用例": row["case_id"], "G9999 进入回复": row["original"].get("G9999_进入回复"),
            "判定": STATUS_LABELS[row["status"]], "C5 命中": row["c5"],
            "失败规则": ", ".join(map(str, row["failed_rules"])), "回复片段": row["original"].get("reply_片段")}
           for row in probe["rows"]], "hallucination_probe")
    st.caption("任一断言检出与命中 C5 分开统计。B 压缩记录未保存数据库权威列表。")
    panel_title("A 有独立标注的有限规则样本","与上面的 B 正式用例、变异矩阵分别统计；不是通用语义准确率。")
    report=read_json(AUDIT_SOURCE/"report.json")
    samples=report["labelled_samples"]
    counts={"TP":0,"FP":0,"FN":0,"TN":0,"无法判定":0}
    for r in samples:
        expected=r.get("expected_semantic_outcome")
        actual=r["judgement"]["hallucination"].get("hallucination_detected")
        key="无法判定" if expected is None or actual is None else "TP" if expected and actual else "FN" if expected else "FP" if actual else "TN"
        counts[key]+=1
    kpis([(k,v,f"{len(samples) - counts['无法判定']} 个可判样本，{counts['无法判定']} 个无法判定")
          for k,v in counts.items()])
    table([{ "样本":r["case_id"],"回复":r["reply"],"标注":r.get("expected_semantic_outcome"),"检测":r["judgement"]["hallucination"].get("hallucination_detected")} for r in samples],"labelled_detector_samples")
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
    st.caption(f"B 独立后端验证 · Mock / TEST_ONLY · {len(data['records'])} 条检查。多个断言可能共享同一场景，按检查计数。")
    import json
    table(data["records"],"b_concurrency")
    st.info("B 本轮 JSON 未保存锁座 ID 和全部请求明细；这些字段显示为未提供。下面可独立查看 A 保存的正常/影子库对照，不能冒充 B 原始证据。")
    from web.evidence import read_jsonl
    audits=[]
    for pattern in ("concurrency-normal-same_lock_two","concurrency-mutant-two"):
        records,_=read_jsonl(AUDIT_SOURCE/"cases"/pattern/"audit_runs.jsonl")
        audits.extend(records)
    table([{ "来源":"A 历史离线自测","组别":r.get("mode"),"并发请求":r.get("concurrency",{}).get("workers"),"落库订单":r.get("judgement",{}).get("actual_behavior",{}).get("orders"),"影子库":r.get("database_isolation",{}).get("shadow_only_mutation"),"资源清理":r.get("resources_cleaned")} for r in audits],"a_concurrency")
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
    table([{ "用例":r["id"],"维度":r["dimension"],"状态":r["status"],"工具序列":" → ".join(t for turn in r.get("executed",[]) for t in turn.get("tool_sequence",[]))} for r in candidates],"specialist_"+choice)
    st.caption("这是相关原始用例入口，不是上述六类专项全部完成的证明。")



def session_assertion_counts(records):
    """Count saved assertion outcomes across this session; unknown stays unknown."""
    counts={'通过':0,'失败':0,'待判定':0}
    for record in records:
        judgement=record.get('judgement') if isinstance(record.get('judgement'),dict) else {}
        assertions=judgement.get('assertions') if isinstance(judgement.get('assertions'),list) else []
        for assertion in assertions:
            if not isinstance(assertion,dict):
                counts['待判定']+=1
                continue
            value=assertion.get('passed')
            key='通过' if value is True else '失败' if value is False else '待判定'
            counts[key]+=1
    return counts


def show_session_audit_summary(records, formal=None):
    import altair as alt
    import pandas as pd
    from web.charts import finish
    from web.evidence import DIMENSIONS
    counts=session_assertion_counts(records)
    st.subheader('当前会话的实际审计结果')
    st.caption(f'汇总当前会话 {len(records)} 条审计记录中保存的规则断言；同一规则多次执行会分别计数，不是 B 正式用例通过率。')
    if sum(counts.values()):
        frame=pd.DataFrame([{'结果':k,'数量':v} for k,v in counts.items()])
        chart=alt.Chart(frame).mark_bar(cornerRadiusEnd=4,size=20).encode(
            y=alt.Y('结果:N',sort=['通过','失败','待判定'],title=None),
            x=alt.X('数量:Q',title='实际断言数量',axis=alt.Axis(tickMinStep=1)),
            color=alt.Color('结果:N',scale=alt.Scale(domain=['通过','失败','待判定'],range=['#54bca4','#f17b86','#d9b76c']),legend=None),
            tooltip=['结果:N','数量:Q'])
        st.altair_chart(finish(chart,160),width='stretch')
    else:
        st.info('当前会话未保存可统计的审计断言，暂无结果图。')
    st.subheader('七维度正式测试状态')
    if not formal or not formal['rows']:
        st.caption('当前会话尚无可关联的 B 用例结果，不能计算维度通过率。')
        table([{'维度':name,'状态':'未提供可关联的正式用例结果'} for name in DIMENSIONS], 'quality_session_untested',search=False)
    else:
        from web.formal_results import formal_dimensions
        rows=formal_dimensions(formal['rows'])
        st.caption('来源为导入文件声称的 B 判定；Trace 已按会话、Provider、模型关联，执行者身份和 Git SHA 尚未独立验证。')
        st.write('批次信息：',formal['batch'])
        measured=[r for r in rows if r['rate'] is not None]
        if measured:
            frame=pd.DataFrame(measured)
            chart=alt.Chart(frame).mark_bar(cornerRadiusEnd=4,size=19,color='#54bca4').encode(
                y=alt.Y('dimension:N',sort=None,title=None),
                x=alt.X('rate:Q',scale=alt.Scale(domain=[0,1]),axis=alt.Axis(format='%'),title='通过 / 已判定'),
                tooltip=['dimension:N','passed:Q','failed:Q','indeterminate:Q'])
            st.altair_chart(finish(chart,245),width='stretch')
        table([{'维度':r['dimension'],'通过':r['passed'],'失败':r['failed'],'待判定':r['indeterminate'],'跳过':r['skipped'],'不适用':r['not_applicable'],'通过率':f"{r['rate']:.1%}" if r['rate'] is not None else '未提供可判定结果'} for r in rows], 'quality_formal_dimensions',search=False)
        st.caption('仅统计已关联当前会话的记录；未执行或缺少 Trace 的用例不会计入通过率。')


def current_session_quality(session):
    from web.evidence import read_audit_records
    records, errors=read_audit_records(session.trace_dir / 'audit_runs.jsonl')
    st.caption('当前会话的有限自动审计，不是七维度正式通过率；没有证据的项目保持待判定。')
    if errors.get('invalid') or errors.get('truncated'):
        st.warning('审计记录存在无法读取或截断情况，请查看原始 Trace。')
    from web.formal_results import parse_formal_results
    uploaded=st.file_uploader('导入 B 的正式测试结果（JSON）',type=['json'],key='quality_formal_upload_'+session.sid,
                              help='仅在当前浏览器会话中使用；不修改 B 原始文件。')
    formal=None
    if uploaded is not None:
        try:
            formal=parse_formal_results(uploaded.getvalue(),records,session.sid)
            if formal['excluded']:
                st.warning(f"{len(formal['excluded'])} 条结果未关联到当前会话，未计入统计。")
                with st.expander('未关联的结果'): st.json(formal['excluded'])
            st.caption(f"导入 {formal['total']} 条，其中关联当前会话 {len(formal['rows'])} 条。")
        except ValueError as exc:
            st.error('导入失败：'+str(exc))
    show_session_audit_summary(records,formal)
    if not records:
        st.info('当前会话暂无审计记录。先在出行助手或测试实验室执行一次。')
        return
    i=st.selectbox('选择当前会话记录',range(len(records)),index=len(records)-1,
                   format_func=lambda n: str(records[n].get('trace_id','未知'))[:16]+' · '+str(records[n].get('timestamp','时间未知')),
                   key='quality_session_record')
    record=records[i]; judgement=record.get('judgement') or {}
    dimensions=judgement.get('dimensions') or {}
    st.write('模型：',record.get('provider','未知'),' / ',record.get('model') or '未知')
    st.write('有限规则质量判定：',judgement.get('quality_verdict','待判定'))
    if record.get('error'): st.warning('执行异常：'+str(record['error'].get('category','未知')))
    if judgement.get('quality_verdict')=='fail' and not judgement.get('failure_reasons'):
        st.warning('记录未保存失败原因，请人工核查；不能推断为通过。')
    labels={'agent_anomaly_recognized':'Agent 识别异常','agent_recovered':'Agent 恢复','business_correct':'业务正确','platform_defect_detected':'平台检出','injection_applied':'变异注入'}
    table([{'项目':label,'结果':'是' if dimensions.get(key) is True else '否' if dimensions.get(key) is False else '待判定'} for key,label in labels.items()], 'quality_current_dimensions')
    assertions=judgement.get('assertions') or []
    if assertions:
        table([{'规则':a.get('assertion','未知'),'结果':a.get('result','待判定'),'依据':a.get('failure_reason') or '见 Trace'} for a in assertions if isinstance(a,dict)],'quality_current_assertions')
    else: st.info('本次未保存可用断言，无法计算通过率。')
    with st.expander('查看当前记录完整证据'):
        show_record(record,key='quality_current_trace')


def quality_page(sessions=()):
    header("质量分析","分别检查既有断言、注入检出、事实一致性与并发边界。","会话审计 / 历史证据")
    source=st.radio('数据来源',['B 历史测试','当前会话'],index=0,horizontal=True,key='quality_source')
    if source=='当前会话':
        if not sessions:
            st.info('暂无当前浏览器会话。请先运行出行助手或测试实验室。')
            return
        i=st.selectbox('选择会话',range(len(sessions)),index=len(sessions)-1,
                       format_func=lambda n: ('出行助手' if sessions[n].mode=='user' else '测试实验室')+' · '+sessions[n].sid,
                       key='quality_session')
        current_session_quality(sessions[i])
        return
    section=st.radio("质量专题",["七维度","变异热力图","幻觉检测","并发幂等","AI 专项"],horizontal=True,key="quality_section")
    {"七维度":quality_dimensions,"变异热力图":mutation_matrix,"幻觉检测":hallucination_topic,"并发幂等":concurrency_topic,"AI 专项":specialist_topics}[section]()
