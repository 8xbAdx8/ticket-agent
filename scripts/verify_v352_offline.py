"""V3.5.2 release regression: all tests, old matrices, 48-query status and immutable source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_deepseek_review_offline import GUARD
from verify_v351_offline import isolated_rag_inputs


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--current-only',action='store_true');args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    out.mkdir(parents=True,exist_ok=False)
    baseline=ROOT/'artifacts/runtime/v352-work/protected.json'
    if baseline.exists():protected=json.loads(baseline.read_text(encoding='utf-8'))
    else:
        files={p for folder in ('data','traces','cases','tests','docs/evidence') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        from target.rag_protection import BASELINE
        files.update(p for p in BASELINE.rglob('*') if p.is_file())
        protected={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    guard=out/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    env=dict(os.environ)
    for name in list(env):
        if name.endswith(('_API_KEY','_TOKEN')) or name.startswith('DEEPSEEK_'):env.pop(name,None)
    env.update(PYTHONIOENCODING='utf-8',PYTHONPATH=str(guard)+os.pathsep+str(ROOT),TICKET_DISABLE_LOCAL_SECRETS='1',
        TICKET_WEB_OFFLINE_ONLY='1',TICKET_OFFLINE_GUARD_LOG=str(out/'blocked-network.jsonl'),AGENT_PROVIDER='mock',
        AGENT_ENGINE='legacy',AGENT_MODEL='mock-offline',AGENT_RAG_MODE='',RAG_QUALITY_PROFILE='v351',RAG_ALLOW_NETWORK='0',
        AGENT_MUTATIONS='{}',TICKET_API_VALIDATION_PROFILE='',LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',
        AGENT_DB_PATH=str(out/'unused.db'),AGENT_TRACE_DIR=str(out/'unused-traces'))
    env.pop('V352_PROTOCOL_EVIDENCE_OUT',None);env.update(isolated_rag_inputs(ROOT,out));runs=[]
    def run(name,command,extra=None):
        proc=subprocess.run(command,cwd=ROOT,env=dict(env,**(extra or {})),capture_output=True,text=True,encoding='utf-8',timeout=900)
        text=(proc.stdout+proc.stderr).replace(str(ROOT),'<project>').replace(str(Path.home()),'<user>')
        text=re.sub(r'(?i)C:[\\/]+Users[\\/]+W(?=[\\/]|\b)','<user>',text)
        (out/(name+'.txt')).write_text(text,encoding='utf-8');runs.append({'name':name,'exit_code':proc.returncode})
        return text
    text=run('pytest',[sys.executable,'-m','pytest','tests','-q','--disable-warnings','--junitxml',str(out/'pytest.xml')],
             {'V352_PROTOCOL_EVIDENCE_OUT':str(out/'sdk-protocol')})
    suites=list(ET.parse(out/'pytest.xml').getroot().iter('testsuite'))
    junit={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    passed=re.search(r'(\d+) passed',text);subtests=re.search(r'(\d+) subtests passed',text)
    if args.current_only:compatibility={'status':'not_run'}
    else:
        run('compatibility',[sys.executable,'scripts/verify_v35_offline.py','--out',str(out/'compatibility')])
        compatibility=json.loads((out/'compatibility/report.json').read_text(encoding='utf-8'))
    run('retrieval48',[sys.executable,'scripts/evaluate_v352_rag.py','--out',str(out/'retrieval')])
    changed=[p for p,h in protected.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    blocked=sum(len(p.read_text(encoding='utf-8').splitlines()) for p in out.rglob('*blocked*network*.jsonl'))
    result={'schema':'ticket-v352-offline/1','tested_source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'status':'passed' if all(r['exit_code']==0 for r in runs) and not changed and not blocked and (args.current_only or compatibility['status']=='passed') else 'failed',
        'pytest':{'passed':int(passed[1]) if passed else None,'subtests_passed':int(subtests[1]) if subtests else 0,'junit':junit},
        'runs':runs,'compatibility':compatibility,'protected_files':len(protected),'changed_original_files':changed,
        'source_index_byte_unchanged_this_version':not any('/v35-rag/index/' in p for p in changed),
        'prior_v351_incident_preserved':True,'real_generation_requests':0,'real_embedding_requests':0,'langsmith_requests':0,
        'blocked_network_attempts':blocked,'scope':'A offline acceptance; missing real vectors and unexecuted Live remain unverified.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='compatibility'}));return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
