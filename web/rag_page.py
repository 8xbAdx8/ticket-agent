"""Working RAG administration/retrieval and source-backed acceptance replay. No auto API calls."""
import json
import os
from pathlib import Path
import uuid
import streamlit as st
from web.design import header,empty
from target.embeddings import AUTH
from target.rag_store import ROOT,documents


RAG_MUTATION_LABELS = {
    'rag_missing_doc': ('政策文档缺失', '模拟删除锁座政策 P11，检查能否发现应有文档缺失。'),
    'rag_conflicting_doc': ('政策内容冲突', '加入与现有锁座时限矛盾的测试政策，检查冲突是否被发现。'),
    'rag_stale_doc': ('引用过期政策', '加入标记为过期的政策，检查能否识别旧版本风险。'),
    'rag_wrong_citation': ('引用编号错误', '用不存在的政策编号 P99 构造回答，检查引用编号是否与检索证据匹配。'),
    'rag_low_similarity': ('检索相似度过低', '模拟很低的相似度，检查阈值是否过滤不相关结果。'),
    'rag_prompt_injection': ('政策文档恶意指令', '在测试文档中加入恶意指令，检查风险规则是否检出。'),
    'rag_empty_index': ('知识库索引为空', '创建空测试索引，检查是否显示索引不可用。'),
    'rag_embedding_error': ('向量服务异常', '模拟 Embedding 服务返回 503，检查错误分类。'),
}


def saved(name):
    for p in (AUTH/name,ROOT/'docs/evidence/v35/live'/name):
        if p.is_file():return json.loads(p.read_text(encoding='utf-8'))
    return None


def current_session_rag(sessions):
    from web.evidence import read_jsonl
    st.subheader('当前会话的政策检索证据')
    st.caption('只读取已保存的检索记录；浏览本区不会调用模型或 Embedding。')
    if not sessions:
        st.info('暂无当前浏览器会话。先在出行助手或测试实验室提问政策问题。')
        return
    i=st.selectbox('选择 RAG 会话',range(len(sessions)),index=len(sessions)-1,
                   format_func=lambda n: ('出行助手' if sessions[n].mode=='user' else '测试实验室')+' · '+sessions[n].sid,
                   key='rag_session')
    records,errors=read_jsonl(sessions[i].trace_dir/'rag_runs.jsonl')
    if errors.get('invalid') or errors.get('truncated'):
        st.warning('部分检索记录无法读取或超出读取范围。')
    if not records:
        st.info('该会话尚无 RAG 检索旁证；普通聊天不会自动产生政策检索记录。')
        return
    n=st.selectbox('选择检索记录',range(len(records)),index=len(records)-1,
                   format_func=lambda n: str(records[n].get('retrieval_id','未知'))[:16]+' · '+str(records[n].get('question','问题未知'))[:40],key='rag_session_record')
    record=records[n]
    st.write('Trace ID：',record.get('trace_id') or '未知', ' · 检索状态：',record.get('status','未知'))
    st.write('检索模式：',record.get('mode','未知'),' · 检索问题：',record.get('question','未知'))
    if record.get('error_category'):st.warning('检索错误：'+str(record['error_category']))
    hits=record.get('hits') or []
    if hits:
        st.dataframe([{k:h.get(k) for k in ('rank','doc_id','title','source','score')} for h in hits if isinstance(h,dict)],hide_index=True)
    else: st.info('没有保存可展示的命中文档；这不代表回答忠实度通过。')
    with st.expander('检索内容与原始证据'):
        st.json(record)
    st.caption('引用和全文忠实度需要结合该 Trace 中的回答及审计证据核对，不能仅凭检索成功判定。')


def render_mutation_result(record):
    """Present saved evidence without treating a stub result as a Live score."""
    name=record.get('mutation','未知')
    label,description=RAG_MUTATION_LABELS.get(name,(name,'没有该变异的说明。'))
    judgement=record.get('judgement') if isinstance(record.get('judgement'),dict) else {}
    detected=judgement.get('detected')
    st.markdown('### 本次实验结果：'+label)
    if record.get('executed') is not True:
        st.warning('未确认实验已执行；不能判定检出结果。')
    elif detected is True:
        st.success('离线规则已检出本次构造的问题。')
    elif detected is False:
        st.error('本次构造的问题未被离线规则检出，请查看原始证据。')
    else:
        st.warning('检出结果未知，不能判为通过。')
    st.write('实验内容：'+description)
    st.caption('这是隔离的模拟文档与向量实验，不代表真实模型识别或恢复了问题。')
    st.write('真实 API 请求次数：',record.get('real_api_requests') if type(record.get('real_api_requests')) is int else '未知')
    st.write('正常索引是否修改：','否' if record.get('normal_index_modified') is False else '是' if record.get('normal_index_modified') is True else '未知')
    before=record.get('before') if isinstance(record.get('before'),dict) else {}
    after=record.get('after') if isinstance(record.get('after'),dict) else {}
    if before.get('question'):st.write('测试问题：',before['question'])
    if name=='rag_wrong_citation':
        st.write('模拟回答：',after.get('model_fixture_reply') or '未保存')
        assessment=judgement.get('assessment') or {}
        st.write('检索到的来源：', '、'.join(assessment.get('allowed_doc_ids') or []) or '未提供')
        st.write('被判为错误的引用：', '、'.join(assessment.get('wrong_citations') or []) or '未提供')
    elif name=='rag_missing_doc':
        st.write('变异前文档：', '、'.join(h.get('doc_id','未知') for h in before.get('hits',[]) if isinstance(h,dict)) or '未提供')
        st.write('变异后文档：', '、'.join(h.get('doc_id','未知') for h in after.get('hits',[]) if isinstance(h,dict)) or '无或未提供')
    elif name=='rag_low_similarity':
        st.write('模拟低分条数：',len(after.get('hits',[])) if isinstance(after.get('hits'),list) else '未知')
        st.write('过滤后条数：',len(after.get('filtered_hits',[])) if isinstance(after.get('filtered_hits'),list) else '未知')
    elif name=='rag_embedding_error':
        error=after.get('error') or {}
        st.write('模拟错误类别：',error.get('category','未知'),'；HTTP 状态：',error.get('status','未知'))
    elif name=='rag_empty_index':
        st.write('空索引状态：',after.get('state','未知'))
    elif judgement.get('findings'):
        st.write('规则发现：')
        st.json(judgement['findings'],expanded=False)
    if record.get('mutation') != st.session_state.get('rag_mutation'):
        st.caption('上面显示的是上次执行的实验；切换选项不会自动重新运行。')
    with st.expander('查看完整原始实验记录（JSON）'):
        st.json(record,expanded=False)


