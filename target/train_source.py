"""Train query sources: pinned fixture, local snapshot, disabled live.

Model providers never grant data-network permission. Snapshot rows are never
written to the demo inventory. Public Agent/Tool contracts are unchanged.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,asdict
from datetime import datetime,timezone,timedelta
import copy
import hashlib
import json
import os
from pathlib import Path
import uuid
from typing import Protocol
import config
from target.train_snapshot import read_snapshot,SYNTHETIC

FIXTURE_ID='ticket-trains-v1-20261020'
FIXTURE_SHA256='feaec244decbe9ed25f42b5fa7767bb4fb65d76e5313d8b1a52db14826b29217'
FIXTURE_CLOCK='2026-10-20T12:00:00'
FIXTURE_PATH=Path(__file__).resolve().parents[1]/'data/fixtures/train-v1.json'
LIVE_BLOCK='LIVE_SOURCE_BLOCKED_PENDING_AUTHORIZATION'
class FixtureUnavailable(ValueError):pass
MESSAGES={
 'FOUND':'已找到匹配车次。','NO_MATCH':'数据中没有匹配的车次；不代表其他来源无票。',
 'NO_AVAILABILITY':'有匹配车次，但所查席别余票为0。','AVAILABILITY_UNKNOWN':'有匹配车次，余票数量未提供，不能保证可售。',
 'SNAPSHOT_MISSING':'快照缺失，请先导入合法取得的快照。','SNAPSHOT_EXPIRED':'快照已过期，不能用于当前余票判断。',
 'OUT_OF_COVERAGE':'快照未覆盖目标日期。','SOURCE_UNAVAILABLE':'数据源不可用，未使用演示库存替代。',
 'INVALID_SNAPSHOT':'快照格式、来源或SHA256校验失败。','LIVE_DISABLED':'实时数据源未获授权，未发送网络请求。',
 'FIXTURE_MISSING':'固定Fixture缺失或SHA256不匹配，已停止查询。'}
ERRORS=set(MESSAGES)-{'FOUND','NO_MATCH','NO_AVAILABILITY','AVAILABILITY_UNKNOWN'}

@dataclass(frozen=True)
class SourceChoice:
    mode:str='fixture'
    snapshot_path:str|None=None
    sha256:str|None=None
    max_age_seconds:int=3600

class TrainSource(Protocol):
    def query_tickets(self,from_city,to_city,date,seat_type=None,kind=None):...
    def get_train_detail(self,train_no,date):...

STATE=ContextVar('ticket_train_source',default=None)

def _baseline():
    from target.execution_config import CURRENT
    effective=CURRENT.get()
    return os.getenv('TICKET_TEST_MODE')=='1' or effective is not None and effective.execution_mode=='baseline'

def selected():
    if _baseline():return SourceChoice()
    state=STATE.get()
    if state and state['choice'] is not None:return state['choice']
    return SourceChoice(os.getenv('TICKET_DATA_MODE','fixture'),os.getenv('TICKET_TRAIN_SNAPSHOT_PATH') or None,os.getenv('TICKET_TRAIN_SNAPSHOT_SHA256') or None)

def validate_choice(choice):
    if not isinstance(choice,SourceChoice) or choice.mode not in ('fixture','snapshot','live'):raise ValueError('未知车次数据来源')
    if type(choice.max_age_seconds) is not int or not 60<=choice.max_age_seconds<=86400:raise ValueError('快照有效期配置错误')
    if choice.mode!='snapshot' and (choice.snapshot_path is not None or choice.sha256 is not None):raise ValueError('非快照模式不能携带快照')
    return choice

@contextmanager
def source_scope(choice=None):
    if choice is not None:validate_choice(choice)
    else:choice=SourceChoice(os.getenv('TICKET_DATA_MODE','fixture'),os.getenv('TICKET_TRAIN_SNAPSHOT_PATH') or None,os.getenv('TICKET_TRAIN_SNAPSHOT_SHA256') or None)
    state={'choice':choice,'now':datetime.now(timezone.utc),'last_result':None}
    token=STATE.set(state)
    try:yield state
    finally:STATE.reset(token)

@contextmanager
def conversation_scope(session):
    choice=SourceChoice() if session.execution_mode=='baseline' else getattr(session,'train_source_choice',None)
    with source_scope(choice) as state:
        session.last_train_query=None
        try:yield state
        finally:session.last_train_query=copy.deepcopy(state['last_result'])

def load_fixture():
    path=FIXTURE_PATH
    if not path.is_file() or path.is_symlink():raise FixtureUnavailable(MESSAGES['FIXTURE_MISSING'])
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FIXTURE_SHA256:raise FixtureUnavailable(MESSAGES['FIXTURE_MISSING'])
    data=json.loads(raw)
    if data['fixture_id']!=FIXTURE_ID or len(data['inventory'])!=2100:raise FixtureUnavailable(MESSAGES['FIXTURE_MISSING'])
    return data

def _status(rows):
    if not rows:return 'NO_MATCH'
    if any(type(t.get('seats_left')) is int and t['seats_left']>0 for t in rows):return 'FOUND'
    if all(t.get('seats_left')==0 for t in rows):return 'NO_AVAILABILITY'
    return 'AVAILABILITY_UNKNOWN'

def _result(status,rows,meta):
    meta={**meta,'status':status,'message':MESSAGES[status],'real_time':False,'demo_transactions_only':True}
    out={'trains':rows,'count':len(rows),'data_source':meta}
    if status in ERRORS:out['error']=MESSAGES[status]
    return out

class FixtureTrainSource:
    def __init__(self,backend=None):self.backend=backend
    def query_tickets(self,from_city,to_city,date,seat_type=None,kind=None):
        data=load_fixture()
        if self.backend is not None:
            original=self.backend(from_city,to_city,date,seat_type,kind)
            rows=original.get('trains',[])
        else:
            rows=[dict(t) for t in data['inventory'] if (not from_city or from_city in t['from_city']) and (not to_city or to_city in t['to_city']) and (not date or t['date']==date) and (not seat_type or t['seat_type']==seat_type) and (not kind or t['kind']==kind)]
            rows=sorted(rows,key=lambda t:(-t['seats_left'],t['depart']))[:20]
        return _result(_status(rows),rows,{'mode':'fixture','classification':SYNTHETIC,'fixture_id':FIXTURE_ID,'sha256':FIXTURE_SHA256,
            'clock':data['clock'],'state_scope':'isolated_demo_transaction_database' if self.backend else 'pinned_immutable_fixture',
            'source':'固定演示数据','fetched_at':None,
            'coverage':None if self.backend else {'start_date':'2026-10-20','end_date':'2026-10-26'},
            'returned_dates':sorted({t['date'] for t in rows})})
    def get_train_detail(self,train_no,date):
        return [t for t in load_fixture()['inventory'] if t['train_no']==train_no and t['date']==date]

class SnapshotTrainSource:
    def __init__(self,choice,now=None):
        self.choice=validate_choice(choice);self.now=now or datetime.now(timezone.utc)
    def read(self):
        c=self.choice
        if c.snapshot_path is None or not Path(c.snapshot_path).exists():return None,{'mode':'snapshot'},'SNAPSHOT_MISSING'
        try:
            data,h=read_snapshot(c.snapshot_path,c.sha256)
            fetched=datetime.fromisoformat(data['fetched_at'])
            age=(self.now-fetched).total_seconds()
            meta={'mode':'snapshot','classification':data['classification'],'source':data['source'],'snapshot_id':data['snapshot_id'],
                  'fetched_at':data['fetched_at'],'coverage':data['coverage'],'sha256':h,'timezone':data['timezone'],
                  'collector_version':data['collector_version'],'source_verified_independently':False,'max_age_seconds':c.max_age_seconds,'validated_at':self.now.isoformat()}
            meta['observed_dates']=sorted({t['date'] for t in data['trains']})
            if age < -300:return None,meta,'INVALID_SNAPSHOT'
            if age>c.max_age_seconds:return None,meta,'SNAPSHOT_EXPIRED'
            return data,meta,None
        except (ValueError,OSError,TypeError):return None,{'mode':'snapshot','sha256':c.sha256},'INVALID_SNAPSHOT'
    def query_tickets(self,from_city,to_city,date,seat_type=None,kind=None):
        data,meta,error=self.read()
        if error:return _result(error,[],meta)
        if not data['coverage']['start_date']<=date<=data['coverage']['end_date'] or date not in meta['observed_dates']:
            return _result('OUT_OF_COVERAGE',[],meta)
        rows=[]
        for t in data['trains']:
            if t['date']!=date or from_city and from_city not in t['from_city'] or to_city and to_city not in t['to_city'] or kind and kind!=t['kind']:continue
            for seat,values in t['seats'].items():
                if seat_type and seat!=seat_type:continue
                rows.append({k:t[k] for k in ('kind','train_no','from_city','to_city','date','depart','arrive','duration_min')}|{'seat_type':seat,'price':values['price'],'seats_left':values['count']})
        rows=sorted(rows,key=lambda t:(t['seats_left'] is None,-(t['seats_left'] or 0),t['depart']))[:20]
        return _result(_status(rows),rows,meta)
    def get_train_detail(self,train_no,date):
        data,meta,error=self.read()
        if error:return _result(error,[],meta)
        return [copy.deepcopy(t) for t in data['trains'] if t['train_no']==train_no and t['date']==date]

class LiveTrainSource:
    """Deliberately has no client, URL, login, crawler or network code."""
    def query_tickets(self,*args,**kwargs):return _result('LIVE_DISABLED',[],{'mode':'live','blocker':LIVE_BLOCK})
    def get_train_detail(self,*args,**kwargs):return self.query_tickets()

def _record(result,choice):
    from target.run_events import identity,emit
    meta=result['data_source'];ids=identity();query_id=uuid.uuid4().hex
    record={'schema_version':1,'query_id':query_id,**ids,'created_at':datetime.now(timezone.utc).isoformat(),
            'requested_mode':choice.mode,'test_or_baseline_forced_fixture':_baseline(),'data_source':meta}
    directory=config.TRACE_DIR/'train-data-events';directory.mkdir(parents=True,exist_ok=True)
    with (directory/(query_id+'.json')).open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
    emit('train_data_source_selected',source_mode=meta['mode'],source_sha256=meta.get('sha256'),query_id=query_id)
    emit('train_data_query',meta['status'],query_id=query_id,data_source=meta,returned_rows=result['count'])
    state=STATE.get()
    if state is not None:state['last_result']=copy.deepcopy(result)

def query_tickets(from_city,to_city,date,seat_type=None,kind=None,*,fixture_backend=None):
    choice=selected()
    try:
        validate_choice(choice)
        if choice.mode=='fixture':result=FixtureTrainSource(fixture_backend).query_tickets(from_city,to_city,date,seat_type,kind)
        elif choice.mode=='snapshot':result=SnapshotTrainSource(choice,(STATE.get() or {}).get('now')).query_tickets(from_city,to_city,date,seat_type,kind)
        else:result=LiveTrainSource().query_tickets()
    except FixtureUnavailable:result=_result('FIXTURE_MISSING',[],{'mode':'fixture'})
    except ValueError:result=_result('SOURCE_UNAVAILABLE',[],{'mode':choice.mode if choice.mode in ('fixture','snapshot','live') else 'unavailable'})
    except Exception:
        _record(_result('SOURCE_UNAVAILABLE',[],{'mode':choice.mode}),choice)
        raise
    _record(result,choice)
    return result

def assert_demo_acquisition():
    if selected().mode!='fixture':raise ValueError('快照和实时数据仅供查询。请切换固定演示数据并重新查询；不会向12306提交订单、真实锁座或扣款。')

def external_authority():
    choice=selected()
    if choice.mode=='fixture':return None
    if choice.mode!='snapshot':return {'available':False,'trains':[],'source':'live_disabled'}
    data,meta,error=SnapshotTrainSource(choice,(STATE.get() or {}).get('now')).read()
    return {'available':data is not None,'trains':sorted({t['train_no'] for t in data['trains']}) if data else [],
            'source':'validated_local_snapshot','source_sha256':meta.get('sha256'),'reason':error}

def summary(result):
    m=result.get('data_source') or {}
    lines=[m.get('message','数据源状态未记录')]
    for t in result.get('trains',[])[:3]:
        stock='未知' if t['seats_left'] is None else str(t['seats_left'])
        price='未提供' if t['price'] is None else str(t['price'])
        lines.append(f"{t['train_no']} {t['from_city']}→{t['to_city']} {t['date']} {t['depart']} {t['seat_type']}，票价{price}，余票{stock}。")
    lines.append('历史快照不是实时余票保证；仅供查询，不会真实锁座、出票或扣款。')
    if m.get('classification')==SYNTHETIC:lines.append('SYNTHETIC_TEST_FIXTURE：合成测试数据，非真实12306数据。')
    return '\n'.join(lines)
