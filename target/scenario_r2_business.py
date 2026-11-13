"""Keep one original Agent and its SQLite evidence across trusted UI decisions."""
import json
from types import SimpleNamespace

from target.consistency_audit import audit_conversation
from target.scenario_abc_budget import R2_ROOT
from target.scenario_abc_live import PILOT_ARGS
from target.scenario_live_agent import AgentRun
from target.scenario_v310 import assert_value
from target.scenario_workbench import Workbench, _verified_nodes
from target.scenario_workbench_evidence import private_evidence, snapshot_conversation


class BusinessRun:
    def __init__(self, workbench, model, approval):
        self.case, self.plan = self._approved_case(workbench, model, approval)
        self.workbench = workbench
        self.run_id = workbench.run_id
        self.model = model
        self.agent = AgentRun(model.batch.root, model.provider, batch=model.batch, evidence_root=R2_ROOT)
        self.frozen_approval = approval
        self.confirm_action = None
        self.failed = False
        self.restored = False

    @staticmethod
    def _approved_case(workbench, model, approval):
        current = Workbench.reopen(workbench.run_id, workbench.manifest['session_id'], root=workbench.directory.parent)
        receipt, selected = current.approved_review(model)
        if model.source != 'r2_live_model' or receipt != approval or len(selected) != 1:
            raise ValueError('R2_TRUSTED_APPROVAL_REQUIRED')
        return selected[0]

    @classmethod
    def recover(cls, workbench, model, approval):
        from target.scenario_business_oracle import snapshot
        from web.session_store import restore_session
        case, plan = cls._approved_case(workbench, model, approval)
        matches = []
        for path in (R2_ROOT/'agent-executions').glob('*/approved-candidate.json'):
            item = json.loads(path.read_text(encoding='utf8'))
            if item.get('approval') == approval and item.get('mode') == 'live_agent':
                matches.append(path.parent)
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('R2_AMBIGUOUS_EXECUTION')
        area = matches[0]
        files = sorted(area.glob('run-*.json'))
        record = json.loads(files[-1].read_text(encoding='utf8'))
        if (record.get('execution_id') != area.name or record.get('provider') != model.provider
                or record.get('mode') != 'live_agent'):
            raise ValueError('R2_EXECUTION_BINDING_MISMATCH')
        database = area/'simulation.sqlite'
        rows = record['rows']
        if rows and snapshot(database)['state_sha256'] != rows[-1]['after']['state_sha256']:
            raise ValueError('R2_EXECUTION_DATABASE_CHANGED')
        session = restore_session(area/'conversation', expected_sid=record['session_id'])
        instance = cls.__new__(cls)
        instance.case, instance.plan = case, plan
        instance.workbench = workbench
        instance.run_id, instance.model = workbench.run_id, model
        instance.frozen_approval, instance.confirm_action = approval, None
        instance.failed, instance.restored = False, True
        instance.agent = SimpleNamespace(id=area.name, root=area, session=session, rows=rows, halted=True,
            read=lambda: snapshot(database),
            pending=lambda: [row for row in snapshot(database)['tables']['proposals'] if row['state'] == 'PENDING'])
        return instance

    def remaining_http(self):
        rows = self.model.batch.ledger()
        return min(8-sum(row['run_id'] == self.run_id for row in rows),
                   40-len(rows), 20-sum(row['provider'] == self.model.provider for row in rows))

    def _turn(self, message, expectations):
        if self.failed or self.agent.halted or self.remaining_http() < 2:
            raise ValueError('R2_AGENT_STOPPED_OR_RUN_BUDGET_LOW')
        self._approved_case(self.workbench, self.model, self.frozen_approval)
        with self.model.batch.scope(self.run_id, self.model.provider, 'agent', scenario_id=self.case['case_id'],
                                    execution_id=self.agent.id, evidence_root=R2_ROOT):
            row = self.agent.turn(message, expectations=expectations)
        if not row['passed']:
            self.failed = True
        return row

    def query(self):
        if self.agent.rows or len(self.plan['integration_steps']) != 1 or self.plan['integration_steps'][0]['kind'] != 'chat':
            raise ValueError('R2_INVALID_INITIAL_QUERY')
        return self._turn(self.plan['integration_steps'][0]['message'],
                          dict(required_tools=['railway_query_trips'], args={'railway_query_trips': PILOT_ARGS},
                               unchanged=['orders', 'transactions', 'holds']))

    def _trip(self, current=None):
        for event in reversed(self.agent.rows[0]['executed_tools']):
            if event.get('tool') == 'railway_query_trips' and event.get('ok'):
                trips = event.get('result', {}).get('data', [])
                for trip in trips:
                    if trip.get('trip_id') and trip['trip_id'] != current:
                        return trip['trip_id']
        raise ValueError('R2_CURRENT_TRACE_TRIP_REQUIRED')

    def next_stage(self):
        if self.restored or self.failed or self.agent.halted or self.agent.pending() or self.remaining_http() < 2:
            return None
        if not self.agent.rows:
            return 'QUERY'
        db = self.agent.read()['tables']
        orders = db['orders']
        if not orders:
            return 'CREATE' if db['quotes'] else 'PREPARE'
        order = orders[0]
        if order['order_status'] == 'PENDING_PAYMENT':
            return 'PAY'
        if order['order_status'] == 'PAID':
            if not order['refunded_total_fen']:
                return 'PARTIAL_REFUND'
            return 'CHANGE' if any(q['trip_id'] != order['trip_id'] for q in db['quotes']) else 'CHANGE_QUOTE'
        return 'FINAL_REFUND' if order['order_status'] == 'CHANGED' else None

    def perform(self, stage):
        if stage != self.next_stage():
            raise ValueError('R2_CURRENT_STAGE_REQUIRED')
        if stage == 'QUERY':
            return self.query()
        db = self.agent.read()['tables']
        order = db['orders'][0] if db['orders'] else {}
        oid = order.get('order_id')
        actions = {'CREATE': 'CREATE_ORDER', 'PAY': 'PAY', 'PARTIAL_REFUND': 'REFUND',
                   'CHANGE': 'CHANGE', 'FINAL_REFUND': 'REFUND'}
        if stage in ('PREPARE', 'CHANGE_QUOTE'):
            trip = self._trip(order.get('trip_id'))
            head = '查该车次经停站及二等座模拟库存，并' if stage == 'PREPARE' else '仅'
            message = (f'{head}为 trip_id={trip}、2026-11-05、AOH 到 HGH、二等座 '
                       f'{2 if stage == "PREPARE" else 1} 名合成乘客生成模拟报价。禁止建单、支付和改签。')
            tools = ['railway_trip_stops', 'railway_check_inventory', 'railway_quote_fare'] if stage == 'PREPARE' else ['railway_quote_fare']
        elif stage == 'CREATE':
            quote = db['quotes'][-1]['quote_id']
            message = f'使用报价 {quote} 为两名合成乘客合成甲、合成乙生成建单提案。联系人使用当前登录手机号。等待我确认，禁止自动建单。'
            tools = ['railway_create_order']
        elif stage == 'PAY':
            message = f"只为当前订单 {oid} 生成模拟支付提案，金额 {order['total_fen']} 分，等待我确认。"
            tools = ['railway_pay_order']
        elif stage == 'PARTIAL_REFUND':
            item = next(x for x in db['order_items'] if x['order_id'] == oid and x['item_status'] == 'ACTIVE')
            message = f"只为订单 {oid} 的明细 {item['item_id']} 生成部分退款提案，scope=ITEMS，等待我确认。"
            tools = ['railway_refund_order']
        elif stage == 'CHANGE':
            target = next(q for q in reversed(db['quotes']) if q['trip_id'] != order['trip_id'])
            message = (f"为订单 {oid} 生成改签提案：target_quote_id={target['quote_id']}，target_trip_id={target['trip_id']}，"
                       'target_service_date=2026-11-05，target_origin_stop_id=AOH，target_destination_stop_id=HGH，target_seat_class=SECOND。等待我确认。')
            tools = ['railway_change_order']
        else:
            message = f'为订单 {oid} 剩余有效乘客生成模拟退款提案，scope=FULL，等待我确认。'
            tools = ['railway_refund_order']
        row = self._turn(message, dict(required_tools=tools, unchanged=['orders', 'order_items', 'transactions', 'holds']))
        self.confirm_action = actions.get(stage) if row['passed'] else None
        return row

    def confirm(self, preview, approved):
        if self.failed or not self.confirm_action or preview['action'] != self.confirm_action:
            raise ValueError('R2_CURRENT_ACTION_REQUIRED')
        self._approved_case(self.workbench, self.model, self.frozen_approval)
        row = self.agent.confirm(preview, approved, actor='test_user')
        self.confirm_action = None
        if not row['passed'] or not approved:
            self.failed = True
        return row

    def evidence(self, case, plan, directory, _engine):
        from web.evidence import session_execution_events
        if case['case_id'] != self.case['case_id'] or case['run_id'] != self.run_id or not self.agent.rows:
            raise ValueError('R2_APPROVED_EXECUTION_NOT_FOUND')
        events, _ = session_execution_events(self.agent.session.trace_dir, self.agent.session.sid)
        rows = self.agent.rows
        steps, tool_evidence = [], []
        for index, row in enumerate(rows):
            result = row['result'] or {}
            traces = [call for turn in result.get('steps', []) for call in turn.get('calls', []) if call.get('tool', '').startswith('railway_')]
            output = dict(reply=result.get('reply', ''), public_result=result, queries=traces)
            db = row['after']['tables']
            state = dict(orders=db['orders'], holds=db['holds'], transactions=db['transactions'],
                         refunds=db['refund_requests'], changes=db['change_requests'])
            metrics = dict(order_count=len(db['orders']), transaction_count=len(db['transactions']), hold_count=len(db['holds']))
            context = dict(result=output, state=state, metrics=metrics, db={'v39_'+name: data for name, data in db.items()})
            checks = [assert_value(check, context, {}) for check in plan['integration_steps'][0]['checks']] if index == 0 else []
            checks += [dict(path='oracle.'+check['rule'], ok=check['passed']) for check in row['checks'] + (row['task_checks'] or [])]
            steps.append(dict(kind='chat' if row['kind'] == 'agent_turn' else 'confirmation', index=index,
                              result=output, trace_id=row.get('trace_id'), checks=checks, state=state, db_metrics=metrics))
            tool_evidence.extend(row.get('executed_tools', []))
        invoked = any(row.get('model_called') and row.get('http_requests') for row in rows)
        refs = [f"run_events.jsonl#{event['event_id']}" for event in events]
        objective = 'indeterminate' if not invoked else 'passed' if all(check['ok'] for check in steps[0]['checks']) and all(row['passed'] for row in rows) else 'failed'
        observed = []
        if self.agent.session.history:
            from target.scenario_live_agent import save
            subject = snapshot_conversation(self.agent.session)
            save(self.agent.root/'subject-conversation.json', subject)
            observed = audit_conversation(subject)
            for assessment in observed:
                for layer in assessment['layers'].values():
                    for observation in layer:
                        observation['ref'] = observation['ref'].replace(
                            'conversation.json#', f'agent-executions/{self.agent.id}/subject-conversation.json#', 1)
        return private_evidence(dict(run_id=self.run_id, case_id=case['case_id'], execution_id=self.agent.id,
            subject_session_id=self.agent.session.sid, ref=f"executions/{case['case_id']}.json",
            trace_refs=refs, agent_trace_refs=refs, agent_invoked=invoked, executed=invoked, objective_status=objective,
            verified_nodes=_verified_nodes(case['covered_nodes'], {'steps':steps}), mutation_status='not_run',
            mode='live_agent', engine='langchain', steps=steps, retrieval_evidence=[], tool_evidence=tool_evidence,
            oracle_ref=f'agent-executions/{self.agent.id}/run-{len(rows):03d}.json',
            oracle_evidence=dict(state_sha256=rows[-1]['after']['state_sha256'], checks=rows[-1]['checks']),
            order_observations=observed, metrics=dict(tool_times=[]))), events
