"""Phase7 objective data/state checks; not B's original 103 evaluator."""
import copy
from datetime import datetime,timezone,timedelta,date
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch
import pytest
import config
from target.train_snapshot import validate,import_snapshot,SYNTHETIC,read_snapshot
from target.train_source import SourceChoice,FixtureTrainSource,SnapshotTrainSource,LiveTrainSource,source_scope,query_tickets

DAY='2026-11-02'
NOW=datetime(2026,11,1,10,tzinfo=timezone(timedelta(hours=8)))

def example():
    return {'schema_version':1,'snapshot_id':'synthetic-v1','fetched_at':NOW.isoformat(),'source':SYNTHETIC,'timezone':'Asia/Shanghai',
      'classification':SYNTHETIC,'source_url':None,'coverage':{'start_date':'2026-11-01','end_date':'2026-11-10'},
      'collector_version':'test-1','provenance':{'acquisition':SYNTHETIC},'trains':[
       {'train_no':'G9998','from_city':'上海','to_city':'杭州','date':DAY,'depart':'06:00','arrive':'07:00','duration_min':60,'kind':'高铁',
        'seats':{'二等座':{'price':81.5,'count':3},'一等座':{'price':None,'count':None}}}]}

def imported(tmp_path,data=None):
    d=data or example();source=tmp_path/'input.json';source.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
    path,receipt=import_snapshot(source,tmp_path/'snapshots')
    return SourceChoice('snapshot',str(path),receipt['sha256'])

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'TRACE_DIR',tmp_path/'traces');monkeypatch.setattr(config,'DB_PATH',tmp_path/'tickets.db')
    for key in ('TICKET_TEST_MODE','TICKET_DATA_MODE','TICKET_TRAIN_SNAPSHOT_PATH','TICKET_TRAIN_SNAPSHOT_SHA256'):monkeypatch.delenv(key,raising=False)

def test_pinned_fixture_independent_of_clock_network_and_snapshot(monkeypatch):
    source=FixtureTrainSource()
    with patch.object(socket.socket,'connect',side_effect=AssertionError('no network')),patch('target.train_source.read_snapshot',side_effect=AssertionError('no snapshot')):
        a=source.query_tickets('上海','杭州','2026-10-21','二等座','高铁')
        monkeypatch.setattr(config,'today',lambda:date(2040,1,1));b=source.query_tickets('上海','杭州','2026-10-21','二等座','高铁')
    assert a==b and a['count']==3 and a['trains'][0]['price']==73.0 and a['trains'][0]['seats_left']==51
    assert source.query_tickets('北京','上海','2026-10-21','二等座','高铁')['data_source']['status']=='NO_AVAILABILITY'

def test_missing_fixture_stops_before_backend(monkeypatch,tmp_path):
    monkeypatch.setattr('target.train_source.FIXTURE_PATH',tmp_path/'missing.json')
    with patch('target.mock_core._query_fixture_inventory',side_effect=AssertionError('no fallback')):
        result=query_tickets('上海','杭州','2026-10-21')
    assert result['data_source']['status']=='FIXTURE_MISSING' and 'error' in result

@pytest.mark.parametrize('forced',['test','baseline'])
def test_baseline_and_test_ignore_snapshot_and_override(monkeypatch,tmp_path,forced):
    from target.execution_config import scope,resolve_effective_config
    from target.dev_overrides import Store
    e=resolve_effective_config('formal','baseline')
    if forced=='test':monkeypatch.setenv('TICKET_TEST_MODE','1')
    with source_scope(SourceChoice('snapshot','missing','0'*64)),scope(e if forced=='baseline' else None):
        with patch.object(Store,'load',side_effect=AssertionError('must not read override')),patch('target.train_source.read_snapshot',side_effect=AssertionError('must not read snapshot')):
            r=query_tickets('上海','杭州','2026-10-21')
    assert r['data_source']['mode']=='fixture' and r['count']>0

