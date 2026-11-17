"""Read actual benchmark artifacts. Browsing never runs retrieval or generation."""
import io
import json
import zipfile
from pathlib import Path
import streamlit as st
from target import rag_benchmark as benchmark
from web.design import kpis, table

CATEGORY_LABELS = dict(zip(benchmark.QUOTAS, ('正常问答', '口语改写', '多政策组合', '无答案',
    '条件缺失', '冲突与版本', '提示词注入', '错误前提', '数值边界')))


def report_view(report):
    summary = report['summary']
    st.write('实际批次：' + report['run_id'] + ' · ' + report['state'])
    st.caption('数据集 ' + report['dataset_version'] + ' · ' + report['configuration']['mode'] +
               ' · 来源 ' + str(report.get('embedding', {}).get('origin', '未知')))
    counts = summary['execution']
    kpis([('检索已执行', counts.get('completed', 0), '不等于检索质量通过'),
          ('阻塞/异常', sum(counts.get(k, 0) for k in ('blocked', 'error')), '缺缓存不伪装为已执行'),
          ('回答已评估', sum(v for k, v in summary['answer_verdicts'].items() if k != 'not_evaluated'), '未生成新回答'),
          ('本轮真实请求', report['real_api_requests'], '本入口仅离线执行')])
    table([{'指标': k, '数值': v['value'] if v['value'] is not None else '未知/不适用', '有效分母': v['denominator']}
           for k, v in summary['metrics'].items()], 'rag_benchmark_metrics_' + report['run_id'], search=False)
    st.caption('Recall 是相关文档覆盖比例；多文档问题必须取齐证据。无答案误召回衡量无关文档暴露，不等于回答错误。')
    rows = report['rows']
    categories = ['全部'] + sorted({r['category'] for r in rows})
    category = st.selectbox('筛选题目类别', categories, format_func=lambda c: CATEGORY_LABELS.get(c, c), key='benchmark_category_' + report['run_id'])
    failures = st.checkbox('仅看检索未通过或未执行', value=True, key='benchmark_failures_' + report['run_id'])
    filtered = [r for r in rows if (category == '全部' or r['category'] == category) and
                (not failures or r.get('retrieval_verdict') != 'pass')]
    table([{'题号': r['case_id'], '问题': r['question'], '执行': r['execution_status'],
            '检索判定': r.get('retrieval_verdict', '未评估'), '原因': r.get('reason', ''),
            '标注状态': r['annotation_status']} for r in filtered], 'benchmark_cases_' + report['run_id'])
    if filtered:
        n = st.selectbox('逐题证据', range(len(filtered)), format_func=lambda n: filtered[n]['case_id'] + ' · ' + filtered[n]['question'], key='benchmark_evidence_' + report['run_id'])
        row = filtered[n]
        st.write('预期文档：', row['expected_doc_ids'])
        if row.get('hits'):
            table([{'排名': h.get('rank'), '文档': h['doc_id'], '版本': h.get('version'), '分数': h.get('score'),
                    '原文': h['content']} for h in row['hits']], 'benchmark_hits_' + report['run_id'], search=False)
        else:
            st.info('本题没有已保存的检索文档。')
        st.caption('直接检索评测不是 Agent 工具执行；没有 Agent Trace ID，不补造。检索快照哈希：' + str(row.get('retrieval_sha256', '旧版未记录')))
        with st.expander('完整原始记录与回答判定'):
            st.json(row, expanded=False)
    directory = benchmark.STORE / report['run_id']
    if directory.is_dir():
        st.download_button('下载 Markdown 评测报告', (directory/'report.md').read_bytes(), file_name=report['run_id']+'.md', key='benchmark_md_' + report['run_id'])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ('report.json', 'report.md', 'results.jsonl', 'results.csv', 'receipt.json', 'dataset-manifest.json', 'corpus-snapshot.json'):
                if (directory/name).is_file():
                    archive.write(directory/name, name)
        st.download_button('下载本批报告与逐题日志 ZIP', buffer.getvalue(), file_name=report['run_id']+'.zip', key='benchmark_zip_' + report['run_id'])


