"""Run the authorized pilot over the existing guarded Provider and original Agent."""
from contextlib import contextmanager
import json
import os
import time
from unittest.mock import patch

from target import p2_generator
from target.api_config import model_config
from target.deepseek_runtime import Settings
from target.scenario_abc_budget import IntegrationBatch
from target.scenario_live_agent import AgentRun
from target.scenario_v310 import assert_value
from target.scenario_workbench import ModelReply, _verified_nodes
from target.scenario_workbench_evidence import private_evidence, retrieval_documents


PILOT_QUERY = '查询 2026-11-05 上海虹桥（AOH）到杭州东（HGH）的高铁车次。'
PILOT_ARGS = dict(service_date='2026-11-05', origin_stop_id='AOH', destination_stop_id='HGH')


@contextmanager
def configured_provider(provider):
    import config
    cfg = model_config(provider, active=os.getenv('AGENT_PROVIDER') == provider)
    if not cfg['configured']:
        raise ValueError('ABC_PROVIDER_NOT_CONFIGURED')
    with patch.multiple(config, PROVIDER=provider, MODEL_NAME=cfg['model'], BASE_URL=cfg['base_url'],
                        API_KEY=os.environ[cfg['key_env']].strip()):
        from target import bailian_runtime, deepseek_runtime
        (deepseek_runtime if provider == 'deepseek' else bailian_runtime).validate_configuration()
        yield cfg['model']


