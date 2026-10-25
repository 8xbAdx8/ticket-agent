"""Freeze all V3.5 paid evidence, block remote Python sockets, and run all regressions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_deepseek_review_offline import GUARD


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    out.mkdir(parents=True,exist_ok=False)
    protected={}
    def keep(path):
        if path.is_file() and '__pycache__' not in path.parts:protected[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    for folder in ('data','traces','docs/evidence','web/datasets','artifacts/runtime/v35-qwen38-rag/authorization-20261026'):
        for f in (ROOT/folder).rglob('*'):keep(f)
    for f in (ROOT/'artifacts/runtime').rglob('*.db'):
        if not f.is_relative_to(out):keep(f)
    keep(ROOT/'docs/contract.md')
    guard=out/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    env=dict(os.environ)
    for n in list(env):
        if n.endswith(('_API_KEY','_TOKEN')) or n.startswith('DEEPSEEK_'):env.pop(n,None)
    env.update(PYTHONIOENCODING='utf-8',PYTHONPATH=str(guard)+os.pathsep+str(ROOT),TICKET_DISABLE_LOCAL_SECRETS='1',
               TICKET_OFFLINE_GUARD_LOG=str(out/'blocked_network.jsonl'),TICKET_WEB_OFFLINE_ONLY='1',
               AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_MODEL='mock-offline',AGENT_RAG_MODE='',RAG_ALLOW_NETWORK='0',
               AGENT_MUTATIONS='{}',TICKET_API_VALIDATION_PROFILE='',LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',
               AGENT_DB_PATH=str(out/'unused.db'),AGENT_TRACE_DIR=str(out/'unused-traces'))
    runs=[]
    def run(name,argv):
        p=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=600)
        text=p.stdout+p.stderr
        text=text.replace(str(ROOT),'<project>').replace(str(Path.home()),'<user>')
        text=re.sub(r'(?i)C:[\\/]+Users[\\/]+W(?=[\\/]|\b)','<user>',text)
        (out/(name+'.txt')).write_text(text,encoding='utf-8')
        count=re.findall(r'Ran (\d+) tests?',text);skipped=re.findall(r'skipped=(\d+)',text)
        runs.append({'name':name,'exit_code':p.returncode,'collected':int(count[-1]) if count else None,
                     'skipped':int(skipped[-1]) if skipped else 0})
    run('v35_full_unit',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
    run('old_environment_regression',[sys.executable,'scripts/verify_v33_offline.py','--out',str(out/'old-environments')])
    code="from pathlib import Path;from target.rag_faults import NAMES,run_experiment;import json;out=Path(__import__('sys').argv[1]);rows=[run_experiment(n,out/n) for n in NAMES];print(json.dumps({'mutations':len(rows),'passed':sum(r['passed'] for r in rows),'real_requests':0}));raise SystemExit(0 if all(r['passed'] for r in rows) else 1)"
    run('rag_eight_mutations',[sys.executable,'-c',code,str(out/'rag-mutations')])
    changed=[f for f,h in protected.items() if not (ROOT/f).is_file() or hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=h]
    network=sum(len(f.read_text(encoding='utf-8').splitlines()) for f in out.rglob('*blocked*network*.jsonl'))
    old=json.loads((out/'old-environments/report.json').read_text(encoding='utf-8'))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    result={'schema':'ticket-v35-offline/1','tested_source_head':head,
            'status':'passed' if all(r['exit_code']==0 for r in runs) and old['status']=='passed' and not changed and not network else 'failed',
            'runs':runs,'old_environment_regression':old,'protected_files':len(protected),'changed_original_files':changed,
            'real_embedding_requests':0,'real_generation_requests':0,'langsmith_requests':0,'blocked_network_attempts':network,
            'scope':'A offline regression. Real V3.5 evidence is separate; offline stubs do not count as Live.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='old_environment_regression'},ensure_ascii=False))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
