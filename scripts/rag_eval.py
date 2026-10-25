"""Evaluate fixed 30 queries against the real persisted index; no generation calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',action='store_true',help='Explicitly allow at most the remaining fixed embedding quota')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    out.mkdir(parents=True,exist_ok=False)
    from target.api_config import bootstrap
    bootstrap(ROOT)
    from target.rag_service import configured_index
    from target.rag_quality import query_text,retrieval_metrics
    from target.diagnostics import sanitize
    path=ROOT/'cases/rag_quality_v35.json';quality=json.loads(path.read_text(encoding='utf-8'));cases=quality['cases']
    index=configured_index();budget=index.provider.budget;before=budget.snapshot()['used']
    plan={'queries':len(cases),'batch_size':10,'estimated_max_new_requests':3,'current_embedding_budget':before,
          'embedding_limit':8,'generation_requests':0,'fixed_dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps(plan),flush=True)
    try:
        state,_=index.load(require_real=True)
        vectors=index.provider.embed_many([query_text(c) for c in cases],allow_network=a.run)
        receipts=list(index.provider.last_receipts)
        results={mode:{} for mode in ('keyword','vector','hybrid')}
        for case in cases:
            for mode in results:
                evidence=index.retrieve(query_text(case),mode,k=quality['top_k'],threshold=quality['vector_threshold'],require_real=True)
                results[mode][case['id']]=evidence
        report={'status':'executed','scope':'Real embedding retrieval evaluation only; no generated-answer accuracy inferred',
                'dataset_sha256':plan['fixed_dataset_sha256'],'index_version':state['index_version'],
                'embedding_origin':state['embedding_origin'],'query_embedding_receipts':receipts,
                'new_embedding_requests':budget.snapshot()['used']-before,'generation_requests':0,
                'metrics':{m:retrieval_metrics(cases,r,quality['top_k']) for m,r in results.items()},'results':results,
                'generation_quality':{'executed':0,'faithfulness':None,'citation_support':None,'status':'not_run'},
                'same_evidence_cross_model':{'frozen_retrievals':True,'deepseek_generation':'not_run','qwen_generation':'separate_live_acceptance'}}
        (out/'query_vectors.json').write_text(json.dumps({'origin':index.provider.origin,'model':index.provider.settings.model,
           'dimensions':index.provider.settings.dimensions,'queries':[{'case_id':c['id'],'embedding_query':query_text(c),'vector':v}
           for c,v in zip(cases,vectors)]},ensure_ascii=False),encoding='utf-8')
        (out/'report.json').write_text(json.dumps(sanitize(report),ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('results','query_embedding_receipts','metrics')},ensure_ascii=False))
        print(json.dumps({m:{k:v for k,v in r.items() if k!='rows'} for m,r in report['metrics'].items()},ensure_ascii=False));return 0
    except Exception as exc:
        result={'status':'failed','category':getattr(exc,'category',str(exc) if type(exc).__name__=='RagError' else type(exc).__name__),
                'new_embedding_requests':budget.snapshot()['used']-before,'generation_requests':0,'passed':False}
        (out/'report.json').write_text(json.dumps(result),encoding='utf-8');print(json.dumps(result));return 1


if __name__=='__main__':raise SystemExit(main())
