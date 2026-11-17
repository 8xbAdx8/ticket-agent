"""Reproducible offline lab baseline/mutant matrix; never calls an external API."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))

SCENARIOS={
    'date_offset':'查明天上海到杭州的高铁二等座',
    'skip_lock':'订明天上海到杭州的高铁二等座',
    'repeat_call':'查明天上海到杭州的高铁二等座',
    'infinite_loop':'抢明天北京到上海的高铁票',
    'route_error':'退票手续费政策是什么？',
    'no_citation':'退票手续费政策是什么？',
    'hallucinated_train':'查明天上海到杭州的高铁二等座',
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve();runtime=(ROOT/'artifacts/runtime').resolve()
    if not out.is_relative_to(runtime) or out==runtime:parser.error('fresh artifacts/runtime directory required')
    out.mkdir(parents=True,exist_ok=False)
    for name in list(os.environ):
        if name.endswith(('_API_KEY','_TOKEN')) or name.startswith(('AGENT_','DEEPSEEK_','DASHSCOPE_','RAG_','LANGCHAIN_','LANGSMITH_')):
            os.environ.pop(name,None)
    os.environ.update(TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='1',
        TICKET_OFFLINE_GUARD_LOG=str(out/'blocked_network.jsonl'),TICKET_API_USAGE_DIR=str(out/'usage'),
        AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_USE_HTTP='0',AGENT_VECTOR_RAG='0',
        AGENT_DB_PATH=str(out/'unused.db'),AGENT_TRACE_DIR=str(out/'unused-traces'),AGENT_MUTATIONS='{}',
        LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false')
    from run_deepseek_review_offline import GUARD
    exec(GUARD,{})
    from web.runtime import Conversation
    from target.diagnostics import sanitize
    rows=[]
    for engine in ('legacy','langchain'):
        for name,message in SCENARIOS.items():
            pair={}
            for phase in ('baseline','mutant'):
                mutations={name:1 if name=='date_offset' else True} if phase=='mutant' else {}
                session=Conversation('lab',engine=engine,mutations=mutations,root=out/engine/name/phase)
                try:result=session.send(message,uuid.uuid4().hex);error=None
                except Exception as exc:
                    result=None;error={'type':type(exc).__name__,'category':(session.error or {}).get('category')}
                audit=session.audits[-1] if session.audits else {}
                judgement=audit.get('judgement',{});events=audit.get('mutation_events',[])
                injection=[e for e in events if e.get('mutation_name')==name and e.get('status')!='disabled']
                pair[phase]={'trace_id':audit.get('trace_id'),'trace_dir':session.trace_dir.relative_to(ROOT).as_posix(),
                    'input':message,'tool_sequence':result.get('tool_sequence') if result else None,
                    'finish_reason':result.get('finish_reason') if result else None,'error':error,
                    'injections':injection,'dimensions':judgement.get('dimensions',{}),
                    'quality_verdict':judgement.get('quality_verdict'),'failure_reasons':judgement.get('failure_reasons',[]),
                    'indeterminate_reasons':judgement.get('indeterminate_reasons',[]),
                    'assertions':judgement.get('assertions',[]),'contract_returned':audit.get('contract_returned')}
            baseline=pair['baseline'];mutant=pair['mutant']
            checks={'baseline_trace_saved':bool(baseline['trace_id']),
                    'mutant_trace_saved':bool(mutant['trace_id']),
                    'baseline_has_no_injection':not baseline['injections'],
                    'actual_injection_applied':any(e.get('status')=='applied' for e in mutant['injections']),
                    'baseline_no_false_alarm':baseline['dimensions'].get('platform_defect_detected') is False,
                    'platform_detected':mutant['dimensions'].get('platform_defect_detected') is True}
            rows.append({'engine':engine,'mutation':name,'checks':checks,'baseline':baseline,'mutant':mutant})
    session=Conversation('lab',root=out/'concurrency')
    normal,mutant=session.concurrency('same_lock_many')
    rows.append({'engine':'backend_concurrency','mutation':'concurrent_duplicate_order',
        'checks':{'baseline_trace_saved':bool(normal.get('trace_id')),'mutant_trace_saved':bool(mutant.get('trace_id')),
                  'baseline_has_no_injection':not normal['judgement']['dimensions']['injection_applied'],
                  'actual_injection_applied':mutant['judgement']['dimensions']['injection_applied'] is True,
                  'baseline_no_false_alarm':normal['judgement']['dimensions']['platform_defect_detected'] is False,
                  'platform_detected':mutant['judgement']['dimensions']['platform_defect_detected'] is True},
        'baseline':{'trace_id':normal['trace_id'],'trace_dir':session.trace_dir.relative_to(ROOT).as_posix(),
                    'dimensions':normal['judgement']['dimensions'],'quality_verdict':normal['judgement']['quality_verdict'],
                    'assertions':normal['judgement']['assertions'],'resources_cleaned':normal['resources_cleaned']},
        'mutant':{'trace_id':mutant['trace_id'],'trace_dir':session.trace_dir.relative_to(ROOT).as_posix(),
                  'dimensions':mutant['judgement']['dimensions'],'quality_verdict':mutant['judgement']['quality_verdict'],
                  'assertions':mutant['judgement']['assertions'],'resources_cleaned':mutant['resources_cleaned'],
                  'injections':mutant['mutation_events'],'database_isolation':mutant['database_isolation']}})
    failures=[{'engine':r['engine'],'mutation':r['mutation'],'failed':[k for k,v in r['checks'].items() if not v]}
              for r in rows if not all(r['checks'].values())]
    report=sanitize({'schema':'test-lab-offline-matrix/1','status':'failed' if failures else 'passed',
        'scope':'actual offline mock/backend execution, not live model evidence or B score',
        'real_model_requests':0,'embedding_requests':0,'langsmith_requests':0,'rows':rows,'failures':failures})
    (out/'matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'pairs':len(rows),'failures':failures},ensure_ascii=False))
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
