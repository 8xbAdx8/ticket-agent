"""Read-only developer views, sourced from the running code and saved audits."""
import hashlib
import re
import streamlit as st

from target.agent import SYSTEM_PROMPT
from target.tools import TOOLS
from target.write_authorization import WRITE_TOOLS
from web.design import header


def developer_page(sessions,compact=False):
    if not compact:header('Agent 开发者端', '查看源码配置和已有运行证据；本页不会发起模型请求。', '只读')
    tabs=st.tabs(['提示词设计','工具配置','权限矩阵','设计决策'] if compact else
                 ['提示词设计','工具配置','权限矩阵','设计决策','工作流编排','调试与 Trace'])
    prompt,tools,permissions,decisions=tabs[:4]
    flow=st.container() if compact else tabs[4]
    debug=st.container() if compact else tabs[5]
    with prompt:
        st.caption('基础提示词来自 target/agent.py；只读模式可能使用不同提示词，运行时还会追加日期和上下文。')
        st.write('基础提示词 SHA-256：', hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest())
        rules = re.findall(r'(?m)^\d+\..*$', SYSTEM_PROMPT)
        st.write('实际识别规则数：', len(rules))
        for rule in rules:
            st.write(rule)
        with st.expander('完整基础提示词'):
            st.code(SYSTEM_PROMPT, language=None)
        from target.deepseek_runtime import READ_ONLY_PROMPT
        with st.expander('只读 Live 模式提示词'):
            st.caption('来源 target/deepseek_runtime.py；是否生效取决于实际工具集和运行配置。')
            st.code(READ_ONLY_PROMPT, language=None)
            for i,line in enumerate(READ_ONLY_PROMPT.splitlines(),1):
                st.json({'rule_id':f'READONLY-{i:02}','text':line,'source':'target/deepseek_runtime.py:READ_ONLY_PROMPT',
                         'hash':hashlib.sha256(line.encode()).hexdigest(),'verification':'待独立验证',
                         'related_tests':'tests/test_deepseek_readonly_quality.py（模块级关联，未自动推断逐条通过）'})
        st.caption('规则目的、缺陷关联及独立验证状态尚未逐条建立证据映射。')
        from web.run_evidence import rule_rows
        from web.evidence import cases,read_json,B_SOURCE,batch
        historical=batch()
        for row in rule_rows(SYSTEM_PROMPT,cases(),read_json(B_SOURCE/'manifest.json')):
            with st.expander(row['rule_id']+' · 测试证据关联'):
                st.caption('规则来源 target/agent.py；版本为上方模板哈希。历史关联不代表当前通过。')
                st.json(row)
                st.json({'historical_source':historical['source'],'historical_code_sha':historical['commit'],
                         'results':[r for r in historical['rows'] if r['id'] in row['case_ids']]},expanded=False)
    with flow:
        if not compact:
            st.markdown('用户输入 → Agent → 模型/规则选择 → 参数与权限校验 → 工具执行 → 结果回传 → 后续调用或回复')
            st.caption('这是静态架构说明；具体分支与执行结果请查看“调试与 Trace”。不展示或推测内部思维链。')
    with tools:
        for entry in TOOLS:
            spec=entry['function']
            with st.expander(spec['name']+' · '+spec.get('description','')):
                st.json(spec['parameters'])
        st.caption('Schema 来自 target/tools.py；返回内容以各次实际工具结果为准。')
    with permissions:
        st.caption('写操作分类来自 target/write_authorization.py；具体授权还受会话模式、用户确认和业务约束影响。')
        st.table([{'工具': item['function']['name'], '类别': '模拟状态变更' if item['function']['name'] in WRITE_TOOLS else '查询',
                   '当前会话可用性': '查看已创建会话的实际工具集'} for item in TOOLS])
        if sessions:
            current=sessions[-1]
            engine=getattr(getattr(current,'agent',None),'langchain_engine',None)
            if engine is not None:
                st.write('最近已创建 LangChain 会话实际工具：', ', '.join(engine.tool_names))
            else:
                st.info('最近会话没有已创建的 LangChain 执行器；未推测其工具集。')
    with debug:
        if not compact:
            from web.trace_view import trace_page
            trace_page([s.trace_dir for s in sessions])
    with decisions:
        st.markdown('**模拟操作确认**：页面在模型提出模拟写操作后提供用户确认；具体行为和限制见 `web/runtime.py`、`target/langchain_agent.py`。')
        st.markdown('**历史与实时分离**：本地 Trace 保留实际执行记录；历史结果不代表本次运行。')
        st.caption('开发历史和验证范围见 docs/handoff/v36；逐项决策背景与证据映射待补充。')
