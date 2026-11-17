import hashlib
import json
from unittest.mock import patch
import pytest
import config
from target import tools
from target.agent import Agent
from target.dev_overrides import Store,defaults
from target.execution_config import resolve_effective_config,scope
from web.runtime import Conversation,scoped
from tests.test_refund_by_train import db,dump


@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_actual_dispatch_blocked_in_both_engine_adapters(db,tmp_path,engine):
    store=Store(tmp_path/'overrides');d=defaults(engine);d['tool_whitelist']=['search_policy'];store.save('own',d,owner='own')
    e=resolve_effective_config('own','developer_custom',engine=engine,store=store)
    before=dump(db)
    with scoped(dict(DB_PATH=db,TRACE_DIR=tmp_path/'traces',PROVIDER='mock',ENGINE=engine,LC_TOOLSET='all')):
        with scope(e):
            if engine=='legacy':result,ok,_=tools.dispatch('query_order',{});assert not ok and '禁止' in result['error']
            else:
                from target.langchain_agent import adapt_tool,BackendToolFailure
                with pytest.raises(BackendToolFailure):adapt_tool('query_order').invoke({})
    assert dump(db)==before


@pytest.mark.parametrize('permission',['deny','confirm'])
def test_write_policy_does_not_authorize_by_itself(db,tmp_path,permission):
    s=Store(tmp_path/'overrides');d=defaults();d['write_policy']['cancel_order']=permission;s.save('own',d,owner='own')
    e=resolve_effective_config('own','developer_custom',store=s);before=dump(db)
    with scoped(dict(DB_PATH=db,TRACE_DIR=tmp_path/'traces')):
        with scope(e):result,ok,_=tools.dispatch('cancel_order',{'order_id':'OD1'})
    assert not ok and dump(db)==before


@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_final_prompt_matches_actual_model_and_sidecar(tmp_path,engine):
    from target.providers import MockProvider
    from data.seed import build_db
    store=Store(tmp_path/'overrides');d=defaults(engine);d['system_prompt_suffix']='[实验提示-证据]';store.save('own',d,owner='own')
    e=resolve_effective_config('own','developer_custom',engine=engine,store=store)
    values=dict(DB_PATH=tmp_path/'tickets.db',TRACE_DIR=tmp_path/'traces',ENGINE=engine,PROVIDER='mock',LC_TOOLSET='all')
    with scoped(values):
        build_db();agent=Agent(engine=engine,effective_config=e);agent.chat('own','查明天上海到杭州的高铁二等座')
        if engine=='legacy':actual=agent.sessions['own'][0]['content']
        else:actual=agent.langchain_engine.model.received_messages[0][0].content
    assert actual==e.prompt and hashlib.sha256(actual.encode()).hexdigest()==e.prompt_sha256
    sidecars=[json.loads(p.read_text(encoding='utf-8')) for p in (tmp_path/'traces/config-events').glob('*.json')]
    assert sidecars and all(r['prompt_sha256']==e.prompt_sha256 for r in sidecars)
    assert all(r['override_revision']==1 for r in sidecars)


def test_saved_override_rebuilds_next_round_preserves_history():
    s=Conversation('user');store=Store();d=defaults();store.save(s.sid,d,owner=s.sid)
    s.send('查明天上海到杭州的高铁二等座','one');first=s.agent;first_hash=s.effective_hash
    d['system_prompt_suffix']='第二轮简洁回答';store.save(s.sid,d,owner=s.sid)
    assert s.agent is first and s.effective_hash==first_hash
    s.send('退票手续费怎么算','two')
    assert s.agent is not first and s.effective_hash!=first_hash and len(s.history)==2
    assert '第二轮简洁回答' in s.agent.sessions[s.sid][0]['content']


def test_frozen_run_does_not_follow_store_edits(tmp_path):
    s=Store(tmp_path);s.save('own',defaults(),owner='own');e=resolve_effective_config('own','developer_custom',store=s)
    with scope(e):
        d=defaults();d['tool_whitelist']=[];s.save('own',d,owner='own')
        from target.execution_config import tool_denial
        assert tool_denial('query_order') is None
    newer=resolve_effective_config('own','developer_custom',store=s)
    with scope(newer):assert tool_denial('query_order')


def test_provider_switch_never_inherits_fee_consent():
    s=Conversation('user');d=defaults(provider='bailian',model='qwen3.8-flash');Store().save(s.sid,d,owner=s.sid)
    s.config_cost_consent=(s.sid,'deepseek',1)
    with patch('web.runtime.live_ready',return_value=True),patch('web.runtime.Agent') as agent:
        with pytest.raises(ValueError,match='服务已切换'):s.send('查票','one')
        assert s.config_cost_consent is None
        with pytest.raises(ValueError,match='费用授权'):s.send('查票','two')
        agent.assert_not_called()


