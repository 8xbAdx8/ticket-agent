import json
from langchain_core.messages import ToolMessage,HumanMessage
from target.v39.model_result import messages,project
from target.v39.static import RailwayStatic

def test_projection_preserves_count_and_source_without_mutating_trace():
    original=dict(source='GTFS_SQLITE',total_count=40,returned_count=20,limit=20,has_more=True,
                  real_time=False,data=[dict(trip_id='T',trip_short_name='G1',departure_at='2026-11-06T08:00:00+08:00',shape_status='SHAPE_UNAVAILABLE',internal_row_version=123)])
    msg=ToolMessage(content=json.dumps(original),name='railway_query_trips',tool_call_id='call1')
    result=messages([HumanMessage('查车次'),msg])
    parsed=json.loads(result[1].content)
    assert parsed['total_count']==40 and parsed['returned_count']==20 and parsed['has_more']
    assert parsed['data'][0]['trip_id']=='T' and parsed['real_time'] is False
    assert 'internal_row_version' not in parsed['data'][0]
    assert json.loads(msg.content)==original

def test_original_tools_and_transaction_results_are_not_projected():
    obj={'trains':[{'anything':'unchanged'}]}
    assert project('query_tickets',obj) is obj
    assert project('railway_pay_order',obj) is obj

def test_real_gtfs_pagination_metadata_matches_complete_query():
    s=RailwayStatic()
    full=s.trips('2026-11-06','VNP','AOH',limit=50)
    first=s.trips('2026-11-06','VNP','AOH',limit=20)
    second=s.trips('2026-11-06','VNP','AOH',limit=20,cursor=first['next_cursor'])
    assert first['total_count']==len(full['data'])==second['total_count']
    assert first['returned_count']==len(first['data'])==20
    assert first['has_more'] and first['source']=='GTFS_SQLITE'
    assert [v['trip_id'] for v in first['data']+second['data']]==[v['trip_id'] for v in full['data']]
