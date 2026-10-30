"""Independent B batches and A audit results never share an invented total."""
import streamlit as st
from web.design import header,kpis,empty,panel_title,table
from web import charts
from web.evidence import batch,summary,dimension_rows,latency_rows,mutation_totals,verified_manifest,export_rows,read_json,B_SOURCE,audit_batch,b_aux_batch


def choose_batch(key,show_meta=True):
    engine=st.selectbox("当前数据源",["legacy","langchain"],format_func=lambda e:"B 独立测试 · "+("Legacy Mock" if e=="legacy" else "LangChain Mock"),key=key)
    data=batch(engine)
    if show_meta:
        st.caption(f"B 独立测试 · Mock · 执行日期 {data['date']}（精确时间未知） · 代码 {data['commit'][:12]} · {data['source']}")
    return data


def current_lab_page(runtime_dirs):
    from collections import Counter
    from web.evidence import recent_lab_records, lab_record_rows
    st.subheader("当前测试实验室记录")
    st.caption("本浏览器中测试实验室产生的审计记录；打开本页、切换筛选或点击刷新会重新读取，不调用模型。")
    st.button("刷新实验记录", key="dashboard_live_refresh")
    records, read_status=recent_lab_records(runtime_dirs)
    rows=lab_record_rows(records)
    if not rows:
        st.info("暂无本浏览器实验记录。请到测试实验室执行一次，再返回本页。")
        if read_status['invalid']: st.warning("部分记录无法读取或校验。")
        return
    sources=sorted({(r['provider'],r['model']) for r in rows})
    provider,model=st.selectbox("实验模型与模式", sources,format_func=lambda v: v[0]+" · "+v[1],key="dashboard_live_source")
    selected=[r for r in rows if (r['provider'],r['model'])==(provider,model)]
    counts=Counter(r['status'] for r in selected)
    kpis([("记录数",len(selected),"每条是一次审计记录"),
          ("有限规则未发现问题",counts['有限规则未发现问题'],"不代表正式测试通过"),
          ("审计发现问题",counts['审计发现问题'],"仅按已记录规则"),
          ("待判定 / 执行异常",counts['待判定']+counts['执行异常'],"不计为通过")])
    st.info("这是 A 的实验审计，不是 B 的正式测试成绩。质量规则通过不代表业务一定正确；变异实验与正常实验不可直接混算通过率。")
    if read_status['truncated']: st.warning("记录较多，仅展示近期最多 300 条；不是全部历史。")
    if read_status['invalid']: st.warning(f"有 {read_status['invalid']} 条记录无法读取或校验，未计入统计。")
    table([{'时间（UTC）':r['time'],'Trace ID':r['trace_id'],'审计状态':r['status'],
            '测试预期':r['test_verdict'],'耗时 ms':r['latency_ms'] if r['latency_ms'] is not None else '未知',
            'Token':str(r['tokens']) if r['tokens'] is not None else '未知','错误':r['error'] or '无已记录错误'} for r in selected],"dashboard_live_rows")
    st.caption("查看原始工具调用、判断原因和证据：进入 Trace 分析并选择对应 Trace ID。")


