"""Explicit two-provider policy acceptance. Default/--prepare never calls a model."""
import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))


def prepare():
    from target.v352_validation import AUTH,QUESTION,embedding_settings,cached_source,cache_survey,canonical_hash,new_json,read
    from target.rag_protection import BASELINE,working_index,tree_hashes,hash_tree,logical_snapshot
    from target.rag_store import documents
    from target.embeddings import EmbeddingProvider
    destination=AUTH/'prepared'
    if (destination/'frozen.json').exists():return read(destination/'frozen.json')
    settings=embedding_settings();survey=cache_survey([QUESTION],settings,cached_source())
    if survey['missing_queries']:raise ValueError('policy_query_not_cached_no_embedding_authorized')
    destination.mkdir(parents=True,exist_ok=False)
    cache=destination/'embedding-cache.db';shutil.copyfile(cached_source(),cache)
    provider=EmbeddingProvider(replace(settings,cache=cache))
    with working_index(BASELINE,provider,parent=destination/'query-work') as (index,receipt):
        evidence=index.retrieve(QUESTION,'hybrid',3,.35,require_real=True,allow_network=False,quality_profile='v351')
        logical=logical_snapshot(index)
    result={'question':QUESTION,'hits':evidence['hits'],'count':len(evidence['hits'])}
    frozen={'schema':'ticket-v352-frozen-policy/1','question':QUESTION,'mode':'hybrid','quality_profile':'v351','top_k':3,'threshold':.35,
        'source_tree_sha256':hash_tree(tree_hashes(BASELINE)),'policy_chunks_sha256':canonical_hash(documents(ROOT/'data/policies.md')),
        'tool_result':result,'tool_result_sha256':canonical_hash(result),'retrieval':evidence,'logical_index':logical,
        'execution':'actual_cached_chroma_on_copy_no_generation','real_generation_requests':0,'real_embedding_requests':0}
    new_json(destination/'frozen.json',frozen);return frozen


@contextmanager
def environment(values):
    import config
    previous={k:os.environ.get(k) for k in values}
    os.environ.update(values);importlib.reload(config)
    try:yield
    finally:
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        importlib.reload(config)


