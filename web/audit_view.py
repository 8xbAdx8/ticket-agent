"""只展示保存过的审计事实；不调用模型，也不推测模型内部思考。"""
import streamlit as st
from target.diagnostics import read_audits, metrics, digest


LABELS={"injection_applied":"注入成功","platform_defect_detected":"平台检出缺陷",
        "agent_anomaly_recognized":"Agent 识别异常","agent_recovered":"Agent 正确恢复",
        "safe_stop":"安全停止","business_correct":"业务结果正确"}


def show_audit(record):
    st.subheader("V3.2 · 独立诊断与判定")
    if not record:
        st.info("该历史记录未包含此项诊断信息")
        return
    st.caption("Trace ID："+record.get("trace_id","不可用"))
    judgement=record.get("judgement",{})
    dimensions=judgement.get("dimensions",{})
    for name,label in LABELS.items():
        value=dimensions.get(name)
        st.write(f"{label}：{'是' if value is True else '否' if value is False else '待判定 / 不适用'}")
    st.write("业务质量判定：",judgement.get("quality_verdict","indeterminate"))
    if judgement.get("test_verdict"):
        st.write("受控测试预期判定：",judgement["test_verdict"])
    st.caption("故意注入缺陷的用例可满足测试预期，同时业务质量失败。stop 不代表业务成功。")
    for reason in judgement.get("failure_reasons",[]):st.warning(reason)
    events=record.get("mutation_events",[])
    if events:
        st.dataframe([{k:e.get(k) for k in ("mutation_id","mutation_name","status","target","reason")} for e in events],hide_index=True)
    with st.expander("变异前后与工具实际执行证据"):
        st.json({"mutation_events":events,"model_requests":record.get("fault_report",{}).get("model_requests",[]),
                 "executions":record.get("fault_report",{}).get("executions",[]),
                 "authority":record.get("authority",{}),"raw_model_reply":record.get("raw_model_reply"),
                 "hallucination":judgement.get("hallucination"),"assertions":judgement.get("assertions",[])})
    if record.get("requests"):
        with st.expander("并发请求、订单与唯一性断言"):
            st.json({key:record.get(key) for key in ("requests","authority_before","authority","followup_query","database_isolation","resources_cleaned","concurrency","judgement")})
    with st.expander("完整版本化旁证"):
        st.json(record)


def show_audit_replay(directory):
    st.subheader("全部保存的诊断记录（含独立并发测试）")
    records=read_audits(directory)
    if not records:
        show_audit(None)
        return
    chosen=st.selectbox("选择诊断记录（按唯一 Trace ID）",range(len(records)),index=len(records)-1,
        format_func=lambda i:f"{i+1}: {records[i].get('trace_id','损坏记录')} · {records[i].get('provider','unknown')}")
    st.caption("仅回放保存的旁证，不重新运行模型；此列表独立于旧十字段 Trace，避免相同输入的重复记录被错误关联。")
    show_audit(records[chosen])
    with st.expander("当前旁证集合的指标与分母（非 B 正式成绩）"):
        st.json(metrics(records))


def show_linked_audit(public_trace,directory):
    matches=[a for a in read_audits(directory) if a.get("public_trace_sha256")==digest(public_trace)]
    if len(matches)>1:
        chosen=st.selectbox("同内容记录有多个诊断 ID，请明确选择",range(len(matches)),
                           format_func=lambda i:matches[i]["trace_id"])
        show_audit(matches[chosen])
    else:
        show_audit(matches[0] if matches else None)
