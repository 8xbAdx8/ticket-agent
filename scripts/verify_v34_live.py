"""V3.4 one-shot acceptance: 2 DeepSeek + 2 Bailian, one separately consented synthetic upload."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
AUTH=ROOT/'artifacts/runtime/v34-api-audit/authorization-20261025'


def write(path,value):
    from target.diagnostics import sanitize
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(sanitize(value),ensure_ascii=False,indent=2),encoding='utf-8')


def head():
    return subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()


def display(value):
    from target.diagnostics import sanitize
    print(json.dumps(sanitize(value),ensure_ascii=False))


def gate(path):
    report=json.loads(Path(path).read_text(encoding='utf-8'))
    if (report.get('status')!='passed' or report.get('real_api_requests')!=0 or report.get('blocked_network_attempts')!=0
            or report.get('tested_source_head')!=head()):raise ValueError('matching_frozen_offline_acceptance_required')
    dirty=subprocess.run(['git','diff','--name-only','HEAD','--','target','config.py','scripts','web','tests'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
    if dirty.strip():raise ValueError('tracked_source_must_be_frozen')


def claim(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump({'started_at':datetime.now(timezone.utc).isoformat(),'git_sha':head(),'retry_allowed':False},f)


def old_reconciliation():
    from target.request_accounting import snapshot
    base=ROOT/'artifacts/runtime/v33-live-providers'
    group=snapshot(base/'initial-total.db',3)
    providers={p:snapshot(base/p/'requests.db',3) for p in ('deepseek','bailian')}
    return {'shared':group,'providers':providers,'provider_total':sum(r['reserved_requests'] for r in providers.values()),
            'identity_linkage_verified':False,'historical_unknowns_released':0,
            'conclusion':'No shared request IDs; matching counts/timestamps do not prove per-request identity. Original ledgers unchanged.'}


def prepare():
    from target.api_config import bootstrap,status
    sources=bootstrap(ROOT)
    os.environ['TICKET_API_VALIDATION_PROFILE']='v34'
    from target.live_providers import isolated_environment
    from target.deepseek_runtime import safe_error
    from target.request_accounting import CoordinatedBudget,snapshot
    from web.runtime import scoped
    import config
    rows={}
    for provider in ('deepseek','bailian'):
        env=isolated_environment(provider,AUTH/provider/'case')
        values=dict(PROVIDER=provider,ENGINE='langchain',MODEL_NAME=env['AGENT_MODEL'],BASE_URL=env['AGENT_BASE_URL'],
            API_KEY=os.getenv('DEEPSEEK_API_KEY' if provider=='deepseek' else 'DASHSCOPE_API_KEY',''),
            DB_PATH=Path(env['AGENT_DB_PATH']),TRACE_DIR=Path(env['AGENT_TRACE_DIR']),LC_TOOLSET='read_only',USE_HTTP_MOCK=False,USE_VECTOR_RAG=False,MAX_STEPS=2)
        with scoped(values,env):
            from target import deepseek_runtime,bailian_runtime
            runtime=deepseek_runtime if provider=='deepseek' else bailian_runtime
            try:
                runtime.validate_configuration(); settings=runtime.Settings.from_env()
                __import__('langchain_deepseek' if provider=='deepseek' else 'langchain_openai')
                budget=CoordinatedBudget(settings,provider)
                rows[provider]={'configuration':status(provider),'preflight':'ready','usage':budget.snapshot()}
            except Exception as exc:rows[provider]={'configuration':status(provider),'preflight':'not_ready','error':safe_error(exc)}
    from target.observability import configuration_status
    return {'schema':'v34-preflight/1','source_sha':head(),'key_sources':sources,'providers':rows,
            'usage_policy':'unlimited_usage_only','langsmith':configuration_status(),
            'limits':{'deepseek':None,'bailian':None,'total_generation':None,'synthetic_upload_attempts':1,'automatic_retries':0}}


def run_provider(provider,row):
    from target.deepseek_runtime import safe_error
    from target.live_providers import isolated_environment
    from target.request_accounting import snapshot
    from web.runtime import scoped
    from data.seed import build_db
    from target.agent import Agent
    case=AUTH/provider/('case-'+uuid.uuid4().hex);env=isolated_environment(provider,case)
    if row['preflight']!='ready':return {'status':'skipped','reason':'configuration_not_ready','new_requests':0}
    values=dict(PROVIDER=provider,ENGINE='langchain',LC_TOOLSET='read_only',MODEL_NAME=env['AGENT_MODEL'],BASE_URL=env['AGENT_BASE_URL'],
        API_KEY=os.environ['DEEPSEEK_API_KEY' if provider=='deepseek' else 'DASHSCOPE_API_KEY'],
        DB_PATH=case/'tickets.db',TRACE_DIR=case/'traces',MAX_STEPS=2,USE_HTTP_MOCK=False,USE_VECTOR_RAG=False)
    env.update(TICKET_CASE_ID='v34-query-'+provider,LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false')
    result=None;record=None;error=None
    with scoped(values,env):
        try:
            if values['DB_PATH'].exists():raise ValueError('fresh_simulated_database_required')
            build_db(values['DB_PATH'])
            agent=Agent()
            try:result=agent.chat('v34-'+provider+'-'+uuid.uuid4().hex[:12],'查明天上海到杭州的高铁二等座，请列出有余票的车次；以工具结果为依据。')
            finally:record=agent.langchain_engine.last_live_run
        except Exception as exc:error=safe_error(exc)
    events=(record or {}).get('events',[])
    tools=[e for e in events if e.get('event')=='tool_end']
    requests=[e for e in events if e.get('event')=='http_request']
    model=[e for e in events if e.get('event')=='model_response']
    selected=[c for e in model for c in e.get('tool_calls',[]) if c.get('name')=='query_tickets']
    returned={i for e in requests for i in e.get('summary',{}).get('returned_tool_call_ids',[])}
    closure=bool(result and result['finish_reason']=='stop' and selected and len(requests)==2
        and all(c['id'] in returned for c in selected) and any(e.get('event')=='model_final' for e in events)
        and tools and all(e.get('ok') and e.get('executed') is True and e.get('tool')=='query_tickets' for e in tools))
    output={'status':'passed' if closure else 'failed','provider':provider,'configured':True,
        'connection_verified':bool(model),'tool_calling_verified':closure,'business_verified':None,
        'agent_completed':bool(result and result['finish_reason']=='stop' and not error),'error':error,
        'new_requests':len(requests),'tokens':(record or {}).get('tokens'),'observed_tokens':(record or {}).get('observed_tokens'),
        'cost':None,'cost_basis':'No authoritative price/billing evidence','public_trace':result,'live_record':record,
        'provider_budget':snapshot(AUTH/provider/'requests.db',2)}
    write(AUTH/provider/'result.json',output)
    return output


def synthetic_preview():
    from target.observability import export_payload
    record={'trace_id':'synthetic-'+uuid.uuid4().hex,'provider':'synthetic','mode':'synthetic','git_sha':head(),
        'case_id':'v34-langsmith-synthetic','user_msg':'合成测试：查询虚构出行信息。','reply':'这是合成观测测试，不是模型执行结果。',
        'tokens':None,'total_latency_ms':0,'finish_reason':'synthetic','local_trace_saved':False,'local_sidecar_saved':True,
        'events':[]}
    write(AUTH/'langsmith/synthetic_local.json',record)
    payload=export_payload(record)
    from target.diagnostics import digest
    write(AUTH/'langsmith/filtered_preview.json',payload)
    return {'preview_sha256':digest(payload),'preview':payload,'real_model_requests':0,'synthetic_only':True}


def upload(preview_sha):
    from target.diagnostics import digest
    from target.observability import export_payload,export_run,settings
    from web.runtime import scoped
    key,endpoint,project,_=settings()
    if not key:return {'remote_status':'not_configured','http_requests':0,'remote_verified':False}
    record=json.loads((AUTH/'langsmith/synthetic_local.json').read_text(encoding='utf-8'))
    if not preview_sha or digest(export_payload(record))!=preview_sha:raise ValueError('reviewed_preview_sha_required')
    if (AUTH/'langsmith/attempt.json').exists():raise ValueError('synthetic_upload_already_attempted')
    claim(AUTH/'langsmith/attempt.json')
    with scoped({}, {'LANGCHAIN_TRACING_V2':'true','LANGSMITH_TRACING':'true'}):
        receipt=export_run(record,consent=True,trace_dir=AUTH/'langsmith')
    write(AUTH/'langsmith/result.json',receipt)
    return receipt


def main():
    global AUTH
    p=argparse.ArgumentParser(description=__doc__)
    actions=p.add_mutually_exclusive_group()
    actions.add_argument('--run-models',action='store_true');actions.add_argument('--prepare-langsmith',action='store_true');actions.add_argument('--upload-langsmith',action='store_true')
    actions.add_argument('--readback-langsmith',action='store_true',help='Requires separate user authorization for one additional GET; never reuploads')
    p.add_argument('--offline-report',type=Path);p.add_argument('--preview-sha')
    a=p.parse_args()
    if not (a.prepare_langsmith or a.upload_langsmith or a.readback_langsmith):
        AUTH=ROOT/'artifacts/runtime/live-checks'/('v34-'+uuid.uuid4().hex)
    if a.upload_langsmith or a.readback_langsmith:
        if not a.offline_report:raise ValueError('offline_acceptance_required')
        gate(a.offline_report)
    state=prepare()
    write(AUTH/'preflights'/('preflight-'+uuid.uuid4().hex+'.json'),state)
    if a.run_models:
        results={provider:run_provider(provider,state['providers'][provider]) for provider in ('deepseek','bailian')}
        write(AUTH/'models-result.json',results)
        display({k:{n:r.get(n) for n in ('status','new_requests','connection_verified','tool_calling_verified','business_verified','tokens','error')} for k,r in results.items()})
    elif a.prepare_langsmith:display(synthetic_preview())
    elif a.upload_langsmith:display(upload(a.preview_sha))
    elif a.readback_langsmith:
        from target.observability import verify_existing
        receipt=json.loads((AUTH/'langsmith/result.json').read_text(encoding='utf-8'))
        preview=json.loads((AUTH/'langsmith/filtered_preview.json').read_text(encoding='utf-8'))
        claim(AUTH/'langsmith/readback-attempt.json')
        result=verify_existing(receipt,preview,consent=True)
        write(AUTH/'langsmith/readback-result.json',result);display(result)
    else:
        write(AUTH/'historical-reconciliation.json',old_reconciliation())
        display(state)


if __name__=='__main__':main()