def rag_page(sessions=()):
    header('RAG 知识库','真实向量、政策来源和有限验收。票价/余票仍由query_tickets查询。','V3.5.2 · 模拟政策')
    current_session_rag(sessions)
    from web.rag_acceptance import render_acceptance
    render_acceptance()
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
    from target.api_usage import provider_usage
    embedding_usage=provider_usage('embedding')
    cols[2].metric('Embedding当前请求次数',embedding_usage['request_count'] if embedding_usage['request_count'] is not None else '未知')
    cols[3].metric('生成当前请求次数',_generation_used())
    st.caption('索引状态：'+state['state']+' · 版本：'+str(state.get('index_version','未知'))+' · 类别：'+state.get('category','正常'))
    st.caption('Live模型与Embedding累计请求次数不设本地上限。真实API可能产生费用；缓存命中不发送新Embedding请求，历史证据单独保留。')
    with st.expander('索引元数据与API来源回执'):
        st.json(state)
    mode=st.selectbox('政策检索模式',['keyword','vector','hybrid'],key='rag_mode')
    k=st.number_input('Top-K',min_value=1,max_value=10,value=3,step=1,key='rag_k')
    threshold=st.slider('向量cosine最低分',min_value=0.0,max_value=1.0,value=0.35,step=0.05,key='rag_threshold')
    question=st.text_input('政策问题',value='锁座后多久必须完成支付？',key='rag_question')
    offline=os.getenv('TICKET_WEB_OFFLINE_ONLY')=='1'
    consent=st.checkbox('允许本次检索/构建调用真实Embedding（可能产生费用）',value=False,disabled=offline,key='rag_network_consent')
    if offline:st.caption('当前由离线启动器强制禁止网络；在线模式确认费用后可执行真实Embedding。')
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
    if state.get('immutable_baseline'):st.caption('冻结基线索引只读；查询在副本进行。构建新版本须配置独立RAG_INDEX_DIR，禁止覆盖基线。')
    if st.button('显式增量构建 / 重建索引',disabled=not consent or offline or index is None or state.get('immutable_baseline',False),key='rag_build'):
        try:
            st.write(index.build(allow_network=True,rebuild=state['state']!='ready'))
        except Exception as exc:st.error('索引构建失败：'+getattr(exc,'category',type(exc).__name__))
    result=st.session_state.get('rag_retrieval_result')
    if result:
        st.dataframe([{k:h.get(k) for k in ('rank','doc_id','title','source','score','vector_score','keyword_score','fusion_ranks')} for h in result['hits']],hide_index=True)
        st.caption('vector为cosine，keyword为字词重叠分，hybrid为RRF(k=60)，不同模式分值不能横向当概率。')
        with st.expander('完整检索正文和来源'):
            st.json(result)
    st.subheader('V3.5 历史真实验收回放与质量指标')
    evaluation=saved('retrieval-evaluation/report.json')
    if evaluation and evaluation.get('metrics'):
        st.dataframe([{'mode':m,**{k:v for k,v in r.items() if k!='rows'}} for m,r in evaluation['metrics'].items()],hide_index=True)
        st.warning('固定30问题：26有答案、4无答案；只衡量检索。无答案误召回按原结果保留，不能当作回答准确率或B正式成绩。')
    generation=saved('generation-result.json');review=saved('generation-assessment-review.json')
    if generation:
        if model.startswith('DeepSeek'):
            st.info('V3.5历史样本未包含DeepSeek同证据生成；以下Qwen记录不作为DeepSeek成绩。V3.5.2双模型证据见上方单独回放。')
        st.caption('只读回放：真实调用源码与当前后续UI代码可能不同；没有新增模型请求。新的只读Live对话可在出行助手或测试实验室显式执行，无累计请求上限。')
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
    mutation=st.selectbox('RAG 变异',NAMES,format_func=lambda name: RAG_MUTATION_LABELS[name][0]+' · '+name,key='rag_mutation')
    st.info(RAG_MUTATION_LABELS[mutation][1])
    st.caption('使用独立Chroma索引和明确标记的桩向量；不是Live质量成绩，不修改正常索引或旧八变异。')
    if st.button('执行隔离离线RAG变异',key='rag_mutation_run'):
        with st.spinner('正在执行隔离索引实验…'):
            try:st.session_state['rag_mutation_record']=run_experiment(mutation,ROOT/'artifacts/runtime/v35-rag-experiments'/uuid.uuid4().hex)
            except Exception as exc:st.error('隔离实验未完成：'+type(exc).__name__)
    if st.session_state.get('rag_mutation_record'):render_mutation_result(st.session_state['rag_mutation_record'])


def _generation_used():
    from target.api_usage import provider_usage
    counts=[provider_usage(p)['request_count'] for p in ('deepseek','bailian')]
    return sum(counts) if all(type(n) is int for n in counts) else '未知'
