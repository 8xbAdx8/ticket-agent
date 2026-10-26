"""Run pytest and the unchanged V3.5/old-environment matrix with remote sockets blocked."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from run_deepseek_review_offline import GUARD


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--current-only',action='store_true',help='Only pytest in the installed environment; omit the optional older-venv matrix')
    args=parser.parse_args(argv);out=args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime') or out==(ROOT/'artifacts/runtime'):
        raise ValueError('isolated_output_required')
    out.mkdir(parents=True,exist_ok=False)
    baseline=ROOT/'artifacts/runtime/v351-work/protected.json'
    if baseline.exists():original=json.loads(baseline.read_text(encoding='utf-8'))
    else:
        # A clean clone has no ignored A-machine snapshot. Protect its actual
        # current files instead; never pretend it contains the original DBs.
        files=set()
        for name in ('data','traces','docs/evidence','docs/handoff','cases','tests'):
            files.update(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        files.update(p for p in (ROOT/'artifacts/runtime').rglob('*.db') if not p.is_relative_to(out))
        files.add(ROOT/'docs/contract.md')
        original={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    guard=out/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    env=dict(os.environ)
    for name in list(env):
        if name.endswith(('_API_KEY','_TOKEN')) or name.startswith('DEEPSEEK_'):env.pop(name,None)
    env.update(TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='1',RAG_ALLOW_NETWORK='0',
        AGENT_RAG_MODE='',RAG_QUALITY_PROFILE='v351',AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_MUTATIONS='{}',
        AGENT_DB_PATH=str(out/'unused.db'),AGENT_TRACE_DIR=str(out/'unused-traces'),
        PYTHONIOENCODING='utf-8',PYTHONPATH=str(guard)+os.pathsep+str(ROOT),
        TICKET_OFFLINE_GUARD_LOG=str(out/'blocked_network.jsonl'),LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false')
    def run(name,command):
        proc=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=900)
        text=(proc.stdout+proc.stderr).replace(str(ROOT),'<project>').replace(str(Path.home()),'<user>')
        text=re.sub(r'(?i)C:[\\/]+Users[\\/]+W(?=[\\/]|\b)','<user>',text)
        (out/(name+'.txt')).write_text(text,encoding='utf-8')
        return proc.returncode,text
    pytest_code,console=run('pytest',[sys.executable,'-m','pytest','tests','-q','--disable-warnings','--junitxml',str(out/'pytest.xml')])
    xml=ET.parse(out/'pytest.xml').getroot()
    suites=list(xml.iter('testsuite'))
    counts={name:sum(int(s.get(name,'0')) for s in suites) for name in ('tests','failures','errors','skipped')}
    passed=re.search(r'(\d+) passed',console);subtests=re.search(r'(\d+) subtests passed',console)
    if args.current_only:old_code=0;compatibility={'status':'not_run','reason':'current-only requested'}
    else:
        old_code,_=run('v35_and_older',[sys.executable,'scripts/verify_v35_offline.py','--out',str(out/'compatibility')])
        compatibility=json.loads((out/'compatibility/report.json').read_text(encoding='utf-8'))
    changed=[p for p,h in original.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    blocked=sum(len(p.read_text(encoding='utf-8').splitlines()) for p in out.rglob('*blocked*network*.jsonl'))
    result={'schema':'ticket-v351-offline/1','tested_source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'status':'passed' if pytest_code==old_code==0 and (args.current_only or compatibility['status']=='passed') and not changed and not blocked else 'failed',
        'pytest':{'exit_code':pytest_code,'passed_console':int(passed[1]) if passed else None,
                  'subtests_passed_console':int(subtests[1]) if subtests else 0,'junit':counts},
        'compatibility':compatibility,'protected_files':len(original),'changed_original_files':changed,
        'blocked_network_attempts':blocked,'real_generation_requests':0,'real_embedding_requests':0,'langsmith_requests':0,
        'new_api_cost':0,'scope':'A offline development regression, not B official scores or post-fix Live acceptance.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='compatibility'},ensure_ascii=False))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
