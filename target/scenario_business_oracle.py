"""Independent read-only SQL and integer-money oracle; imports no business Service."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import hashlib
import json
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('orders', 'order_items', 'holds', 'hold_segments', 'transactions',
          'transaction_allocations', 'refund_requests', 'refund_items', 'change_requests',
          'inventory_segments', 'inventory_events', 'proposals', 'idempotency',
          'order_snapshots', 'item_price_snapshots', 'audit_events', 'quotes')
IDENTITY = ('scenario_id', 'dataset_version', 'trip_id', 'service_date', 'seat_class', 'segment_index')
LEGAL = {(None, 'PENDING_PAYMENT'), ('PENDING_PAYMENT', 'PAID'), ('PENDING_PAYMENT', 'PAYMENT_FAILED'),
         ('PENDING_PAYMENT', 'EXPIRED'), ('PENDING_PAYMENT', 'CANCELLED'), ('PAID', 'PAID'),
         ('PAID', 'CHANGED'), ('PAID', 'CANCELLED'), ('CHANGED', 'CHANGED'), ('CHANGED', 'CANCELLED')}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def snapshot(path):
    path = Path(path).resolve()
    runtime = ROOT / 'artifacts/runtime'
    if not path.is_relative_to(runtime) or path.name != 'simulation.sqlite':
        raise ValueError('ORACLE_TEST_DATABASE_ONLY')
    namespace = path.relative_to(runtime).parts[0]
    if namespace not in ('v311-abc-integration-20261112', 'v311-r2-qa09-live-20261112') and not namespace.startswith(('v310-v311-', 'v310-ai-executions')):
        raise ValueError('ORACLE_TEST_DATABASE_ONLY')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None)) as c:
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        c.execute('BEGIN')
        rows = {t: [dict(r) for r in c.execute('SELECT * FROM v39_' + t + ' ORDER BY rowid')] for t in TABLES}
        foreign_keys = [list(r) for r in c.execute('PRAGMA foreign_key_check')]
    departures={}
    # Read the frozen GTFS independently, without the production Static adapter.
    static=ROOT/'artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite'
    if rows['refund_items']:
        with closing(sqlite3.connect(static.as_uri()+'?mode=ro',uri=True)) as c:
            for item in rows['refund_items']:
                q=next((q for q in rows['quotes'] if q['quote_id']==item['price_quote_id']),None)
                if not q: continue
                value=c.execute('SELECT departure_seconds FROM source_stop_times WHERE trip_id=? AND stop_id=? AND CAST(stop_sequence AS INTEGER)=?',(q['trip_id'],q['origin_stop_id'],q['origin_sequence'])).fetchone()
                if value:
                    base=datetime.fromisoformat(q['service_date']).replace(tzinfo=timezone(timedelta(hours=8)))
                    departures[q['quote_id']]=(base+timedelta(seconds=value[0])).isoformat()
    return dict(tables=rows, foreign_keys=foreign_keys, state_sha256=digest(rows),departures=departures)


def p01(fare, departure, now):
    if type(fare) is not int or fare <= 0:
        raise ValueError('INVALID_FARE')
    seconds = (datetime.fromisoformat(departure) - datetime.fromisoformat(now)).total_seconds()
    if seconds <= 0:
        raise ValueError('REFUND_AFTER_DEPARTURE')
    rate = Decimal('0.05') if seconds > 48 * 3600 else Decimal('0.10') if seconds >= 24 * 3600 else Decimal('0.20')
    fee = int((Decimal(fare) * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return dict(amount_fen=fare, fee_fen=fee, net_fen=fare-fee)


def invariants(view):
    t = view['tables']; checks = []
    def check(rule, ok, identity=None):
        checks.append(dict(rule=rule, passed=bool(ok), identity=identity))
    check('foreign_keys', not view['foreign_keys'])
    for inv in t['inventory_segments']:
        events = [e for e in t['inventory_events'] if all(e[k] == inv[k] for k in IDENTITY)]
        check('inventory_event_balance', sum(e['delta_held'] for e in events) == inv['held'] and sum(e['delta_sold'] for e in events) == inv['sold'], [inv[k] for k in IDENTITY])
        check('inventory_capacity', 0 <= inv['held'] and 0 <= inv['sold'] and inv['held']+inv['sold'] <= inv['capacity'])
        owned=[(s,h) for s in t['hold_segments'] for h in t['holds'] if s['hold_id']==h['hold_id'] and all(s[k]==inv[k] for k in IDENTITY)]
        check('inventory_owned_balance',inv['held']==sum(s['quantity'] for s,h in owned if h['status']=='ACTIVE') and inv['sold']==sum(s['quantity'] for s,h in owned if h['status']=='CONSUMED'),[inv[k] for k in IDENTITY])
    for h in t['holds']:
        owner=next((o for o in t['orders'] if o['order_id']==h['order_id']),None)
        check('hold_order_identity',owner and all(owner[k]==h[k] for k in ('scenario_id','session_id','owner_phone')),h['hold_id'])
        quote=next((q for q in t['quotes'] if q['quote_id']==h['quote_id']),None)
        segments=[s for s in t['hold_segments'] if s['hold_id']==h['hold_id']]
        check('hold_quote_identity',quote and all(h[k]==quote[k] for k in ('scenario_id','session_id','owner_phone','trip_id','service_date','seat_class')),h['hold_id'])
        if quote:
            check('hold_exact_interval',len(segments)==quote['destination_position']-quote['origin_position'] and {s['segment_index'] for s in segments}==set(range(quote['origin_position'],quote['destination_position'])),h['hold_id'])
            check('hold_segment_identity',all(all(s[k]==quote[k] for k in IDENTITY[:-1]) for s in segments),h['hold_id'])
            if owner and owner['hold_id']==h['hold_id']:
                check('current_order_quote_identity',all(owner[k]==quote[k] for k in ('dataset_version','trip_id','service_date','seat_class','origin_position','destination_position')),h['hold_id'])
        if owner and owner['order_status'] in ('CANCELLED','EXPIRED','PAYMENT_FAILED'):
            check('terminal_order_no_occupancy',h['remaining_quantity']==0 and h['status'] not in ('ACTIVE','CONSUMED'),h['hold_id'])
    for segment in t['hold_segments']:
        check('segment_inventory_exists',any(all(segment[k]==v[k] for k in IDENTITY) for v in t['inventory_segments']),segment['hold_id'])
    for order in t['orders']:
        oid = order['order_id']; items = [i for i in t['order_items'] if i['order_id'] == oid]
        active = [i for i in items if i['item_status'] == 'ACTIVE']
        tx = [x for x in t['transactions'] if x['order_id'] == oid and x['status'] == 'SUCCEEDED']
        debit = sum(x['amount_fen'] for x in tx if x['direction'] == 'DEBIT')
        credit = sum(x['amount_fen'] for x in tx if x['direction'] == 'CREDIT')
        fees = sum(r['fee_fen'] for r in t['refund_requests'] if r['order_id'] == oid and r['status'] == 'SUCCEEDED')
        check('ledger_totals', (debit, credit, debit-credit, fees) == (order['paid_total_fen'], order['refunded_total_fen'], order['net_paid_fen'], order['fee_total_fen']), oid)
        check('passenger_counts', len(items) == order['initial_passenger_count'] and len(active) == order['active_item_count'], oid)
        if order['payment_status'] == 'SUCCEEDED':
            check('money_conservation', debit-credit == sum(i['fare_fen'] for i in active)+fees, oid)
        hold = next((h for h in t['holds'] if h['hold_id'] == order['hold_id'] and h['order_id'] == oid), None)
        check('hold_owned', hold is not None, oid)
        if hold:
            segments = [s for s in t['hold_segments'] if s['hold_id'] == hold['hold_id']]
            check('hold_segment_quantity', bool(segments) and all(s['quantity'] == hold['remaining_quantity'] for s in segments), oid)
            if hold['status'] in ('ACTIVE', 'CONSUMED'):
                check('hold_active_people', hold['remaining_quantity'] == len(active), oid)
        check('change_limit', order['change_count'] <= 1, oid)
    for tx in t['transactions']:
        allocations = [a for a in t['transaction_allocations'] if a['transaction_id'] == tx['transaction_id']]
        check('transaction_allocations', sum(a['amount_fen'] for a in allocations) == tx['amount_fen'] and all(a['order_id'] == tx['order_id'] for a in allocations), tx['transaction_id'])
        check('transaction_direction', tx['direction'] == ('DEBIT' if tx['transaction_type'] in ('PAYMENT', 'CHANGE_SUPPLEMENT') else 'CREDIT'), tx['transaction_id'])
    succeeded = [r for r in t['refund_items'] if r['status'] == 'SUCCEEDED']
    check('one_successful_refund_per_passenger', len({r['order_item_id'] for r in succeeded}) == len(succeeded))
    for item in t['refund_items']:
        request=next((r for r in t['refund_requests'] if r['refund_id']==item['refund_id'] and r['order_id']==item['order_id']),None)
        price=next((p for p in t['item_price_snapshots'] if p['item_id']==item['order_item_id'] and p['quote_id']==item['price_quote_id']),None)
        try:
            expected=p01(price['fare_fen'],view['departures'][item['price_quote_id']],request['created_at'])
            ok=all(item[k]==v for k,v in expected.items())
        except (KeyError,TypeError,ValueError): ok=False
        check('refund_frozen_price_p01',ok,item['order_item_id'])
    for event in t['audit_events']:
        if event.get('aggregate_type') != 'order': continue
        # State transitions are explicit fields in order events, not inferred from text.
        before, after = event.get('from_state'), event.get('to_state')
        if after and before != after:
            check('legal_order_transition', (before, after) in LEGAL, event['event_id'])
    return checks


def receipt_proof(view, proposal_id, result, *, before=None):
    t=view['tables']; proposal=next((p for p in t['proposals'] if p['proposal_id']==proposal_id),None)
    if not proposal: return False
    key='confirm:'+proposal['session_id']+':'+proposal_id+':'+proposal['action']
    row=next((r for r in t['idempotency'] if r['scope']=='confirm' and r['key']==key),None)
    if not row or json.loads(row['response_json'])!=result: return False
    if before and any(p['proposal_id']==proposal_id and p['state']=='CONFIRMED' for p in before['tables']['proposals']):
        return before['tables']==view['tables']
    if result.get('error'):
        if row['status']!='FAILED' or before is None:return False
        old=before['tables'];oid=json.loads(proposal['payload_json']).get('order_id')
        old_order=next((o for o in old['orders'] if o['order_id']==oid),None)
        new_order=next((o for o in t['orders'] if o['order_id']==oid),None)
        if not old_order or not new_order:return False
        success=lambda rows:[x for x in rows if x['status']=='SUCCEEDED']
        if success(old['transactions'])!=success(t['transactions']):return False
        if old['order_items']!=t['order_items'] or old['item_price_snapshots']!=t['item_price_snapshots']:return False
        if any(old_order[k]!=new_order[k] for k in ('paid_total_fen','refunded_total_fen','fee_total_fen','net_paid_fen','total_fen','active_item_count','change_count')):return False
        if proposal['action']=='PAY':
            failed=[x for x in t['transactions'] if x['order_id']==oid and x['transaction_type']=='PAYMENT' and x['status'] in ('FAILED','TIMEOUT')]
            return bool(failed) and new_order['order_status']=='PAYMENT_FAILED' and all(h['remaining_quantity']==0 for h in t['holds'] if h['order_id']==oid)
        if old_order['order_status']!=new_order['order_status'] or old['holds']!=t['holds'] or old['hold_segments']!=t['hold_segments']:return False
        quantities=lambda rows:{tuple(i[k] for k in IDENTITY):(i['held'],i['sold']) for i in rows}
        a,b=quantities(old['inventory_segments']),quantities(t['inventory_segments'])
        if any(b.get(k)!=(v) for k,v in a.items()) or any(v!=(0,0) for k,v in b.items() if k not in a):return False
        table='refund_requests' if result.get('refund_id') else 'change_requests'
        identity='refund_id' if table=='refund_requests' else 'change_id'
        failed=next((r for r in t[table] if r[identity]==result.get(identity) and r['order_id']==oid and r['idempotency_key']==proposal_id and r['status']=='FAILED'),None)
        if not failed:return False
        if table!='refund_requests':return True
        items=[i for i in t['refund_items'] if i['refund_id']==failed['refund_id']]
        wanted=json.loads(proposal['payload_json']).get('_refund_preview',{}).get('items',[])
        tx=[x for x in t['transactions'] if x['refund_id']==failed['refund_id'] and x['transaction_type']=='REFUND' and x['order_id']==oid and x['status']=='FAILED']
        return bool(items) and len(items)==len(wanted) and {i['order_item_id'] for i in items}=={i['item_id'] for i in wanted} and all(i['status']=='FAILED' for i in items) and len(tx)==1 and tx[0]['amount_fen']==sum(i['net_fen'] for i in items)
    if row['status']!='SUCCEEDED':return False
    order=next((o for o in t['orders'] if o['order_id']==result.get('order_id')),None)
    if not order or proposal['state']!='CONFIRMED' or order['order_status']!=result.get('status'): return False
    payload=json.loads(proposal['payload_json']); oid=order['order_id']
    if proposal['action']=='CREATE_ORDER':
        people=sorted((i for i in t['order_items'] if i['order_id']==oid),key=lambda i:i['passenger_index'])
        return order['proposal_id']==proposal_id and order['quote_id']==payload['quote_id'] and [i['passenger_name'] for i in people]==payload['passengers']
    if payload.get('order_id')!=oid: return False
    if proposal['action']=='PAY':
        paid=[x for x in t['transactions'] if x['order_id']==oid and x['transaction_type']=='PAYMENT' and x['status']=='SUCCEEDED']
        return len(paid)==1 and paid[0]['amount_fen']==payload['expected_total_fen']
    if result.get('refund_id'):
        items=[i for i in t['refund_items'] if i['refund_id']==result['refund_id']]
        wanted=payload.get('_refund_preview',{}).get('items',[])
        return bool(items) and all(i['status']=='SUCCEEDED' and i['order_id']==oid for i in items) and {i['order_item_id'] for i in items}=={i['item_id'] for i in wanted} and sum(i['net_fen'] for i in items)==result['refund_fen'] and sum(i['fee_fen'] for i in items)==result['fee_fen']
    if result.get('change_id'):
        return any(c['change_id']==result['change_id'] and c['order_id']==oid and c['target_quote_id']==payload['target_quote_id'] and c['status']=='CONFIRMED' and c['difference_fen']==result['difference_fen'] for c in t['change_requests'])
    return proposal['action']=='CANCEL' and order['order_status']=='CANCELLED'


def decline_proof(before,after,proposal_id):
    old=next((p for p in before['tables']['proposals'] if p['proposal_id']==proposal_id),None)
    new=next((p for p in after['tables']['proposals'] if p['proposal_id']==proposal_id),None)
    if not old or not new or old['state'] not in ('PENDING','CANCELLED') or new['state']!='CANCELLED':return False
    if {k:v for k,v in old.items() if k!='state'}!={k:v for k,v in new.items() if k!='state'}:return False
    if [p for p in before['tables']['proposals'] if p['proposal_id']!=proposal_id]!=[p for p in after['tables']['proposals'] if p['proposal_id']!=proposal_id]:return False
    return all(before['tables'][t]==after['tables'][t] for t in TABLES if t not in ('proposals','audit_events'))


def reply_claims(text,view):
    """Bounded positive-claim rules, not a universal natural-language judge."""
    checks=[];t=view['tables']
    named=set(re.findall(r'V39-[a-f0-9]{32}',text or ''))
    orders=[o for o in t['orders'] if not named or o['order_id'] in named]
    patterns=dict(pay=r'已(?:经)?(?:成功)?(?:支付|付款)|支付成功|付款成功',
                  create=r'已(?:经)?(?:成功)?(?:创建订单|建单)',
                  refund=r'退款成功|退票成功|已(?:经)?(?:成功)?(?:退款|退票)',
                  change=r'改签成功|已(?:经)?(?:成功)?改签',
                  hold=r'已(?:经)?锁座|锁座成功')
    for clause in re.split(r'[。！!？?；;，,\n]|但是|但|不过',text or ''):
        for kind,pattern in patterns.items():
            if kind=='change':
                # A policy condition does not consume a separate claim in the same clause.
                match=next((candidate for candidate in re.finditer(pattern,clause)
                    if not re.match(r'的(?:车票|订单)\s*(?:[”"』」*]*\s*)?(?:仍可申请退票|不予退票|不接受退票|不退)',
                                    clause[candidate.end():])),None)
            else:
                match=re.search(pattern,clause)
            if not match:continue
            prefix=clause[:match.start()]
            if re.search(r'(?:未|尚未|不能|不得|没有|不代表|不应|不表示|并非|不是)[^，,。；;]{0,6}$',prefix):continue
            # A future UI message is not an assertion that a transaction happened.
            # Keep current-tense "系统提示已支付成功" subject to proof. Also
            # reject explicit conditional future wording such as
            # "点击确认后 Service 才会执行支付".
            if re.search(r'(?:将|会)[^，,。；;]{0,8}(?:提示|显示|告知|返回)[“"：: ]*$',prefix):continue
            if re.search(r'(?:点击|确认)[^，,。；;]{0,40}(?:后|之后)[^，,。；;]{0,20}(?:才会|将|会|方可)',prefix):continue
            amount=re.search(r'已(?:经)?(?:成功)?(?:支付|付款)\s*(\d+(?:\.\d+)?)\s*(分|元)',clause) if kind=='pay' else None
            if amount:
                value=Decimal(amount[1])*(100 if amount[2]=='元' else 1)
                proof=False
                if value==int(value) and len(orders)==1:
                    o=orders[0]
                    debits=sum(x['amount_fen'] for x in t['transactions'] if x['order_id']==o['order_id'] and x['status']=='SUCCEEDED' and x['direction']=='DEBIT')
                    proof=o['paid_total_fen']==int(value)==debits
                checks.append(dict(rule='explicit_paid_amount',kind=kind,text=clause,passed=proof))
                continue
            proof=False
            for o in orders:
                oid=o['order_id']
                if kind=='create':proof=True
                elif kind=='pay':proof=any(x['order_id']==oid and x['transaction_type']=='PAYMENT' and x['status']=='SUCCEEDED' for x in t['transactions'])
                elif kind=='refund':proof=any(x['order_id']==oid and x['status']=='SUCCEEDED' for x in t['refund_requests'])
                elif kind=='change':proof=any(x['order_id']==oid and x['status']=='CONFIRMED' for x in t['change_requests'])
                elif kind=='hold':proof=any(x['order_id']==oid and x['status'] in ('ACTIVE','CONSUMED') and x['remaining_quantity']>0 for x in t['holds'])
                if proof:break
            checks.append(dict(rule='positive_business_claim',kind=kind,text=clause,passed=proof))
    return dict(scope='bounded explicit positive claims only; no-claim is not task success',status='FAIL' if any(not c['passed'] for c in checks) else 'PASS' if checks else 'N/A',checks=checks)
