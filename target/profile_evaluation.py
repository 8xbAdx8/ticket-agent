"""Explicit offline profile gateway. Never regrades or replaces B's results."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import socket
import uuid
import config
from target.dev_overrides import PROFILE,digest
from target.execution_config import resolve_effective_config,scope


@contextmanager
def offline_baseline(root,engine='legacy'):
    """Trusted test entry: fixed fixture/clock, no Override read or network."""
    from web.runtime import scoped
    from data.seed import build_db
    root=Path(root).resolve();base=(config.BASE_DIR/'artifacts/runtime').resolve()
    if root==base or not root.is_relative_to(base):raise ValueError('测试目录必须独立位于runtime')
    root.mkdir(parents=True,exist_ok=False)
    fixed=datetime.fromisoformat(PROFILE['clock'])
    old_now,old_today=config.now,config.today
    connect=socket.socket.connect;connect_ex=socket.socket.connect_ex
    def reject(*args,**kwargs):raise OSError('正式Baseline禁止网络')
    values=dict(DB_PATH=root/'tickets.db',TRACE_DIR=root/'traces',PROVIDER='mock',ENGINE=engine,MODEL_NAME='langchain-mock' if engine=='langchain' else 'mock-offline',API_KEY='',USE_HTTP_MOCK=False,USE_VECTOR_RAG=False,LC_TOOLSET='all',POLICY_PATH=config.BASE_DIR/'data/policies.md',CURRENT_USER_PHONE='13800000001',OTHER_USER_PHONE='13900000002',MAX_STEPS=8,TOP_K=3)
    environment={'AGENT_RAG_MODE':'','RAG_ALLOW_NETWORK':'0','AGENT_MUTATIONS':'{}','LANGSMITH_TRACING':'false','LANGCHAIN_TRACING_V2':'false','TICKET_PROFILE_BATCH_ID':root.name}
    with scoped(values,environment):
        from target import rag
        old_cache=rag._CACHE
        try:
            rag._CACHE=None
            config.now=lambda:fixed;config.today=lambda:fixed.date()
            socket.socket.connect=socket.socket.connect_ex=reject
            effective=resolve_effective_config('formal-baseline','baseline',engine=engine)
            build_db(config.DB_PATH)
            with scope(effective):yield effective
        finally:
            config.now,config.today=old_now,old_today
            socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
            rag._CACHE=old_cache


def run_batch(mode,*,session_id=None,messages=None,case_ids=None,engine='legacy',executor=None):
    """B may supply its original executor; absent it, record inputs without grading.

    This gateway never copies/reimplements the 103 original expect assertions.
    Unsupported setup cases require the original B executor instead of being
    silently simplified or reported as passing.
    """
    if mode not in ('baseline','developer_custom'):raise ValueError('执行模式无效')
    batch_id=uuid.uuid4().hex
    root=config.BASE_DIR/'artifacts/runtime/profile-evaluations'/mode/batch_id
    if mode=='baseline':
        catalogue=json.loads((config.BASE_DIR/'web/datasets/b_v32_20261020/case_catalog.json').read_text(encoding='utf-8'))
        ids=case_ids or [r['id'] for r in catalogue]
        if set(ids)-{r['id'] for r in catalogue}:raise ValueError('未知正式用例')
        with offline_baseline(root,engine) as effective:
            rows=[]
            for case in catalogue:
                if case['id'] not in ids:continue
                row={'case_id':case['id'],'input_sha256':digest(case),'expect_sha256':digest(case.get('expect',{}))}
                if executor:row['result']=executor(case,effective)
                else:row.update(status='not_verified',reason='未提供B原始独立执行器；只核验原输入与配置，不能宣称断言通过')
                rows.append(row)
    else:
        if not session_id or not messages:raise ValueError('自定义实验必须指定会话及输入')
        from web.runtime import Conversation
        root.mkdir(parents=True,exist_ok=False)
        effective=resolve_effective_config(session_id,'developer_custom',engine=engine)
        if effective.provider!='mock':raise ValueError('本评估入口只允许离线Mock，不能调用真实API')
        s=Conversation('lab',engine=engine,sid=session_id,root=root,execution_mode='developer_custom')
        from web.runtime import scoped
        with scoped({}, {'TICKET_PROFILE_BATCH_ID':batch_id}):rows=[s.send(m,uuid.uuid4().hex) for m in messages]
    identity={k:getattr(effective,k) for k in ('execution_mode','config_source','baseline_id','override_revision','fixture_id','config_hash')}
    identity['batch_id']=batch_id
    report={'schema':'ticket-profile-evaluation/1','identity':identity,'label':'Formal Baseline configuration' if mode=='baseline' else 'Developer Experiment · Non-Baseline',
            'official_scores_replaced':False,'assertion_executor':'B original callback' if executor and mode=='baseline' else 'not_run' if mode=='baseline' else 'developer_only','rows':rows}
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return root/'report.json'
