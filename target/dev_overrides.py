"""Strict session-owned experimental settings; never stores credentials."""
from pathlib import Path
from threading import RLock
from contextlib import contextmanager
import hashlib
import json
import math
import os
import re
import uuid
import config

LOCK=RLock()
PROFILE=json.loads(Path(__file__).with_name('baseline_profile.json').read_text(encoding='utf-8'))
TOOLS=tuple(PROFILE['tool_names'])
WRITES=tuple(PROFILE['write_policy'])


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def registry():
    from target.live_providers import configuration
    result={k:list(v) for k,v in PROFILE['providers'].items()}
    for p in ('deepseek','bailian'):
        model=configuration(p)['model']
        if model and model not in result[p]:result[p].append(model)
    return result


def defaults(engine='legacy',provider='mock',model=None):
    return dict(system_prompt_suffix='',tool_whitelist=list(TOOLS),write_policy=dict(PROFILE['write_policy']),
                provider=provider,model=model or ('langchain-mock' if engine=='langchain' else 'mock-offline') if provider=='mock' else model or registry()[provider][0],
                temperature=None,rag_mode='keyword',allow_embedding=False)


def validate(value):
    keys=set(defaults())
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('配置字段缺失或存在未知字段')
    if not isinstance(value['system_prompt_suffix'],str) or len(value['system_prompt_suffix'])>12000:raise ValueError('追加提示词必须是12000字以内文本')
    if re.search(r'sk-[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY|(?i:Bearer)\s+[A-Za-z0-9_-]{20,}',value['system_prompt_suffix']):raise ValueError('追加提示词不能包含密钥或凭据')
    names=value['tool_whitelist']
    if not isinstance(names,list) or any(not isinstance(n,str) or n not in TOOLS for n in names) or len(set(names))!=len(names):raise ValueError('工具白名单无效')
    policy=value['write_policy']
    if not isinstance(policy,dict) or set(policy)!=set(WRITES) or any(v not in ('deny','confirm') for v in policy.values()):raise ValueError('写权限只能为deny或confirm，不能自动执行')
    if not isinstance(value['provider'],str) or not isinstance(value['model'],str) or value['provider'] not in registry() or value['model'] not in registry()[value['provider']]:raise ValueError('Provider或Model不在现有注册范围')
    t=value['temperature']
    if value['provider']=='mock' and t is not None:raise ValueError('Mock temperature必须为N/A')
    if t is not None and (type(t) not in (float,int) or not math.isfinite(t) or not 0<=t<=1):raise ValueError('temperature必须为0到1的有限数字')
    if value['rag_mode'] not in ('keyword','hybrid','vector') or type(value['allow_embedding']) is not bool:raise ValueError('RAG设置无效')
    return json.loads(json.dumps(value,allow_nan=False))


class Store:
    def __init__(self,root=None):
        self.root=Path(root) if root is not None else config.BASE_DIR/'artifacts/runtime/developer-overrides'

    def path(self,sid,owner):
        if owner!=sid or not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}',sid):raise ValueError('会话身份或路径无效')
        p=self.root/(sid+'.json')
        if self.root.is_symlink() or p.is_symlink() or (self.root/sid).is_symlink():raise ValueError('配置路径不可为符号链接')
        return p

    def load(self,sid,*,owner):
        p=self.path(sid,owner)
        if not p.exists():return None
        if p.stat().st_size>128000:raise ValueError('配置超出读取上限')
        d=json.loads(p.read_text(encoding='utf-8'))
        keys={'schema_version','session_id','revision','config_source','settings','sha256'}
        if set(d)!=keys or d['schema_version']!=1 or d['session_id']!=sid or type(d['revision']) is not int or d['revision']<1 or d['config_source'] not in ('baseline','developer_override'):raise ValueError('配置身份或版本无效')
        validate(d['settings'])
        if digest({k:v for k,v in d.items() if k!='sha256'})!=d['sha256']:raise ValueError('配置哈希不匹配')
        history=self.root/sid/'revisions'/f"{d['revision']:08d}.json"
        if history.is_symlink() or history.parent.is_symlink() or not history.resolve().is_relative_to(self.root.resolve()) or history.read_bytes()!=p.read_bytes():raise ValueError('配置与不可变revision不一致')
        return d

    @contextmanager
    def transaction(self,sid,owner):
        self.path(sid,owner);self.root.mkdir(parents=True,exist_ok=True)
        lock=self.root/(sid+'.lock')
        if lock.is_symlink():raise ValueError('锁路径无效')
        with lock.open('a+b') as f:
            if lock.stat().st_size==0:f.write(b'1');f.flush()
            f.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_EX)
            try:yield
            finally:
                f.seek(0)
                if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(f,fcntl.LOCK_UN)

    def save(self,sid,settings,*,owner,source='developer_override',expected_revision=None):
        settings=validate(settings)
        if source not in ('baseline','developer_override'):raise ValueError('配置来源无效')
        with LOCK,self.transaction(sid,owner):
            p=self.path(sid,owner);old=self.load(sid,owner=owner)
            previous=old['revision'] if old else 0
            if expected_revision is not None and previous!=expected_revision:raise ValueError('配置已被其他页面更新，请重新载入')
            directory=self.root/sid/'revisions'
            revisions=[int(f.stem) for f in directory.glob('????????.json') if f.stem.isdigit()]
            d={'schema_version':1,'session_id':sid,'revision':max([previous,*revisions])+1,'config_source':source,'settings':settings};d['sha256']=digest(d)
            raw=json.dumps(d,ensure_ascii=False,indent=2).encode();directory=self.root/sid/'revisions';directory.mkdir(parents=True,exist_ok=True)
            if directory.is_symlink() or not directory.resolve().is_relative_to(self.root.resolve()):raise ValueError('revision路径无效')
            tmp=directory/(uuid.uuid4().hex+'.tmp');revision=directory/f"{d['revision']:08d}.json"
            pointer=None
            try:
                with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                os.link(tmp,revision)  # Atomic, refuses an existing revision.
                pointer=self.root/(uuid.uuid4().hex+'.tmp')
                with pointer.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                pointer.replace(p)
            finally:
                if tmp.exists():tmp.unlink()
                if pointer is not None and pointer.exists():pointer.unlink()
            return d
