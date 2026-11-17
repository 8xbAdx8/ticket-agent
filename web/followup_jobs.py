"""One auxiliary job per answer; uses existing generation, clients and ledgers."""
import copy,concurrent.futures,threading

POOL=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='ticket-followups')
LOCK=threading.RLock()
JOBS={}


def schedule(session,record,authorized=False):
    from target.followups import read_record
    audit=session._audit_for(record)
    if not audit or audit.get('error') or record.get('finish_reason')!='stop' or session.read_only:return None
    if ((audit.get('judgement') or {}).get('hallucination') or {}).get('hallucination_detected') is True:return None
    operation=next((r for r in getattr(session,'operations',[]) if r.get('run_id')==audit['trace_id']),None)
    if operation and operation['status']!='SUCCEEDED':return None
    if session.pending_action():return None
    key=(session.sid,audit['trace_id'])
    with LOCK:
        if key in JOBS or read_record(session.trace_dir,*key,record):return JOBS.get(key)
        engine=getattr(session.agent,'langchain_engine',None)
        values=session._values()
        environment={'LANGSMITH_TRACING':'false','LANGCHAIN_TRACING_V2':'false'}
        if session.live:
            from target.live_providers import manual_environment
            environment.update(manual_environment(session.live_provider,session.root,model=session.live_model,full_tools=session.full_tools))
        snapshot=dict(record=copy.deepcopy(record),audit=copy.deepcopy(audit),values=values,environment=environment,
            live=session.live,authorized=authorized,ready=session.live and __import__('web.runtime',fromlist=['live_ready']).live_ready(session.live_provider),
            model=getattr(engine,'model',None),settings=getattr(engine,'deepseek_settings',None),
            asked=[r['user_msg'] for r in session.history]+session.shown_followups(),
            prior=[a['trace_id'] for a in session.audits if not a.get('error') and a.get('public_trace') in session.history])
        def work():
            from web.runtime import scoped
            from target.run_events import capture
            from target.followups import generate_and_save
            from web.evidence import read_jsonl
            rows,_=read_jsonl(session.trace_dir/'run_events.jsonl',limit=10000)
            rows=[e for e in rows if e.get('run_id')==key[1] and e.get('session_id')==key[0]]
            with scoped(snapshot['values'],snapshot['environment']),capture(session.trace_dir/'run_events.jsonl') as state:
                state.update(run_id=key[1],session_id=key[0],provider=record.get('provider'),model=record.get('model'),
                    last=rows[-1]['event_id'] if rows else None,sequence=len(rows),ids={e['event_id'] for e in rows})
                return generate_and_save(snapshot['record'],snapshot['audit'],session.trace_dir,asked=snapshot['asked'],live=snapshot['live'],
                    authorized=snapshot['authorized'],network_ready=snapshot['ready'],model=snapshot['model'],settings=snapshot['settings'],
                    prior_run_ids=snapshot['prior'],enhanced=True)
        future=POOL.submit(work);JOBS[key]=future
        return future


def pending(session):return any(sid==session.sid and not future.done() for (sid,_),future in list(JOBS.items()))
