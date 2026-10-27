"""Evaluate the frozen 48 questions; no network without the explicit Embedding command."""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))


def evaluate(out,*,run=False,authorize=0):
    from target.v352_validation import AUTH,embedding_settings,cache_survey,cached_source,metrics,read,new_json
    from target.rag_quality import query_text
    from target.rag_store import documents,keyword
    from target.rag_relevance import apply_quality
    from target.rag_protection import BASELINE,working_index,tree_hashes,hash_tree
    from target.embeddings import EmbeddingProvider
    out.mkdir(parents=True,exist_ok=False)
    groups={s:read(ROOT/f'cases/rag_quality_v351_{s}.json')['cases'] for s in ('development','holdout')}
    cases=groups['development']+groups['holdout'];texts=[query_text(c) for c in cases]
    settings=embedding_settings();source=cached_source();survey=cache_survey(texts,settings,source)
    plan={'schema':'ticket-v352-embedding-plan/1','questions':len(cases),'cached_real_queries':survey['cached_real_queries'],
          'missing_queries':len(survey['missing_queries']),'required_new_requests':survey['new_request_upper_bound'],
          'batch_size':10,'local_request_limit':None,'generation_requests':0,'max_retries':0,
          'embedding_model':settings.model,'dimensions':settings.dimensions,'endpoint':settings.base_url,
          'explicit_embedding_authorization':authorize if run else 0}
    new_json(out/'plan.json',plan);print(json.dumps(plan),flush=True)
    before=tree_hashes(BASELINE);error=None;request_ids=[]
    if run:
        from target.api_config import bootstrap
        bootstrap(ROOT)
        if not os.getenv('DASHSCOPE_API_KEY','').strip():raise ValueError('missing_DASHSCOPE_API_KEY')
        configured=os.getenv('DASHSCOPE_EMBEDDING_BASE_URL',os.getenv('DASHSCOPE_BASE_URL',''))
        if configured and configured.rstrip('/')!=settings.base_url.rstrip('/'):
            raise ValueError('embedding_endpoint_differs_frozen_index_migration_required')
        new_json(out/'embedding-attempt.json',{'explicit_command_authorization':True,'schema':'ticket-v352-attempt/1',
            'out':out.relative_to(ROOT).as_posix(),'input_dataset_sha256':{s:hashlib.sha256((ROOT/f'cases/rag_quality_v351_{s}.json').read_bytes()).hexdigest() for s in groups}})
        settings=replace(settings,cache=out/'requested-embedding-cache.db',ledger=out/'unused-history-label.db',limit=0)
        if not settings.cache.exists():
            settings.cache.parent.mkdir(parents=True,exist_ok=True)
            if source.exists():shutil.copyfile(source,settings.cache)
        provider=EmbeddingProvider(settings)
        try:provider.embed_many(texts,allow_network=True)
        except Exception as exc:error={'category':getattr(exc,'category',type(exc).__name__)}
        request_ids=list(provider.request_ids)
        source=settings.cache;survey=cache_survey(texts,settings,source)
    # Offline cache-only runs read the old cache through a local copy as well.
    cache=out/'embedding-cache.db'
    if source.exists():shutil.copyfile(source,cache)
    provider=EmbeddingProvider(replace(settings,cache=cache))
    results={m:{} for m in ('keyword','vector','hybrid')};chunks=documents(ROOT/'data/policies.md')
    for c in cases:
        q=query_text(c)
        results['keyword'][c['id']]={'mode':'keyword','question':q,**apply_quality(q,keyword(chunks,q,20),[],'keyword',3)}
    if survey['vectors']:
        with working_index(BASELINE,provider,parent=out/'chroma-work') as (index,receipt):
            for c in cases:
                q=query_text(c)
                for mode in ('vector','hybrid'):
                    if q not in survey['vectors']:continue
                    try:results[mode][c['id']]=index.retrieve(q,mode,require_real=True,allow_network=False,quality_profile='v351')
                    except Exception as exc:results[mode][c['id']]={'error':getattr(exc,'category',type(exc).__name__)}
    after=tree_hashes(BASELINE)
    if run and survey['missing_queries'] and error is None:error={'category':'genuine_query_embeddings_still_missing'}
    metrics_by_split={s:{m:metrics(rows,results[m]) for m in results} for s,rows in groups.items()}
    metrics_by_split['all48']={m:metrics(cases,results[m]) for m in results}
    rows=[{'case':c,'mode':m,'result':results[m].get(c['id'],{'status':'not_run','reason':'genuine_query_embedding_missing'})} for c in cases for m in results]
    new_json(out/'rows.json',rows)
    used=provider.budget.snapshot()['used']
    report={'schema':'ticket-v352-retrieval-evaluation/1',
       'status':'failed' if error else 'completed' if not survey['missing_queries'] else 'partial_no_new_embedding_authorization',
       'execution_mode':'real_embedding_cache_and_chroma' if survey['vectors'] else 'offline_keyword_only',
       'metrics':metrics_by_split,'plan':plan,'remaining_missing_queries':len(survey['missing_queries']),
       'source_index_unchanged':before==after,'source_tree_sha256':hash_tree(before),
       'new_embedding_requests_this_command':len(request_ids),'new_generation_requests':0,'langsmith_requests':0,
       'embedding_usage_count':used,'embedding_limit':None,'error':error,
       'input_sha256':{s:hashlib.sha256((ROOT/f'cases/rag_quality_v351_{s}.json').read_bytes()).hexdigest() for s in groups},
       'algorithm_sha256':hashlib.sha256((ROOT/'target/rag_relevance.py').read_bytes()).hexdigest(),
       'limits':['No parameter tuning or label changes. Uncached vector/hybrid results are not_run, not zero.',
                 'Retrieval quality is separate from generated answer/refusal quality.']}
    new_json(out/'report.json',report)
    print(json.dumps({'source_index_unchanged':report['source_index_unchanged'],'remaining_missing_queries':report['remaining_missing_queries'],
        'new_embedding_requests_this_command':report['new_embedding_requests_this_command'],
        'metrics':{m:{k:v for k,v in r.items() if k!='rows'} for m,r in report['metrics']['all48'].items()}},ensure_ascii=False))
    return 0 if before==after and not error else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--run',action='store_true',help='Explicit new paid Embedding validation; never generation')
    parser.add_argument('--authorize-embedding-requests',type=int,default=0,help='已弃用并忽略；--run显式授权本轮执行，不设置请求总额')
    args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    return evaluate(out,run=args.run,authorize=args.authorize_embedding_requests)


if __name__=='__main__':raise SystemExit(main())
