"""Auditable event viewer; no guessed intermediate stages or internal reasoning."""
import json
import streamlit as st
from web.design import header, kpis, empty, escape, panel_title,table
from web.evidence import audit_catalog, diff_values, export_rows, read_jsonl
from target.diagnostics import sanitize, digest


def safe_json(value,key):
    value=sanitize(value)
    needle=st.text_input("搜索 JSON 字段或值",key=key+"_search")
    if needle:
        def matches(obj,path="$"):
            if isinstance(obj,dict):
                return [m for k,v in obj.items() for m in matches(v,path+"."+str(k))]
            if isinstance(obj,list):
                return [m for i,v in enumerate(obj) for m in matches(v,path+f"[{i}]")]
            return [{"path":path,"value":obj}] if needle.lower() in (path+" "+str(obj)).lower() else []
        visible=matches(value)
        st.caption(f"匹配 {len(visible)} 个叶节点；原记录保留。")
    else:
        visible=value
    st.json(visible,expanded=1)
    with st.expander("复制 JSON"):
        st.caption("使用代码块右上角的复制按钮。内容与当前脱敏视图一致。")
        st.code(export_rows(visible),language="json")
    st.download_button("下载当前脱敏视图",export_rows(visible),file_name="ticket-agent-evidence.json",mime="application/json",key=key+"_download")


def timeline_items(audit,public=None):
    public=public or audit.get("public_trace",{})
    result=[]
    if public.get("user_msg"):
        result.append({"kind":"用户输入","title":public["user_msg"],"data":{"user_msg":public["user_msg"]}})
    fault=audit.get("fault_report") or {}
    for r in fault.get("model_requests",[]):
        result.append({"kind":"模型/规则输出","title":"调用选择 · step "+str(r.get("model_step","未知")),"data":r})
    for e in fault.get("executions",[]):
        diagnostic=e.get("parameter_validation") or e.get("execution_diagnostic") or {}
        if diagnostic:
            result.append({"kind":"参数校验旁证","title":e.get("tool","工具"),"data":diagnostic})
        result.append({"kind":"实际执行","title":e.get("tool","工具"),"data":e})
    for e in audit.get("mutation_events",[]):
        if e.get("status")=="disabled":
            continue  # Full JSON retains disabled switches without cluttering the timeline.
        result.append({"kind":"变异事件","title":e.get("mutation_name",e.get("mutation_id","变异"))+" · "+str(e.get("status","未知")),"data":e})
    if not fault.get("executions"):
        for step in public.get("steps",[]):
            for call in step.get("calls",[]):
                result.append({"kind":"公共 Trace 工具调用","title":call.get("tool","工具"),"data":call})
    if public.get("reply"):
        result.append({"kind":"最终回复","title":"Agent 公开回答","data":{"reply":public["reply"],"finish_reason":public.get("finish_reason")}})
    if audit.get("judgement"):
        result.append({"kind":"自动判定","title":"独立审计结果","data":audit["judgement"]})
    return result


def verdict_cards(audit):
    dims=(audit.get("judgement") or {}).get("dimensions",{})
    labels=[("injection_applied","变异注入"),("platform_defect_detected","平台检出"),("agent_anomaly_recognized","Agent 识别"),("agent_recovered","Agent 恢复"),("business_correct","业务正确")]
    kpis([(label,"是" if dims.get(key) is True else "否" if dims.get(key) is False else None,"独立判断；未知不当成功") for key,label in labels])
    judgement=audit.get("judgement",{})
    st.caption("业务质量："+str(judgement.get("quality_verdict","indeterminate"))+" · 测试预期："+str(judgement.get("test_verdict","未提供"))+"。故意注入被检出不等于 Agent 已识别或恢复。")


