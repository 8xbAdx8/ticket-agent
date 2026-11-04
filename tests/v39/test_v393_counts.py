from target.v39.counts import reconcile
from target.v39.registry import TOOLS,StrictValidator

def test_total_correction_keeps_answer_and_page_count():
    events=[dict(event='tool_end',tool='railway_query_trips',ok=True,call_id='c',result=dict(total_count=40,returned_count=20))]
    for wrong in (38,41):
        raw=f'查询到 **{wrong} 班**，当前返回20班。G531在06:08出发。'
        reply,changes=reconcile(raw,events)
        assert '40 班' in reply and '返回20班' in reply and 'G531在06:08' in reply
        assert changes[0]['claimed']==wrong

def test_failed_or_legacy_results_do_not_authorize_correction():
    raw='共41班，G531。'
    assert reconcile(raw,[dict(event='tool_end',tool='query_tickets',ok=True,result={'total_count':40})])==(raw,[])
    assert reconcile(raw,[dict(event='tool_end',tool='railway_query_trips',ok=False,result={'total_count':40})])==(raw,[])

def test_user_approved_optional_cursor_schema():
    for name,args in [('railway_query_trips',dict(service_date='2026-11-06')),('railway_search_stations',dict(name='北京'))]:
        schema=next(t['function']['parameters'] for t in TOOLS if t['function']['name']==name)
        assert StrictValidator(schema).is_valid(args)
        assert StrictValidator(schema).is_valid(dict(args,cursor='20'))
        assert not StrictValidator(schema).is_valid(dict(args,cursor='-20'))
