import json
from dataclasses import FrozenInstanceError
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
import config
from target.dev_overrides import Store,defaults,digest
from target.execution_config import resolve_effective_config


def test_revision_atomic_pointer_history_and_sha(tmp_path):
    s=Store(tmp_path);a=s.save('own',defaults(),owner='own');old=(tmp_path/'own/revisions/00000001.json').read_bytes()
    v=defaults();v['system_prompt_suffix']='简洁回答';b=s.save('own',v,owner='own',expected_revision=1)
    assert (a['revision'],b['revision'])==(1,2) and s.load('own',owner='own')==b
    assert old==(tmp_path/'own/revisions/00000001.json').read_bytes()
    assert digest({k:v for k,v in b.items() if k!='sha256'})==b['sha256']
    assert not list(tmp_path.rglob('*.tmp'))


@pytest.mark.parametrize('field,value',[('extra',1),('tool_whitelist',['unknown']),('tool_whitelist',['query_tickets','query_tickets']),('provider','fake'),('provider',[]),('model','https://external.invalid'),('temperature',float('nan')),('temperature',1.2),('temperature',True),('write_policy',{'pay_order':'auto'}),('allow_embedding','yes'),('rag_mode','unknown')])
def test_invalid_settings_never_save(tmp_path,field,value):
    d=defaults();d[field]=value
    with pytest.raises(ValueError):Store(tmp_path).save('own',d,owner='own')
    assert not (tmp_path/'own.json').exists()


@pytest.mark.parametrize('sid,owner',[('../escape','../escape'),('own','foreign'),('a/b','a/b'),('',''),('x'*97,'x'*97)])
def test_owner_and_path_fenced(tmp_path,sid,owner):
    with pytest.raises(ValueError):Store(tmp_path).load(sid,owner=owner)


def test_tamper_and_invalid_json_fail_closed(tmp_path):
    s=Store(tmp_path);d=s.save('own',defaults(),owner='own');p=tmp_path/'own.json'
    p.write_text('{broken',encoding='utf-8')
    with pytest.raises(ValueError):s.load('own',owner='own')
    d['settings']['tool_whitelist'].append('forbidden');p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(ValueError):s.load('own',owner='own')


def test_concurrent_revision_compare_and_swap(tmp_path):
    s=Store(tmp_path);s.save('own',defaults(),owner='own')
    def save(i):
        try:return s.save('own',defaults(),owner='own',expected_revision=1)['revision']
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(save,[1,2]))
    assert sorted(map(str,results))==['2','rejected']


def test_baseline_never_reads_override_and_config_frozen(tmp_path):
    s=Store(tmp_path)
    with patch.object(s,'load',side_effect=AssertionError('baseline cannot read store')):
        e=resolve_effective_config('own','baseline',store=s)
    assert e.config_source=='baseline' and e.override_revision==0 and e.provider=='mock'
    with pytest.raises(FrozenInstanceError):e.provider='bailian'
    assert isinstance(e.write_policy,tuple)


def test_baseline_prompt_ignores_runtime_validation_profile(monkeypatch):
    monkeypatch.delenv('TICKET_API_VALIDATION_PROFILE',raising=False)
    original=resolve_effective_config('formal','baseline',engine='langchain')
    monkeypatch.setenv('TICKET_API_VALIDATION_PROFILE','v352')
    monkeypatch.setattr(config,'CURRENT_USER_PHONE','13900000002')
    inherited=resolve_effective_config('formal','baseline',engine='langchain')
    assert inherited.prompt==original.prompt
    assert inherited.prompt_sha256==original.prompt_sha256
    assert inherited.config_hash==original.config_hash


def test_suffix_revision_actual_prompt_and_scope(tmp_path):
    s=Store(tmp_path);a=resolve_effective_config('own','developer_custom',store=s)
    d=defaults();d['system_prompt_suffix']='请用短句回答';s.save('own',d,owner='own')
    b=resolve_effective_config('own','developer_custom',store=s);other=resolve_effective_config('other','developer_custom',store=s)
    assert b.prompt!=a.prompt and b.prompt_sha256!=a.prompt_sha256 and b.override_revision==1
    assert '必须调用相应工具' in b.prompt and '请用短句回答' not in other.prompt


@pytest.mark.parametrize('provider,model',[('deepseek','deepseek-flash'),('bailian','qwen3.8-flash')])
def test_provider_temperature_and_readonly_intersection(tmp_path,provider,model):
    s=Store(tmp_path);d=defaults(provider=provider,model=model);d['temperature']=0.25;s.save('own',d,owner='own')
    e=resolve_effective_config('own','developer_custom',store=s,full_tools=False)
    assert set(e.tool_whitelist)=={'query_tickets','search_policy'} and e.temperature==0.25 and e.temperature_applicable
    assert all(v=='deny' for n,v in e.write_policy)


def test_restore_retains_history(tmp_path):
    s=Store(tmp_path);d=defaults();d['tool_whitelist']=[];s.save('own',d,owner='own')
    s.save('own',defaults(),owner='own',source='baseline')
    e=resolve_effective_config('own','developer_custom',store=s)
    assert e.config_source=='baseline' and e.override_revision==2 and len(e.tool_whitelist)==8


def test_formal_103_identity_without_regrading(tmp_path):
    from target.profile_evaluation import run_batch
    with patch('target.dev_overrides.Store.load',side_effect=AssertionError('must not read overrides')):
        p=run_batch('baseline')
    d=json.loads(p.read_text(encoding='utf-8'))
    assert len(d['rows'])==103 and all(r['status']=='not_verified' for r in d['rows'])
    assert d['identity']['execution_mode']=='baseline' and not d['official_scores_replaced']


def test_failed_pointer_replace_preserves_valid_revision_and_retry(tmp_path):
    from pathlib import Path
    s=Store(tmp_path);a=s.save('own',defaults(),owner='own')
    with patch.object(Path,'replace',side_effect=OSError('injected pointer failure')):
        with pytest.raises(OSError):s.save('own',defaults(),owner='own')
    assert s.load('own',owner='own')==a and not list(tmp_path.rglob('*.tmp'))
    b=s.save('own',defaults(),owner='own');assert b['revision']==3
    assert len(list((tmp_path/'own/revisions').glob('*.json')))==3