def test_test_clock_fixed_without_modifying_seed(monkeypatch):
    monkeypatch.setenv('TICKET_TEST_MODE','1')
    assert config.now()==datetime(2026,10,20,12) and config.today()==date(2026,10,20)

@pytest.mark.parametrize('scenario,status',[('normal','FOUND'),('empty','NO_MATCH'),('sold','NO_AVAILABILITY'),('unknown','AVAILABILITY_UNKNOWN'),('expired','SNAPSHOT_EXPIRED'),('outside','OUT_OF_COVERAGE'),('missing','SNAPSHOT_MISSING'),('hash','INVALID_SNAPSHOT'),('receipt','INVALID_SNAPSHOT')])
def test_snapshot_statuses_never_fallback(tmp_path,scenario,status):
    d=example();day=DAY;now=NOW
    if scenario=='empty':d['trains'][0]['from_city']='北京'
    if scenario=='sold':d['trains'][0]['seats']['二等座']['count']=0
    if scenario=='unknown':d['trains'][0]['seats']['二等座']['count']=None
    if scenario=='expired':now=NOW+timedelta(hours=2)
    if scenario=='outside':day='2026-12-01'
    choice=imported(tmp_path,d)
    if scenario=='missing':choice=SourceChoice('snapshot')
    if scenario=='hash':choice=SourceChoice('snapshot',choice.snapshot_path,'0'*64)
    if scenario=='receipt':Path(choice.snapshot_path).with_suffix('.receipt.json').write_text('{}',encoding='utf-8')
    with patch('target.train_source.load_fixture',side_effect=AssertionError('no fixture fallback')):
        r=SnapshotTrainSource(choice,now).query_tickets('上海','杭州',day,'二等座','高铁')
    assert r['data_source']['status']==status
    assert ('error' in r)==(status in ('SNAPSHOT_EXPIRED','OUT_OF_COVERAGE','SNAPSHOT_MISSING','INVALID_SNAPSHOT'))
    if scenario=='unknown':assert r['trains'][0]['seats_left'] is None

@pytest.mark.parametrize('bad',['json','schema','time','coverage','train','city','duplicate','seat','price','count','missing','privacy','source','nan','duplicate_json_key'])
def test_validator_rejects_invalid_data(tmp_path,bad):
    d=example()
    if bad=='schema':d['schema_version']=2
    if bad=='time':d['fetched_at']='2026-11-01T10:00:00'
    if bad=='coverage':d['coverage']['end_date']='2026-10-01'
    if bad=='train':d['trains'][0]['train_no']='not-train'
    if bad=='city':d['trains'][0]['to_city']='上海'
    if bad=='duplicate':d['trains']*=2
    if bad=='seat':d['trains'][0]['seats']={}
    if bad=='price':d['trains'][0]['seats']['二等座']['price']=-1
    if bad=='count':d['trains'][0]['seats']['二等座']['count']=True
    if bad=='missing':del d['trains'][0]['depart']
    if bad=='privacy':d['snapshot_id']='13800000001'
    if bad=='source':d['source']='12306'
    if bad=='nan':d['trains'][0]['seats']['二等座']['price']=float('nan')
    raw=json.dumps(d,ensure_ascii=False).encode()
    if bad=='json':raw=b'bad json'
    if bad=='duplicate_json_key':raw=b'{"schema_version":1,"schema_version":1}'
    with pytest.raises(ValueError):validate(raw)
    source=tmp_path/'bad.json';source.write_bytes(raw)
    with pytest.raises(ValueError):import_snapshot(source,tmp_path/'destination')
    assert not (tmp_path/'destination').exists()

