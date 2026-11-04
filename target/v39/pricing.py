"""Integer-only simulation pricing; no inferred/official railway fares."""
from datetime import datetime
from target.v39.store import integer


def price(rule,segments,passengers):
    integer(segments,'segments',1,1000);integer(passengers,'passengers',1,6)
    base=integer(rule['base_fen_per_segment'],'base_fen_per_segment',1)
    bp=integer(rule['seat_multiplier_bp'],'seat_multiplier_bp',1,1000000)
    fixed=integer(rule['fixed_fee_fen'],'fixed_fee_fen')
    single_base=base*segments;single_seat=(single_base*bp+5000)//10000
    if single_seat<=0:raise ValueError('PRICE_RULE_ZERO_FARE')
    q,r=divmod(fixed,passengers)
    items=[dict(base_fen=single_base,seat_fen=single_seat,fixed_fee_share_fen=q+(i<r),fare_fen=single_seat+q+(i<r)) for i in range(passengers)]
    return dict(single_base_fen=single_base,single_seat_fen=single_seat,base_total_fen=single_base*passengers,seat_total_fen=single_seat*passengers,fixed_fee_fen=fixed,total_fen=sum(i['fare_fen'] for i in items),items=items)


def select_rule(c,scenario,dataset,trip,seat,now):
    stamp=datetime.fromisoformat(now)
    if stamp.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    candidates=[]
    for row in c.execute("SELECT * FROM v39_price_rules WHERE scenario_id=? AND dataset_version=? AND seat_class=? AND status='ACTIVE' AND (trip_id=? OR trip_id IS NULL)",(scenario,dataset,seat,trip)):
        start=datetime.fromisoformat(row['valid_from']);end=datetime.fromisoformat(row['valid_until']) if row['valid_until'] else None
        if start.tzinfo is None or end and end.tzinfo is None:raise ValueError('PRICE_RULE_TIME_INVALID')
        if end and end<=start:raise ValueError('PRICE_RULE_TIME_INVALID')
        if start<=stamp and (end is None or stamp<end):candidates.append(dict(row))
    if not candidates:raise ValueError('PRICE_NOT_CONFIGURED')
    rank=max((int(r['trip_id'] is not None),r['priority']) for r in candidates)
    choices=[r for r in candidates if (int(r['trip_id'] is not None),r['priority'])==rank]
    if len(choices)!=1:raise ValueError('PRICE_RULE_AMBIGUOUS')
    return choices[0]