def show_record(audit,public=None,key="trace"):
    public=public or audit.get("public_trace",{})
    st.caption("Trace ID："+audit.get("trace_id","历史记录未提供该字段")+" · "+str(audit.get("timestamp","精确执行时间未提供")))
    if audit.get("evidence_kind")=="offline_sdk_stub":
        st.warning("这是离线 SDK 桩；provider 字段虽为 deepseek_live，也不代表真实 API 请求。")
    if audit.get("display_warning"):
        st.warning(audit["display_warning"])
    tokens=public.get("tokens") or {}
    is_mock=public.get("provider") in ("mock","langchain_mock") or audit.get("provider") in ("mock","langchain_mock","backend_concurrency")
    calls=[c for s in public.get("steps",[]) for c in s.get("calls",[])]
    tool_ms=sum(c["latency_ms"] for c in calls) if calls and all(isinstance(c.get("latency_ms"),(int,float)) for c in calls) else None
    token_text=lambda value:str(value) if type(value) is int else "未知"
    kpis([("工具执行",len(calls) if "steps" in public else None,"缺少历史字段时显示未知"),
          ("总耗时",str(public["total_latency_ms"])+" ms" if public.get("total_latency_ms") is not None else None,"不含虚构阶段时间"),
          ("Token 用量","不适用" if is_mock else token_text(tokens.get("prompt"))+" / "+token_text(tokens.get("completion")),"输入 / 输出；桩用量非真实计费"),
          ("结束原因",public.get("finish_reason"),"stop ≠ 业务成功")])
    st.caption("工具累计耗时："+(str(tool_ms)+" ms" if tool_ms is not None else "未提供")+"；模型分阶段耗时未提供。不用总耗时减工具耗时猜测 API 时间。")
    st.caption("以下按证据类别排列；缺少统一时钟时不推断全局先后或阶段起止，不绘制伪精确瀑布图。展开卡片查看实际字段。")
    if not audit:
        st.info("历史记录未提供模型请求、参数验证与独立审计字段；仅展示公共 Trace 已保存内容。")
    if audit.get("judgement"):
        verdict_cards(audit)
    for i,event in enumerate(timeline_items(audit,public)):
        with st.expander(f"{i+1:02}  {event['kind']} · {event['title'][:65]}"):
            st.json(sanitize(event["data"]),expanded=1)
    events=(audit.get("fault_report") or {}).get("injection_events",[])
    if events:
        panel_title("变异前后对照","只显示保存的 original / mutated，不反推缺失内容。")
        index=st.selectbox("选择变异事件",range(len(events)),format_func=lambda i:str(i+1)+" · "+events[i].get("mutation","unknown"),key=key+"_mutation")
        event=events[index]
        left,right=st.columns(2)
        with left:
            st.caption("原始参数 / 结果")
            st.json(sanitize(event.get("original")),expanded=1)
        with right:
            st.caption("变异后参数 / 结果")
            st.json(sanitize(event.get("mutated")),expanded=1)
        changes=diff_values(sanitize(event.get("original")),sanitize(event.get("mutated")))
        if changes:
            table(changes,key+"_diff")
        else:
            st.caption("没有可比较的字段差异；查看事件状态与原因。")
    with st.expander("完整 JSON 与脱敏导出"):
        safe_json({"public_trace":public,"audit":audit or "历史记录未提供该字段"},key)


def trace_page(runtime_dirs):
    header("Trace 分析","从原始调用到独立判定。每条事件都可以展开核对。","只读回放")
    entries=audit_catalog(runtime_dirs)
    scope=st.radio("证据范围",["当前工作空间","历史离线自测","公共历史 Trace"],horizontal=True,key="trace_scope")
    if scope=="公共历史 Trace":
        from pathlib import Path
        import config
        paths=[config.TRACE_DIR/"traces.jsonl",Path(config.BASE_DIR)/"docs/evidence/mock_traces.jsonl"]
        paths=[p for p in paths if p.is_file()]
        if not paths:
            empty("暂无公共 Trace","发送消息后会保存到各工作空间；也可以选择历史离线自测。")
            return
        path=st.selectbox("公共 Trace 来源",paths,format_func=lambda p:p.name+" · "+str(p.parent.name))
        records,errors=read_jsonl(path)
        if errors["invalid"] or errors["truncated"]:
            st.warning("存在损坏行或达到读取上限；原文件未修改。")
        if records:
            i=st.selectbox("选择回放记录",range(len(records)),format_func=lambda i:str(i+1)+" · "+str(records[i].get("user_msg","旧记录"))[:45])
            linked=[e["record"] for e in entries if e["record"].get("public_trace_sha256")==digest(records[i])]
            if len(linked)>1:
                chosen=st.selectbox("同内容记录的独立审计 ID",range(len(linked)),format_func=lambda j:linked[j]["trace_id"])
                audit=linked[chosen]
            else:
                audit=linked[0] if linked else {}
            show_record(audit,records[i],"public_replay")
        return
    entries=[e for e in entries if e["kind"]==scope]
    entries.sort(key=lambda e:e["record"].get("timestamp", ""))
    if not entries:
        empty("暂无该范围的审计记录","先在测试实验室执行离线案例，或切换到历史离线自测。不会自动重跑。")
        return
    i=st.selectbox("选择诊断记录（按唯一 Trace ID）",range(len(entries)),index=len(entries)-1,format_func=lambda i:str(i+1)+" · "+entries[i]["record"].get("test_case_label",entries[i]["record"].get("scenario",entries[i]["record"].get("public_trace",{}).get("user_msg","记录")))[:42]+" · "+entries[i]["record"].get("trace_id","missing")[:8])
    st.caption("来源："+str(entries[i]["source"].relative_to(__import__('config').BASE_DIR))+" · A 自测，不替代 B 正式测试。")
    show_record(entries[i]["record"],key="audit_replay")
    source_dir=entries[i]["source"].parent
    trace_id=entries[i]["record"].get("trace_id")
    for filename,title,id_field in (("provider_runs.jsonl","当前 Live 模型元数据（独立旁证）","trace_id"),
                                    ("langsmith_exports.jsonl","LangSmith 独立上报回执","local_trace_id")):
        path=source_dir/filename
        if path.is_file():
            records,_=read_jsonl(path)
            matched=[r for r in records if r.get(id_field)==trace_id]
            if matched:
                with st.expander(title):
                    safe_json(matched,"live_sidecar_"+filename)
