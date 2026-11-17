"""Prepare a local-only acceptance plan. This module has no HTTP/model execution path."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent.parent
AUTH=ROOT/'artifacts/runtime/v35-qwen38-rag/authorization-20261026'
DEFAULT_SOURCE=ROOT/'docs/evidence/v35/live/generation-result.json'
QUESTION='锁座后多久必须完成支付？'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def frozen_evidence(source=None):
    source=Path(source or DEFAULT_SOURCE).resolve()
    if not source.is_relative_to(ROOT):raise ValueError('project_evidence_source_required')
    raw=source.read_bytes();data=json.loads(raw.decode('utf-8-sig'))
    if 'records' in data:
        record=next(r for r in data['records'] if r.get('scenario')=='RQ01')
        evidence=record['frozen_retrieval_evidence']
    else:evidence=data.get('retrieval_evidence',data)
    if evidence.get('question')!=QUESTION or not isinstance(evidence.get('hits'),list):
        raise ValueError('RQ01_retrieval_evidence_required')
    if evidence.get('embedding_origin')!='real_api':raise ValueError('real_embedding_provenance_required')
    if not any(h.get('doc_id')=='P11' for h in evidence['hits']):raise ValueError('P11_support_required')
    # This freezes the actual tool return, not performance times/provider-specific metadata.
    result={'question':QUESTION,'hits':evidence['hits'],'count':len(evidence['hits'])}
    return {'source':source.relative_to(ROOT).as_posix(),'source_file_sha256':hashlib.sha256(raw).hexdigest(),
            'question':QUESTION,'retrieval_mode':evidence.get('mode'),'quality_profile':evidence.get('quality_profile','v35'),
            'index_version':evidence.get('index_version'),'embedding_origin':'real_api',
            'tool_result':result,'tool_result_sha256':canonical_hash(result)}


def readonly_count(path):
    if not path.is_file():return {'status':'missing','used':None,'sha256':None}
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
        count=connection.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
    after=hashlib.sha256(path.read_bytes()).hexdigest()
    if before!=after:raise ValueError('ledger_modified_during_readonly_plan')
    return {'status':'read_only','used':count,'sha256':after}


def plan(source=None):
    frozen=frozen_evidence(source)
    return {'schema':'ticket-v351-acceptance-plan/1','execution_status':'not_run','network_requests':0,
        'reads_api_keys':False,'has_execution_switch':False,'frozen_evidence':frozen,
        'current_v35_budgets':{'embedding':{**readonly_count(AUTH/'embedding.db'),'limit':8},
            'qwen_generation':{**readonly_count(AUTH/'generation.db'),'limit':4},
            'shared_generation':{**readonly_count(AUTH/'generation-total.db'),'limit':4}},
        'minimum_new_authorization':{'qwen_generation':2,'deepseek_generation':2,'total_generation':4,
            'embedding':0,'automatic_retries':0,'max_output_tokens_each_request':512,
            'embedding_basis':'RQ01 is already cached. Validate cache/index provenance first; cache miss must stop, not request implicitly.'},
        'execution_prerequisite':'Wait for explicit new authorization; bind a new fixed V3.5.1 validation profile without changing the exhausted V3.5 guard or old ledger. This script cannot do that.',
        'paired_run_rules':[
            'Isolated new session, simulated SQLite and local trace directory for each Provider.',
            'Same user question, read-only tools, system prompt, model-call limit and frozen tool result hash.',
            'Each model independently requests search_policy; Python executes the new RAG cache-only, then verify frozen hash before returning evidence.',
            'A missing/different cache-only result stops the pair; do not substitute fixture tool_calls or fake a successful tool return.',
            'Retain two original model outputs, actual tool_call_id, args, request IDs and local sidecars; compare using the same fidelity rules.',
            'Model error, no tool call, unsupported citation and budget exhaustion are separate outcomes, never automatic retry or Mock fallback.'
        ],
        'pass_criteria':{'protocol':'real HTTP responses plus actual model search_policy tool call, executed new RAG and ToolMessage return before final answer',
            'evidence':'Both providers consume byte-identical canonical tool-result hash; provenance matches real cached vectors and current corpus.',
            'fidelity':'No determined unsupported fact/citation/action; uncertain semantics remain manual-review, not automatic pass.',
            'budget':'At most 2 generation attempts per provider, 4 total, retries zero; old budget hashes unchanged.'},
        'cost':'Unknown until actual request usage and reliable account billing are available; 2048 aggregate maximum output tokens is a request cap, not a currency hard limit.',
        'limits':['A single paired sample cannot establish model-wide accuracy.',
                  'Default frozen evidence comes from V3.5; use --retrieval-file with a saved V3.5.1 RQ01 result to freeze the new optimized profile.',
                  'No new Live evidence is produced by preparing this plan.']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval-file',type=Path,help='Saved real RQ01 evidence; no API call is made to create it')
    parser.add_argument('--out',type=Path,help='A new directory under artifacts/runtime; omitted means print only')
    args=parser.parse_args(argv);result=plan(args.retrieval_file)
    if args.out:
        out=args.out.resolve()
        if not out.is_relative_to(ROOT/'artifacts/runtime') or out==ROOT/'artifacts/runtime':raise ValueError('isolated_output_required')
        out.mkdir(parents=True,exist_ok=False)
        (out/'plan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'frozen_tool_result.json').write_text(json.dumps(result['frozen_evidence']['tool_result'],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
