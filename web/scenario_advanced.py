"""Plain-language views over the existing scenario plans and measurements."""
from html import escape
from pathlib import Path

import streamlit as st

from target.scenario_plans import candidate, plans
from target.scenario_quality import coverage, model_comparison, quality


PLAN_COPY = {
    'railway_queries': ('铁路查询', '核对车站搜索、区间车次和指定车次的经停查询。', '检查查票功能或静态时刻表接入。'),
    'lifecycle': ('从建单到退改签', '核对库存、报价、建单、支付、部分退款、改签及退清后取消订单。', '回归验证多步订单业务。'),
    'hold_expiry': ('未付款订单超时', '推进演示时间，核对订单过期及占座释放。', '检查占座时限或库存回收。'),
    'cancel': ('取消未付款订单', '建单后取消，核对订单状态变为已取消。', '检查用户主动撤销订单。'),
    'amount_mismatch': ('拦截错误支付金额', '提交不符的支付金额，检查请求是否被拦截。', '检查支付金额校验。'),
    'invalid_parameters': ('拒绝缺少查询参数', '省略必要参数，检查查询是否返回参数错误。', '检查表单或工具参数校验。'),
    'no_match': ('查询无匹配车站', '搜索预设的不存在车站，核对返回零条记录。', '检查搜索无结果时的处理。'),
    'read_only_history': ('历史记录只读', '在历史查看状态尝试支付，检查是否被拦截且未产生交易。', '检查历史页面的写入限制。'),
    'payment_replay': ('防止重复支付', '重放已确认的支付操作，核对仍只有一笔交易。', '检查用户重复操作或重放请求。'),
    'feature_revoked': ('关闭功能后拦截确认', '关闭铁路模拟后尝试确认已有支付请求，检查是否被拦截。', '检查权限或功能开关变更后的旧请求。'),
    'proposal_expired': ('过期请求不能确认', '推进演示时间再确认建单，检查未创建订单。', '检查用户长时间未确认的情况。'),
    'full_refund': ('已付款订单全额退票', '完成模拟支付后发起整单退款，核对订单变为已取消。', '检查整单退款流程。'),
    'paid_reply': ('支付状态与回复一致', '支付后查询订单，检查回复中没有过时的待付款提示。', '检查助手是否反映已付款状态。'),
    'cross_owner': ('拦截他人访问订单', '以其他身份尝试确认请求和读取订单，核对访问均被拦截。', '检查跨会话或跨身份越权。'),
    'payment_failure': ('支付失败后释放库存', '在模拟失败场景中检查订单状态，并核对占座和已售数量。', '检查支付异常后的库存恢复。'),
    'conversation': ('连续两轮查票', '用两轮模拟对话核对查询工具收到的日期和车站，确认没有建单。', '检查多轮查询的参数传递。'),
}

RAILWAY_METRICS = (
    ('tools', '工具覆盖', '已实际调用且步骤验证成功的铁路工具，占已注册铁路工具的比例。'),
    ('workflows', '业务流程覆盖', '统计查询、建单、支付、退款、改签五类流程。退款项以「已付款订单全额退票」流程通过为依据。'),
    ('states', '订单状态覆盖', '在已验证步骤中观察到的已保存订单状态，占本批次规定状态的比例。'),
    ('security', '安全与权限', '已通过的预设越权、权限拦截和防重复操作检查。'),
    ('exceptions', '异常与恢复', '已通过的预设过期、支付失败和参数异常检查。此范围不含模型请求超时或截断恢复。'),
    ('trace', '执行证据', '拥有同一次运行的开始和结束记录的步骤。详细执行记录也称为 Trace。'),
)


def _help_card(intro, bullets, questions):
    items = ''.join(f'<li>{escape(item)}</li>' for item in bullets)
    answers = ''.join(f'<dt>{escape(question)}</dt><dd>{escape(answer)}</dd>' for question, answer in questions)
    st.html(f'''<details class="ta-advanced-help">
      <summary>这是什么？</summary>
      <div class="ta-advanced-help-body">
        <strong>这个功能有什么用？</strong>
        <p>{escape(intro)}</p><ul>{items}</ul><dl>{answers}</dl>
      </div>
    </details>''')


def _plan_name(identity):
    return PLAN_COPY.get(identity, (identity, '', ''))[0]


def _preset_panel(store):
    st.write('这里提供项目提前准备好的标准测试流程。你可以直接使用这些流程检查车次查询、库存查询以及其他业务功能是否正常，不需要自己从零编写测试内容。')
    _help_card(
        '预设测试流程相当于提前准备好的标准考试题。',
        ('验证已有业务功能', '重复执行相同流程', '检查代码变更是否引入问题', '对比不同版本的测试结果'),
        (('什么时候使用？', '想快速检查已有功能，或者想从现成的测试开始时使用。'),
         ('使用后会发生什么？', '系统把选中的流程载入下方候选列表，等待人工审核。'),
         ('怎样判断正常？', '载入成功时会显示待审核。审核、批准并执行后，查看执行结果和证据来判断功能。'),
         ('容易误解什么？', '这些流程由项目预先准备。载入只创建候选，测试结果要等实际执行后才能得到。')),
    )
    references = {plan['title']: plan for plan in plans()}
    selected = st.selectbox('选择测试流程', list(references), format_func=_plan_name, key='scenario_reference_plan')
    st.markdown('**测试流程说明**')
    if selected in PLAN_COPY:
        _, checks, use = PLAN_COPY[selected]
        st.write(checks)
        st.caption(use)
    else:
        st.caption('载入后可在候选列表查看此流程的具体检查项。')
    if st.button('载入为待审核测试', key='scenario_import_reference'):
        store.save(candidate(references[selected]), 'reference-plan-import')
        st.session_state['scenario_reference_loaded'] = _plan_name(selected)
        st.rerun()
    st.caption('载入后不会立即执行。请先检查并批准，再运行测试。执行使用独立测试数据库。')
    loaded = st.session_state.pop('scenario_reference_loaded', None)
    if loaded:
        st.success(f'已载入「{loaded}」，请到下方候选列表审核。')