class PilotModel:
    source = 'abc_live_model'

    def __init__(self, provider, *, batch=None, evidence_root=None):
        self.provider = provider
        self.batch = batch if batch is not None else IntegrationBatch()
        self.evidence_root = evidence_root if evidence_root is not None else self.batch.root

    def provider_for(self, stage):
        return self.provider

    def pilot_marker(self):
        return self.evidence_root/f'pilot-{self.provider}.json'

    @staticmethod
    def prepare_prompt(system, user, step):
        if step != 'generate':
            return system, user
        checks = [dict(path='result.queries.0.tool', op='eq', value='railway_query_trips')]
        checks.extend(dict(path='result.queries.0.args.'+key, op='eq', value=value) for key, value in PILOT_ARGS.items())
        checks.append(dict(path='metrics.order_count', op='eq', value=0))
        example = dict(title='核验车次查询参数', objective='核验查询区间与日期', difficulty='easy', risk_level='low',
                       turns=[PILOT_QUERY], execution_adapter='v310', fixture_scenario='default',
                       dimension='工具调用', source_turn_ids=['turn-001'], covered_nodes=['工具选择', '参数构造'],
                       integration_steps=[dict(kind='chat', message=PILOT_QUERY, checks=checks)],
                       expected_tool_calls=[], expected_state_changes=[], expect={})
        return (system + '\n只生成一条只读 Pilot 候选，保持以下字段和 JSON 类型完整。'
                'turns 是字符串数组，chat 步骤必须有 message 和非空 checks。禁止生成交易或故障注入。'
                + json.dumps(dict(scenarios=[example]), ensure_ascii=False), user)

    def __call__(self, system, user, *, directory, run_id, step):
        from target.diagnostics import redact_credentials
        if os.getenv('TICKET_WEB_OFFLINE_ONLY') == '1':
            raise ValueError('ABC_OFFLINE_MODE')
        stage = 'generate' if step == 'generate' else 'judge'
        if stage == 'generate':
            with self.pilot_marker().open('x', encoding='utf8') as stream:
                json.dump(dict(run_id=run_id, provider=self.provider), stream)
        case_id = None if stage == 'generate' else step.removeprefix('judge-').removesuffix('-revision-2')
        execution_id = None
        if case_id:
            execution = json.loads((directory/'executions'/f'{case_id}.json').read_text(encoding='utf8'))
            execution_id = execution.get('execution_id')
        provider = self.provider_for(stage)
        with self.batch.scope(run_id, provider, stage, scenario_id=case_id, execution_id=execution_id,
                              evidence_root=self.evidence_root):
            with configured_provider(provider) as model:
                started = time.monotonic()
                raw, usage, ids, events = p2_generator.call(
                    provider, Settings(max_output_tokens=4096 if stage == 'generate' else 2048,
                                            max_model_calls=1, timeout=45, max_payload_bytes=64000),
                    system, user, run_id=run_id, model_step=step,
                )
        # Persist the effective provider prompt, including the fixed Pilot constraints.
        path = self.evidence_root/'prompts'/f'{run_id}-{step}.json'
        with path.open('x', encoding='utf8') as stream:
            import hashlib
            json.dump(redact_credentials(dict(run_id=run_id, step=step, system=system, user=user, events=events,
                      provider=provider, model=model, prompt_sha256=hashlib.sha256((system+'\n'+user).encode('utf8')).hexdigest(),
                      request_ids=ids, token_usage=usage)),
                      stream, ensure_ascii=False)
        if len(ids) != 1 or not isinstance(raw, str) or not any(
                row.get('event') == 'http_response' and row.get('request_id') == ids[0]
                and 200 <= row.get('http_status', 0) < 300 for row in events):
            raise ValueError('ABC_MODEL_RESPONSE_NOT_VERIFIED')
        return ModelReply(raw, model, ids[0], usage, round((time.monotonic()-started)*1000, 2))

    def runner(self, case, plan, directory, _engine):
        if case.get('mutation') or len(plan['integration_steps']) != 1 or plan['integration_steps'][0]['kind'] != 'chat':
            raise ValueError('ABC_PILOT_REQUIRES_SINGLE_READ_ONLY_CHAT')
        from web.evidence import session_execution_events
        step = plan['integration_steps'][0]
        agent = AgentRun(self.batch.root, self.provider, batch=self.batch, evidence_root=self.evidence_root)
        with self.batch.scope(case['run_id'], self.provider, 'agent', scenario_id=case['case_id'], execution_id=agent.id,
                              evidence_root=self.evidence_root):
            row = agent.turn(step['message'], expectations=dict(required_tools=['railway_query_trips'],
                             args={'railway_query_trips': PILOT_ARGS}, unchanged=['orders', 'transactions']))
        events, _ = session_execution_events(agent.session.trace_dir, agent.session.sid)
        events = [event for event in events if event.get('run_id') == row['trace_id']]
        invoked = bool(row['http_requests'] and row['model_called'] and any(event.get('event_type') == 'agent_start' for event in events))
        result = row['result']
        output = dict(reply=result.get('reply', ''), public_result=result,
                      queries=[call for turn in result.get('steps', []) for call in turn.get('calls', [])
                               if call.get('tool', '').startswith('railway_')])
        db = row['after']['tables']
        metrics = dict(order_count=len(db['orders']), transaction_count=len(db['transactions']),
                       hold_count=len(db['holds']), foreign_keys_ok=not row['after']['foreign_keys'])
        state = dict(orders=db['orders'], pending_proposals=agent.pending())
        context = dict(result=output, state=state, metrics=metrics, db={'v39_'+name: data for name, data in db.items()})
        checks = [assert_value(check, context, {}) for check in step['checks']]
        checks += [dict(path='oracle.'+check['rule'], ok=check['passed']) for check in row['checks'] + (row['task_checks'] or [])]
        refs = [f"run_events.jsonl#{event['event_id']}" for event in events]
        retrieval = [dict(documents=retrieval_documents(event), ref=f"run_events.jsonl#{event['event_id']}")
                     for event in events if retrieval_documents(event) is not None]
        details = dict(kind='chat', index=0, result=output, trace_id=row['trace_id'], checks=checks, state=state, db_metrics=metrics)
        objective = 'indeterminate' if not invoked else 'passed' if not row['error'] and all(c['ok'] for c in checks) else 'failed'
        return private_evidence(dict(run_id=case['run_id'], case_id=case['case_id'], execution_id=agent.id,
                                     subject_session_id=agent.session.sid,
                                     ref=f"executions/{case['case_id']}.json", trace_refs=refs, agent_trace_refs=refs,
                                     agent_invoked=invoked, executed=invoked, objective_status=objective,
                                     verified_nodes=_verified_nodes(case['covered_nodes'], {'steps': [details]}) if invoked else [],
                                     mutation_status='not_run', mode='live_agent', engine='langchain', steps=[details],
                                     retrieval_evidence=retrieval, tool_evidence=row['executed_tools'],
                                     oracle_ref=f'{agent.root.parent.name}/{agent.id}/run-001.json',
                                     oracle_evidence=dict(state_sha256=row['after']['state_sha256'], checks=row['checks']),
                                     order_observations=dict(status='not_applicable' if not state['orders'] else 'unknown'),
                                     metrics=dict(tool_times=[]))), events
