"""Evidence paths for runtime-only V3.10 results. Shapes never prove values."""
from contextlib import closing
from functools import cache
from pathlib import Path
import sqlite3

from target.payment_qr import payment_payload
from target.scenario_v310 import TABLES
from target.v39.pricing import price
from target.v39.registry import ACTIONS, TOOLS
from target.v39.store import statements

METRICS = frozenset('order_count hold_count transaction_count held sold foreign_keys_ok inventory_conserved money_conserved ui_consistent'.split())
SQL = Path(__file__).with_name('v39')
ERROR = {'error': None, 'simulation': None}


def fields(names):
    return dict.fromkeys(names.split())


@cache
def rows():
    """Use the versioned DDL for field names. No business database is opened."""
    with closing(sqlite3.connect(':memory:')) as connection:
        for name in ('schema.sql', 'hardening.sql', 'migration_002.sql'):
            for statement in statements((SQL/name).read_text(encoding='utf-8')):
                connection.execute(statement)
        tables = (*TABLES, 'v39_quotes', 'v39_audit_events', 'v39_item_price_snapshots')
        return {table: {row[1]: None for row in connection.execute(f'PRAGMA table_info({table})')}
                for table in tables}


@cache
def snapshot_shape():
    table = rows()
    order = order_detail() | {
        'hold': table['v39_holds'], 'hold_status': None, 'hold_expired_at_read': None,
        'passenger_ids': [None], 'transaction_records': [table['v39_transactions']],
        'inventory': [table['v39_inventory_segments'] | fields('hold_segment_quantity inventory_role')],
        'operation_events': [table['v39_audit_events']], 'pending_proposals': [None], 'ledger_verified': None,
    }
    proposal = table['v39_proposals'] | {'payload': UNKNOWN}
    state = fields('schema session_id source scenario_id updated_at state_sha256') | {
        'orders': [order], 'quotes': [table['v39_quotes']], 'proposals': [proposal],
        'pending_proposals': [proposal], 'operation_events': [table['v39_audit_events']],
        'operations': [fields('operation_id proposal_id order_id action status tool_call_id database_verified created_at finished_at') |
                       dict(actual_result=UNKNOWN, before=UNKNOWN, after=UNKNOWN)],
    }
    return dict(state=state, ui=state, db={t:[table[t]] for t in TABLES},
                metrics=dict.fromkeys(METRICS))


def order_detail():
    table = rows()
    return table['v39_orders'] | {
        'items': [table['v39_order_items']], 'transactions': [table['v39_transactions']],
        'refunds': [table['v39_refund_requests']], 'changes': [table['v39_change_requests']],
        'refund_items': [table['v39_refund_items']], 'price_snapshots': [table['v39_item_price_snapshots']],
    }


UNKNOWN = object()


def result_shape(step):
    kind = step['kind']
    if kind == 'tool':
        name = step['tool']
        clock = {'simulation_clock': UNKNOWN}
        if name == 'railway_check_inventory':
            return ERROR | clock | fields('status available dataset_version')
        if name == 'railway_quote_fare':
            fare = price(dict(base_fen_per_segment=1, seat_multiplier_bp=10000, fixed_fee_fen=0), 1, 1)
            return ERROR | clock | dict(status=None, quote=rows()['v39_quotes'], items=[dict.fromkeys(fare['items'][0])])
        if name == 'railway_get_order':
            if 'order_id' in step['args']:
                return ERROR | clock | order_detail()
            return ERROR | {'data': [rows()['v39_orders']]}
        if name in ACTIONS:
            shape = ERROR | clock | fields('proposal_id status expires_at') | dict(preview=UNKNOWN)
            return shape | (dict(message=None, missing_fields=[None]) if name=='railway_create_order' else {})
        return UNKNOWN  # A static step without concrete evidence will need review.
    if kind in ('confirm', 'foreign_confirm'):
        return ERROR | fields('status proposal_id order_id total_fen refund_id refund_fen fee_fen remaining_passengers change_id difference_fen')
    if kind == 'foreign_order':
        return ERROR | order_detail()
    if kind == 'history':
        return {'read_only': None}
    if kind == 'flag':
        return {'enabled': None}
    if kind == 'advance':
        return ERROR | {'advanced': None}
    if kind == 'qr':
        return ERROR | dict(payload=dict.fromkeys(payment_payload('contract', 1, '1')), expected_fen=None, png_bytes=None)
    if kind == 'chat':
        arg_names = {key: None for tool in TOOLS for key in tool['function']['parameters']['properties']}
        return ERROR | dict(reply=None, public_result={'tool_sequence': [None]},
                            queries=[dict(tool=None, args=arg_names)])
    return UNKNOWN


def traverse(shape, parts):
    """Require real keys and dot-separated numeric array indices."""
    for part in parts:
        if shape is UNKNOWN:
            return UNKNOWN
        if isinstance(shape, list) and part.isascii() and part.isdigit():
            shape = shape[0]
        elif isinstance(shape, dict) and part in shape:
            shape = shape[part]
        else:
            raise KeyError(part)
    return shape