def _metric_card(title, metric, description, *, available=True):
    numerator, denominator, value = (metric.get(key) for key in ('numerator', 'denominator', 'value'))
    count = ''
    meter = ''
    if not available:
        status = '尚无执行证据'
    elif denominator == 0:
        status = '不适用'
    elif (type(numerator) is not int or type(denominator) is not int or denominator < 1
          or not 0 <= numerator <= denominator or type(value) not in (int, float) or not 0 <= value <= 1):
        status = '未知'
    else:
        percent = f'{value:.1%}'
        if value < 1 and percent == '100.0%':
            percent = '接近 100%'
        count = f'<div class="ta-advanced-count"><strong>{numerator}/{denominator}</strong><span>{percent}</span></div>'
        meter = f'<progress value="{numerator}" max="{denominator}" aria-hidden="true"></progress>'
        status = '本项全部达到' if numerator == denominator else '部分达到' if numerator else '尚无符合项'
    return f'''<article class="ta-advanced-metric" aria-label="{escape(title)}">
      <h4>{escape(title)}</h4>{count}{meter}<p class="ta-advanced-status">{status}</p>
      <p>{escape(description)}</p>
    </article>'''


def _report_panel(store, rows, runs):
    st.write('这里可以查看测试实际检查了哪些功能、哪些测试已经执行、哪些项目还没有验证，以及每项测试是否有真实的执行记录作为依据。')
    _help_card(
        '这是一张执行后的成绩单，能看到通过多少，也能看到哪些地方还缺少证据。',
        ('查看工具、参数和业务流程的检查范围', '了解订单状态、权限和异常场景是否验证', '核对数据库相关结果和详细执行记录'),
        (('什么时候使用？', '执行测试后或准备验收时使用。'),
         ('使用后会看到什么？', '这里按原有执行记录展示覆盖情况、运行结果和证据。参数检查单独统计候选内容。'),
         ('怎样判断正常？', '核对关心的业务是否被覆盖，查看失败记录及对应的证据。下方候选列表可以筛选执行失败。'),
         ('容易误解什么？', '某项达到 100% 只表示该项统计范围已达到要求。这里的铁路覆盖来自本地隔离执行。')),
    )
    st.warning('覆盖率只代表已经检查的范围，不代表整个系统没有缺陷。即使某项达到 100%，也不意味着所有业务功能都已经通过验收。')
    bodies = [run['body'] for run in runs]
    metrics = quality(rows, runs)
    measured = coverage(bodies)
    has_railway_steps = any(body.get('mode') == 'deterministic_v310_integration' and not body.get('fault')
                            and body.get('steps') for body in bodies)
    st.markdown('**执行结果**')
    st.caption('运行通过统计来自当前候选库。铁路覆盖仅统计本地隔离测试，排除故障注入。在线模型的生成记录可在技术详情查看。')
    execution = _metric_card('运行通过', metrics.get('execution', {}),
                             '通过的运行次数，占当前候选库记录的全部独立运行次数。', available=bool(runs))
    cards = ''.join(_metric_card(title, measured.get(key, {}), description, available=has_railway_steps)
                    for key, title, description in RAILWAY_METRICS)
    st.html(f'<div class="ta-advanced-grid">{execution}{cards}</div>')
    st.markdown('**候选内容检查**')
    parameters = _metric_card('参数检查', metrics.get('parameters', {}),
                              '通过静态校验的已提供参数组合。此项排除依赖运行结果的引用，单独于执行覆盖统计。')
    st.html(f'<div class="ta-advanced-grid ta-advanced-parameters">{parameters}</div>')
    with st.expander('查看技术详情', key='scenario_report_details'):
        st.caption('原始分子、分母、定义和证据范围。候选检查、本地铁路执行和在线模型生成分别记录。')
        st.markdown('**候选和独立运行统计**')
        st.json(metrics, expanded=False)
        st.markdown('**本地铁路执行覆盖**')
        st.json(measured, expanded=False)
        st.markdown('**在线模型生成比较**')
        st.json(model_comparison(store.original_candidates(), store.generations()), expanded=False)


def advanced_tools(store, rows, runs):
    with st.container(key='scenario_advanced'):
        st.html(Path(__file__).with_suffix('.css'))
        st.subheader('高级测试工具')
        st.caption('这里提供预设测试流程和测试结果分析功能，适合需要进一步验证项目质量的用户。')
        with st.expander('预设测试流程　:gray-badge[高级功能]', key='scenario_presets', icon=':material/checklist:'):
            _preset_panel(store)
        with st.expander('测试覆盖情况与执行报告　:gray-badge[测试结果分析]', key='scenario_report', icon=':material/assessment:'):
            _report_panel(store, rows, runs)
