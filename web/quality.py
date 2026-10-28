"""Mutation and specialist analysis preserve their original denominators."""
import streamlit as st
from web.design import header,panel_title,kpis,empty,table
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
    table([{ "用例":r["case_id"],"G9999 进入回复":r["G9999_进入回复"],"任意规则检出":r["killed"],"C5 命中":"C5" in r["failed_rules"],"失败规则":", ".join(r["failed_rules"]),"回复片段":r["reply_片段"]} for r in probe["details"]],"hallucination_probe")
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
    st.caption("B 独立后端验证 · 2026-10-20 · Mock · 10 条检查，包含多个断言共享一个场景；不是 10 次模型对话。")
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
    section=st.radio("质量专题",["七维度","变异热力图","幻觉检测","并发幂等","AI 专项"],horizontal=True)
    {"七维度":quality_dimensions,"变异热力图":mutation_matrix,"幻觉检测":hallucination_topic,"并发幂等":concurrency_topic,"AI 专项":specialist_topics}[section]()