def test_import_byte_identity_sha_append_only_and_no_real_directory(tmp_path):
    source=tmp_path/'input.json';source.write_text(json.dumps(example()),encoding='utf-8')
    raw=source.read_bytes();path,receipt=import_snapshot(source,tmp_path/'out')
    assert path.read_bytes()==raw and receipt['sha256']==hashlib.sha256(raw).hexdigest()
    assert receipt['source_verified_independently'] is False
    with pytest.raises(FileExistsError):import_snapshot(source,tmp_path/'out')
    with pytest.raises(ValueError):import_snapshot(source,Path(__file__).resolve().parents[1]/'data/real')
    assert path.read_bytes()==raw

@pytest.mark.parametrize('provider',['mock','deepseek','bailian'])
def test_live_has_no_network_or_fixture_fallback(monkeypatch,provider):
    monkeypatch.setattr(config,'PROVIDER',provider)
    with patch.object(socket.socket,'connect',side_effect=AssertionError('no network')),patch('target.train_source.load_fixture',side_effect=AssertionError('no fallback')),source_scope(SourceChoice('live')):
        r=query_tickets('上海','杭州',DAY)
    assert r['data_source']['status']=='LIVE_DISABLED' and 'error' in r

@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_actual_agent_query_snapshot_no_demo_db_and_provenance(tmp_path,engine,monkeypatch):
    from web.runtime import Conversation
    from target.train_source import FIXTURE_SHA256
    d=example();d['fetched_at']=datetime.now(timezone.utc).isoformat();choice=imported(tmp_path,d)
    monkeypatch.setattr(config,'today',lambda:date(2026,11,1))
    session=Conversation('user',engine=engine);session.set_train_source(choice)
    record=session.send('查2026-11-02上海到杭州的高铁二等座','query')
    assert 'query_tickets' in record['tool_sequence'] and session.last_train_query['trains'][0]['train_no']=='G9998'
    assert not (session.root/'tickets.db').exists()
    events=[json.loads(p.read_text(encoding='utf-8')) for p in (session.trace_dir/'train-data-events').glob('*.json')]
    assert events and all(e['data_source']['sha256']==choice.sha256 for e in events)
    assert events[0]['run_id'] in {a['trace_id'] for a in session.audits}
    assert len(record)==10 and all(len(c)==5 for s in record['steps'] for c in s['calls'])

def test_snapshot_block_writes_before_opening_database(tmp_path):
    from target import mock_core,tools,reschedule
    with source_scope(SourceChoice('snapshot')):
        with patch.object(mock_core,'_conn',side_effect=AssertionError('DB must not open')):
            r,ok,_=tools.dispatch('lock_seat',{'train_no':'G7301','date':DAY,'seat_type':'二等座','passengers':['演示乘客']})
            assert not ok and '12306' in r['error']
            with pytest.raises(ValueError):reschedule.confirm(tmp_path/'missing.db',{})
    assert not config.DB_PATH.exists()

def test_source_selection_rebuilds_no_request_and_blocks_old_page_preview(tmp_path):
    from web.runtime import Conversation
    s=Conversation('user');s.bind_page_proposal({'id':'old'})
    with patch('web.runtime.Agent',side_effect=AssertionError('save must not call Agent')):
        s.set_train_source(SourceChoice('snapshot'))
        with pytest.raises(ValueError):s.assert_page_proposal({'id':'old'})
        s.set_train_source(SourceChoice())
        with pytest.raises(ValueError):s.assert_page_proposal({'id':'old'})
    assert s.agent is None and not s.history

def test_snapshot_source_and_time_are_visible_in_apptest(tmp_path):
    from streamlit.testing.v1 import AppTest
    r=SnapshotTrainSource(imported(tmp_path),NOW).query_tickets('上海','杭州',DAY,'二等座')
    app=AppTest.from_string('import streamlit as st\nfrom web.train_data import source_status\nsource_status(st.session_state["result"])')
    app.session_state['result']=r;app.run()
    assert not app.exception
    captions=' '.join(x.value for x in app.caption)
    assert SYNTHETIC in captions and '2026-11-01 10:00:00' in captions and '不会向12306' in captions