def _execute_pair(*,model_factory=None,resume_unattempted_qwen=False):
    from target.v352_validation import AUTH,QUESTION,read,new_json,canonical_hash,embedding_settings,cache_survey
    from target.rag_protection import BASELINE,tree_hashes,hash_tree,copy_workspace
    from target.request_accounting import snapshot
    from target.live_providers import isolated_environment
    from target.deepseek_runtime import safe_error
    import config
    frozen=prepare()
    if hash_tree(tree_hashes(BASELINE))!=frozen['source_tree_sha256']:raise ValueError('immutable_source_changed_since_prepare')
    from target.rag_store import documents
    if canonical_hash(documents(ROOT/'data/policies.md'))!=frozen['policy_chunks_sha256']:
        raise ValueError('policy_corpus_changed_before_generation')
    if cache_survey([QUESTION],embedding_settings(),AUTH/'prepared/embedding-cache.db')['missing_queries']:
        raise ValueError('frozen_query_cache_integrity_failed')
    records=[];continued_from=None
    if resume_unattempted_qwen:
        previous=read(AUTH/'paired-report.json')
        qwen=next(r for r in previous['records'] if r['provider']=='bailian')
        deep=next(r for r in previous['records'] if r['provider']=='deepseek')
        if not deep.get('protocol_closure') or not deep.get('agent_completed'):
            raise ValueError('resume_requires_completed_deepseek_evidence')
        continued_from=hashlib.sha256((AUTH/'paired-report.json').read_bytes()).hexdigest()
        new_json(AUTH/('qwen-resume-'+uuid.uuid4().hex+'.json'),
                 {'reason':'Explicit current Qwen run, no cumulative quota', 'original_report_sha256':continued_from})
        records=[deep]
    else:
        new_json(AUTH/'generation-attempt.json',{'explicit_command_authorization':True,'local_request_limit':None,
            'evidence_mode':'offline_sdk_stub' if model_factory else 'real_api','tool_result_sha256':frozen['tool_result_sha256']})
    before=tree_hashes(BASELINE);new_requests=0
    for provider in (('bailian',) if resume_unattempted_qwen else ('bailian','deepseek')):
        root=AUTH/'runs'/(provider+'-resumed-'+uuid.uuid4().hex if resume_unattempted_qwen else provider);root.mkdir(parents=True,exist_ok=False)
        workspace,_=copy_workspace(BASELINE,root/'chroma-work')
        shutil.copyfile(AUTH/'prepared/embedding-cache.db',workspace/'embedding-cache.db')
        env=isolated_environment(provider,root,profile='v352')
        env.update(TICKET_API_VALIDATION_PROFILE='v352',TICKET_FROZEN_RAG_EVIDENCE=str(AUTH/'prepared/frozen.json'),DEEPSEEK_MAX_MODEL_CALLS='2',BAILIAN_MAX_MODEL_CALLS='2',AGENT_MAX_STEPS='2',AGENT_RAG_MODE='hybrid',RAG_TOP_K='3',RAG_VECTOR_THRESHOLD='0.35',RAG_INDEX_DIR=str(workspace/'index'),RAG_EMBEDDING_CACHE=str(workspace/'embedding-cache.db'),
                   TICKET_CASE_ID='v352-shared-policy',DASHSCOPE_EMBEDDING_BASE_URL=embedding_settings().base_url)
        with environment(env):
            from data.seed import build_db
            from target.agent import Agent
            from target import bailian_runtime,deepseek_runtime
            build_db(config.DB_PATH)
            runtime=bailian_runtime if provider=='bailian' else deepseek_runtime
            model=None;agent=None;result=None;error=None
            try:
                if model_factory:model=model_factory(provider,runtime)
                agent=Agent(model=model) if model is not None else Agent()
                result=agent.chat('v352-'+provider+'-'+uuid.uuid4().hex,QUESTION)
            except Exception as exc:error=safe_error(exc)
            finally:
                if model is not None:model.root_client.close()
                elif agent is not None:
                    try:agent.langchain_engine.model.root_client.close()
                    except Exception:pass
            live=(agent.langchain_engine.last_live_run or {}) if agent is not None else {}
            events=live.get('events',[])
            tools=[e for e in events if e.get('event')=='tool_end' and e.get('tool')=='search_policy']
            payloads=[(e,p) for e in events if e.get('event')=='http_dispatch_evidence' for p in e.get('tool_payloads',[])]
            received=[p for e,p in payloads if any(r.get('event')=='http_response' and r.get('request_id')==e['request_id'] and r.get('http_status')==200 for r in events)]
            correct=bool(len(tools)==1 and tools[0].get('ok') and tools[0].get('executed') and canonical_hash(tools[0]['result'])==frozen['tool_result_sha256'])
            delivered=bool(correct and any(p['parsed_result_sha256']==frozen['tool_result_sha256'] and p['tool_call_id']==tools[0]['call_id'] for p in received))
            raw=next((e['text'] for e in reversed(events) if e.get('event')=='model_final'),None)
            ragfile=config.TRACE_DIR/'rag_runs.jsonl'
            rag=[json.loads(s) for s in ragfile.read_text(encoding='utf-8').splitlines()] if ragfile.exists() else []
            answer=next((r for r in reversed(rag) if r.get('schema')=='ticket-rag-answer/1'),None)
            request_count=sum(e.get('event')=='http_request' for e in events)
            if model_factory is None:new_requests+=request_count
            closure=bool(correct and delivered and raw and len([e for e in events if e.get('event')=='model_response'])==2)
            expected_model='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash'
            identities=live.get('actual_models',[])
            identity_verified=bool(identities and all(isinstance(m,str) and (m==expected_model or m.startswith(expected_model+'-')) for m in identities))
            record={'provider':provider,'evidence_mode':'offline_sdk_stub' if model_factory else 'real_api',
                'status':('protocol_passed_guard_rejected' if error else 'protocol_passed') if closure else 'failed_or_incomplete',
                'real_function_calling_verified':closure and identity_verified and model_factory is None,
                'model_identity_verified':identity_verified,'actual_models':identities,'agent_completed':bool(result and not error),
                'protocol_closure':closure,'model_response_received':live.get('model_response_received',False),
                'tool_execution_verified':correct,'tool_result_delivered_with_http200':delivered,
                'policy_tool_call_count':len(tools),
                'expected_evidence_sha256':frozen['tool_result_sha256'],'delivered_evidence':received,
                'original_model_reply':raw,'final_display_result':result['reply'] if result else None,
                'faithfulness':answer,'public_trace':result,'live_evidence':live,'error':error,
                'generation_requests':request_count,'real_generation_requests':0 if model_factory else request_count,
                'generation_latency_ms':sum(e['latency_ms'] for e in events if e.get('event')=='model_response') if any(e.get('event')=='model_response' for e in events) else None,
                'retrieval_latency_ms':[r.get('total_latency_ms') for r in rag if r.get('schema')=='ticket-rag-retrieval/1'],
                'tokens':live.get('tokens'),'token_usage_status':live.get('token_usage_status','unknown'),
                'business_success':None,'automatic_retries':0,'cost':None}
            new_json(root/'report.json',record);records.append(record)
    after=tree_hashes(BASELINE)
    prompt_hashes=[next((e['system_prompt_sha256'] for e in r['live_evidence'].get('events',[]) if e.get('event')=='http_dispatch_evidence'),None) for r in records]
    report={'schema':'ticket-v352-paired-live/1','evidence_mode':'offline_sdk_stub' if model_factory else 'real_api',
        'records':records,'same_tool_evidence_verified':all(r['tool_result_delivered_with_http200'] for r in records),
        'same_system_prompt_verified':all(prompt_hashes) and len(set(prompt_hashes))==1,
        'source_index_unchanged':before==after,'source_tree_sha256':hash_tree(before),
        'real_generation_requests':sum(r['real_generation_requests'] for r in records),'generation_limit':None,
        'real_generation_requests_this_command':new_requests,'continued_from_sha256':continued_from,
        'real_embedding_requests':0,'langsmith_requests':0,'cost':None,
        'faithfulness_scope':'Finite checks and manual review, independent of protocol closure; no overall model accuracy inferred.'}
    new_json(AUTH/('paired-report-resumed-'+uuid.uuid4().hex+'.json' if resume_unattempted_qwen else 'paired-report.json'),report);return report


