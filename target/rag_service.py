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
    import config
    from target.rag_store import PolicyIndex,ROOT
    from target.rag_protection import is_baseline,ProtectedPolicyIndex
    path=Path(os.getenv('RAG_INDEX_DIR',str(ROOT/'artifacts/runtime/v35-rag/index')))
    if is_baseline(path) and config.POLICY_PATH.resolve() != (ROOT/'data/policies.md').resolve():
        raise ValueError('new_policy_requires_independent_index')
    return ProtectedPolicyIndex(path) if is_baseline(path) else PolicyIndex(path,policy=config.POLICY_PATH)


def retrieve(question,mode=None,*,allow_network=False,k=None,threshold=None):
    import config
    from target.rag_store import documents,keyword
    from target.run_events import emit
    mode=mode or os.getenv('AGENT_RAG_MODE','keyword')
    started=time.perf_counter();identity=uuid.uuid4().hex
    # capture owns run_id/session_id. Do not overwrite them with optional RAG
    # scope values; the latter may be absent in direct/local invocations.
    event_scope={key:SCOPE.get()[key] for key in ('call_id',) if SCOPE.get().get(key) is not None}
    evidence=None
    try:
        if mode not in ('keyword','vector','hybrid'):raise ValueError('invalid_rag_mode')
        k=k or int(os.getenv('RAG_TOP_K','3'))
        if not 1<=k<=20:raise ValueError('invalid_top_k')
        emit('rag_start','running',tool='search_policy',retrieval_id=identity,
             mode=mode,top_k=k,question=question,**event_scope)
        frozen=None
        if os.getenv('TICKET_FROZEN_RAG_EVIDENCE'):
            from target.v352_validation import AUTH,read,canonical_hash
            frozen=read(Path(os.environ['TICKET_FROZEN_RAG_EVIDENCE']))
            if question!=frozen['question']:raise ValueError('paired_policy_query_changed_cache_only')
            if canonical_hash(documents(config.POLICY_PATH))!=frozen['policy_chunks_sha256']:
                raise ValueError('paired_policy_corpus_changed')
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
        if frozen is not None:
            actual={'question':question,'hits':evidence['hits'],'count':len(evidence['hits'])}
            if canonical_hash(actual)!=frozen['tool_result_sha256']:raise ValueError('paired_policy_evidence_changed')
            evidence['paired_tool_result_sha256']=frozen['tool_result_sha256']
        record={'schema':'ticket-rag-retrieval/1','retrieval_id':identity,**SCOPE.get(),'question':question,
                **evidence,'status':'retrieved','business_success':None}
    except Exception as exc:
        record={'schema':'ticket-rag-retrieval/1','retrieval_id':identity,**SCOPE.get(),'question':question,'mode':mode,
                'status':'failed','error_category':getattr(exc,'category',str(exc) if type(exc).__name__=='RagError' else type(exc).__name__),
                'retrieval_evidence':evidence,
                'total_latency_ms':round((time.perf_counter()-started)*1000),'business_success':False}
        try:
            save(record)
        finally:
            # A failed retrieval may have partial/risky candidates. Never
            # promote those candidates to successful result documents.
            emit('rag_error','failed',tool='search_policy',retrieval_id=identity,
                 mode=mode,error_category=record['error_category'],
                 duration_ms=record['total_latency_ms'],**event_scope)
        raise
    try:
        save(record)
    except Exception as exc:
        emit('rag_error','failed',tool='search_policy',retrieval_id=identity,
             mode=mode,error_category=type(exc).__name__,stage='evidence_persistence',
             duration_ms=round((time.perf_counter()-started)*1000),**event_scope)
        raise
    emit('rag_result','succeeded' if record['hits'] else 'insufficient_evidence',
         tool='search_policy',retrieval_id=identity,mode=mode,
         documents=record['hits'],hit_count=len(record['hits']),
         duration_ms=record.get('total_latency_ms'),sufficiency=record.get('sufficiency'),
         evidence_location='rag_runs.jsonl:retrieval_id='+identity,
         context_delivery='not_proven_by_retrieval_event',answer_support='not_verified',**event_scope)
    return {'question':question,'hits':record['hits'],'count':len(record['hits'])}


def save(record):
    import config
    from target.diagnostics import sanitize
    path=config.TRACE_DIR/'rag_runs.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(sanitize(record),ensure_ascii=False)+'\n')


def citation_check(reply,hits):
    allowed={h.get('doc_id') for h in hits if h.get('doc_id')}
    explicit=re.findall(r'\bdoc_id\s*[：:]\s*[`*]*([A-Za-z0-9_-]+)',reply,re.I)
    citations=list(dict.fromkeys([*re.findall(r'\bP\d+\b',reply),*explicit]))
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
        import config
        from target.rag_store import documents
        versions={h['doc_id']:h['version'] for h in documents(config.POLICY_PATH)}
        # Read actual current-user order state, without mutating the database or
        # treating this snapshot as a newly executed payment tool.
        from contextlib import closing
        import sqlite3
        statuses={}
        try:
            uri=config.DB_PATH.resolve().as_uri()+'?mode=ro'
            with closing(sqlite3.connect(uri,uri=True,timeout=5)) as conn:
                statuses={row[0]:row[1] for row in conn.execute(
                    'SELECT order_id,status FROM orders WHERE phone=?',(config.CURRENT_USER_PHONE,))}
        except (sqlite3.Error,OSError):
            pass
        check=check_answer(reply,hits,events=events,question=trace.user_msg,policy_versions=versions,order_statuses=statuses)
        wrong=list(dict.fromkeys([*result['wrong_citations'],*(d for finding in check['findings'] if finding['type']=='nonexistent_citation' for d in finding['doc_ids'])]))
        result.update(status=check['status'],wrong_citations=wrong,faithfulness_check=check,
                      citation_status='failed' if wrong else 'checked_ids_match' if check['cited_doc_ids'] else 'indeterminate')
    save({'schema':'ticket-rag-answer/1','trace_id':trace.trace_id,'session_id':trace.session_id,
          'provider':trace.provider,'model':trace.model,'original_model_reply':reply,**result,
          'business_success':False if result.get('status')=='failed' else None})
    return result
