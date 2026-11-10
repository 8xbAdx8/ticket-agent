"""Project-local candidate desk, deliberately independent of official scores."""
import json
import streamlit as st
from target.scenario_generator import Store, CATEGORIES, review


def page():
    st.header('AI 测试场景生成')
    st.caption('生成候选 → 确定性校验 → 人工审核 → 独立离线执行')
    store = Store()
    rows = store.list()
    runs = store.runs()
    with st.expander('V3.10 确定性集成计划'):
        from target.scenario_plans import plans, candidate
        references = {p['title']: p for p in plans()}
        selected_plan = st.selectbox('参考计划', list(references))
        st.caption('参考计划来自版本化确定性夹具。载入后仍需人工审核，执行时使用新数据库和真实Registry/Service。')
        if st.button('载入参考计划为待审核候选'):
            store.save(candidate(references[selected_plan]), 'reference-plan-import')
            st.rerun()
    with st.expander('质量与覆盖率（实际执行证据）'):
        from target.scenario_quality import quality, coverage, model_comparison
        metrics = quality(rows, runs)
        measured = coverage([r['body'] for r in runs])
        st.caption('每项包含分子、分母和定义。无数据为N/A。确定性集成与Live Agent分别记录。')
        st.json(metrics)
        st.json(measured)
        st.json(model_comparison(store.original_candidates(), store.generations()))
    st.write(f"候选 {len(rows)} · 待审核 {sum(r['status']=='PENDING' for r in rows)} · 已批准 {sum(r['status']=='APPROVED' for r in rows)} · 已执行 {len({r['case_id'] for r in runs})}")
    if rows:
        st.caption('最近一次生成 ' + max(r['body']['created_at'] for r in rows))
    budget_path = store.root / 'generation-budget.sqlite'
    if budget_path.is_file():
        from target.acceptance_budget import Batch
        budget = Batch(budget_path).snapshot()
        st.caption(f"生成批次剩余 {budget['remaining_http_requests']} 个请求，累计 Token 不设硬上限，费用 UNKNOWN")
        if budget['warning']:
            st.warning('当前生成批次已达到Token预警线。')
    with st.expander('生成测试场景', expanded=True):
        with st.form('ai_scenario_generate'):
            objective = st.text_area('测试目标', height=120, max_chars=4000)
            category = st.selectbox('测试领域', list(CATEGORIES))
            difficulty = st.selectbox('测试难度', ['easy', 'medium', 'hard'], index=1)
            count = st.number_input('生成数量', min_value=1, max_value=5, value=1)
            provider = st.selectbox('生成模型', ['Mock', 'deepseek', 'bailian'])
            adapter_label = st.selectbox('生成目标适配器', ['V3.10 DSL', 'Legacy P2'])
            adapter = 'v310' if adapter_label == 'V3.10 DSL' else 'p2'
            constraints = st.text_area('高级生成约束', max_chars=2000)
            consent = st.checkbox('授权本次生成调用所选在线模型并产生费用')
            st.caption('V3.10 DSL 生成真实 railway_* 可执行步骤；Legacy P2 保留兼容。单次最多1个HTTP请求、4096输出Token、零自动重试。在线共享持久批次上限50请求，累计Token无硬上限、320000预警。费用未知时记录UNKNOWN。Mock只验证流程，不冒充AI生成。')
            generate = st.form_submit_button('生成候选场景', type='primary')
        if generate:
            if provider != 'Mock' and not consent:
                st.warning('请先授权本次在线生成。')
            else:
                try:
                    with st.spinner('正在生成并保存候选'):
                        result = store.generate(objective, category, difficulty, int(count), provider, constraints, adapter=adapter)
                    if result['status'] == 'SUCCEEDED':
                        st.success('候选已保存，请查看校验结果并人工审核。')
                    else:
                        st.error('生成失败，原因 ' + result['error'])
                    with st.expander("生成回执与用量"):
                        st.json(result)
                except ValueError as exc:
                    st.error(str(exc))
    rows = store.list()
    st.subheader('候选场景管理')
    search = st.text_input('搜索场景')
    status = st.selectbox('审核状态', ['全部', 'PENDING', 'APPROVED', 'REJECTED', 'ARCHIVED'])
    view = st.selectbox('执行状态', ['全部', '已执行', '执行失败'])
    order = st.selectbox('排序', ['最近更新', '标题'])
    executed = {r['case_id'] for r in runs}
    failed = {r['case_id'] for r in runs if r['status'] in ('failed', 'error', 'invalid')}
    visible = [r for r in rows if (status == '全部' or r['status'] == status)
               and search.lower() in (r['id'] + r['body']['title'] + r['body']['objective']).lower()
               and (view == '全部' or r['id'] in (executed if view == '已执行' else failed))]
    if order == '标题':
        visible.sort(key=lambda r: r['body']['title'])
    st.download_button('导出当前列表 JSON', json.dumps(visible, ensure_ascii=False, indent=2), 'ai-candidates.json', 'application/json')
    if not visible:
        st.info('暂无匹配场景。填写测试目标后生成候选，或调整筛选条件。')
        return
    by_id = {r['id']: r for r in visible}
    selected = st.multiselect('批量审核选择', list(by_id), format_func=lambda n: by_id[n]['body']['title'])
    actor = st.text_input('审核人（写入审计记录）')
    action = st.selectbox('审核操作', ['APPROVED', 'REJECTED', 'DELETED', 'ARCHIVED'])
    st.caption('批准要求校验PASS。已批准内容冻结。删除仅适用于待审核候选，删除历史仍可追溯。')
    if st.button('应用人工审核', disabled=not selected or not actor.strip()):
        try:
            store.decide([(n, by_id[n]['revision']) for n in selected], action, actor)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    identity = st.selectbox('查看场景详情', list(by_id), format_func=lambda n: by_id[n]['body']['title'])
    row = by_id[identity]
    case = row['body']
    st.write(case['title'])
    st.caption(f"{identity} · {case['category']} · {case['difficulty']} · {case['risk_level']} · {row['status']} · 版本{row['revision']}")
    peers = [r['body'] for r in rows if r['id'] != identity]
    quality = review(case, peers)
    st.json(quality)
    st.json(case)
    with st.expander('编辑候选 JSON'):
        text = st.text_area('场景内容', json.dumps(case, ensure_ascii=False, indent=2), height=300, key='ai_edit_' + identity + '_' + str(row['revision']))
        if st.button('保存新版本', disabled=row['status'] != 'PENDING' or not actor.strip()):
            try:
                edited = json.loads(text)
                if edited.get('case_id') != identity:
                    raise ValueError('用例ID不能修改')
                store.save(edited, actor, row['revision'])
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error(str(exc))
    adapter_name = 'V3.10确定性集成' if case.get('execution_adapter') == 'v310' else 'Legacy Mock'
    st.caption('以下为确定性适配器执行，与 V3.11 原 Agent 验收分别记录。')
    if st.button(f'独立执行已批准场景（{adapter_name}）', disabled=row['status'] != 'APPROVED'):
        with st.spinner('正在独立沙箱执行'):
            st.json(store.run(identity, row['revision']))
    with st.expander('执行记录与 Trace'):
        st.json([r for r in runs if r['case_id'] == identity])
    from web.scenario_live_desk import desk
    desk(store,row,actor)