def render():
    st.subheader('千题 RAG 评测工程 · 候选版')
    st.caption('独立冻结语料与题库；旧30题、48题和历史模型证据保持原样。浏览不会发起任何API请求。')
    cases, corpus, manifest = benchmark.load()
    version = manifest['dataset_version']
    verified = sum(c['provenance']['review_status'] == 'verified' for c in cases)
    kpis([('候选题', len(cases), version), ('已核验标注', verified, 'AI来源核对 + 确定性校验，非B人工验收'),
          ('待语义复核', len(cases)-verified, '未计入1000道已验证题'),
          ('意图组', len({c['group_id'] for c in cases}), '改写不冒充独立能力')])
    table([{'类别': CATEGORY_LABELS[c], '目标': n, '候选': sum(r['category']==c for r in cases),
            '已核验': sum(r['category']==c and r['provenance']['review_status']=='verified' for r in cases)}
           for c, n in benchmark.QUOTAS.items()], 'benchmark_distribution', search=False)
    st.warning('这是1000条候选题，不是1000条全部已验收题。复杂标注尚需B复核；无新模型回答时，不展示回答忠实度通过率。')
    if st.button('校验冻结题库与划分', key='benchmark_validate'):
        result = benchmark.validate(cases, corpus, manifest)
        st.session_state['benchmark_validation'] = result
    validation = st.session_state.get('benchmark_validation')
    if validation:
        (st.success if validation['valid_structure'] else st.error)('结构/证据/划分检查：' + ('通过' if validation['valid_structure'] else '失败'))
        with st.expander('校验详情及近重复候选'):
            st.json(validation, expanded=False)
    with st.form('rag_benchmark_execute'):
        a, b = st.columns(2)
        split = a.selectbox('评测集合', ['development', 'validation', 'holdout'], key='benchmark_split')
        mode = b.selectbox('评测模式', ['keyword', 'vector', 'hybrid'], key='benchmark_mode')
        index = st.text_input('兼容真实 Chroma 索引路径（Vector/Hybrid必需，只操作副本）', key='benchmark_index')
        cache = st.text_input('真实问题向量缓存路径（仅使用已有缓存，不联网补齐）', key='benchmark_cache')
        st.caption('原业务检索器保留；本评测使用同一Keyword算法、cosine与RRF60。阈值固定0.35、Top5，未用验收集调参。')
        submitted = st.form_submit_button('开始离线评测', type='primary')
    if submitted:
        progress = st.progress(0, text='正在校验并建立独立运行目录')
        def notify(done, total, row):
            progress.progress(done/total, text=f"已保存 {done}/{total} · {row['case_id']} · {row['execution_status']}")
        try:
            _, report = benchmark.run(split=split, mode=mode, index=Path(index) if index else None,
                cache=Path(cache) if cache else None, notify=notify)
            st.session_state['benchmark_latest'] = report['run_id']
        except Exception as exc:
            st.error('评测未完成：' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
    history_errors = []
    records = benchmark.history(errors=history_errors)
    if history_errors:
        st.warning(f'{len(history_errors)}个历史批次文件无法读取；没有把它们计为成功。')
    if not records:
        st.info('暂无新题库运行记录。点击上方按钮才会执行离线检索。')
        return
    selected = st.selectbox('读取已保存批次', range(len(records)), format_func=lambda n: records[n]['run_id'] + ' · ' + records[n]['configuration']['mode'], key='benchmark_history')
    report_view(records[selected])
    if len(records) > 1:
        with st.expander('对比另一个批次（数据集、题目集合和配置必须一致才可公平比较）'):
            other = st.selectbox('对照批次', range(len(records)), index=1, format_func=lambda n: records[n]['run_id'], key='benchmark_compare')
            left, right = records[selected], records[other]
            comparison = benchmark.compare_runs(left, right)
            st.write('数据集、题集、源码及受控配置可比：', '是' if comparison['same_controlled_inputs_except_retrieval_mode'] else '否，不能单独归因为模型/检索模式差异')
            if comparison['differences']:
                st.write('不同项：', '、'.join(comparison['differences']))
            table([{'批次': r['run_id'], '数据集': r['dataset_version'], '模式': r['configuration']['mode'],
                    '状态': r['state'], '源码指纹': r['source_sha256'],
                    **{k: v['value'] for k, v in r['summary']['metrics'].items()}} for r in (left, right)], 'benchmark_compare_rows', search=False)