def dashboard_page(runtime_dirs=(), lab_runtime_dirs=(), source=None):
    header("测试总览","按批次审阅质量，保留失败、未验证与证据边界。","质量工作台")
    owner_col,kind_col,batch_col=st.columns([1,1.15,1.25])
    if source is None:
        with owner_col:
            source=st.selectbox("证据批次",["当前测试实验室（实时）","B 独立测试","A 历史离线自测","A 当前隔离实验"],key="dashboard_owner")
    if source=="当前测试实验室（实时）":
        current_lab_page(lab_runtime_dirs)
        return
    if source=="B 独立测试":
        with kind_col:
            kind=st.selectbox("B 结果类型",["正式功能用例","新增代码专项（47 检查）","M8 并发幂等（10 检查）","选定变异矩阵（69 组合）"],key="dashboard_kind")
        if kind=="正式功能用例":
            with batch_col:
                data=choose_batch("dashboard_batch",show_meta=False)
        else:
            data=b_aux_batch(kind)
            if data["original_generated"]:
                st.caption("原文件 generated="+data["original_generated"]+"；不将此旧标记冒充精确执行时间。专项使用离线桩，0 次真实 API 请求。")
        st.caption(data["title"]+" · "+data["mode"]+" · 执行日期 "+data["date"]+"（精确时间未知） · 代码 "+data["commit"][:12]+" · "+data["source"])
    else:
        data=audit_batch(runtime_dirs,historical=source=="A 历史离线自测")
        st.caption(data["title"]+" · "+data["mode"]+" · "+data["date"]+" · "+data["source"])
        st.info("此处按有限审计/受控预期统计，不是 B 正式功能成绩。注入被检出可满足测试预期，同时业务质量失败；当前 Live 不混入本地批次。")
    counts=summary(data["rows"])
    good,bad=data.get("outcome_labels",("通过","失败"))
    kpis([("已判定记录" if data["owner"]=="A" else "实际执行",counts["executed"],f"本批次 {counts['defined']}；{data['grain']}"),
          (good,counts["passed"],"当前批次结果"),(bad,counts["failed"],"当前保存结果"),
          ("选定检出率" if good=="已检出" else "通过率",f"{counts['rate']:.1%}" if counts["rate"] is not None else None,f"{counts['passed']} / {counts['executed']}；不含不适用")])
    a,b=st.columns([1.2,1],gap="large")
    with a,st.container(border=True):
        panel_title("七维度通过情况","这是已有断言的通过率，不是功能覆盖率或真实模型正确率。")
        if data.get("seven_dimensions"):
            st.altair_chart(charts.dimensions(dimension_rows(data["rows"])),width="stretch")
        else:
            empty("本批次未映射七维度","专项检查/审计记录与正式功能用例的粒度不同，不生成虚构维度得分。")
    with b,st.container(border=True):
        panel_title("执行状态分布",f"不适用 {counts['not_applicable']} · 跳过 {counts['skipped']} · 未验证 {counts['not_verified']} · 无法判定 {counts['indeterminate']}")
        st.altair_chart(charts.statuses(counts,(good,bad)),width="stretch")
    c,d=st.columns([1.2,1],gap="large")
    with c,st.container(border=True):
        panel_title("单轮执行耗时","Mock 工具与规则耗时；不能当作 DeepSeek API 性能。")
        timings=latency_rows(data["rows"])
        if timings:
            st.altair_chart(charts.latency(timings),width="stretch")
        else:
            empty("暂无同口径耗时序列","各审计记录的工具/总耗时可在 Trace 分析中查看。")
    with d,st.container(border=True):
        panel_title("B 选定七类变异矩阵 · 独立参考","来源：B mutation.json；69 / 69 个指定组合被任意规则检出。与当前选中批次不合并，M8 单列。")
        st.altair_chart(charts.mutation_distribution(mutation_totals()),width="stretch")
    st.warning("已知边界：T04 假车次未检出；R01 政策场景不适用；F15、M12 被其他规则检出，不能算 C5 命中。当前 V3.3 真实模型专项未执行。")
    with st.expander("失败、不适用与未验证用例"):
        rows=[{"用例":r["id"],"维度":r["dimension"],"状态":r["status"],"说明":r.get("note","")} for r in data["rows"] if r["status"]!="passed"]
        table(rows,"dashboard_exceptions") if rows else st.caption("本批次没有该类记录；不代表未测试功能已通过。")
    with st.expander("来源校验与当前批次下载"):
        meta,checks=verified_manifest()
        st.json({"metadata":meta,"sha256_match":checks})
        st.download_button("下载当前批次脱敏结果",export_rows(data),file_name=data["id"]+".json",mime="application/json")
    empty("历史趋势：暂无足够可比批次","当前接入 B 本轮两个独立引擎批次；未把 A 自测或旧版文字报告拼成趋势线。")


def quality_dimensions():
    data=choose_batch("quality_batch")
    from web.evidence import DIMENSIONS, cases
    from target.diagnostics import sanitize
    dimension=st.selectbox("证据维度", ["全部", *DIMENSIONS], key="quality_dimension")
    rows=dimension_rows(data["rows"])
    if dimension != "全部":
        rows=[r for r in rows if r["dimension"]==dimension]
    st.altair_chart(charts.dimensions(rows),width="stretch")
    table([{ "维度":r["dimension"],"定义用例":r["defined"],"执行":r["executed"],"通过":r["passed"],"失败":r["failed"],"跳过":r["skipped"],"不适用":r["not_applicable"],"未验证":r["not_verified"],"无法判定":r["indeterminate"]} for r in rows],"quality_dimensions")
    st.caption("来源为 B 原始用例及执行记录；没有以代码覆盖率代替测试维度。RAG 15 条是现有政策断言，不代表已完成 RAGAS/DeepEval 忠实度评测。")
    if dimension == "全部":
        st.caption("选择一个证据维度，可查看该引擎对应的用例、原始断言和实际执行记录。")
        return
    selected=[r for r in data["rows"] if r["dimension"]==dimension]
    table([{"用例":r["id"],"维度":r["dimension"],"状态":r["status"],
            "断言数量":len(r.get("checks",[])),"执行轮数":len(r.get("executed",[])),
            "说明":r.get("note") or "未记录"} for r in selected], "quality_case_records")
    ids=[r["id"] for r in selected]
    if not ids:
        st.info("此维度没有可读取的用例记录。")
        return
    if st.session_state.get("quality_case") not in ids:
        st.session_state.pop("quality_case",None)
    case_id=st.selectbox("查看用例原始证据",ids,key="quality_case")
    record=next(r for r in selected if r["id"]==case_id)
    definition=next((r for r in cases() if r["id"]==case_id),None)
    st.caption(f"{dimension} · {data['engine']} · {case_id} · {data['source']}")
    with st.expander("用例定义与期望",expanded=True):
        st.json(sanitize(definition) if definition is not None else {"状态":"未记录"})
    with st.expander("原始断言与实际执行记录",expanded=True):
        st.json(sanitize(record))
        if not record.get("executed"):
            st.caption("无工具 Trace；入口异常用例可由原始断言验证。不适用或未验证记录不代表执行成功。")
        for index,trace in enumerate(record.get("executed",[]),1):
            st.caption(f"执行轮次 {index} · Trace ID：{trace.get('trace_id') or '未记录'}")
