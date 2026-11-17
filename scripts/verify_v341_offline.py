"""Offline-only V3.4.1 evidence export plus existing full regression. No Live action."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from run_deepseek_review_offline import GUARD


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    base=(ROOT/'artifacts/runtime').resolve()
    if not out.is_relative_to(base) or out==base:raise ValueError('new_runtime_child_required')
    out.mkdir(parents=True,exist_ok=False)
    protected={}
    for name in ('data','traces','docs/evidence','web/datasets'):
        for p in (ROOT/name).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:protected[p.relative_to(ROOT).as_posix()]=sha(p)
    for p in (ROOT/'artifacts/runtime').rglob('*.db'):
        if not p.is_relative_to(out):protected[p.relative_to(ROOT).as_posix()]=sha(p)
    protected['docs/contract.md']=sha(ROOT/'docs/contract.md')
    save(out/'protection-before.json',protected)
    guard=out/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    env=dict(os.environ)
    for name in list(env):
        if name.endswith(('_API_KEY','_TOKEN')) or name.startswith('DEEPSEEK_'):env.pop(name,None)
    env.update(PYTHONIOENCODING='utf-8',PYTHONPATH=str(guard)+os.pathsep+str(ROOT),
               TICKET_OFFLINE_GUARD_LOG=str(out/'blocked_network.jsonl'),TICKET_WEB_OFFLINE_ONLY='1',
               TICKET_DISABLE_LOCAL_SECRETS='1',AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',
               AGENT_MODEL='mock-offline',AGENT_DB_PATH=str(out/'unused.db'),AGENT_TRACE_DIR=str(out/'unused-traces'),
               AGENT_MUTATIONS='{}',LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',TICKET_INITIAL_LIVE_BUDGET='')
    runs=[]
    def run(name,argv):
        p=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=600)
        log=p.stdout+p.stderr
        log=log.replace(str(ROOT),'<project>').replace(str(Path.home()),'<user>')
        log=re.sub(r'(?i)C:[\\/]+Users[\\/]+W(?=[\\/]|\b)','<user>',log)
        (out/(name+'.txt')).write_text(log,encoding='utf-8',newline='\n')
        counts=re.findall(r'Ran (\d+) tests?',log)
        skipped=re.findall(r'skipped=(\d+)',log)
        runs.append({'name':name,'exit_code':p.returncode,'collected':int(counts[-1]) if counts else None,
                     'skipped':int(skipped[-1]) if skipped else 0,'log':name+'.txt'})
    run('specialist',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_v341_reply_consistency.py','-v'])
    run('existing_full_regression',[sys.executable,'scripts/verify_v33_offline.py','--out',str(out/'full')])
    # The export itself only imports a pure local checker, never a model/client.
    from target.reply_consistency import check
    fixtures=json.loads((ROOT/'tests/fixtures/v341_reply_cases.json').read_text(encoding='utf-8'))['cases']
    cases=[]
    for case in fixtures:
        result=check(case['model_output'],case['authority_events'])
        expected=case['assertion']
        reason=expected.get('indeterminate_reason')
        passed=(result['status']==expected['status'] and
                sorted(f['field'] for f in result['findings'])==sorted(expected['finding_fields']) and
                (not reason or reason in [i['reason'] for i in result['indeterminate']]))
        value={**case,'actual':result,'assertion_passed':passed,'new_model_requests':0,
               'scope':'A deterministic regression; not B formal grading or post-fix Live'}
        save(out/'cases'/(case['id']+'.json'),value)
        cases.append({'case_id':case['id'],'assertion_passed':passed,'detector_status':result['status']})
    comparison=[]
    for provider in ('deepseek','bailian'):
        path=ROOT/'docs/evidence/v34/live-20261025'/provider/'original_result.json'
        d=json.loads(path.read_text(encoding='utf-8'));record=d['live_record']
        final=next((e for e in record['events'] if e.get('event')=='model_final'),{})
        comparison.append({'provider':provider,'source':path.relative_to(ROOT).as_posix(),'source_sha256':sha(path),
            'trace_id':record['trace_id'],'live_source_sha':record['git_sha'],'model':record['actual_models'],
            'user_input':d['public_trace']['user_msg'],'original_reply':d['public_trace']['reply'],
            'tool_calling_verified':d['tool_calling_verified'],
            'tool_executed':all(e.get('executed') is True for e in record['events'] if e.get('event')=='tool_end'),
            'actual_tools':[{'tool':e['tool'],'args':e.get('args'),'result':e.get('result')} for e in record['events'] if e.get('event')=='tool_end'],
            'historical_business_verified':provider=='deepseek',
            'original_live_guard':final.get('reply_consistency'),'original_live_guard_triggered':False,
            'v341_offline_replay':check(d['public_trace']['reply'],record['events']),
            'tokens':record['tokens'],'latency_ms':d['public_trace']['total_latency_ms'],'cost':None,
            'new_live_requests':0,'postfix_live_retested':False,
            'scope':'One saved Live query per provider; no general accuracy estimate'})
    save(out/'historical_comparison.json',comparison)
    changed=[n for n,h in protected.items() if not (ROOT/n).is_file() or sha(ROOT/n)!=h]
    network=sum(len(p.read_text(encoding='utf-8').splitlines()) for p in out.rglob('*blocked*network*.jsonl'))
    full=json.loads((out/'full/report.json').read_text(encoding='utf-8'))
    passed=all(r['exit_code']==0 for r in runs) and all(c['assertion_passed'] for c in cases) and not changed and not network and full['status']=='passed'
    head=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
    report={'schema':'ticket-v341-offline/1','timestamp':datetime.now(timezone.utc).isoformat(),
            'tested_source_head':head,'status':'passed' if passed else 'failed','runs':runs,
            'field_cases':len(cases),'field_assertions_passed':sum(c['assertion_passed'] for c in cases),
            'field_case_results':cases,'full_regression':full,
            'protected_files':len(protected),'changed_original_files':changed,
            'real_model_requests':0,'langsmith_requests':0,'blocked_network_attempts':network,
            'postfix_live_retested':False,'historical_source_files_unchanged':not changed,
            'limits':['Offline assertions are A self-tests, not B official results.',
                      'Field consistency is not general natural-language accuracy.',
                      'The historical Live samples were produced before this fix.']}
    save(out/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('full_regression','field_case_results','limits')},ensure_ascii=False))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
