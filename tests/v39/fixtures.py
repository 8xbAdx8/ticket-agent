"""Synthetic fixture: A/B own three-person paid orders on separate pools."""
from pathlib import Path
import sqlite3


def seed(schema_text=None):
    root=Path(__file__).resolve().parents[2]
    ddl=schema_text or '\n'.join((root/'target/v39'/n).read_text(encoding='utf-8') for n in ('schema.sql','hardening.sql','migration_002.sql'))
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;c.executescript(ddl)
    stamp='2026-11-03T08:00:00+00:00'
    def ins(table,tag='A',**v):
        if table=='v39_order_items' and schema_text is None:v.setdefault('price_quote_id','Q'+tag)
        common=dict(session_id='S'+tag,owner_phone='U'+tag,scenario_id=tag,dataset_version='v1',trip_id='T',service_date='2026-11-04',seat_class='SECOND',currency='CNY',created_at=stamp,updated_at=stamp,applied_at=stamp,expires_at='2026-11-03T08:15:00+00:00',config_json='{}',payload_json='{}',origin_stop_id='X',destination_stop_id='Z',origin_sequence=1,destination_sequence=3,origin_position=0,destination_position=2,passenger_count=3,initial_passenger_count=3,active_item_count=3,quantity=3,initial_quantity=3,remaining_quantity=3)
        for row in c.execute('PRAGMA table_info('+table+')'):
            _,name,kind,required,default,pk=row
            if name not in v and required and default is None:v[name]=common.get(name,0 if kind=='INTEGER' else 'fixture')
        c.execute('INSERT INTO '+table+' ('+','.join(v)+') VALUES ('+','.join('?' for _ in v)+')',tuple(v.values()))
        if table=='v39_order_items' and schema_text is None:
            c.execute('INSERT INTO v39_item_price_snapshots VALUES (?,?,?,?,?,?,?,?)',(v['item_id'],v['price_quote_id'],v['passenger_index'],v['base_fen'],v['seat_fen'],v.get('fixed_fee_share_fen',0),v['fare_fen'],stamp))
    def quote(q,tag='A',rule=None,version='v1',trip='T',day='2026-11-04'):
        ins('v39_quotes',tag,quote_id=q,dataset_version=version,trip_id=trip,service_date=day,rule_id=rule or 'R'+tag,rule_version=1,base_fen_per_segment=1000,seat_multiplier_bp=10000,segment_count=2,single_base_fen=2000,single_seat_fen=2000,base_total_fen=6000,seat_total_fen=6000,total_fen=6000,status='CONSUMED')
    for tag in ('A','B'):
        ins('v39_scenarios',tag,scenario_id=tag,name='default',seed=1,status='ACTIVE')
        ins('v39_price_rules',tag,rule_id='R'+tag,version=1,trip_id=None,base_fen_per_segment=1000,seat_multiplier_bp=10000,valid_from=stamp,status='ACTIVE')
        quote('Q'+tag,tag)
        ins('v39_holds',tag,hold_id='H'+tag,quote_id='Q'+tag,order_id='O'+tag,status='CONSUMED')
        ins('v39_proposals',tag,proposal_id='P'+tag,action='CREATE_ORDER',state='CONFIRMED',idempotency_key='P'+tag,execution_mode='developer_custom',feature_flag='1',config_revision=1)
        ins('v39_orders',tag,order_id='O'+tag,proposal_id='P'+tag,quote_id='Q'+tag,hold_id='H'+tag,total_fen=6000,paid_total_fen=6000,net_paid_fen=6000,order_status='PAID',payment_status='SUCCEEDED',refund_status='NONE',change_status='NONE',idempotency_key='O'+tag)
        for i in range(3):ins('v39_order_items',tag,item_id=tag+str(i),order_id='O'+tag,passenger_index=i,passenger_name='Demo'+str(i),base_fen=2000,seat_fen=2000,fare_fen=2000,item_status='ACTIVE')
        for i in range(2):
            ins('v39_inventory_segments',tag,segment_index=i,from_stop_id=str(i),from_sequence=i+1,from_position=i,to_stop_id=str(i+1),to_sequence=i+2,to_position=i+1,capacity=10,held=0,sold=3)
            ins('v39_hold_segments',tag,hold_id='H'+tag,segment_index=i,inventory_role='NEW')
    quote('QT',trip='T2',day='2026-11-05')
    ins('v39_holds',hold_id='HT',quote_id='QT',order_id='OA',trip_id='T2',service_date='2026-11-05',status='CONSUMED')
    ins('v39_transactions',transaction_id='PAY',order_id='OA',transaction_type='PAYMENT',direction='DEBIT',amount_fen=6000,status='PENDING',idempotency_key='PAY')
    for i in range(3):ins('v39_transaction_allocations',allocation_id='AL'+str(i),transaction_id='PAY',order_id='OA',order_item_id='A'+str(i),amount_fen=2000)
    c.execute("UPDATE v39_transactions SET allocated_fen=6000,status='SUCCEEDED' WHERE transaction_id='PAY'")
    c.commit()
    return c,dict(ins=ins,quote=quote)
