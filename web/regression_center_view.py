"""Human-readable offline regression center; execution requires an explicit click."""
import io
import json
from pathlib import Path
import zipfile
import streamlit as st
from scripts import regression_center as runner
from web import test_console as console
from web.design import header,kpis,table,empty,escape
from target.diagnostics import sanitize


def step_rows(report):
    return [{'步骤':s['name'],'状态':'评估执行完成' if s['id']=='rag' and s['status']=='passed' else runner.LABELS[s['status']],
             '耗时（秒）':s.get('seconds'),'原因':s.get('reason') or '查看检查明细'} for s in report['steps']]


def bundle(directory):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(Path(directory).iterdir()):
            if file.is_file() and file.suffix in ('.json','.html','.log','.xml'):
                archive.writestr(file.name,sanitize(file.read_text(encoding='utf8',errors='replace')))
    return output.getvalue()


def meta_strip(report):
    """Version / time / environment / scope, so a result is never shown bare."""
    with st.container(key='console_meta'):
        st.markdown('<div class="ta-rail-head"><b>批次元信息</b><span>来源：本批次 report.json</span></div>',
                    unsafe_allow_html=True)
        for label, value in console.batch_meta(report):
            st.caption(f'{label}：{value}')


def show_report(report,key='current'):
    directory=Path(report['directory'])
    st.subheader('本批次结果')
    st.caption('批次 '+report['batch_id']+' · '+report['started']+' · A 工程验收，非 B 正式成绩')
    meta_strip(report)
    steps=report['steps'];py=next(s for s in steps if s['id']=='pytest').get('details') or {}
    kpis([('流程状态',{'completed':'检查流程完成','failed':'存在失败','blocked':'存在阻塞','interrupted':'未完成，状态待确认'}.get(report['status'],'执行中'),'不是业务正确率'),
          ('pytest 通过',py.get('passed'),'子测试单独统计：'+str(py.get('subtests_passed','未知'))),
          ('pytest 失败',py.get('failed'),'包括已记录的测试异常'),
          ('外部连接阻断',report.get('blocked_external_connections'),'离线守卫记录，不是API成功次数')])
    table(step_rows(report),'steps_'+key,search=False)
    for step in steps:
        status='评估执行完成' if step['id']=='rag' and step['status']=='passed' else runner.LABELS[step['status']]
        with st.expander(step['name']+' · '+status,expanded=step['status'] in ('failed','blocked')):
            if step.get('reason'):st.warning(step['reason'])
            details=step.get('details')
            if step['id']=='pytest' and details:
                st.write('通过',details.get('passed','未知'),'· 失败',details.get('failed','未知'),'· 跳过',details.get('skipped','未知'),
                         '· 子测试失败',details.get('subtests_failed','未知'))
                for failure in details.get('failures',[]):
                    st.error(failure['case_id']+' · '+str(failure.get('stage','')))
                    st.code(sanitize(failure['reason']),language=None)
                if step['status']=='failed' and not details.get('failures'):st.info('进程未正常完成，未获得完整用例清单；请查看进程日志。')
            elif step['id']=='rag' and isinstance(details,dict) and details.get('metrics'):
                st.info('独立Chroma + 离线哈希向量；评估执行完成不代表质量达标，不是新的真实Embedding或模型成绩。')
                table([{'模式':m,**r} for m,r in details['metrics'].items()],'rag_'+key,search=False)
            elif isinstance(details,list):table(details,'detail_'+key+'_'+step['id'],search=False)
            elif isinstance(details,dict):table([{'检查项':k,'结果':v} for k,v in details.items()],'detail_'+key+'_'+step['id'],search=False)
            else:st.caption('没有该步骤的详细结果。')
    with st.expander('原始日志与证据下载'):
        files=sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in ('.log','.xml'))
        if files:
            selected=st.selectbox('日志文件',files,format_func=lambda p:p.name,key='log_'+key)
            st.code(sanitize(selected.read_text(encoding='utf8',errors='replace')[-16000:]),language=None)
            st.caption('页面最多显示末16000字符；下载包保留完整脱敏日志。')
        else:st.info('本批次尚无进程日志。')
        st.download_button('下载批次报告 JSON',json.dumps(sanitize(report),ensure_ascii=False,indent=2),file_name=report['batch_id']+'.json',key='json_'+key)
        if (directory/'report.html').is_file():st.download_button('下载可独立打开的 HTML 报告',sanitize((directory/'report.html').read_text(encoding='utf8')),file_name=report['batch_id']+'.html',mime='text/html',key='html_'+key)
        st.download_button('下载报告与日志 ZIP',bundle(directory),file_name=report['batch_id']+'-evidence.zip',mime='application/zip',key='zip_'+key)
    with st.expander('完整结构化记录（高级）'):st.json(sanitize(report),expanded=False)


