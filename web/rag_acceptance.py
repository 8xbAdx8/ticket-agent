"""Read-only V3.5.2 evidence views. No model or Embedding invocation here."""
import json
from pathlib import Path
import streamlit as st
from target.v352_validation import AUTH,ROOT,QUESTION


def load_evidence(runtime,public):
    for path in (runtime,public):
        if path.is_file():
            try:return json.loads(path.read_text(encoding='utf-8'))
            except (ValueError,OSError):return None
    return None


def provider_view(report,provider):
    if not report or report.get('evidence_mode')!='real_api':
        return {'label':'未验证','record':None,'reason':'无本轮真实API证据；离线SDK桩不能作为Live成功'}
    record=next((r for r in report.get('records',[]) if r.get('provider')==provider),None)
    if record is None:return {'label':'未验证','record':None,'reason':'该Provider没有本轮记录'}
    verified=bool(record.get('real_function_calling_verified') and record.get('evidence_mode')=='real_api'
        and report.get('same_tool_evidence_verified') and report.get('same_system_prompt_verified') and report.get('source_index_unchanged'))
    return {'label':'真实工具闭环已验证' if verified else '已执行但未通过/未完成','record':record,
            'reason':'协议、证据和回答质量分别判断'}


def render_acceptance():
    st.subheader('V3.5.2 双模型真实RAG验收')
    st.caption('同一问题：'+QUESTION+' · Hybrid / Top-K 3 / cosine 0.35 / v351规则。刷新与回放不请求API。')
    report=load_evidence(AUTH/'paired-report.json',ROOT/'docs/evidence/v352/live/paired-report.json')
    cols=st.columns(2)
    for col,provider,name in zip(cols,('bailian','deepseek'),('Qwen3.8-Flash','DeepSeek Flash')):
        view=provider_view(report,provider)
        with col:
            st.markdown('**'+name+'：'+view['label']+'**');st.caption(view['reason'])
            row=view['record']
            if row:
                st.write(row.get('original_model_reply') or '没有最终原回复')
                st.json({'protocol_closure':row.get('protocol_closure'),'agent_completed':row.get('agent_completed'),
                         'expected_evidence_sha256':row.get('expected_evidence_sha256'),
                         'tokens':row.get('tokens'),'latency_ms':row.get('generation_latency_ms'),
                         'faithfulness':row.get('faithfulness'),'error':row.get('error')})
                with st.expander(name+' 实际ToolMessage与最终展示结果'):
                    st.json({'received_evidence':row.get('delivered_evidence'),'final_display_result':row.get('final_display_result')})
    frozen=load_evidence(AUTH/'prepared/frozen.json',ROOT/'docs/evidence/v352/prepared/frozen.json')
    if frozen:
        with st.expander('本轮冻结知识库、索引哈希与实际政策证据（缓存读取，不是新Live）'):
            st.json({'index_version':frozen.get('retrieval',{}).get('index_version'),
                     'source_tree_sha256':frozen.get('source_tree_sha256'),
                     'tool_result_sha256':frozen.get('tool_result_sha256'),'tool_result':frozen.get('tool_result')})
    st.caption('无答案真实复验：本轮尚无记录。历史RQ26与离线拒答测试另列，不据此填写本轮Live拒答率。')
    st.subheader('新增48题：三模式质量与适用样本')
    evaluation=load_evidence(AUTH/'retrieval-report.json',ROOT/'docs/evidence/v352/retrieval/report.json')
    if evaluation:
        split=st.selectbox('V3.5.2 评估集合',['holdout','development','all48'],key='v352_quality_split')
        rows=[]
        for mode,result in evaluation['metrics'][split].items():
            rows.append({'模式':mode,'集合':split,'样本':result['cases'],'Recall@1':result['recall_at_1'],
                'Recall@3':result['recall_at_3'],'MRR':result['mrr'],'无答案误召回':result['no_answer_false_recall_rate'],
                '正样本适用':result['answerable_scored'],'无答案已测':result['no_answer_scored'],
                '未运行':result['not_run_cases'],'无法判定':result['indeterminate_cases'],
                'Recall/MRR不适用':result['not_applicable_recall_mrr_cases']})
        st.dataframe(rows,hide_index=True)
        st.caption('数据集是V3.5.1固定新增48题，开发/保留各24；缺真实向量时Vector/Hybrid为未运行，空值不是0分。来源：'+evaluation.get('execution_mode','未知'))
    else:st.info('新增48题尚无本轮评估文件；Vector/Hybrid未验证。')
    old=load_evidence(ROOT/'docs/evidence/v351/quality/summary.json',ROOT/'docs/evidence/v351/quality/summary.json')
    if old:
        with st.expander('旧30题：V3.5真实检索与V3.5.1离线重放前后对照'):
            st.json(old['fixed30']);st.caption('旧30题成绩不会填到新增48题。本轮无新生成时答案忠实度仍待复验。')
