from target.reply_consistency import _authority

def test_later_static_query_is_not_compared_with_old_fixture():
    old=dict(event='tool_end',tool='query_tickets',ok=True,result=dict(trains=[dict(train_no='G1',depart='09:00')]))
    stations=dict(event='tool_end',tool='railway_search_stations',ok=True,result=dict(data=[dict(stop_id='VNP',stop_name='北京南')]))
    static=dict(event='tool_end',tool='railway_query_trips',ok=True,args=dict(service_date='2026-11-06',origin_stop_id='VNP'),
                result=dict(data=[dict(trip_short_name='G531',departure_at='2026-11-06T06:08:00+08:00')]))
    rows,_=_authority([old,stations,static])
    assert rows[0]['values']==dict(train_no='G531',date='2026-11-06',depart='06:08',from_city='北京南')
    assert 'price' not in rows[0]['values'] and 'seats_left' not in rows[0]['values']
    rows,_=_authority([static,old]);assert rows[0]['values']['train_no']=='G1'