def test_readonly_restore_never_executes_or_loads_latest_override():
    s=Conversation('user');s.read_only=True
    with patch('target.dev_overrides.Store.load',side_effect=AssertionError('history must not load current')):
        with pytest.raises(ValueError,match='只读'):s.send('支付','one')


@pytest.mark.parametrize('provider',['deepseek','bailian'])
def test_temperature_reaches_real_sdk_constructor_offline(provider):
    from types import SimpleNamespace
    if provider=='deepseek':
        from target import deepseek_runtime as runtime
        target='langchain_deepseek.ChatDeepSeek'
    else:
        from target import bailian_runtime as runtime
        target='langchain_openai.ChatOpenAI'
    with patch.object(runtime,'validate_configuration'),patch.object(runtime,'guarded_client',return_value=object()),patch.dict('os.environ',{'DASHSCOPE_API_KEY':'offline-only'}),patch(target) as constructor:
        runtime.make_model(SimpleNamespace(timeout=1,max_output_tokens=100),temperature=0.25)
        assert constructor.call_args.kwargs['temperature']==0.25


def test_page_payment_and_refund_cannot_bypass_deny(db):
    import shutil
    from web.order_actions import execute
    s=Conversation('user');s.root.mkdir(parents=True,exist_ok=True);shutil.copy2(db,s.root/'tickets.db')
    d=defaults();d['write_policy']['pay_order']='deny';d['write_policy']['cancel_order']='deny';Store().save(s.sid,d,owner=s.sid)
    before=dump(s.root/'tickets.db')
    with pytest.raises(ValueError,match='禁止'):s.confirm_demo_payment('OD1',100,'alipay',confirmed=True)
    with pytest.raises(ValueError,match='禁止'):execute(s,'refund',{'order_id':'OD1'},confirmed=True)
    assert dump(s.root/'tickets.db')==before


@pytest.mark.parametrize('provider,model',[('deepseek','deepseek-flash'),('bailian','qwen3.8-flash')])
def test_direct_langchain_rejects_model_mismatch_before_construction(tmp_path,provider,model):
    from target.langchain_agent import LangChainAgent
    from target.agent import SYSTEM_PROMPT
    store=Store(tmp_path/'overrides')
    store.save('own',defaults(provider=provider,model=model),owner='own')
    effective=resolve_effective_config('own','developer_custom',store=store)
    with patch.multiple(config,PROVIDER=provider,MODEL_NAME='wrong-model'):
        with pytest.raises(ValueError,match='Model'):
            LangChainAgent(SYSTEM_PROMPT,effective_config=effective)


