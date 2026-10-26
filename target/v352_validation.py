"""Fixed V3.5.2 validation paths and read-only cache/budget inspection."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent.parent
AUTH=ROOT/'artifacts/runtime/v352-rag-live-eval/authorization-20261026'
QUESTION='锁座后多久必须完成支付？'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def new_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2)


def embedding_settings():
    from target.rag_protection import BASELINE
    from target.embeddings import EmbeddingSettings
    state=read(BASELINE/'manifest.json')
    return EmbeddingSettings(base_url=state['endpoint'],model=state['model'],dimensions=state['dimensions'],
        ledger=AUTH/'embedding.db',limit=5,cache=AUTH/'embedding-cache.db')


def cache_survey(texts,settings,source=None):
    from target.embeddings import EmbeddingProvider
    provider=EmbeddingProvider(settings);path=Path(source or settings.cache)
    vectors={};receipts={};invalid=[]
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
            for text in dict.fromkeys(texts):
                row=c.execute('SELECT vector,receipt FROM vectors WHERE cache_key=?',(provider.cache_key(text),)).fetchone()
                if row:
                    try:
                        vector,receipt=json.loads(row[0]),json.loads(row[1])
                        valid=(len(vector)==settings.dimensions and all(type(x) in (int,float) and math.isfinite(x) for x in vector)
                            and sum(x*x for x in vector)>0 and receipt.get('origin')=='real_api'
                            and receipt.get('dimensions')==settings.dimensions and receipt.get('model')==settings.model)
                        if not valid:raise ValueError('invalid_cached_vector')
                        vectors[text]=vector;receipts[text]=receipt
                    except (ValueError,TypeError,KeyError):invalid.append(hashlib.sha256(text.encode()).hexdigest())
    missing=[text for text in dict.fromkeys(texts) if text not in vectors]
    return {'unique_queries':len(set(texts)),'cached_real_queries':len(vectors),'missing_queries':missing,
            'new_request_upper_bound':math.ceil(len(missing)/settings.batch_size),'invalid_cache_entries':invalid,
            'vectors':vectors,'receipts':receipts}


def cached_source():
    new=AUTH/'embedding-cache.db'
    return new if new.exists() else ROOT/'artifacts/runtime/v35-rag/embedding-cache.db'


def metrics(cases,results):
    scores={1:[],3:[]};rr=[];false=[];rows=[];missing=0;indeterminate=0
    for case in cases:
        result=results.get(case['id']);expected=set(case['expected_doc_ids'])
        if result is None or result.get('status')=='not_run':
            missing+=1;rows.append({'case_id':case['id'],'status':'not_run','expected_doc_ids':sorted(expected)});continue
        if result.get('error'):
            indeterminate+=1;rows.append({'case_id':case['id'],'status':'indeterminate','error':result['error']});continue
        hits=list(dict.fromkeys(h['doc_id'] for h in result.get('hits',[])))[:3]
        rank=next((i+1 for i,d in enumerate(hits) if d in expected),None)
        if expected:
            for k in scores:scores[k].append(len(expected.intersection(hits[:k]))/len(expected))
            rr.append(1/rank if rank else 0)
        else:false.append(bool(hits))
        rows.append({'case_id':case['id'],'status':'scored','expected_doc_ids':sorted(expected),'actual_doc_ids':hits,
                     'first_correct_rank':rank,'recall_at_1':len(expected.intersection(hits[:1]))/len(expected) if expected else None,
                     'recall_at_3':len(expected.intersection(hits))/len(expected) if expected else None,
                     'rr':(1/rank if rank else 0) if expected else None,'no_answer_false_recall':bool(hits) if not expected else None})
    average=lambda values:sum(values)/len(values) if values else None
    return {'cases':len(cases),'answerable_scored':len(rr),'no_answer_scored':len(false),
            'recall_at_1':average(scores[1]),'recall_at_3':average(scores[3]),'mrr':average(rr),
            'no_answer_false_recall_rate':average(false),'not_run_cases':missing,'indeterminate_cases':indeterminate,
            'not_applicable_recall_mrr_cases':sum(not c['expected_doc_ids'] for c in cases),'rows':rows}


def validate_generation_binding(settings,provider):
    from target.deepseek_runtime import DeepSeekError
    expected=AUTH/(provider+'-generation.db')
    if (settings.ledger_path.resolve()!=expected.resolve() or settings.max_requests!=2 or settings.max_model_calls!=2
        or Path(os.getenv('TICKET_INITIAL_LIVE_BUDGET','')).resolve()!=(AUTH/'generation-total.db').resolve()
        or os.getenv('TICKET_TOTAL_REQUEST_LIMIT')!='4'):
        raise DeepSeekError('v352_fixed_generation_budget_required')
    marker=AUTH/'generation-attempt.json'
    if not marker.exists() or read(marker).get('explicit_command_authorization')!=4:
        raise DeepSeekError('v352_explicit_validation_command_required')
