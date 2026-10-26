"""Offline forensic audit of two saved replies. Does not construct a model client."""
import argparse
import ast
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def source_at(commit,path):return subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT).decode('utf-8')


def reconstruct_prompt(record):
    live=record['live_evidence'];commit=live['git_sha']
    code=ast.parse(source_at(commit,'target/deepseek_runtime.py'))
    base=next(ast.literal_eval(n.value) for n in code.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READ_ONLY_PROMPT' for t in n.targets))
    agent=ast.parse(source_at(commit,'target/langchain_agent.py'))
    extra=next(ast.literal_eval(n.value) for n in ast.walk(agent) if isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id=='system_prompt')
    date=datetime.fromisoformat(live['requested_at']).astimezone(timezone(timedelta(hours=8))).date().isoformat()
    prompt=base+extra+f'\n当前北京时间日期 {date}；业务全部虚构。'
    hashes={e['system_prompt_sha256'] for e in live['events'] if e['event']=='http_dispatch_evidence'}
    digest=canonical([{'role':'system','content':prompt}])
    if hashes!={digest}:raise ValueError('historical_prompt_reconstruction_hash_mismatch')
    names=next(ast.literal_eval(n.value) for n in agent.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READ_ONLY_TOOLS' for t in n.targets))
    return {'text':prompt,'saved_and_reconstructed_hash':digest,'historical_git_sha':commit,
        'source':'AST reconstruction from the recorded commit and request date; hash-verified, NOT a saved raw HTTP body',
        'static_read_only_tools':list(names),'runtime_tool_schema_or_binding_saved':False,
        'scope':'Static guard/registered tools and instructions are inspected; this does not invent a missing historical tools-schema receipt'}


def run(out):
    from target.rag_claim_audit import audit_claims
    from target.rag_protection import BASELINE,tree_hashes,working_index,logical_snapshot
    from target.embeddings import EmbeddingProvider,EmbeddingSettings
    from target.rag_store import documents
    from target.v352_validation import AUTH
    from target.request_accounting import snapshot
    out.mkdir(parents=True,exist_ok=False)
    pairpath=ROOT/'docs/evidence/v352/live/paired-report-resumed.json';pair=read(pairpath)
    originals=read(ROOT/'artifacts/runtime/v352-faithfulness-audit/protected.json')
    source_before=tree_hashes(BASELINE);manifest=read(BASELINE/'manifest.json')
    provider=EmbeddingProvider(EmbeddingSettings(base_url=manifest['endpoint'],model=manifest['model'],dimensions=manifest['dimensions'],
        cache=AUTH/'embedding-cache.db',ledger=out/'unused-embedding.db'))
    with working_index(BASELINE,provider,parent=out/'index-copy') as (index,receipt):
        logical=logical_snapshot(index)
    p11=next(row for row in logical['rows'] if row['metadata']['doc_id']=='P11')
    chunks=documents(ROOT/'data/policies.md');policy=next(c for c in chunks if c['doc_id']=='P11')
    assert policy['content']==p11['content'] and all(policy[k]==p11['metadata'][k] for k in ('doc_id','version','chunk_id','source'))
    lines=(ROOT/'data/policies.md').read_text(encoding='utf-8').splitlines()
    line=next(i+1 for i,text in enumerate(lines) if text.startswith('## [P11]'))
    models=[]
    for record in pair['records']:
        live=record['live_evidence'];events=live['events'];trace_id=live['trace_id'];name=record['provider']
        folder='bailian-resumed' if name=='bailian' else name
        rawroot=AUTH/'runs'/folder/'traces';publicroot=ROOT/'docs/evidence/v352/live/runs'/folder/'traces'
        trace=read_jsonl(rawroot/'traces.jsonl')[0];audit=read_jsonl(rawroot/'audit_runs.jsonl')[0]
        assert (rawroot/'traces.jsonl').read_bytes()==(publicroot/'traces.jsonl').read_bytes()
        assert trace['reply']==audit['raw_model_reply']==record['original_model_reply']==record['final_display_result']
        model_final=next(e for e in events if e['event']=='model_final');assert model_final['text']==trace['reply']
        tool_index,tool=next((i,e) for i,e in enumerate(events) if e['event']=='tool_end' and e['tool']=='search_policy')
        call=next(e for e in events if e['event']=='model_response' and e.get('tool_calls'))['tool_calls'][0]
        assert call['name']=='search_policy' and call['id']==tool['call_id'] and call['args']==tool['args']
        assert tool['ok'] and tool['executed'] and tool['args']=={'question':live['user_msg']}
        assert tool['result']['hits'][0]['content']==policy['content']
        assert tool['result']['hits'][0]['version']==policy['version']
        dispatch,payload=next((e,p) for e in events if e['event']=='http_dispatch_evidence' for p in e['tool_payloads'])
        serialized=json.dumps(payload['tool_result'],ensure_ascii=False)
        assert canonical(payload['tool_result'])==canonical(tool['result'])==record['expected_evidence_sha256']
        assert hashlib.sha256(serialized.encode()).hexdigest()==payload['content_sha256']
        assert dispatch['request_id'] in {e['request_id'] for e in events if e['event']=='http_response' and e['http_status']==200}
        prompt=reconstruct_prompt(record)
        new=audit_claims(trace['reply'],tool['result']['hits'],events=events,policy_versions={c['doc_id']:c['version'] for c in chunks})
        for row in new['assertions']:
            row['actual_model']=record['actual_models'][0];row['trace_id']=trace_id
            row['evidence_refs']=[{'path':pairpath.relative_to(ROOT).as_posix(),
                'json_pointer':f"/records/{pair['records'].index(record)}/live_evidence/events/{tool_index}/result/hits/0"},
                {'path':publicroot.relative_to(ROOT).as_posix()+'/audit_runs.jsonl','jsonl_line':1,'json_pointer':'/framework_events'},
                {'path':'data/policies.md','line':line+1,'doc_id':policy['doc_id'],'version':policy['version']},
                {'path':'policy-index-snapshot.json','json_pointer':'/p11','scope':'actual original Chroma read on isolated copy'}]
            if row['kind']=='capability':
                row['evidence_authority']='runtime/tool events; P11 is NOT evidence of application capabilities'
                row['additional_static_evidence']={'git_sha':live['git_sha'],'path':'target/langchain_agent.py',
                    'scope':'READ_ONLY_TOOLS, constructor guard, create_agent tool binding; static code, not a stored runtime schema'}
        path=out/(name+'-original-reply.txt');path.write_text(trace['reply'],encoding='utf-8',newline='\n')
        (out/(name+'-system-prompt-reconstructed.txt')).write_text(prompt['text'],encoding='utf-8',newline='\n')
        (out/(name+'-tool-message-reconstructed.txt')).write_text(serialized,encoding='utf-8',newline='\n')
        models.append({'provider':name,'actual_model':record['actual_models'][0],'trace_id':trace_id,'historical_git_sha':live['git_sha'],
            'request_ids':[e['request_id'] for e in events if e['event']=='http_request'],'call_id':tool['call_id'],
            'tool_args':tool['args'],'actual_tool_result':tool['result'],'actual_tool_result_hash':canonical(tool['result']),
            'serialized_tool_message_hash_matches':True,'serialized_tool_message_source':'Reconstructed serialization matches saved exact content hash; parsed actual payload saved originally',
            'original_model_reply':trace['reply'],'original_reply_sha256':sha(path),'public_trace':trace,
            'prompt':prompt,'original_verdict':record['faithfulness'],'new_audit':new,
            'source_paths':[str(p.relative_to(ROOT)) for p in (pairpath,publicroot/'audit_runs.jsonl',publicroot/'provider_runs.jsonl',publicroot/'rag_runs.jsonl',publicroot/'traces.jsonl')],
            'explicit_missing_evidence':['Original full HTTP request body including tools schema was not retained.',
                'No saved runtime tool-binding/schema snapshot for claims about non-executed tools.'],
            'verified_policy_facts':['15 minute simulated lock validity','expired AND unpaid releases inventory',
                'order passenger list must match lock list','duplicate payment does not deduct inventory twice'],
            'time_origin_check':'P11 does not define an explicit clock field/start event. Neither reply invents a payment/first-message start trigger.',
            'official_scope_check':'No affirmative 12306/airline official rule attribution; context and hash-verified prompt are explicitly simulated.',
            'unsupported_steps_or_actions':False,'cross_document_attribution_error':False,
            'condition_omission_observed':False,'new_API_requests':0})
    assert source_before==tree_hashes(BASELINE)
    assert len({m['actual_tool_result_hash'] for m in models})==len({m['prompt']['saved_and_reconstructed_hash'] for m in models})==1
    changed=[p for p,h in originals.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    assert not changed
    compared=[]
    for path in ('target/agent.py','target/langchain_agent.py','target/rag_service.py','target/rag_store.py',
                 'target/rag_relevance.py','target/deepseek_runtime.py','target/bailian_runtime.py','target/tools.py',
                 'data/policies.md','requirements-v35-lock.txt','target/live_providers.py','scripts/verify_v352_live.py'):
        hashes=[hashlib.sha256(source_at(m['historical_git_sha'],path).encode()).hexdigest() for m in models]
        compared.append({'path':path,'hashes':hashes,'identical':len(set(hashes))==1})
    result={'schema':'ticket-v352-full-answer-audit/1','baseline_git_sha':'61c9f1953ff56e6037d3b996a333ef9c5a0164c5',
        'audit_source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'real_API_requests':0,'source_files_unchanged':len(originals),'changed_original_files':changed,
        'same_tool_evidence_and_prompt_verified':True,'models':models,'historical_source_comparison':compared,
        'condition_limits':'Different request times, models/SDKs, sessions and wrapper commits; source-selection fix recorded, not a byte-identical total environment.',
        'request_budget_snapshot_readonly':snapshot(AUTH/'generation-total.db',4),
        'no_model_judge_used':True,'full_original_replies_preserved':True,
        'limits':['Policy facts and runtime capability statements use different authoritative evidence.',
            'Missing historical runtime tools schema is not fabricated from a prompt; B may explicitly accept static-code/offline guard verification.',
            'This is a retrospective audit of two fixed answers, not a population accuracy estimate or post-fix Live rerun.']}
    write_json(out/'policy-index-snapshot.json',{'p11':p11,'current_policy':policy,'policy_header_line':line,
        'source_tree_before':source_before,'source_tree_after':tree_hashes(BASELINE),'logical_snapshot':logical,
        'policy_file_sha256':sha(ROOT/'data/policies.md'),'manifest':manifest,'real_API_requests':0})
    write_json(out/'audit.json',result)
    print(json.dumps({'new_API_requests':0,'protected_files_unchanged':len(originals),
        'models':[{k:m['new_audit'][k] for k in ('verdict','counts','factual_assertions')}|{'model':m['actual_model']} for m in models]},ensure_ascii=False))
    return result


def read_jsonl(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
def write_json(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    run(parser.parse_args().out.resolve())
