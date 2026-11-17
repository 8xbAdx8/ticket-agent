from web.railway_cards import projection, instant, minutes, card_html
from web.railway_queries import visible_rows
from web.railway_queries import page_args

def test_agent_page_metadata_does_not_send_null_optional_arguments():
    from target.v39.registry import StrictValidator,TOOLS
    row={'result':{'query_parameters':{'service_date':'2026-11-05','origin_stop_id':'AOH','destination_stop_id':'HGH','train_no':None,'cursor':None},'limit':20}}
    args=dict(page_args(row),cursor='20')
    schema=next(t['function']['parameters'] for t in TOOLS if t['function']['name']=='railway_query_trips')
    assert StrictValidator(schema).is_valid(args) and args['limit']==20

def test_cross_day_and_long_gtfs_time():
    a=instant('23:50:00','2026-11-05');b=instant('30:51:00','2026-11-05')
    assert minutes(a,b)==421 and b.day==6 and b.hour==6

def test_card_uses_only_real_fields_and_escapes():
    v=projection(dict(trip_short_name='<G1>',departure_at='2026-11-05T23:50:00+08:00',arrival_at='2026-11-06T06:51:00+08:00'),dict(service_date='2026-11-05',origin_stop_id='A',destination_stop_id='B'),{'A':'上海虹桥','B':'杭州东'})
    assert v['duration']=='7小时1分钟' and v['day_offset']==1
    html=card_html(v)
    assert '&lt;G1&gt;' in html and '上海虹桥' in html and '￥' not in html and '有票' not in html

def test_missing_times_do_not_invent_duration():
    v=projection({}, {}, {})
    assert v['departure']=='—' and v['duration']=='时长未提供'
    assert minutes(instant('10:00:00','2026-11-05'),instant('09:00:00','2026-11-05')) is None

def test_helpers_suppressed_pages_replaced_raw_history_preserved():
    station=dict(tool='railway_search_stations',source='default_query',result={})
    page=lambda cursor:dict(tool='railway_query_trips',args={'service_date':'2026-11-05','cursor':cursor},result={})
    rows=[station,page('0'),page('20')]
    assert visible_rows(rows)==[rows[-1]] and len(rows)==3
    standalone=dict(station,source='page_query')
    assert visible_rows([standalone])==[standalone]
