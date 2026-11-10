"""V3.11-R1 full read/write lifecycle driver, test-only and no automatic retry."""
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


def first_quote(row):
    for event in row.get('executed_tools', []):
        if event.get('tool') == 'railway_quote_fare' and event.get('ok'):
            quote = (event.get('result') or {}).get('quote') or {}
            if quote.get('quote_id'):
                return quote
    raise RuntimeError('NO_REAL_QUOTE_RETURNED')


def first_trip(row):
    for event in row.get('executed_tools', []):
        if event.get('tool') == 'railway_query_trips' and event.get('ok'):
            data = (event.get('result') or {}).get('data') or []
            if data:
                return data[0]
    raise RuntimeError('NO_REAL_TRIP_RETURNED')


def run_chain(root: Path, provider: str):
    from target.scenario_r1_lifecycle import R1Run
    run = R1Run(root, provider, scenario='default')
    out = {'provider': provider, 'execution_id': run.execution_id, 'session_id': run.session_id, 'steps': [], 'status': 'RUNNING'}
    try:
        route = '2026-11-05 上海虹桥（AOH）到杭州东（HGH）'
        row = run.turn(
            f'查询{route}的静态车次，返回最早两班；选择第一班二等座，查询2人模拟库存并生成2人报价。只读，不要建单或支付。',
            expectations={'required_tools': ['railway_query_trips', 'railway_check_inventory', 'railway_quote_fare']}, phase='QUERY_QUOTE')
        out['steps'].append({'phase': 'QUERY_QUOTE', 'passed': row['passed'], 'row': row['index']})
        trip = first_trip(row); quote = first_quote(row); out['trip_id'] = trip['trip_id']; out['quote_id'] = quote['quote_id']
        row = run.turn(
            f'使用报价{quote["quote_id"]}为2名合成乘客（合成甲、合成乙）生成建单提案，联系人使用当前登录手机号。只生成提案，等待我确认，禁止直接建单或支付。',
            expectations={'required_tools': ['railway_create_order']}, phase='CREATE_PROPOSAL')
        out['steps'].append({'phase': 'CREATE_PROPOSAL', 'passed': row['passed'], 'row': row['index']})
        created = run.confirm('CREATE_ORDER'); oid = created['result']['order_id']; out['order_id'] = oid
        out['steps'].append({'phase': 'CREATE_ORDER', 'passed': created['passed'], 'row': created['index']})
        total = next(o['total_fen'] for o in run.read()['tables']['orders'] if o['order_id'] == oid)

        row = run.turn(
            f'为订单{oid}生成支付提案，金额{total}分，等待我确认；不要直接支付。',
            expectations={'required_tools': ['railway_pay_order']}, phase='PAY_PROPOSAL')
        out['steps'].append({'phase': 'PAY_PROPOSAL', 'passed': row['passed'], 'row': row['index']})
        paid = run.confirm('PAY'); out['steps'].append({'phase': 'PAY', 'passed': paid['passed'], 'row': paid['index']})

        item = run.read()['tables']['order_items'][0]
        row = run.turn(
            f'为订单{oid}中的乘客合成甲明细{item["item_id"]}生成部分退款提案，scope=ITEMS，只退这一人，其他一人保持有效，等待我确认。',
            expectations={'required_tools': ['railway_refund_order']}, phase='PARTIAL_REFUND_PROPOSAL')
        out['steps'].append({'phase': 'PARTIAL_REFUND_PROPOSAL', 'passed': row['passed'], 'row': row['index']})
        partial = run.confirm('REFUND'); out['steps'].append({'phase': 'PARTIAL_REFUND', 'passed': partial['passed'], 'row': partial['index']})

        # Target query + quote is a read turn; change proposal is a separate write turn.
        row = run.turn(
            f'查询{route}同日的静态车次，返回两班，不要查询库存、不要报价、不要改签；只调用 railway_query_trips。',
            expectations={'required_tools': ['railway_query_trips']}, phase='CHANGE_TRIPS')
        out['steps'].append({'phase': 'CHANGE_TRIPS', 'passed': row['passed'], 'row': row['index']})
        target_trip = None
        for event in row.get('executed_tools', []):
            if event.get('tool') == 'railway_query_trips' and event.get('ok'):
                for candidate in (event.get('result') or {}).get('data') or []:
                    if candidate.get('trip_id') != trip['trip_id']:
                        target_trip = candidate; break
                if target_trip: break
        if not target_trip:
            raise RuntimeError('NO_SECOND_TARGET_TRIP')
        row = run.turn(
            f'只为目标车次 trip_id={target_trip["trip_id"]}、2026-11-05、AOH→HGH、二等座、剩余1名ACTIVE乘客生成目标报价；不要查询库存或改签。',
            expectations={'required_tools': ['railway_quote_fare']}, phase='CHANGE_QUOTE')
        out['steps'].append({'phase': 'CHANGE_QUOTE', 'passed': row['passed'], 'row': row['index']})
        target_quote = first_quote(row)
        out['target_trip_id'] = target_trip['trip_id']; out['target_quote_id'] = target_quote['quote_id']
        row = run.turn(
            f'为订单{oid}剩余1名ACTIVE乘客生成改签提案：target_quote_id={target_quote["quote_id"]}，target_trip_id={target_trip["trip_id"]}，target_service_date=2026-11-05，target_origin_stop_id=AOH，target_destination_stop_id=HGH，target_seat_class=SECOND。等待我确认，不要直接改签。',
            expectations={'required_tools': ['railway_change_order']}, phase='CHANGE_PROPOSAL')
        out['steps'].append({'phase': 'CHANGE_PROPOSAL', 'passed': row['passed'], 'row': row['index']})
        changed = run.confirm('CHANGE'); out['steps'].append({'phase': 'CHANGE', 'passed': changed['passed'], 'row': changed['index']})

        row = run.turn(
            f'为订单{oid}全部剩余ACTIVE乘客生成整单退款提案，scope=FULL，等待我确认。',
            expectations={'required_tools': ['railway_refund_order']}, phase='FULL_REFUND_PROPOSAL')
        out['steps'].append({'phase': 'FULL_REFUND_PROPOSAL', 'passed': row['passed'], 'row': row['index']})
        final = run.confirm('REFUND'); out['steps'].append({'phase': 'FINAL_REFUND', 'passed': final['passed'], 'row': final['index']})
        order = next(o for o in run.read()['tables']['orders'] if o['order_id'] == oid)
        out['final_order'] = {k: order[k] for k in ('order_id', 'order_status', 'paid_total_fen', 'refunded_total_fen', 'fee_total_fen', 'net_paid_fen', 'active_item_count')}
        if order['order_status'] != 'CANCELLED':
            raise RuntimeError('FINAL_STATE_NOT_CANCELLED')
        out['status'] = 'PASS'
    except Exception as exc:
        out['status'] = 'FAIL'
        out['error'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    try:
        out['final_state'] = [{k: o[k] for k in ('order_id', 'order_status', 'paid_total_fen', 'refunded_total_fen', 'fee_total_fen', 'net_paid_fen', 'active_item_count')} for o in run.read()['tables']['orders']]
        out['checkpoints'] = sorted(p.name for p in run.checkpoint_dir.glob('*.json'))
        run.finalize(out['status'])
    except Exception as exc:
        out['finalize_error'] = type(exc).__name__
    save(run.run.root / 'lifecycle-outcome.json', out)
    return out


def cancel_chain(root: Path, provider: str):
    from target.scenario_r1_lifecycle import R1Run
    run = R1Run(root, provider, scenario='default')
    out = {'provider': provider, 'execution_id': run.execution_id, 'session_id': run.session_id, 'steps': [], 'status': 'RUNNING'}
    try:
        route = '2026-11-05 上海虹桥（AOH）到杭州东（HGH）'
        row = run.turn(f'查询{route}最早两班，选择第一班二等座，查询1人库存并报价；只读。', expectations={'required_tools': ['railway_query_trips', 'railway_check_inventory', 'railway_quote_fare']}, phase='CANCEL_QUERY')
        trip = first_trip(row); quote = first_quote(row)
        row = run.turn(f'使用报价{quote["quote_id"]}为合成甲生成1人建单提案，等待确认，不要直接建单。', expectations={'required_tools': ['railway_create_order']}, phase='CANCEL_CREATE_PROPOSAL')
        created = run.confirm('CREATE_ORDER'); oid = created['result']['order_id']; out['order_id'] = oid
        row = run.turn(f'为待支付订单{oid}生成取消提案，展示影响；等待我确认，不要直接取消。', expectations={'required_tools': ['railway_cancel_order']}, phase='CANCEL_PROPOSAL')
        cancelled = run.confirm('CANCEL'); out['steps'].append({'phase': 'CANCEL', 'passed': cancelled['passed'], 'row': cancelled['index']})
        order = next(o for o in run.read()['tables']['orders'] if o['order_id'] == oid)
        out['final_order'] = {k: order[k] for k in ('order_id', 'order_status', 'active_item_count', 'paid_total_fen')}
        if order['order_status'] != 'CANCELLED':
            raise RuntimeError('CANCEL_STATE_NOT_CANCELLED')
        out['status'] = 'PASS'
    except Exception as exc:
        out['status'] = 'FAIL'; out['error'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    try:
        out['checkpoints'] = sorted(p.name for p in run.checkpoint_dir.glob('*.json'))
        run.finalize(out['status'])
    except Exception as exc: out['finalize_error'] = type(exc).__name__
    save(run.run.root / 'cancel-outcome.json', out)
    return out


def main(root: Path):
    from target.api_config import bootstrap
    from target.scenario_r1_budget import R1Batch
    from urllib.parse import urlsplit
    bootstrap()
    auth = json.loads((root / 'authorization.json').read_text('utf-8'))
    batch = R1Batch(root); batch.initialize_authorized(auth)
    if (root / 'lifecycle-start.json').exists():
        raise ValueError('R1_LIFECYCLE_ALREADY_STARTED')
    save(root / 'lifecycle-start.json', {'batch_id': batch.status()['batch_id']})
    results = []
    for provider in ('deepseek', 'bailian'):
        results.append(run_chain(root, provider))
        results.append(cancel_chain(root, provider))
    summary = {'results': results, 'budget': batch.status()}
    save(root / 'lifecycle-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:5000], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--live', action='store_true'); parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if not args.live: parser.error('--live required')
    main(args.root.resolve())