@pytest.mark.parametrize('engine',['legacy','langchain'])
@pytest.mark.parametrize('restriction',['whitelist','write_policy'])
def test_hostile_model_proposal_blocked_at_execution_boundary(db,tmp_path,engine,restriction):
    from target.providers import _as_msg
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult,ChatGeneration
    class Hostile(BaseChatModel):
        calls:int=0
        @property
        def _llm_type(self):return 'offline-hostile-policy-test'
        def bind_tools(self,tools,**kwargs):return self
        def _generate(self,messages,**kwargs):
            self.calls+=1
            message=AIMessage(content='' if self.calls==1 else '未执行',tool_calls=[{'id':'blocked-call','name':'cancel_order','args':{'order_id':'OD1'},'type':'tool_call'}] if self.calls==1 else [])
            return ChatResult(generations=[ChatGeneration(message=message)])
    class Legacy:
        name='mock';last_usage={'prompt':0,'completion':0};calls=0
        def chat(self,messages,schemas):
            self.calls+=1
            return _as_msg(None,[('cancel_order',{'order_id':'OD1'})]) if self.calls==1 else _as_msg('未执行',[])
    store=Store(tmp_path/'overrides');d=defaults(engine)
    if restriction=='write_policy':d['write_policy']['cancel_order']='deny'
    else:d['tool_whitelist'].remove('cancel_order')
    store.save('hostile',d,owner='hostile')
    e=resolve_effective_config('hostile','developer_custom',engine=engine,store=store);before=dump(db)
    with scoped(dict(DB_PATH=db,TRACE_DIR=tmp_path/'traces',PROVIDER='mock',ENGINE=engine,LC_TOOLSET='all')):
        if engine=='legacy':agent=Agent(engine=engine,effective_config=e,provider=Legacy())
        else:
            from target.langchain_agent import LangChainAgent
            agent=LangChainAgent(e.prompt,effective_config=e,model=Hostile())
        result=agent.chat('hostile','退票OD1')
    assert dump(db)==before and len(result)==10
    assert all(not c['ok'] for s in result['steps'] for c in s['calls'])
    events=[json.loads(l) for l in (tmp_path/'traces/run_events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert any(e['event_type']=='config_permission_denied' and e['status']=='blocked' and e['run_id'] for e in events)


def test_formal_import_rejects_custom_even_with_owner_spoof():
    from web.formal_results import parse_formal_results
    payload={'schema':'ticket-agent-b-formal-results/1','batch':{'execution_mode':'developer_custom','owner':'B'},'results':[]}
    with pytest.raises(ValueError,match='Developer'):parse_formal_results(json.dumps(payload).encode(),[],'own')


def test_custom_report_separate_namespace_and_unmodified_formal_scores():
    from target.profile_evaluation import run_batch
    s=Conversation('user');Store().save(s.sid,defaults(),owner=s.sid)
    p=run_batch('developer_custom',session_id=s.sid,messages=['查询我的订单'])
    d=json.loads(p.read_text(encoding='utf-8'))
    assert '/developer_custom/' in p.as_posix() and d['identity']['execution_mode']=='developer_custom'
    assert d['label']=='Developer Experiment · Non-Baseline' and not d['official_scores_replaced']


def test_editor_save_next_execution_and_baseline_view_never_construct_agent():
    from streamlit.testing.v1 import AppTest
    s=Conversation('user')
    a=AppTest.from_string('import streamlit as st\nfrom web.developer_config import editor\neditor(st.session_state.s)',default_timeout=30)
    a.session_state.s=s
    with patch('web.runtime.Agent') as agent:
        a.run();assert not a.exception
        a.text_area(key='dev_suffix_'+s.sid).set_value('简洁实验')
        next(b for b in a.button if b.label=='保存会话配置').click().run()
        assert not a.exception and Store().load(s.sid,owner=s.sid)['revision']==1
        a.radio(key='dev_profile_view').set_value('正式 Baseline（只读）').run()
        assert not a.exception and not any(b.label=='保存会话配置' for b in a.button)
        agent.assert_not_called()


def test_pending_langchain_proposal_keeps_revision_and_requires_cancel(db):
    import shutil
    s=Conversation('lab',engine='langchain',execution_mode='developer_custom');s.root.mkdir(parents=True,exist_ok=True);shutil.copy2(db,s.root/'tickets.db')
    d=defaults('langchain');Store().save(s.sid,d,owner=s.sid)
    before=dump(s.root/'tickets.db')
    s.send('订2026-12-10上海到杭州的高铁二等座','proposal')
    assert s.pending_action() and s.agent.effective_config.override_revision==1
    original=dict(s.pending_action());d['write_policy']['lock_seat']='deny';Store().save(s.sid,d,owner=s.sid)
    with pytest.raises(ValueError,match='旧配置'):s.confirm_action(True,'approved')
    assert s.pending_action()==original and dump(s.root/'tickets.db')==before
    s.confirm_action(False,'cancel');assert not s.pending_action()
    s.send('查询我的订单','new-run');assert s.agent.effective_config.override_revision==2


def test_baseline_gateway_fixed_clock_network_and_restore():
    from target.profile_evaluation import offline_baseline
    import socket,uuid
    old_now,old_connect=config.now,socket.socket.connect
    directory=config.BASE_DIR/'artifacts/runtime/profile-gateway-tests'/uuid.uuid4().hex
    with offline_baseline(directory) as e:
        assert config.now().isoformat()=='2026-10-20T12:00:00'
        assert Agent().effective_config is e
        with socket.socket() as s:
            with pytest.raises(OSError,match='禁止网络'):s.connect(('127.0.0.1',1))
    assert config.now is old_now and socket.socket.connect is old_connect


@pytest.mark.parametrize('provider,model,endpoint',[('deepseek','deepseek-flash','https://api.deepseek.com'),('bailian','qwen3.8-flash','https://dashscope.aliyuncs.com/compatible-mode/v1')])
def test_sdk_mock_transport_captures_exact_temperature_and_prompt(tmp_path,provider,model,endpoint):
    import httpx
    from langchain_core.messages import SystemMessage,HumanMessage
    from target import deepseek_runtime,bailian_runtime
    runtime=deepseek_runtime if provider=='deepseek' else bailian_runtime
    seen=[]
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'phase6-offline-sdk','object':'chat.completion','created':1,'model':model,
            'choices':[{'index':0,'message':{'role':'assistant','content':'你好'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
    s=Store(tmp_path/'overrides');d=defaults(provider=provider,model=model);d['temperature']=0.25;d['system_prompt_suffix']='测试追加';s.save('sdk',d,owner='sdk')
    e=resolve_effective_config('sdk','developer_custom',full_tools=False,store=s)
    with patch.multiple(config,PROVIDER=provider,MODEL_NAME=model,BASE_URL=endpoint,API_KEY='offline-phase6-only'),patch.dict('os.environ',{'DEEPSEEK_API_KEY':'offline-phase6-only','DASHSCOPE_API_KEY':'offline-phase6-only','DASHSCOPE_BASE_URL':endpoint,'TICKET_API_USAGE_DIR':str(tmp_path/'usage')}):
        sdk=runtime.make_model(runtime.Settings(ledger_path=tmp_path/'ledger.db'),transport=httpx.MockTransport(respond),temperature=e.temperature)
        try:sdk.invoke([SystemMessage(e.prompt),HumanMessage('你好')])
        finally:sdk.http_client.close()
    assert len(seen)==1 and seen[0]['temperature']==0.25 and seen[0]['model']==model
    assert hashlib.sha256(seen[0]['messages'][0]['content'].encode()).hexdigest()==e.prompt_sha256


def test_page_preview_config_change_requires_new_preview(db):
    import shutil
    from tests.test_refund_by_train import get_quote
    from web.order_actions import execute
    s=Conversation('user');s.root.mkdir(parents=True,exist_ok=True);shutil.copy2(db,s.root/'tickets.db')
    d=defaults();Store().save(s.sid,d,owner=s.sid);q=get_quote(s.root/'tickets.db');s.bind_page_proposal(q)
    d['system_prompt_suffix']='另一revision';Store().save(s.sid,d,owner=s.sid)
    before=dump(s.root/'tickets.db')
    with pytest.raises(ValueError,match='配置已变更'):execute(s,'refund',q,confirmed=True)
    assert dump(s.root/'tickets.db')==before


def test_selected_rag_mode_reaches_actual_retrieval():
    s=Conversation('user');d=defaults();d['rag_mode']='hybrid';Store().save(s.sid,d,owner=s.sid)
    with patch('target.rag_service.retrieve',return_value={'question':'退票手续费怎么算','hits':[],'count':0}) as retrieve:
        s.send('退票手续费怎么算','rag-run')
    assert retrieve.called
    assert s.agent.effective_config.rag_mode=='hybrid' and not s.agent.effective_config.allow_embedding


def test_baseline_does_not_inherit_policy_identity_or_rag_cache(tmp_path):
    from target.profile_evaluation import offline_baseline
    from target import rag
    import uuid
    old_policy,old_phone,old_cache=config.POLICY_PATH,config.CURRENT_USER_PHONE,rag._CACHE
    try:
        config.POLICY_PATH=tmp_path/'untrusted-policy.md';config.CURRENT_USER_PHONE='foreign';rag._CACHE=['foreign-cache']
        directory=config.BASE_DIR/'artifacts/runtime/profile-gateway-tests'/uuid.uuid4().hex
        with offline_baseline(directory):
            assert config.POLICY_PATH==config.BASE_DIR/'data/policies.md' and config.CURRENT_USER_PHONE=='13800000001'
            assert rag._CACHE is None
        assert config.CURRENT_USER_PHONE=='foreign' and rag._CACHE==['foreign-cache']
    finally:config.POLICY_PATH,config.CURRENT_USER_PHONE,rag._CACHE=old_policy,old_phone,old_cache


def test_custom_save_trace_false_still_has_mandatory_config_identity(tmp_path):
    from target.execution_config import run_identity
    e=resolve_effective_config('no-public','developer_custom')
    with scoped(dict(TRACE_DIR=tmp_path/'trace',PROVIDER='mock',ENGINE='legacy')):
        a=Agent(effective_config=e);a.chat('no-public','你好',save_trace=False)
    identity=run_identity(a.last_audit_report['trace_id'],'no-public')
    assert identity['execution_mode']=='developer_custom' and not (tmp_path/'trace/traces.jsonl').exists()


def test_restore_returns_original_session_model_not_last_override():
    s=Conversation('user',engine='legacy');d=defaults('langchain');Store().save(s.sid,d,owner=s.sid)
    s.send('查询我的订单','override');assert s.engine=='langchain'
    Store().save(s.sid,s.baseline_settings(),owner=s.sid,source='baseline')
    s.send('查询我的订单','baseline');assert s.engine=='legacy' and s.agent.effective_config.model=='mock-offline'


def test_legacy_runtime_sidecar_observes_actual_langchain_subset_and_mock_na(tmp_path):
    from data.seed import build_db
    with scoped(dict(DB_PATH=tmp_path/'tickets.db',TRACE_DIR=tmp_path/'trace',PROVIDER='mock',ENGINE='langchain',LC_TOOLSET='all')):
        build_db();a=Agent(engine='langchain',tool_names=['query_order']);a.chat('observed','查询我的订单')
    records=[json.loads(p.read_text(encoding='utf-8')) for p in (tmp_path/'trace/config-events').glob('*.json')]
    assert records and all(r['tool_whitelist']==['query_order'] and not r['temperature_applicable'] for r in records)
