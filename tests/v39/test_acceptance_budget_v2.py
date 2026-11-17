"""Hard shared admission boundaries; zero external HTTP connections."""
import json,uuid,concurrent.futures,subprocess,sys,os
import pytest
from target.acceptance_budget import Batch,controlled_read_retry
from target.deepseek_runtime import DeepSeekError


def payload(size=0,write=False):
    body=dict(model='fixture',messages=[dict(role='user',content='x'*size)],max_tokens=4096)
    if write:body['tools']=[dict(function=dict(name='railway_pay_order'))]
    return body,json.dumps(body).encode()


@pytest.fixture
def batch(tmp_path):
    b=Batch(tmp_path/'acceptance.sqlite');b.initialize();return b


def test_fifty_http_across_providers_and_reopen_cannot_reset(batch):
    body,raw=payload()
    for n in range(50):
        uid=str(n);Batch(batch.path).reserve(uid,'deepseek' if n%2 else 'bailian',body,raw)
        batch.settle(uid,dict(prompt_tokens=5,completion_tokens=3),'response_received')
    reopened=Batch(batch.path);reopened.initialize()
    assert reopened.snapshot()['http_requests']==50 and reopened.snapshot()['observed_tokens']==400
    with pytest.raises(DeepSeekError,match='acceptance_http_budget_exhausted'):reopened.reserve('51','bailian',body,raw)
    assert reopened.snapshot()['cost'] is None


def test_token_warning_is_observability_not_a_hard_cap(batch):
    body,raw=payload(30000)
    for n in range(11):
        uid=str(n);batch.reserve(uid,'deepseek',body,raw);batch.settle(uid,dict(prompt_tokens=30000,completion_tokens=500),'response_received')
    assert batch.snapshot()['warning'] and batch.snapshot()['known_observed_tokens']==335500
    batch.reserve('unknown','bailian',body,raw);batch.settle('unknown',None,'timeout_outcome_unknown')
    state=batch.snapshot();assert state['observed_tokens'] is None and state['unresolved_request_ids']==['unknown']
    assert state['charged_or_reserved_tokens']>335500
    # New policy: provider quotas and HTTP admission remain, but project-local
    # cumulative token accounting must not block a valid request.
    bound=batch.reserve('over','bailian',body,raw);assert bound>0
    assert batch.snapshot()['remaining_tokens'] is None
    assert batch.snapshot()['warning']


def test_output_limit_and_unknown_usage_never_zero(batch):
    body,raw=payload();body['max_tokens']=4097
    with pytest.raises(DeepSeekError,match='acceptance_output_limit'):batch.reserve('bad','deepseek',body,raw)
    body,raw=payload();batch.reserve('u','deepseek',body,raw)
    batch.settle('u',dict(prompt_tokens=9),'response_body_unknown')
    state=batch.snapshot();assert state['observed_tokens'] is None and state['requests'][0]['completion'] is None
    assert state['charged_or_reserved_tokens']==state['requests'][0]['reserved_tokens']


def test_controlled_read_retry_two_only_and_transaction_zero(batch):
    body,raw=payload();batch.reserve('root','deepseek',body,raw);batch.settle('root',None,'service_unavailable')
    for n in range(2):
        with controlled_read_retry('root'):batch.reserve('retry'+str(n),'deepseek',body,raw)
        batch.settle('retry'+str(n),dict(prompt_tokens=1,completion_tokens=1),'response_received')
    with controlled_read_retry('root'),pytest.raises(DeepSeekError,match='acceptance_retry_limit'):batch.reserve('retry3','deepseek',body,raw)
    body,raw=payload(write=True);batch.reserve('write','bailian',body,raw);batch.settle('write',None,'service_unavailable')
    with controlled_read_retry('write'),pytest.raises(DeepSeekError,match='acceptance_transaction_retry_forbidden'):batch.reserve('write2','bailian',body,raw)


def test_real_guarded_sdk_admission_uses_same_persistent_batch(batch,monkeypatch):
    from tests.test_followups_mvp import FollowupMVPTests
    from langchain_core.messages import HumanMessage
    monkeypatch.setenv('TICKET_ACCEPTANCE_BATCH',str(batch.path))
    case=FollowupMVPTests();case.setUp()
    try:
        for provider in ('deepseek','bailian'):
            model,settings=case.sdk(provider)
            # Their original controlled MockTransport invokes the real SDK,
            # request hooks and observed usage settlement; no provider network.
            from web.runtime import scoped
            with scoped(dict(PROVIDER=provider,MODEL_NAME='deepseek-flash' if provider=='deepseek' else 'qwen3.8-flash')):
                model.bind(response_format=dict(type='json_object')).invoke([HumanMessage(json.dumps(dict(candidates=[dict(id='one',question='one'),dict(id='two',question='two')])) )])
        state=batch.snapshot()
        assert state['http_requests']==2 and state['observed_tokens']==60
        assert {r['provider'] for r in state['requests']}=={'bailian','deepseek'}
    finally:case.doCleanups()


def test_budget_admission_fails_closed_if_ledger_lost(tmp_path,monkeypatch):
    import httpx
    from target.request_accounting import reserve
    from target.api_usage import UsageLog
    monkeypatch.setenv('TICKET_ACCEPTANCE_BATCH',str(tmp_path/'missing.sqlite'))
    body,raw=payload()
    with pytest.raises(DeepSeekError,match='acceptance_budget_unavailable'):
        reserve(httpx.Request('POST','https://api.deepseek.com/chat/completions',content=raw),UsageLog('deepseek',tmp_path/'usage'), 'deepseek',body)


def test_two_processes_share_fifty_request_limit(batch):
    code='''import sys,json,uuid
from target.acceptance_budget import Batch
b=Batch(sys.argv[1]);body=dict(messages=[],max_tokens=16);raw=json.dumps(body).encode();n=0
for _ in range(35):
 try:
  uid=uuid.uuid4().hex;b.reserve(uid,sys.argv[2],body,raw);b.settle(uid,dict(prompt_tokens=1,completion_tokens=1),'response_received');n+=1
 except Exception as e:
  assert 'acceptance_http_budget_exhausted' in str(e),type(e).__name__;break
print(n)
'''
    procs=[subprocess.Popen([sys.executable,'-B','-c',code,str(batch.path),name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for name in ('deepseek','bailian')]
    outputs=[p.communicate(timeout=30) for p in procs]
    assert all(p.returncode==0 for p in procs),outputs
    assert sum(int(o[0]) for o in outputs)==50 and batch.snapshot()['http_requests']==50
