import copy,json
from datetime import datetime
from pathlib import Path
import pytest
from langchain_core.messages import AIMessage,HumanMessage,ToolMessage
from target.v39.query_facts import collect,durations
from target.reply_consistency import check
from target.v39.model_result import messages,retrieve


def incident():
    return json.loads(Path(__file__).with_name('fixtures').joinpath('v396-incident-pages.json').read_text(encoding='utf8'))


@pytest.fixture
def pages():
    return [copy.deepcopy(e) for e in incident() if e.get('event')=='tool_end']


def test_real_50_50_9_and_first_page_train(pages):
    facts=collect(pages)
    assert facts['complete'] and len(facts['records'])==109
    r=check('D3145 出发06:27，到达07:54。',pages)
    assert r['status']=='checked_fields_match' and not r['findings']
    record=next(r for r in facts['records'] if r['record']['trip_short_name']=='D3145')
    assert record['source']['call_id']==pages[0]['call_id'] and record['source']['page_cursor'] is None


@pytest.mark.parametrize('fault',['missing_middle','missing_first','broken_cursor','duplicate','dataset_version','database_sha','duplicate_trip','conflicting_trip','count'])
def test_incomplete_chain_is_not_proof_of_absence(pages,fault):
    if fault=='missing_middle':pages.pop(1)
    elif fault=='missing_first':pages.pop(0)
    elif fault=='broken_cursor':pages[1]['args']['cursor']='51'
    elif fault=='duplicate':pages.insert(1,copy.deepcopy(pages[0]))
    elif fault=='dataset_version':pages[1]['result']['dataset_version']='OTHER'
    elif fault=='database_sha':pages[1]['result']['database_sha256']='OTHER'
    elif fault=='duplicate_trip':pages[1]['result']['data'][0]=copy.deepcopy(pages[0]['result']['data'][0])
    elif fault=='conflicting_trip':
        pages[1]['result']['data'][0]=copy.deepcopy(pages[0]['result']['data'][0]);pages[1]['result']['data'][0]['arrival_at']='2026-11-05T23:59:00+08:00'
    elif fault=='count':pages[1]['result']['total_count']=110
    assert not collect(pages)['complete']
    r=check('G999999 出发08:00。',pages)
    assert r['status']=='indeterminate' and not r['findings']


def test_other_date_route_filter_not_combined(pages):
    for field in ('service_date','origin_stop_id','train_no'):
        other=copy.deepcopy(pages[-1]);other['args'][field]='DIFFERENT'
        assert not collect(pages+[other])['complete']
        assert len(collect(pages+[other])['records'])==9


def test_duration_sort_and_cross_midnight(pages):
    facts=collect(pages);ranking=durations(facts)
    assert ranking['ranked'][0]['duration_seconds']==45*60
    assert ranking['ranked']==sorted(ranking['ranked'],key=lambda r:(r['duration_seconds'],r['trip_id']))
    facts['records']=[dict(record=dict(trip_id='X',trip_short_name='X',departure_at='2026-11-05T23:50:00+08:00',arrival_at='2026-11-06T00:20:00+08:00'),source={})]
    assert durations(facts)['ranked'][0]['duration_seconds']==1800


def test_single_page_full_query_compatible(pages):
    e=copy.deepcopy(pages[0]);e['result'].update(total_count=50,has_more=False,next_cursor=None)
    assert collect([e])['complete']


def thread(pages):
    values=[HumanMessage('查询车次')]
    for e in pages:
        values += [AIMessage('',tool_calls=[dict(id=e['call_id'],name=e['tool'],args=e['args'])]),ToolMessage(json.dumps(e['result'],ensure_ascii=False),name=e['tool'],tool_call_id=e['call_id'])]
    return values


def test_history_compressed_but_current_results_and_pairing_retained(pages):
    original=thread(pages);before=copy.deepcopy(original)
    current=messages(original)
    assert len(json.loads(current[-1].content)['data'])==9
    new=original+[AIMessage('共109班。'),HumanMessage('我想买G7503的票')]
    compressed=messages(new)
    rawsize=sum(len(str(m.content).encode()) for m in new);smallsize=sum(len(str(m.content).encode()) for m in compressed)
    assert smallsize<rawsize*.25
    assert len(compressed)==len(new) and original==before
    tool_messages=[m for m in compressed if isinstance(m,ToolMessage)]
    assert {m.tool_call_id for m in tool_messages}=={e['call_id'] for e in pages}
    for m in tool_messages:
        d=json.loads(m.content);assert d['history_summary'] and 'data' not in d
        assert all(r['trip_short_name']=='G7503' for r in d['selected_records'])
    row=next(r for e in pages for r in e['result']['data'] if r['trip_short_name']=='G7503')
    call=next(e['call_id'] for e in pages if row in e['result']['data'])
    assert retrieve(new,call,row['trip_id'])==row
    assert retrieve([],call,row['trip_id']) is None


def test_selection_survives_following_seat_and_passenger_turn(pages):
    raw=thread(pages)+[AIMessage('查询完成'),HumanMessage('我想买G7503的票'),AIMessage('请提供席别和乘车人'),HumanMessage('一等座 三三')]
    governed=messages(raw)
    selected=[r for m in governed if isinstance(m,ToolMessage) for r in json.loads(m.content).get('selected_records',[])]
    assert len(selected)==1 and selected[0]['trip_short_name']=='G7503'
    assert governed[-1].content=='一等座 三三'