@contextmanager
def fresh_workspace(out=None):
    """An automatic output location, never a user-created authorization batch."""
    from target import v352_validation as validation
    original=validation.AUTH
    destination=Path(out) if out else ROOT/'artifacts/runtime/live-checks'/('rag-pair-'+uuid.uuid4().hex)
    destination=destination.resolve()
    if not destination.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    source=validation.cached_source()
    destination.mkdir(parents=True,exist_ok=False)
    if source.exists():shutil.copyfile(source,destination/'embedding-cache.db')
    validation.AUTH=destination
    try:yield destination
    finally:validation.AUTH=original


def execute_pair(*,model_factory=None,resume_unattempted_qwen=False,out=None):
    from target import v352_validation as validation
    historical=ROOT/'artifacts/runtime/v352-rag-live-eval/authorization-20261026'
    if out is not None or validation.AUTH.resolve()==historical.resolve():
        with fresh_workspace(out):
            return _execute_pair(model_factory=model_factory,resume_unattempted_qwen=resume_unattempted_qwen)
    # Explicit isolated SDK fixtures may supply their own output directory.
    return _execute_pair(model_factory=model_factory,resume_unattempted_qwen=resume_unattempted_qwen)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true',help='Only prepare cached evidence, no model or Embedding calls')
    parser.add_argument('--run',action='store_true',help='显式执行双模型只读对照；无累计请求上限，保留单轮步数')
    parser.add_argument('--resume-unattempted-qwen',action='store_true',help='兼容：仅执行新的千问政策场景，不读取旧额度')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.resume_unattempted_qwen:
        if not args.run:raise ValueError('resume_requires_explicit_run')
        from scripts.live_providers import main as live
        forwarded=['--provider','bailian','--scenario','policy','--run']
        if args.out:forwarded.extend(['--out',str(args.out)])
        return live(forwarded)
    if not args.run:
        if args.prepare:
            with fresh_workspace(args.out) as root:
                frozen=prepare();print(json.dumps({'status':'prepared_not_live_verified','evidence_sha256':frozen['tool_result_sha256'],'generation_requests':0,'embedding_requests':0,'output':root.relative_to(ROOT).as_posix()}))
        else:print(json.dumps({'status':'not_run','local_request_limit':None,'per_turn_model_calls':2,'embedding_required_if_cached':0,'max_retries':0}))
        return 0
    from target.api_config import bootstrap
    bootstrap(ROOT)
    if any(not os.getenv(k,'').strip() for k in ('DASHSCOPE_API_KEY','DEEPSEEK_API_KEY')):
        print(json.dumps({'status':'not_run','category':'required_provider_key_missing','new_requests':0}));return 2
    report=execute_pair(out=args.out)
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))
    return 0 if all(r['protocol_closure'] and r['agent_completed'] for r in report['records']) and report['same_system_prompt_verified'] and report['source_index_unchanged'] else 1


if __name__=='__main__':raise SystemExit(main())
