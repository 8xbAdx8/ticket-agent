"""Examples for the existing scenario generation form."""
from html import escape
from pathlib import Path

import streamlit as st


OBJECTIVE_PLACEHOLDER = (
    '例如：生成一个测试场景，验证用户查询 2026-11-05 上海虹桥到杭州东的高铁车次后，'
    '能够准确选择 G7331，查询完整经停站，并校验车次信息和经停站数据是否正确。'
)
CONSTRAINTS_PLACEHOLDER = (
    '例如：仅允许使用已注册工具，必须使用真实输出字段和路径，不得编造测试数据；'
    '所有业务断言必须有实际工具执行结果作为依据。'
)
OBJECTIVE_STEPS = (
    '用 railway_query_trips 查询 2026-11-05 上海虹桥（AOH）至杭州东（HGH）的高铁车次。',
    '设置 train_no 为 G7331，并核对选中记录的 trip_short_name 等于 G7331；不能直接把第一条记录当作目标车次。',
    '从已核对的同一条记录取 trip_id，调用 railway_trip_stops 查询同日的完整经停站。',
    '按真实返回结构，从 result.data.stops 提取经停列表。',
    '校验车次编号、全程经停站数及关键站点。',
    '实际结果与预期不一致时，测试必须报告失败。',
)
CONSTRAINTS = (
    '仅允许使用项目已注册的工具。',
    '参数须符合实际工具 Schema。',
    '查询经停站时，使用 railway_trip_stops 的真实返回结构。',
    '经停列表使用实际路径 result.data.stops。',
    '指定 G7331 时，必须用 train_no 精确筛选。',
    '核对选中记录的 trip_short_name，不能默认取第一条。',
    '不得编造经停站数、车站名称或业务状态。',
    '所有断言须能从实际工具结果取得证据。',
    '使用 flag 时，在步骤顶层提供布尔字段 enabled（true 或 false）。',
    '结构或语义校验未通过的候选不得直接批准执行。',
)


def _example_card(key, title, preview, lines, *, intro=''):
    items = ''.join(f'<li>{escape(line)}</li>' for line in lines)
    list_tag = 'ol' if intro else 'ul'
    introduction = f'<p>{escape(intro)}</p>' if intro else ''
    example = [intro] if intro else []
    example.extend(f'{index}. {line}' if intro else f'- {line}' for index, line in enumerate(lines, 1))
    text = escape('\n'.join(example), quote=True)
    st.html(f'''<section class="ta-scenario-example" aria-label="{title}"
                        data-scenario-target="{key}" data-scenario-example="{text}">
        <details>
            <summary><span class="ta-scenario-example-label"><strong>{title}</strong><span>{preview}</span></span></summary>
            <div class="ta-scenario-example-body">{introduction}<{list_tag}>{items}</{list_tag}></div>
        </details>
        <div class="ta-scenario-example-actions">
            <button type="button" data-scenario-action="fill">填入示例</button>
            <button type="button" data-scenario-action="clear">清空</button>
        </div>
    </section>''')


def objective_input():
    key = 'ai_scenario_objective'
    value = st.text_area('测试目标', key=key, height=120, max_chars=4000, placeholder=OBJECTIVE_PLACEHOLDER)
    _example_card(key, '示例目标', '查询 G7331 并校验全程经停站', OBJECTIVE_STEPS,
                  intro='验证铁路车次查询及经停站数据的正确性：')
    return value


def constraints_input():
    key = 'ai_scenario_constraints'
    value = st.text_area('高级生成约束', key=key, max_chars=2000, placeholder=CONSTRAINTS_PLACEHOLDER)
    _example_card(key, '示例约束', '限定工具、返回路径和断言证据', CONSTRAINTS)
    return value


def style_examples():
    st.html(Path(__file__).with_suffix('.css'))
