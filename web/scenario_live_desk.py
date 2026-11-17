"""Opt-in original-Agent experiment desk; no request on load or rerun."""
import json
import os
from pathlib import Path
import streamlit as st


def desk(store,case_row,actor):
    from target.scenario_live_agent import AgentRun,save
    from target.scenario_live_budget import LiveBatch
    from target.v39.registry import NAMES
    with st.expander('V3.11 原 Agent 业务验收',expanded=False):
        st.caption('独立实验：自然语言 → 当前模型 → 原 Agent → 工具 → 模拟业务数据库。不会计入正式成绩；交易仍需人工确认。')
        st.caption('此处按操作者发送前指定的断言检查附加验收轮次，不等于执行了候选中的全部 DSL 判据。候选批准、生成质量和 Agent 业务结果分别记录。')
        configured=os.getenv('TICKET_V311_BATCH_ROOT','').strip()
        if not configured:
            st.info('尚未配置已授权的 V3.11 批次。旧离线执行功能可继续使用。')
            return
        try:
            batch=LiveBatch(Path(configured));budget=batch.status()
        except (ValueError,OSError) as exc:
            st.error('验收账本不可用：'+type(exc).__name__)
            return
        st.write(f"本批次已请求 {budget['http_requests']}/50；当前阶段 {budget['phase']['phase']} 上限 {budget['phase']['http_limit']}。")
        st.caption(f"DeepSeek {budget['providers']['deepseek']} · Qwen {budget['providers']['bailian']}；已知 Token {budget['known_observed_tokens']}，未决请求 {len(budget['unresolved_request_ids'])}，费用 UNKNOWN。累计 Token 无硬上限，320000 预警，输出不超过4096并服从Provider更低限制。")
        saved=sorted((batch.root/'cases').glob('*/run-*.json'))
        latest={p.parent.name:p for p in saved}
        if latest:
            with st.expander('已保存的验收历史（只读）'):
                identity=st.selectbox('历史验收会话',list(latest),key='v311_saved_execution')
                history=json.loads(latest[identity].read_text('utf8'))
                st.caption(history['mode']+'；不会恢复确认密钥或重新执行交易。')
                st.json([dict(index=r['index'],kind=r['kind'],passed=r['passed'],task=r['task_status'],error=r['error'],trace_id=r.get('trace_id')) for r in history['rows']])
                if history['rows']:
                    st.json(history['rows'][-1]['after'])
        provider=st.selectbox('业务执行模型',['deepseek','bailian'],key='v311_provider')
        consent=st.checkbox('我授权本轮模型费用及隔离模拟业务验收',key='v311_consent')
        frozen=dict(case_id=case_row['id'],revision=case_row['revision'],body=case_row['body'])
        key='v311_run_'+case_row['id']
        run=st.session_state.get(key)
        approved=case_row['status']=='APPROVED'
        if st.button('创建独立 Agent 验收会话',key='v311_create',disabled=not approved or not actor.strip() or not consent or run is not None):
            try:
                run=AgentRun(batch.root,provider)
                run.candidate_binding=frozen
                save(run.root/'approved-candidate.json',dict(candidate=frozen,operator=actor,mode=run.mode))
                st.session_state[key]=run
            except Exception as exc:st.error('无法创建隔离会话：'+type(exc).__name__)
        if not run:
            st.caption('先批准候选、填写审核人并授权，再创建会话。创建会话不调用模型。')
            return
        st.write('执行模式：'+run.mode+'；会话 '+run.session.sid)
        if run.mode!='live_agent':st.warning('当前是 SDK 替身验收，不是真实模型验证。')
        current=approved and run.candidate_binding==frozen and run.provider==provider
        if not current:st.warning('候选版本、审批或模型已变化，本会话禁止继续执行。')
        if run.halted:st.error('验证发现不一致，已停止本会话。请先审查数据库及原始记录。')
        turns=case_row['body'].get('conversation',[])
        message=st.text_area('本轮自然语言需求',value=turns[0] if turns else '',height=120,key='v311_message_'+case_row['id'])
        required=st.multiselect('本轮必须成功执行的工具（发送前冻结）',list(NAMES),default=[n for n in case_row['body'].get('expected_tool_calls',[]) if n in NAMES],key='v311_expected_'+case_row['id'])
        readonly=st.checkbox('本轮不得改变订单、乘客和资金交易',value=True,key='v311_readonly_'+case_row['id'])
        if st.button('发送给原 Agent',key='v311_send',disabled=not current or not consent or run.halted or not message.strip() or not required):
            try:
                spec=dict(required_tools=required)
                if readonly:spec['unchanged']=['orders','order_items','transactions']
                with st.spinner('模型执行中；交易不会自动确认'):
                    run.turn(message,expectations=spec)
            except Exception as exc:st.error('本轮未完成：'+type(exc).__name__)
        pending=run.pending()
        if pending:
            st.subheader('模拟业务确认')
            for proposal in pending:
                preview=run.decision_preview(proposal['proposal_id'])
                st.write(preview['action'])
                st.json(preview['payload'])
                st.caption('确认仅执行上述合成乘客的本地模拟操作；无真实支付、出票或铁路请求。')
                decision=st.selectbox('用户决定',['暂不操作','确认','拒绝'],key='v311_decision_'+proposal['proposal_id'])
                if st.button('提交该决定',key='v311_confirm_'+proposal['proposal_id'],disabled=not current or not consent or run.halted or decision=='暂不操作'):
                    try:run.confirm(preview,decision=='确认',actor='test_user')
                    except Exception as exc:st.error('确认未完成：'+type(exc).__name__)
        if run.rows:
            last=run.rows[-1]
            overall='PASS' if last['passed'] else 'NOT_SCORED' if last['task_status']=='NOT_SCORED' and not last['error'] and last['invariant_status']=='PASS' else 'FAIL'
            st.write(f"最新检查：任务 {last['task_status']}；不变量 {last['invariant_status']}；错误 {last['error'] or '无'}；整轮 {overall}。")
            if last.get('original_model_reply'):st.markdown(last['original_model_reply'])
        with st.expander('数据库状态（本次只读快照）'):
            state=run.read();st.caption('状态 SHA-256 '+state['state_sha256'])
            st.json({k:state['tables'][k] for k in ('orders','order_items','transactions','refund_requests','change_requests','holds')})
        with st.expander('原始 Trace、断言与历史轮次'):
            st.json([dict(index=r['index'],kind=r['kind'],passed=r['passed'],task=r['task_status'],invariants=r['invariant_status'],error=r['error'],trace_id=r.get('trace_id')) for r in run.rows])
            if run.rows:
                index=st.selectbox('验收轮次',list(range(len(run.rows))),key='v311_history_'+case_row['id'])
                st.json(run.rows[index])
        st.caption('持久证据：'+str(run.root)+'。刷新后本进程内会话保留；进程重启只能只读审查原件，不恢复确认密钥、不自动重试。')
