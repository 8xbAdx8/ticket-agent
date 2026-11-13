"""Trusted controls for the approved R2 run. No model requests on load."""
import json

import streamlit as st

from target.scenario_abc_budget import R2_ROOT
from target.scenario_live_agent import save
from target.scenario_r2_business import BusinessRun
from target.scenario_r2_live import R2Model
from target.scenario_workbench import Workbench


LABELS = {'QUERY': '执行批准的车次查询', 'PREPARE': '查询经停、库存和报价', 'CREATE': '让 Agent 生成建单提案',
          'PAY': '让 Agent 生成模拟支付提案', 'PARTIAL_REFUND': '让 Agent 生成部分退款提案',
          'CHANGE_QUOTE': '让 Agent 查询改签报价', 'CHANGE': '让 Agent 生成改签提案',
          'FINAL_REFUND': '让 Agent 生成最终退款提案'}


def business_desk(session, manifest, progress, offline, report_progress):
    run_id = manifest['run_id']
    workbench = Workbench.reopen(run_id, session.sid, root=R2_ROOT/'generated-cases')
    approval = json.loads((workbench.directory/'review.json').read_text(encoding='utf8'))
    st.subheader('原 Agent 业务验收')
    st.caption('审核人 test_user。订单和资金操作使用隔离的本地模拟业务。每个提案都需要你在页面上决定。')
    consent = st.checkbox('允许本轮调用原 Agent 与另一家模型 Judge', key='r2_consent_'+run_id)
    key = 'r2_business_'+run_id
    current = st.session_state.get(key)
    if current is None:
        try:
            current = BusinessRun.recover(workbench, R2Model(manifest['provider']), approval)
        except (OSError, ValueError) as exc:
            st.error('已有运行无法只读恢复 · ' + type(exc).__name__)
            return
        if current:
            st.session_state[key] = current
    if st.button('创建隔离 Agent 会话', disabled=current is not None or not consent or offline, key='r2_create_'+run_id):
        try:
            current = BusinessRun(workbench, R2Model(manifest['provider']), approval)
            save(current.agent.root/'approved-candidate.json', dict(approval=approval, mode=current.agent.mode))
            st.session_state[key] = current
        except (OSError, ValueError) as exc:
            st.error('隔离会话创建失败 · ' + type(exc).__name__)
            return
    if not current:
        return
    if current.frozen_approval != approval:
        st.error('批准记录已变化，本轮停止。')
        return
    st.caption(f"执行 ID {current.agent.id} · 剩余 Agent HTTP 最多 {max(0, current.remaining_http())}")
    if current.restored:
        st.info('已只读恢复原执行。可查看数据库、运行记录和封存评判。')
    stage = current.next_stage()
    if stage and st.button(LABELS[stage], disabled=not consent or offline, key=f'r2_{run_id}_{stage}'):
        try:
            current.perform(stage)
        except (OSError, ValueError) as exc:
            st.error('Agent 步骤未完成 · ' + type(exc).__name__)
        st.rerun()
    for item in (() if current.restored else current.agent.pending()):
        preview = current.agent.decision_preview(item['proposal_id'])
        st.write(f"{preview['action']} · {preview['proposal_id']}")
        st.json(preview['payload'], expanded=False)
        choice = st.selectbox('本地模拟交易决定', ['暂不操作','确认','拒绝'], key='r2_decision_'+preview['proposal_id'])
        if st.button('提交该决定', key='r2_submit_'+preview['proposal_id'], disabled=(choice == '暂不操作' or
                     not consent or current.failed or preview['action'] != current.confirm_action)):
            try:
                row = current.confirm(preview, choice == '确认')
                save(R2_ROOT/'approval'/f"{run_id}-{preview['proposal_id']}.json",
                     dict(run_id=run_id, actor=approval['actor'], interaction=approval.get('interaction'),
                          proposal_id=preview['proposal_id'], action=preview['action'], payload_sha256=preview['payload_sha256'],
                          approved=choice == '确认', database_receipt_verified=row.get('database_receipt_verified')))
            except (OSError, ValueError) as exc:
                st.error('确认未完成 · ' + type(exc).__name__)
            st.rerun()
    _evidence(current)
    if current.agent.rows and not current.agent.pending() and st.button('封存并交叉评判',
            disabled=not consent or offline, key='r2_judge_'+run_id):
        try:
            workbench.execute_approved(current.model, runner=current.evidence,
                                        progress=lambda row: report_progress(progress, row))
        except (OSError, ValueError) as exc:
            st.error('本轮尚无法封存 · ' + type(exc).__name__)
        st.rerun()


def _evidence(current):
    from target.v39.read_model import status_text
    from web.order_state_evidence import rendered
    state = current.agent.read()
    session = current.agent.session
    for order in state['tables']['orders']:
        holds = {item['hold_id']: item for item in state['tables']['holds']}
        hold = holds.get(order['hold_id'])
        tx = [item for item in state['tables']['transactions'] if item['order_id'] == order['order_id']]
        displayed = dict(order, hold_status=hold['status'] if hold else None, hold=hold, transactions=tx)
        text = status_text(displayed)
        st.info(text)
        trace = next((row['trace_id'] for row in reversed(current.agent.rows) if row.get('trace_id')), None)
        rendered(session, text, order['order_id'], trace)
    st.caption('SQLite Oracle SHA-256 ' + state['state_sha256'])
    with st.expander('数据库核验和原始执行引用'):
        st.json({name: state['tables'][name] for name in ('orders','order_items','holds','transactions','refund_requests','change_requests')}, expanded=False)
        st.json([{'步骤': row['kind'], '证据': row.get('trace_id'), '任务': row['task_status'],
                  '不变量': row['invariant_status'], '错误': row['error']} for row in current.agent.rows], expanded=False)