def batch_selector(key):
    records=runner.history()
    if not records:
        empty('暂无回归批次','在“执行回归”中启动一次检查后，这里会显示实际保存的结果。')
        return None
    index=st.selectbox('选择批次',range(len(records)),index=0,
        format_func=lambda i:('最新 · ' if i==0 else '')+records[i]['batch_id']+' · '+str(records[i].get('started') or '时间未记录'),
        key='console_batch_'+key)
    return records[index]


def meta_line(report):
    """Compact version / time / scope line for the tabs that select a batch."""
    meta = dict(console.batch_meta(report))
    st.caption(f"{meta['归属']} · 时间 {meta['开始 / 结束（UTC）']} · Git {meta['Git']} · "
               f"源码指纹 {meta['源码指纹']}")
    st.caption(f"环境 {meta['运行环境']} · 范围 {meta['测试范围']}")


def conclusion_strip():
    """Conclusion, sample size, scope and gaps before any drill-down."""
    records = runner.history()
    if not records:
        st.info('还没有回归批次。先在“执行回归”里运行一次；这里不会展示任何未经执行的结论。')
        return
    report = records[0]
    rows = console.case_rows(report['directory'])
    stats = console.case_stats(rows)
    step = next((s for s in report.get('steps') or [] if s.get('id') == 'rag'), {})
    rag = step.get('details') or {}
    dimensions = console.rag_dimensions(rag)
    unevaluated = [d['评估项'] for d in dimensions if d['状态'] != '已评估']
    meta = dict(console.batch_meta(report))
    verdict = {'completed': '流程完成', 'failed': '存在失败', 'blocked': '存在阻塞',
               'interrupted': '未完成，状态待确认'}.get(report.get('status'), '执行中')
    with st.container(key='console_conclusion'):
        st.markdown('<div class="ta-rail-head"><b>最近批次结论</b>'
                    f'<span>{escape(report.get("batch_id"))}</span></div>', unsafe_allow_html=True)
        kpis([('流程结论', verdict, '不是业务正确率'),
              ('用例样本', stats['总计'], '通过 ' + str(stats['通过']) + ' · 失败 ' + str(stats['失败'])
               + ' · 跳过 ' + str(stats['跳过']) + ' · 未记录 ' + str(stats['未记录'])),
              ('RAG 已评估项', sum(1 for d in dimensions if d['状态'] == '已评估'), '共 ' + str(len(dimensions)) + ' 项'),
              ('未评估 / 非直接判定', len(unevaluated), '不计入通过')])
        st.caption(meta['归属'] + ' · 时间 ' + meta['开始 / 结束（UTC）'] + ' · Git ' + meta['Git'])
        st.caption('范围：' + meta['测试范围'])
        if unevaluated:
            st.caption('未评估或仅代理指标：' + '、'.join(unevaluated) + '；这些项目不显示为通过。')


