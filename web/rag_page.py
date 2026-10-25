"""Working RAG administration/retrieval and source-backed acceptance replay. No auto API calls."""
import json
import os
from pathlib import Path
import uuid
import streamlit as st
from web.design import header,empty
from target.embeddings import AUTH,EmbeddingBudget
from target.rag_store import ROOT,documents


def saved(name):
    for p in (AUTH/name,ROOT/'docs/evidence/v35/live'/name):
        if p.is_file():return json.loads(p.read_text(encoding='utf-8'))
    return None


def rag_page():
    header('RAG 知识库','真实向量、政策来源和有限验收。票价/余票仍由query_tickets查询。','V3.5 · 模拟政策')
    model=st.selectbox('RAG 生成模型',['Qwen3.8-Flash Live','DeepSeek Live'],key='rag_generation_model')
    st.caption('模型ID：'+('qwen3.8-flash' if model.startswith('Qwen') else 'deepseek-flash')+' · Embedding：text-embedding-v4')
    try:
        from target.rag_service import configured_index
        index=configured_index();state=index.status()
    except Exception:
        index=None;state={'state':'unavailable','category':'embedding_endpoint_or_dependency_not_configured'}
    cols=st.columns(4)
    cols[0].metric('原始政策文档',len({c['doc_id'] for c in documents(ROOT/'data/policies.md')}))
    cols[1].metric('有效索引切片',state.get('chunk_count','待校验'))
    cols[2].metric('Embedding 已预留请求',EmbeddingBudget(AUTH/'embedding.db').snapshot()['used'])
    cols[3].metric('生成已预留请求',_generation_used())
    st.caption('索引状态：'+state['state']+' · 版本：'+str(state.get('index_version','未知'))+' · 类别：'+state.get('category','正常'))
    st.caption('V3.5固定上限：Embedding 8次、Qwen生成4次；DeepSeek本轮无新增额度。缓存复用不生成向量请求。')
    with st.expander('索引元数据与API来源回执'):
        st.json(state)
    mode=st.selectbox('政策检索模式',['keyword','vector','hybrid'],key='rag_mode')
    k=st.number_input('Top-K',min_value=1,max_value=10,value=3,step=1,key='rag_k')
    threshold=st.slider('向量cosine最低分',min_value=0.0,max_value=1.0,value=0.35,step=0.05,key='rag_threshold')
    question=st.text_input('政策问题',value='锁座后多久必须完成支付？',key='rag_question')
    consent=st.checkbox('允许本次查询或建索引调用真实Embedding（会计费，受8次独立账本限制）',key='rag_network_consent')
    offline=os.getenv('TICKET_WEB_OFFLINE_ONLY')=='1'
    if st.button('检索政策证据',key='rag_retrieve'):
        try:
            from target.rag_service import retrieve,scope
            from web.runtime import scoped
            trace_dir=st.session_state.setdefault('rag_ui_trace_dir',str(ROOT/'artifacts/runtime/v35-rag-ui'/uuid.uuid4().hex/'traces'))
            with scoped({'TRACE_DIR':Path(trace_dir)}),scope(trace_id='rag-ui-'+uuid.uuid4().hex,provider='rag-ui'):
                result=retrieve(question,mode,allow_network=consent and not offline,k=int(k),threshold=threshold)
            st.session_state['rag_retrieval_result']=result
        except Exception as exc:
            st.error('检索未完成：'+getattr(exc,'category',str(exc) if type(exc).__name__=='RagError' else type(exc).__name__)+'；没有回退或重试。')
            st.session_state.pop('rag_retrieval_result',None)
    if st.button('显式增量构建 / 重建索引',disabled=not consent or offline or index is None,key='rag_build'):
        try:
            st.write(index.build(allow_network=True,rebuild=state['state']!='ready'))
        except Exception as exc:st.error('索引构建失败：'+getattr(exc,'category',type(exc).__name__))
    result=st.session_state.get('rag_retrieval_result')
    if result:
        st.dataframe([{k:h.get(k) for k in ('rank','doc_id','title','source','score','vector_score','keyword_score','fusion_ranks')} for h in result['hits']],hide_index=True)
        st.caption('vector为cosine，keyword为字词重叠分，hybrid为RRF(k=60)，不同模式分值不能横向当概率。')
        with st.expander('完整检索正文和来源'):
            st.json(result)
    st.subheader('真实验收回放与质量指标')
    evaluation=saved('retrieval-evaluation/report.json')
    if evaluation and evaluation.get('metrics'):
        st.dataframe([{'mode':m,**{k:v for k,v in r.items() if k!='rows'}} for m,r in evaluation['metrics'].items()],hide_index=True)
        st.warning('固定30问题：26有答案、4无答案；只衡量检索。无答案误召回按原结果保留，不能当作回答准确率或B正式成绩。')
    generation=saved('generation-result.json');review=saved('generation-assessment-review.json')
    if generation:
        if model.startswith('DeepSeek'):
            st.info('本轮没有DeepSeek同证据真实生成；以下Qwen记录不作为DeepSeek成绩。')
        st.caption('只读回放：真实调用源码与当前后续UI代码可能不同；没有新增模型请求。新对话在出行助手执行，仍受已用完的预算约束。')
        scenario=st.selectbox('已保存的真实生成样本',['function_calling','RQ01','RQ26'],key='rag_replay')
        record=next(r for r in generation['records'] if r['scenario']==scenario)
        st.write(record.get('original_model_reply') or '该项没有最终回复，见错误证据。')
        st.metric('该样本生成/Agent总耗时 ms',record.get('latency_ms',(record.get('live_evidence') or {}).get('total_latency_ms','未知')))
        evidence=record.get('frozen_retrieval_evidence')
        if evidence:
            a,b=st.columns(2);a.metric('查询向量阶段 ms',evidence['embedding_latency_ms'])
            b.metric('检索/组装阶段 ms',max(0,evidence['total_latency_ms']-evidence['embedding_latency_ms']))
            st.json({'index_version':evidence['index_version'],'hits':evidence['hits']})
        if review:
            st.json(review['summary'])
            st.caption('首次机械判定误将拒答中的“这些文档未涉及问题”归为正向引用，原结果保留；离线复核区分否定范围。全文忠实度仍无法自动证明。')
        with st.expander('原始执行记录 / 引用证据 / 回放JSON'):st.json(record)
    else:empty('尚无本轮真实生成证据','不使用Mock文本填充真实结果。')
    st.subheader('隔离RAG缺陷注入（明确离线）')
    from target.rag_faults import NAMES,run_experiment
    mutation=st.selectbox('RAG 变异',NAMES,key='rag_mutation')
    st.caption('使用独立Chroma索引和明确标记的桩向量；不是Live质量成绩，不修改正常索引或旧八变异。')
    if st.button('执行隔离离线RAG变异',key='rag_mutation_run'):
        with st.spinner('正在执行隔离索引实验…'):
            try:st.session_state['rag_mutation_record']=run_experiment(mutation,ROOT/'artifacts/runtime/v35-rag-experiments'/uuid.uuid4().hex)
            except Exception as exc:st.error('隔离实验未完成：'+type(exc).__name__)
    if st.session_state.get('rag_mutation_record'):st.json(st.session_state['rag_mutation_record'])


def _generation_used():
    from target.request_accounting import snapshot
    return snapshot(AUTH/'generation-total.db',4)['reserved_requests']
