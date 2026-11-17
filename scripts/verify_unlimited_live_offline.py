"""Current-policy offline regression, with old data protected and sockets blocked.

A assertion source changes are versioned code. Historical B datasets, traces,
budgets, the policy corpus and the original Chroma source remain immutable data.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from run_deepseek_review_offline import GUARD
from verify_v351_offline import isolated_rag_inputs


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--current-only',action='store_true')
    args=parser.parse_args(argv)
    out=(args.out or ROOT/'artifacts/runtime'/('unlimited-offline-'+uuid.uuid4().hex)).resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):parser.error('isolated runtime output required')
    out.mkdir(parents=True,exist_ok=False)
    protected={}
    for folder in ('data','traces','docs/evidence','web/datasets','cases','tests','artifacts/runtime/v35-rag/index'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:protected[path.relative_to(ROOT).as_posix()]=digest(path)
    for path in (ROOT/'artifacts/runtime').rglob('*.db'):
        if not path.is_relative_to(out):protected[path.relative_to(ROOT).as_posix()]=digest(path)
    protected['docs/contract.md']=digest(ROOT/'docs/contract.md')
    guard=out/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    env={k:v for k,v in os.environ.items() if not k.endswith(('_API_KEY','_TOKEN'))
         and not k.startswith(('AGENT_','DEEPSEEK_','BAILIAN_','TICKET_','RAG_','LANGCHAIN_','LANGSMITH_','V352_'))}
    env.update(PYTHONIOENCODING='utf-8',PYTHONPATH=str(guard)+os.pathsep+str(ROOT),
               TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='1',
               TICKET_OFFLINE_GUARD_LOG=str(out/'blocked-network.jsonl'),TICKET_API_USAGE_DIR=str(out/'usage'),
               AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_MODEL='mock-offline',AGENT_RAG_MODE='',
               AGENT_MUTATIONS='{}',RAG_ALLOW_NETWORK='0',RAG_QUALITY_PROFILE='v351',
               LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',
               AGENT_DB_PATH=str(out/'unused.db'),AGENT_TRACE_DIR=str(out/'unused-traces'))
    env.update(isolated_rag_inputs(ROOT,out));runs=[]
    def run(name,command,extra=None):
        proc=subprocess.run(command,cwd=ROOT,env=dict(env,**(extra or {})),capture_output=True,text=True,encoding='utf-8',timeout=1200)
        text=(proc.stdout+proc.stderr).replace(str(ROOT),'<project>').replace(str(Path.home()),'<user>')
        (out/(name+'.txt')).write_text(text,encoding='utf-8')
        runs.append({'name':name,'exit_code':proc.returncode});print(json.dumps(runs[-1]),flush=True)
        return text
    console=run('pytest',[sys.executable,'-m','pytest','tests','-q','--disable-warnings','--junitxml',str(out/'pytest.xml')],
                {'V352_PROTOCOL_EVIDENCE_OUT':str(out/'paired-sdk')})
    suites=list(ET.parse(out/'pytest.xml').getroot().iter('testsuite'))
    junit={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    compatibility={'status':'not_run'}
    if not args.current_only:
        run('compatibility',[sys.executable,'scripts/verify_v35_offline.py','--out',str(out/'compatibility')])
        if (out/'compatibility/report.json').exists():compatibility=json.loads((out/'compatibility/report.json').read_text(encoding='utf-8'))
    run('retrieval48',[sys.executable,'scripts/evaluate_v352_rag.py','--out',str(out/'retrieval48')])
    changed=[name for name,h in protected.items() if not (ROOT/name).is_file() or digest(ROOT/name)!=h]
    blocked=sum(len(p.read_text(encoding='utf-8').splitlines()) for p in out.rglob('*blocked*network*.jsonl'))
    passed=re.search(r'(\d+) passed',console);subtests=re.search(r'(\d+) subtests passed',console)
    source=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    report={'schema':'ticket-unlimited-offline/1','status':'passed' if all(r['exit_code']==0 for r in runs) and not changed and not blocked else 'failed',
        'tested_source_commit':source.stdout.strip() if source.returncode==0 else None,
        'pytest':{'passed':int(passed[1]) if passed else None,'subtests_passed':int(subtests[1]) if subtests else 0,'junit':junit},
        'runs':runs,'compatibility':compatibility,'protected_files':len(protected),'changed_original_files':changed,
        'blocked_network_attempts':blocked,'real_model_requests':0,'real_embedding_requests':0,'langsmith_requests':0,
        'usage_policy':'unlimited_usage_only','scope':'A current-policy offline regression; not a new Live model result or B formal grade'}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='compatibility'},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
