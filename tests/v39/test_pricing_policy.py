import pytest
from target.v39.pricing import price,select_rule
from target.v39.policy import Policy
from tests.v39.fixtures import seed

def test_real_half_up_and_fixed_fee():
    p=price(dict(base_fen_per_segment=1235,seat_multiplier_bp=15000,fixed_fee_fen=100),1,3)
    assert p['single_seat_fen']==1853
    assert p['total_fen']==5659
    assert [i['fixed_fee_share_fen'] for i in p['items']]==[34,33,33]
    assert sum(i['fare_fen'] for i in p['items'])==p['total_fen']

@pytest.mark.parametrize('field',['base_fen_per_segment','seat_multiplier_bp','fixed_fee_fen'])
@pytest.mark.parametrize('value',[True,1.5,'1000'])
def test_price_strict_input(field,value):
    r=dict(base_fen_per_segment=1000,seat_multiplier_bp=15000,fixed_fee_fen=0);r[field]=value
    with pytest.raises(ValueError):price(r,2,3)

def test_rule_scope_priority_and_boundary():
    c,a=seed()
    try:
        rule=select_rule(c,'A','v1','T','SECOND','2026-11-03T08:00:00+00:00');assert rule['rule_id']=='RA'
        a['ins']('v39_price_rules',rule_id='SPECIAL',version=1,trip_id='T',base_fen_per_segment=1200,seat_multiplier_bp=10000,valid_from='2026-11-03T07:00:00+00:00',valid_until='2026-11-03T09:00:00+00:00',status='ACTIVE')
        assert select_rule(c,'A','v1','T','SECOND','2026-11-03T08:00:00+00:00')['rule_id']=='SPECIAL'
        assert select_rule(c,'A','v1','T','SECOND','2026-11-03T09:00:00+00:00')['rule_id']=='RA'
        with pytest.raises(ValueError,match='PRICE_NOT_CONFIGURED'):select_rule(c,'A','v2','T','SECOND','2026-11-03T08:00:00+00:00')
    finally:c.close()

def test_d9_default_remains_pending():
    # Historical pending profile remains testable; current default is approved B.
    assert Policy().approved and Policy().profile=='CHANGED_REFUND_P01'
    with pytest.raises(ValueError,match='PENDING_USER_DECISION'):Policy(version='D9_PENDING',profile=None,approved=False).refund([2000],'2026-11-06T08:00:00+00:00','2026-11-03T08:00:00+00:00')

@pytest.mark.parametrize('hours,fee',[(49,100),(48,200),(36,200),(24,200),(12,400)])
def test_explicit_test_policy_fee(hours,fee):
    from datetime import datetime,timedelta,timezone
    now=datetime(2026,11,3,tzinfo=timezone.utc)
    p=Policy('test-only','CHANGED_REFUND_P01',True,True,True)
    value=p.refund([2000],(now+timedelta(hours=hours)).isoformat(),now.isoformat(),changed=True)[0]
    assert value==dict(amount_fen=2000,fee_fen=fee,net_fen=2000-fee)
