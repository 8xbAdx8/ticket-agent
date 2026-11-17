"""Offline, strict snapshot validation/import. No network implementation."""
from datetime import date,datetime,timezone,timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

SYNTHETIC='SYNTHETIC_TEST_FIXTURE'
REAL='USER_PROVIDED_REAL_SNAPSHOT'
SEATS={'高铁':{'二等座','一等座','商务座'},'机票':{'经济舱','公务舱'}}

def sha(raw):return hashlib.sha256(raw).hexdigest()

def _pairs(items):
    out={}
    for key,value in items:
        if key in out:raise ValueError('JSON存在重复字段')
        out[key]=value
    return out

def _keys(value,keys):
    if not isinstance(value,dict) or set(value)!=set(keys.split()):raise ValueError('快照字段缺失或含未知字段')

def _day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('日期格式错误')
    return date.fromisoformat(value)

def _time(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):raise ValueError('时刻格式错误')
    hour,minute=map(int,value.split(':'));return hour*60+minute

def _privacy(value):
    text=json.dumps(value,ensure_ascii=False)
    if re.search(r'(?<![A-Za-z0-9])1\d{10}(?![A-Za-z0-9])|\b\d{17}[\dXx]\b|sk-[A-Za-z0-9_-]{16,}|(?i:Bearer)\s+\S+|\b(?:OD|LK)[a-f0-9]{8,}\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text):
        raise ValueError('快照含个人、交易或认证信息')

def validate(raw):
    if not isinstance(raw,bytes) or len(raw)>8_000_000:raise ValueError('快照大小或内容类型错误')
    try:
        d=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=_pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('非法数值')))
        _keys(d,'schema_version snapshot_id fetched_at source timezone classification source_url coverage collector_version trains provenance')
        if type(d['schema_version']) is not int or d['schema_version']!=1:raise ValueError('Schema版本错误')
        if not isinstance(d['snapshot_id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',d['snapshot_id']):raise ValueError('快照ID错误')
        if not isinstance(d['collector_version'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,60}',d['collector_version']):raise ValueError('采集器版本错误')
        if d['timezone']!='Asia/Shanghai':raise ValueError('快照时区错误')
        fetched=datetime.fromisoformat(d['fetched_at'])
        if fetched.tzinfo is None:raise ValueError('采集时间必须带时区')
        if fetched>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('采集时间晚于当前时间')
        _keys(d['coverage'],'start_date end_date');start,end=map(_day,[d['coverage']['start_date'],d['coverage']['end_date']])
        if not 0<=(end-start).days<=31:raise ValueError('日期覆盖范围错误')
        if d['classification']==SYNTHETIC:
            if d['source']!=SYNTHETIC or d['source_url'] is not None or d['provenance']!={'acquisition':SYNTHETIC}:raise ValueError('合成数据标记不一致')
        elif d['classification']==REAL:
            if d['source']!='12306':raise ValueError('来源不在本适配器范围')
            url=urlsplit(d['source_url'])
            if url.scheme!='https' or url.hostname not in ('www.12306.cn','kyfw.12306.cn') or url.username or url.password or url.query or url.fragment or url.port not in (None,443):raise ValueError('来源信息错误')
            _keys(d['provenance'],'acquisition evidence_sha256 rights_confirmed')
            p=d['provenance']
            if p['acquisition']!='USER_PROVIDED_FILE' or p['rights_confirmed'] is not True or not isinstance(p['evidence_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',p['evidence_sha256']):raise ValueError('来源声明/证据错误')
        else:raise ValueError('来源分类错误')
        if not isinstance(d['trains'],list) or len(d['trains'])>20000:raise ValueError('车次数量错误')
        seen=set()
        for t in d['trains']:
            _keys(t,'train_no from_city to_city date depart arrive duration_min kind seats')
            if not isinstance(t['train_no'],str) or not re.fullmatch(r'[GDCZTKYSLA][A-Z]?\d{1,5}',t['train_no']):raise ValueError('车次号格式错误')
            for k in ('from_city','to_city'):
                if not isinstance(t[k],str) or not re.fullmatch(r'[\u3400-\u9fffA-Za-z· ]{1,40}',t[k]):raise ValueError('出发或到达地点错误')
            if t['from_city']==t['to_city']:raise ValueError('出发与到达不能相同')
            day=_day(t['date'])
            if not start<=day<=end:raise ValueError('车次不在声明覆盖范围')
            depart,arrive=_time(t['depart']),_time(t['arrive'])
            if type(t['duration_min']) is not int or not 1<=t['duration_min']<=2880 or (depart+t['duration_min'])%1440!=arrive:raise ValueError('车程与时刻不一致')
            if t['kind'] not in SEATS or d['classification']==REAL and t['kind']!='高铁':raise ValueError('交通方式错误')
            key=(t['date'],t['train_no'],t['from_city'],t['to_city'])
            if key in seen:raise ValueError('重复车次')
            seen.add(key)
            if not isinstance(t['seats'],dict) or not t['seats'] or set(t['seats'])-SEATS[t['kind']]:raise ValueError('席别缺失或错误')
            for seat in t['seats'].values():
                _keys(seat,'price count')
                price,count=seat['price'],seat['count']
                if price is not None and (type(price) not in (int,float) or not math.isfinite(price) or not 0<=price<=100000):raise ValueError('票价错误')
                if count is not None and (type(count) is not int or not 0<=count<=100000):raise ValueError('余票数量错误')
        _privacy(d)
        return d
    except (TypeError,KeyError,UnicodeError,RecursionError,OverflowError) as e:raise ValueError('快照格式错误') from e

def read_snapshot(path,expected_sha256=None,*,require_receipt=True):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise FileNotFoundError('快照缺失')
    if path.stat().st_size>8_000_000:raise ValueError('快照大小超限')
    raw=path.read_bytes();actual=sha(raw)
    if not expected_sha256 or actual!=expected_sha256:raise ValueError('快照SHA256不一致或未固定')
    data=validate(raw)
    if require_receipt:
        receipt=path.with_suffix('.receipt.json')
        if receipt.is_symlink() or not receipt.is_file():raise ValueError('缺少导入回执')
        r=json.loads(receipt.read_text(encoding='utf-8'))
        if r.get('sha256')!=actual or r.get('classification')!=data['classification'] or r.get('snapshot_id')!=data['snapshot_id']:raise ValueError('导入回执与原件不一致')
    return data,actual

def _exclusive(path,raw):
    temp=path.parent/(uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.link(temp,path)
    finally:
        if temp.exists():temp.unlink()

def import_snapshot(source,destination,*,evidence=None,acknowledge_rights=False):
    source,destination=Path(source),Path(destination)
    if source.is_symlink() or not source.is_file() or source.stat().st_size>8_000_000:raise ValueError('输入文件不可用')
    raw=source.read_bytes();data=validate(raw);h=sha(raw)
    real_root=Path(__file__).resolve().parents[1]/'data/real'
    if data['classification']==SYNTHETIC and destination.resolve().is_relative_to(real_root.resolve()):raise ValueError('合成测试快照不得进入data/real')
    if data['classification']==REAL:
        if not acknowledge_rights or evidence is None:raise ValueError('需明确来源使用权并提供采集来源证据文件')
        e=Path(evidence)
        if not e.is_file() or e.is_symlink() or e.stat().st_size>2_000_000 or sha(e.read_bytes())!=data['provenance']['evidence_sha256']:raise ValueError('来源证据SHA不匹配')
    destination.mkdir(parents=True,exist_ok=True)
    if destination.is_symlink():raise ValueError('导入目录不能为链接')
    path=destination/('snapshot-'+data['snapshot_id']+'-'+h[:12]+'.json');receipt=path.with_suffix('.receipt.json')
    if path.exists() or receipt.exists():raise FileExistsError('历史快照不可覆盖')
    record={'schema_version':1,'snapshot_id':data['snapshot_id'],'sha256':h,'classification':data['classification'],
            'imported_at':datetime.now(timezone.utc).isoformat(),'fetched_at':data['fetched_at'],'coverage':data['coverage'],
            'collector_version':data['collector_version'],'train_count':len(data['trains']),'failure_count':0,
            'integrity':'validated_structure_and_bytes','source_verified_independently':False,'evidence_sha256':data['provenance'].get('evidence_sha256')}
    _exclusive(path,raw)
    _exclusive(receipt,json.dumps(record,ensure_ascii=False,indent=2).encode())
    return path,record