def test_unknown_mode_is_unavailable_not_fixture(monkeypatch):
    monkeypatch.setenv('TICKET_DATA_MODE','unknown')
    with patch('target.train_source.load_fixture',side_effect=AssertionError('must not fallback')):
        r=query_tickets('上海','杭州',DAY)
    assert r['data_source']['status']=='SOURCE_UNAVAILABLE' and 'error' in r


def test_declared_range_without_observed_date_is_not_coverage(tmp_path):
    r=SnapshotTrainSource(imported(tmp_path),NOW).query_tickets('上海','杭州','2026-11-03')
    assert r['data_source']['status']=='OUT_OF_COVERAGE' and '2026-11-03' not in r['data_source']['observed_dates']


def test_failed_receipt_commit_is_fail_closed_and_preserves_orphan(tmp_path):
    import os
    source=tmp_path/'source.json';source.write_text(json.dumps(example()),encoding='utf-8')
    original=os.link
    def link(a,b):
        if str(b).endswith('.receipt.json'):raise OSError('injected receipt failure')
        return original(a,b)
    with patch('target.train_snapshot.os.link',side_effect=link):
        with pytest.raises(OSError):import_snapshot(source,tmp_path/'out')
    raw=list((tmp_path/'out').glob('snapshot-*.json'));assert len(raw)==1
    with pytest.raises(ValueError):read_snapshot(raw[0],hashlib.sha256(raw[0].read_bytes()).hexdigest())
    assert not list((tmp_path/'out').glob('*.tmp'))


def test_source_save_serialized_by_existing_call_lock():
    from web.runtime import Conversation,CALL_LOCK
    from concurrent.futures import ThreadPoolExecutor
    import threading
    session=Conversation('user');started=threading.Event();finished=threading.Event()
    def save():
        started.set();session.set_train_source(SourceChoice('snapshot'));finished.set()
    with ThreadPoolExecutor(1) as pool:
        with CALL_LOCK:
            job=pool.submit(save);assert started.wait(2)
            assert not finished.wait(.05) and session.train_source_choice is None
        job.result(3)
    assert finished.is_set() and session.train_source_choice.mode=='snapshot'


def test_cli_validate_and_import_are_local_only(tmp_path):
    import subprocess,sys
    root=Path(__file__).resolve().parents[1]
    source=tmp_path/'input.json';source.write_text(json.dumps(example()),encoding='utf-8')
    result=subprocess.run([sys.executable,str(root/'scripts/validate_train_snapshot.py'),str(source)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['status']=='VALID_STRUCTURE'
    result=subprocess.run([sys.executable,str(root/'scripts/import_train_snapshot.py'),str(source),'--destination',str(tmp_path/'imported')],capture_output=True,text=True,check=True)
    receipt=json.loads(result.stdout);assert receipt['receipt']['classification']==SYNTHETIC and receipt['receipt']['source_verified_independently'] is False


def test_inflight_source_does_not_follow_environment_edit(monkeypatch):
    monkeypatch.setenv('TICKET_DATA_MODE','snapshot')
    with source_scope():
        monkeypatch.setenv('TICKET_DATA_MODE','fixture')
        r=query_tickets('上海','杭州',DAY)
    assert r['data_source']['status']=='SNAPSHOT_MISSING' and r['data_source']['mode']=='snapshot'


def test_fixed_seed_initial_state_matches_all_pinned_2100_rows(monkeypatch,tmp_path):
    from data.seed import build_db
    from target.train_source import load_fixture
    monkeypatch.setattr(config,'today',lambda:date(2026,10,20))
    path=tmp_path/'fixed-seed.db';build_db(path)
    with sqlite3.connect(path) as c:
        c.row_factory=sqlite3.Row
        rows=[dict(r) for r in c.execute('SELECT kind,train_no,from_city,to_city,date,depart,arrive,seat_type,price,seats_left FROM inventory ORDER BY id')]
    assert len(rows)==2100 and rows==load_fixture()['inventory']
