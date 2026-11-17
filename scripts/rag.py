"""Explicit RAG administration. Default plan/status never calls an embedding API."""
import argparse
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('plan','status','build','retrieve'))
    p.add_argument('--run',action='store_true',help='显式同意真实Embedding费用，无本地累计请求上限')
    p.add_argument('--rebuild',action='store_true')
    p.add_argument('--mode',choices=('keyword','vector','hybrid'),default='hybrid')
    p.add_argument('--quality-profile',choices=('v35','v351'),default='v351')
    p.add_argument('--question');p.add_argument('--out',type=Path)
    a=p.parse_args()
    from target.api_config import bootstrap
    bootstrap(ROOT)
    from target.rag_store import documents
    chunks=documents(ROOT/'data/policies.md')
    plan={'documents':len({c['doc_id'] for c in chunks}),'chunks':len(chunks),'embedding_model':'text-embedding-v4',
          'dimensions':int(os.getenv('RAG_EMBEDDING_DIMENSIONS','1024')),'batch_size':10,
          'estimated_index_requests':math.ceil(len(chunks)/10),'evaluation_questions':30,'estimated_evaluation_requests':3,
          'embedding_limit':None,'generation_limit':None,'usage_policy':'unlimited_usage_only','model_requests_this_command':0,'max_retries':0}
    try:
        if a.action=='plan':result=plan
        elif a.action=='retrieve' and a.mode=='keyword':
            from target.rag_store import keyword
            hits=keyword(chunks,a.question or '',k=20);quality={}
            if a.quality_profile=='v351':
                from target.rag_relevance import apply_quality
                quality=apply_quality(a.question or '',hits,[],'keyword')
                hits=quality['hits']
            result={'mode':'keyword','question':a.question,'hits':hits,'new_embedding_requests':0,**quality}
        else:
            from target.rag_service import configured_index
            index=configured_index()
            if a.action=='status':result={**index.status(),'budget':index.provider.budget.snapshot()}
            elif a.action=='build':
                print(json.dumps({'preflight_plan':plan,'key_configured':bool(os.getenv('DASHSCOPE_API_KEY','').strip()),
                                  'endpoint':index.provider.settings.base_url,'budget':index.provider.budget.snapshot()},ensure_ascii=False))
                result=index.build(allow_network=a.run,rebuild=a.rebuild) if a.run else {'status':'not_run','plan':plan,'new_embedding_requests':0}
            else:
                if not a.question:raise ValueError('question_required')
                result=index.retrieve(a.question,a.mode,allow_network=a.run,require_real=True,quality_profile=a.quality_profile)
        from target.diagnostics import sanitize
        result=sanitize(result)
        if a.out:
            out=a.out.resolve()
            if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_runtime_output_required')
            out.parent.mkdir(parents=True,exist_ok=True)
            with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as exc:
        category=getattr(exc,'category',str(exc) if type(exc).__name__=='RagError' else type(exc).__name__)
        failure={'status':'failed','category':category,'http_status':getattr(exc,'status',None),'success':False}
        if a.out:
            out=a.out.resolve()
            if out.is_relative_to(ROOT/'artifacts/runtime'):
                out.parent.mkdir(parents=True,exist_ok=True)
                with out.open('x',encoding='utf-8') as f:json.dump(failure,f,ensure_ascii=False,indent=2)
        print(json.dumps(failure));return 1


if __name__=='__main__':raise SystemExit(main())
