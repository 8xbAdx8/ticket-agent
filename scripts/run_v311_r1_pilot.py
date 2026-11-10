"""V3.11-R1 approved pilot: 24 max HTTP, one purchase-prep/create chain per provider.

This is test tooling; it never connects 12306/payment/RAG and never reuses the
old V311 batch. The caller must have user authorization.json in the R1 root.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def run(root: Path):
    from target.api_config import bootstrap, model_config
    from target.scenario_live_agent import save as save_agent
    from target.scenario_r1_budget import R1Batch
    from target.scenario_r1_lifecycle import R1Run
    from urllib.parse import urlsplit
    bootstrap()
    configs = [model_config(p) for p in ('deepseek', 'bailian')]
    if not all(c['configured'] for c in configs):
        raise ValueError('PROVIDER_CONFIGURATION_REQUIRED')
    # Process-local NO_PROXY only; do not modify system proxy/key/env.
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = ','.join(['localhost', '127.0.0.1', *[urlsplit(c['base_url']).hostname for c in configs]])
    auth = json.loads((root / 'authorization.json').read_text('utf-8'))
    batch = R1Batch(root)
    batch.initialize_authorized(auth)
    if (root / 'pilot-start.json').exists():
        raise ValueError('R1_PILOT_ALREADY_STARTED')
    save(root / 'pilot-start.json', {'batch_id': batch.status()['batch_id'], 'prior_http': batch.status()['http_requests']})
    results = []
    for provider in ('deepseek', 'bailian'):
        run = R1Run(root, provider, scenario='default')
        info = {'provider': provider, 'execution_id': run.execution_id, 'session_id': run.session_id, 'steps': []}
        results.append(info)
        try:
            route = '2026-11-05 上海虹桥（AOH）到杭州东（HGH）'
            row = run.turn(
                f'请查询{route}的静态车次，返回最早两班。选择第一班、二等座，查询2人的模拟库存并生成2人报价。只读，不要建单或支付。',
                expectations={'required_tools': ['railway_query_trips', 'railway_check_inventory', 'railway_quote_fare']},
                phase='PREPARE',
            )
            info['steps'].append({'phase': 'PREPARE', 'passed': row['passed'], 'row': row['index']})
            quote = None
            for event in row.get('executed_tools', []):
                if event.get('tool') == 'railway_quote_fare' and event.get('ok'):
                    quote = (event.get('result') or {}).get('quote') or {}
                    break
            if not quote or not quote.get('quote_id'):
                raise ValueError('NO_REAL_QUOTE_RETURNED')
            info['quote_id'] = quote['quote_id']
            # One write proposal per turn; no model confirmation token.
            row = run.turn(
                f'使用刚生成的报价{quote["quote_id"]}，为2名合成乘客（合成甲、合成乙）生成建单提案，联系人使用当前登录手机号。只生成提案，等待我确认；禁止直接建单或支付。',
                expectations={'required_tools': ['railway_create_order']},
                phase='CREATE_PROPOSAL',
            )
            info['steps'].append({'phase': 'CREATE_PROPOSAL', 'passed': row['passed'], 'row': row['index']})
            if not run.pending():
                raise ValueError('NO_CREATE_ORDER_PROPOSAL')
            confirmed = run.confirm('CREATE_ORDER')
            info['steps'].append({'phase': 'CREATE_ORDER', 'passed': confirmed['passed'], 'row': confirmed['index']})
            info['order_id'] = confirmed['result'].get('order_id')
            info['status'] = 'PASS'
        except Exception as exc:
            info['status'] = 'FAIL'
            info['error'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        try:
            info['final_state'] = [
                {k: o[k] for k in ('order_id', 'order_status', 'total_fen', 'paid_total_fen', 'active_item_count')}
                for o in run.read()['tables']['orders']
            ]
            info['checkpoints'] = sorted(p.name for p in run.checkpoint_dir.glob('*.json'))
            run.finalize(info.get('status', 'STOPPED'))
        except Exception as exc:
            info['finalize_error'] = type(exc).__name__
        save(run.run.root / 'pilot-outcome.json', info)
    summary = {'results': results, 'budget': batch.status()}
    save(root / 'pilot-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:4000], flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error('--live required')
    run(args.root.resolve())