def cases_page():
    st.caption('逐条来自该批次的 results.json。预期行为取自测试源码；实际结果取自本次执行的断言文本。'
               '没有记录的用例不会被统计为通过。')
    report=batch_selector('cases')
    if not report:return
    directory=report['directory']
    meta_line(report)
    rows=console.case_rows(directory)
    if not rows:
        st.info('该批次没有逐用例结果文件；无法列出用例，也不推断通过率。')
        return
    stats=console.case_stats(rows)
    st.markdown('**用例结论**：总计 '+str(stats['总计'])+' · 通过 '+str(stats['通过'])
                +' · 失败 '+str(stats['失败'])+' · 跳过 '+str(stats['跳过'])
                +' · 未记录 '+str(stats['未记录'])+'（跳过与未记录不计入通过）')
    left,right=st.columns([1,2])
    status=left.selectbox('状态筛选',['全部','通过','失败','跳过','未记录'],key='console_case_status')
    keyword=right.text_input('按用例名或断言文本筛选',key='console_case_keyword')
    visible=console.filter_cases(rows,status,keyword)
    st.caption(f'当前显示 {len(visible)} / {len(rows)} 条；筛选与导出使用同一批数据。')
    if not visible:
        st.info('没有符合筛选条件的用例。')
        return
    pick=st.selectbox('查看用例详情',range(len(visible)),
        format_func=lambda i:visible[i]['用例'],key='console_case_pick')
    row=visible[pick]
    detail=console.case_detail(row,directory)
    st.caption('状态：'+detail['状态']+' · 阶段：'+detail['阶段']
               +' · 耗时：'+(str(detail['耗时'])+' 秒' if detail['耗时'] is not None else '未记录')
               +' · 预期行为来源：'+detail['预期行为来源'])
    if detail['测试源码']:
        st.code(detail['测试源码'],language='python')
        st.caption('以上是定义该用例的测试源码；它说明预期，不等于本批已通过。')
    else:
        st.info('未找到该用例的源码，未推断预期行为。')
    st.markdown('**实际结果**')
    st.code(detail['实际结果'],language=None)
    with st.expander('原始断言证据'):
        if detail['原始断言证据']:
            st.code(sanitize(detail['原始断言证据']),language=None)
        else:
            st.caption('该用例没有记录断言证据。')
    with st.expander('本批 pytest 进程日志（末尾）'):
        if detail['进程日志']:
            st.code(sanitize(detail['进程日志']),language=None)
        else:
            st.caption('没有可读的 pytest.log。')
    st.download_button('导出该用例证据 JSON',json.dumps(sanitize(detail),ensure_ascii=False,indent=2),
        file_name=row['用例'].replace('::','__')+'.json',key='console_case_json')
    st.divider()
    st.markdown('**筛选结果全表**')
    table(visible,'console_cases',search=False)


def mutation_page():
    st.caption('B 的历史选定变异矩阵（只读，本轮不重跑）。选定矩阵与额外探测分开统计，'
               '未记录判定的组合不计入已检出。')
    summary=console.mutation_summary()
    if not summary:
        st.info('没有可读的变异矩阵数据。')
        return
    table(summary,'console_mutation_summary',search=False)
    rows=console.mutation_matrix()
    missed=[r for r in rows if r['结果']=='未检出']
    unrecorded=[r for r in rows if r['结果']=='未记录']
    if missed:
        st.warning(f'未检出 {len(missed)} 条：这些变异未被任何选中用例捕获，保留为缺陷证据，不改写为通过。')
    if unrecorded:
        st.info(f'未记录 {len(unrecorded)} 条：没有判定文本，不能当作已检出。')
    table(rows,'console_mutation_rows',search=False)
    with st.expander('未检出明细'):
        if missed:
            table(missed,'console_mutation_missed',search=False)
        else:
            st.caption('没有未检出记录。')


def rag_page():
    st.caption('四个评估项分开呈现：检索命中、引用支持、回答正确、无答案拒答。'
               '没有实测证据的项目显示未评估，不显示为通过。')
    report=batch_selector('rag')
    if not report:return
    meta_line(report)
    step=next((s for s in report.get('steps') or [] if s.get('id')=='rag'),None)
    if not step or step.get('status')=='skipped' or not (step.get('details') or {}).get('metrics'):
        status=(step or {}).get('status','未记录')
        st.info('该批次的 RAG 评估状态为「'+runner.LABELS.get(status,status)+'」，没有实测指标；未评估不等于通过。')
        return
    rag=step['details']
    table(console.rag_dimensions(rag),'console_rag_dims',search=False)
    st.markdown('**检索指标（按模式）**')
    table(console.rag_mode_rows(rag),'console_rag_modes',search=False)
    st.caption('Recall 是相关文档覆盖比例；负样本误召回衡量无关文档暴露，不等于回答错误。'
               'answer_faithfulness = '+str(rag.get('answer_faithfulness') or '未记录')+'。')


