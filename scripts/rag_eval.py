"""Explicit 30-question retrieval evaluation on a copy, with no cumulative cap."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='显式允许真实Embedding费用；无本地累计请求上限')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args(argv)
    out=(args.out or ROOT/'artifacts/runtime'/('rag-eval-'+uuid.uuid4().hex)).resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    out.mkdir(parents=True,exist_ok=False)
    from target.api_config import bootstrap
    bootstrap(ROOT)
    from target.rag_service import configured_index
    from target.rag_protection import working_index
    from target.rag_quality import query_text,retrieval_metrics
    from target.diagnostics import sanitize
    source=configured_index()
    dataset=ROOT/'cases/rag_quality_v35.json'
    quality=json.loads(dataset.read_text(encoding='utf-8'));cases=quality['cases']
    plan={'queries':len(cases),'batch_size':10,'estimated_max_new_requests':3,
          'embedding_limit':None,'usage_policy':'unlimited_usage_only','generation_requests':0,
          'fixed_dataset_sha256':hashlib.sha256(dataset.read_bytes()).hexdigest()}
    print(json.dumps(plan),flush=True)
    receipts=[];request_ids=[]
    try:
        with working_index(source.path,source.provider,parent=out/'chroma-work') as (index,protection):
            state,_=index.load(require_real=True)
            from target.rag_service import scope
            with scope(trace_id='rag-eval-'+uuid.uuid4().hex,provider='embedding'):
                try:vectors=index.provider.embed_many([query_text(c) for c in cases],allow_network=args.run)
                finally:request_ids=list(index.provider.request_ids)
            receipts=list(index.provider.last_receipts)
            results={mode:{} for mode in ('keyword','vector','hybrid')}
            for case in cases:
                for mode in results:
                    results[mode][case['id']]=index.retrieve(query_text(case),mode,k=quality['top_k'],
                        threshold=quality['vector_threshold'],require_real=True)
            report={'status':'executed','scope':'Retrieval only; not generated-answer accuracy',
                'dataset_sha256':plan['fixed_dataset_sha256'],'index_version':state['index_version'],
                'embedding_origin':state['embedding_origin'],'query_embedding_receipts':receipts,
                'new_embedding_requests':len(request_ids),
                'generation_requests':0,'usage_policy':'unlimited_usage_only',
                'metrics':{m:retrieval_metrics(cases,r,quality['top_k']) for m,r in results.items()},
                'results':results,'index_protection':protection,'generation_quality':{'executed':0,'status':'not_run'}}
            (out/'query_vectors.json').write_text(json.dumps({'origin':index.provider.origin,'model':index.provider.settings.model,
                'dimensions':index.provider.settings.dimensions,'queries':[{'case_id':c['id'],'embedding_query':query_text(c),'vector':v}
                for c,v in zip(cases,vectors)]},ensure_ascii=False),encoding='utf-8')
        report['source_index_unchanged']=protection['source_unchanged']
        (out/'report.json').write_text(json.dumps(sanitize(report),ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({m:{k:v for k,v in r.items() if k!='rows'} for m,r in report['metrics'].items()},ensure_ascii=False))
        return 0
    except Exception as exc:
        result={'status':'failed','category':getattr(exc,'category',type(exc).__name__),
                'generation_requests':0,'embedding_requests_observed':len(request_ids)}
        (out/'report.json').write_text(json.dumps(result),encoding='utf-8')
        print(json.dumps(result));return 1


if __name__=='__main__':raise SystemExit(main())

