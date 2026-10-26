"""Opt-in RAG service. Local sidecars keep the public search_policy contract intact."""
import contextvars
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
import uuid

SCOPE=contextvars.ContextVar('ticket_rag_scope',default={})


@contextmanager
def scope(**values):
    token=SCOPE.set(values)
    try:yield
    finally:SCOPE.reset(token)


def configured_index():
    from target.rag_store import PolicyIndex,ROOT
    return PolicyIndex(Path(os.getenv('RAG_INDEX_DIR',str(ROOT/'artifacts/runtime/v35-rag/index'))))


def retrieve(question,mode=None,*,allow_network=False,k=None,threshold=None):
    import config
    from target.rag_store import documents,keyword
    mode=mode or os.getenv('AGENT_RAG_MODE','keyword')
    if mode not in ('keyword','vector','hybrid'):raise ValueError('invalid_rag_mode')
    k=k or int(os.getenv('RAG_TOP_K','3'))
    if not 1<=k<=20:raise ValueError('invalid_top_k')
    started=time.perf_counter();identity=uuid.uuid4().hex
    evidence=None
    try:
        if mode=='keyword':
            profile=os.getenv('RAG_QUALITY_PROFILE','v351')
            if profile not in ('v35','v351'):raise ValueError('invalid_quality_profile')
            hits=keyword(documents(config.POLICY_PATH),question,20 if profile=='v351' else k)
            quality={}
            if profile=='v351':
                from target.rag_relevance import apply_quality
                quality=apply_quality(question,hits,[],'keyword',k)
                hits=quality['hits']
            evidence={'mode':'keyword','hits':hits,'embedding_model':None,'index_version':None,
                      'embedding_latency_ms':0,'embedding_receipts':[],'total_latency_ms':round((time.perf_counter()-started)*1000),**quality}
        else:
            evidence=configured_index().retrieve(question,mode,k,float(threshold if threshold is not None else os.getenv('RAG_VECTOR_THRESHOLD','0.35')),
                allow_network=allow_network,require_real=config.PROVIDER in ('deepseek','bailian'),quality_profile=os.getenv('RAG_QUALITY_PROFILE','v351'))
        from target.rag_faults import evidence_risks
        # Keep raw evidence visible to risk checks; scope filtering must not
        # silently hide an injected conflicting/obsolete document.
        risks=evidence_risks(evidence.get('candidate_hits',evidence['hits']))
        if risks:
            from target.rag_store import RagError
            evidence['risk_findings']=risks
            raise RagError('rag_evidence_risk')
        record={'schema':'ticket-rag-retrieval/1','retrieval_id':identity,**SCOPE.get(),'question':question,
                **evidence,'status':'retrieved','business_success':None}
    except Exception as exc:
        record={'schema':'ticket-rag-retrieval/1','retrieval_id':identity,**SCOPE.get(),'question':question,'mode':mode,
                'status':'failed','error_category':getattr(exc,'category',str(exc) if type(exc).__name__=='RagError' else type(exc).__name__),
                'retrieval_evidence':evidence,
                'total_latency_ms':round((time.perf_counter()-started)*1000),'business_success':False}
        save(record);raise
    save(record)
    return {'question':question,'hits':record['hits'],'count':len(record['hits'])}


def save(record):
    import config
    from target.diagnostics import sanitize
    path=config.TRACE_DIR/'rag_runs.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(sanitize(record),ensure_ascii=False)+'\n')


def citation_check(reply,hits):
    allowed={h['doc_id'] for h in hits};citations=list(dict.fromkeys(re.findall(r'\bP\d+\b',reply)))
    wrong=[c for c in citations if c not in allowed]
    return {'allowed_doc_ids':sorted(allowed),'cited_doc_ids':citations,'wrong_citations':wrong,
            'citation_status':'failed' if wrong else 'checked_ids_match' if citations else 'indeterminate',
            'citation_support':'indeterminate','faithfulness':'indeterminate',
            'scope':'Document-ID membership only; does not prove the cited passage supports every claim'}


def attach_answer(trace,events,reply):
    calls=[e for e in events if e.get('event')=='tool_end' and e.get('tool')=='search_policy' and e.get('ok')]
    if not calls:return None
    hits=[h for e in calls for h in e.get('result',{}).get('hits',[])]
    result=citation_check(reply,hits)
    if os.getenv('RAG_QUALITY_PROFILE','v351')=='v351':
        from target.rag_faithfulness import check_answer
        check=check_answer(reply,hits,events=events,question=trace.user_msg)
        wrong=list(dict.fromkeys(d for finding in check['findings'] if finding['type']=='nonexistent_citation' for d in finding['doc_ids']))
        result.update(status=check['status'],wrong_citations=wrong,faithfulness_check=check,
                      citation_status='failed' if wrong else 'checked_ids_match' if check['cited_doc_ids'] else 'indeterminate')
    save({'schema':'ticket-rag-answer/1','trace_id':trace.trace_id,'session_id':trace.session_id,
          'provider':trace.provider,'model':trace.model,'original_model_reply':reply,**result,
          'business_success':False if result.get('status')=='failed' else None})
    return result
