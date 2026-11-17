"""Prepare the authorized read-only pilots and stop for candidate approval."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def source(batch):
    from target.scenario_live_agent import deny_network
    from web.runtime import CALL_LOCK, Conversation
    session = Conversation('user', engine='langchain', live=False, full_tools=True,
                           root=batch.root/('pilot-source-'+uuid4().hex))
    session._unified_interaction = True
    with CALL_LOCK, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, dict(
            RAILWAY_SIMULATION_ENABLED='1', RAILWAY_SIM_CLOCK_MODE='demo',
            RAILWAY_SIM_DB_PATH=str(session.root/'simulation.sqlite'), TICKET_TEST_MODE='1',
            TICKET_DATA_MODE='fixture', TICKET_RAILWAY_QUERY_ENABLED='0', RAG_ALLOW_NETWORK='0',
            TICKET_WEB_OFFLINE_ONLY='1', TICKET_DISABLE_LOCAL_SECRETS='1')))
        for name in ('socket.socket.connect', 'socket.socket.connect_ex', 'socket.create_connection', 'socket.getaddrinfo'):
            stack.enter_context(patch(name, deny_network))
        result = session.send('查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。',
                              'abc-pilot-synthetic-source', defer_followups=True)
    if not session.audits or 'railway_query_trips' not in result.get('tool_sequence', []):
        raise ValueError('ABC_SYNTHETIC_SOURCE_TOOL_EVIDENCE_REQUIRED')
    write(batch.root/'source.json', dict(session_id=session.sid, trace_id=session.audits[-1]['trace_id'],
                                        directory=session.root.name))
    return session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    from target.api_config import bootstrap, model_config
    from target.scenario_abc_budget import IntegrationBatch, PROVIDERS
    from target.scenario_abc_live import PilotModel, configured_provider
    from target.scenario_workbench import Workbench
    from urllib.parse import urlsplit
    bootstrap(ROOT)
    batch = IntegrationBatch()
    batch.initialize_authorized()
    statuses = {}
    for provider in PROVIDERS:
        with configured_provider(provider) as model:
            statuses[provider] = dict(model=model, host=urlsplit(model_config(provider)['base_url']).hostname,
                                      configured=True)
    if not (batch.root/'budget-preflight.json').exists():
        write(batch.root/'budget-preflight.json', dict(configured=statuses, budget=batch.snapshot()))
    if args.check_only:
        print(json.dumps(statuses))
        return
    if batch.ledger():
        raise ValueError('ABC_PILOT_DISPATCH_ALREADY_RECORDED')
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = ','.join(['127.0.0.1','localhost', *[row['host'] for row in statuses.values()]])
    session = source(batch)
    for provider in PROVIDERS:
        workbench = Workbench(session.sid, root=batch.root/'generated-cases')
        result = workbench.execute(session, PilotModel(provider, batch=batch), review_required=True)
        receipt = dict(provider=provider, run_id=workbench.run_id, session_id=session.sid,
                       status=result['status'], generation=result['stages'][1])
        write(batch.root/f'pilot-generation-{provider}.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