def history_page():
    st.button('刷新历史批次',key='refresh_batch_history')
    records=runner.history()
    if not records:
        empty('暂无回归批次','在“执行回归”中启动一次检查后，这里会显示实际保存的结果。');return
    st.caption('仅展示本回归中心产生的批次；旧版静态报告在原页面保留，不自动转换成绩。未结束批次的进程状态不作推断，可刷新查看已保存进度。')
    selection=records
    for field,label in (('suite_sha256','测试集指纹'),('source_sha256','源码版本指纹'),('config_sha256','运行配置')):
        options=['全部']+sorted({r[field] for r in selection})
        value=st.selectbox(label,options,format_func=lambda v:v if v=='全部' else v[:16],key='history_'+field)
        if value!='全部':selection=[r for r in selection if r[field]==value]
    table([{'批次':r['batch_id'],'开始时间（UTC）':r['started'],'状态':runner.LABELS.get(r['status'],'流程完成'),
            'Git':r.get('git_sha') or '未知','源码指纹':r['source_sha256'][:16]} for r in selection],'batch_history')
    if selection:
        chosen=st.selectbox('查看批次',range(len(selection)),format_func=lambda i:selection[i]['batch_id'],key='history_batch')
        show_report(selection[chosen],'history')
    if len(records)>=2:
        with st.expander('与另一个批次对照'):
            st.caption('只有测试集指纹与源码指纹都相同的批次才可归因为代码改动。')
            a,b=st.columns(2)
            left=a.selectbox('本批',range(len(records)),index=0,
                format_func=lambda i:records[i]['batch_id'],key='compare_left')
            right=b.selectbox('对照批',range(len(records)),index=min(1,len(records)-1),
                format_func=lambda i:records[i]['batch_id'],key='compare_right')
            result=console.compare(records[left],records[right])
            if not result:
                st.info('无法比较这两个批次。')
            else:
                st.write('同测试集：'+('是' if result['same_suite'] else '否')+' · 同源码指纹：'+('是' if result['same_source'] else '否'))
                if not result['comparable']:
                    st.warning('测试集或源码指纹不同：差异不能归因为代码改动，只能并列展示。')
                table(result['steps'],'console_compare_steps',search=False)
                table(result['pytest'],'console_compare_pytest',search=False)


def page():
    header('离线回归中心','检查环境、执行回归、逐条核对用例、变异检出与 RAG 四个维度，统一留存可复核证据。','A 工程验收 · 纯离线')
    conclusion_strip()
    execute_tab,cases_tab,mutation_tab,rag_tab,history_tab=st.tabs(['执行回归','用例明细','变异矩阵','RAG 四项','历史批次'])
    with execute_tab:
        st.caption('环境预检 → 证据与隔离副本 → pytest → RAG评估 → 启动器预检 → 文件保护。只在点击执行后运行。')
        plan=st.selectbox('回归范围',['快速专项回归','完整离线回归'],key='center_plan')
        node=st.text_input('pytest 节点',value='tests/test_p0_evidence_chain.py',key='center_node') if plan=='快速专项回归' else ''
        rag=st.checkbox('同时运行60条政策离线检索评估',value=True,key='center_rag')
        performance=st.checkbox('附加数据库并发检查（1 / 10 / 50客户端）',value=False,key='center_performance')
        st.info('测试在独立源码副本中执行；不恢复或覆盖原始证据。RAG使用离线哈希向量，启动器只做配置预检；不会验证真实API连通性。')
        if st.button('开始离线回归',type='primary',key='center_run'):
            progress=st.progress(0,text='准备批次');current=st.empty();overview=st.empty()
            def update(report):
                count=sum(s['status'] not in ('pending','running') for s in report['steps'])
                active=next((s['name'] for s in report['steps'] if s['status']=='running'),'流程已结束')
                progress.progress(count/len(report['steps']),text=active);current.info(active+'；不会自动重试。')
                overview.dataframe(step_rows(report),hide_index=True,width='stretch')
            try:
                report=runner.execute(node=node.strip(),rag=rag,performance=performance,notify=update)
                st.session_state['center_last_report']=report['directory'];current.empty();overview.empty()
            except Exception as exc:current.error('批次未完成：'+type(exc).__name__+'。部分证据保留在批次目录中；不会重试。')
        path=st.session_state.get('center_last_report')
        if path and (Path(path)/'report.json').is_file():show_report(runner.read(Path(path)/'report.json'))
    with cases_tab:cases_page()
    with mutation_tab:mutation_page()
    with rag_tab:rag_page()
    with history_tab:history_page()
    st.caption('测试实验室继续支持交互式变异与Live调试；本中心仅做离线工程回归。B的正式103条用例不由此入口自动判分。')
