"""审查专用离线回归：清空真实模型凭据，阻断 Python 非回环网络。"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

GUARD=r'''import socket, ipaddress, os, json
def _allowed(host):
    if host is None: return True
    if isinstance(host,bytes): host=host.decode('ascii','replace')
    if str(host).lower()=='localhost': return True
    try: return ipaddress.ip_address(str(host)).is_loopback
    except ValueError: return False
def _deny(host):
    with open(os.environ['TICKET_OFFLINE_GUARD_LOG'],'a',encoding='utf-8') as f:
        f.write(json.dumps({'blocked_non_loopback':str(host)})+'\n')
    raise PermissionError('Offline evidence review prohibits non-loopback networking')
_connect=socket.socket.connect
_connect_ex=socket.socket.connect_ex
_getaddrinfo=socket.getaddrinfo
def connect(self,address):
    if isinstance(address,tuple) and not _allowed(address[0]): _deny(address[0])
    return _connect(self,address)
def connect_ex(self,address):
    if isinstance(address,tuple) and not _allowed(address[0]): _deny(address[0])
    return _connect_ex(self,address)
def getaddrinfo(host,*args,**kwargs):
    if not _allowed(host): _deny(host)
    return _getaddrinfo(host,*args,**kwargs)
socket.socket.connect=connect
socket.socket.connect_ex=connect_ex
socket.getaddrinfo=getaddrinfo
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'docs/evidence/deepseek/review-20261016/offline_run')
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    runtime=ROOT/'artifacts/runtime'/('live-review-offline-'+uuid.uuid4().hex[:8])
    runtime.mkdir(parents=True)
    (runtime/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    baseline=json.loads((ROOT/'docs/evidence/deepseek/baseline.json').read_text(encoding='utf-8'))
    critical=list(baseline['protected_sha256'])+[
        'docs/evidence/deepseek/api-20261016-001224-2c3484/report.json',
        'docs/evidence/deepseek/api-20261016-001224-2c3484/tickets.db',
        'docs/evidence/deepseek/api-20261016-001224-2c3484/traces/traces.jsonl',
        'docs/evidence/deepseek/api-20261016-001224-2c3484/traces/deepseek_runs.jsonl',
        'artifacts/runtime/deepseek-budget/requests.db']
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in critical}
    env=dict(os.environ)
    for name in list(env):
        if name.endswith('_API_KEY') or name.endswith('_TOKEN') or name.startswith('DEEPSEEK_'):
            env.pop(name,None)
    env.update(PYTHONIOENCODING='utf-8',PYTHONPATH=str(runtime)+os.pathsep+str(ROOT),
        AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_MODEL='mock-offline-review',
        AGENT_USE_HTTP='0',AGENT_VECTOR_RAG='0',AGENT_MAX_STEPS='8',AGENT_LC_TOOLSET='read_only',
        AGENT_DB_PATH=str(runtime/'base.db'),AGENT_TRACE_DIR=str(runtime/'base-traces'),
        DEEPSEEK_BUDGET_PATH=str(runtime/'offline-only-budget.db'),
        LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',
        TICKET_OFFLINE_GUARD_LOG=str(runtime/'blocked_network.jsonl'))
    jobs=[('deepseek_unit',['.venv-deepseek/Scripts/python.exe','-m','unittest','discover','-s','tests','-v']),
          ('v3_unit',['.venv-v3/Scripts/python.exe','-m','unittest','discover','-s','tests','-v']),
          ('v2_unit',['.venv/Scripts/python.exe','-m','unittest','discover','-s','tests','-v']),
          ('mock_smoke',['.venv-deepseek/Scripts/python.exe','scripts/smoke.py','--output-dir',str(out/'mock_smoke')])]
    def run(job):
        name,command=job
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180)
        text=(result.stdout+result.stderr).replace(str(ROOT),'<project>').replace(str(Path.home()),'<user>')
        (out/(name+'.txt')).write_text(text,encoding='utf-8',newline='\n')
        match=re.search(r'Ran (\d+) tests',text);skip=re.search(r'OK \(skipped=(\d+)\)',text)
        return {'name':name,'exit_code':result.returncode,'tests':int(match[1]) if match else None,
                'skipped':int(skip[1]) if skip else 0,'log':name+'.txt'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run,jobs))
    blocked=runtime/'blocked_network.jsonl'
    attempts=blocked.read_text(encoding='utf-8').splitlines() if blocked.exists() else []
    unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    passed=all(r['exit_code']==0 for r in results) and not attempts and unchanged
    report={'status':'passed' if passed else 'failed','scope':'A offline regression, not B official 100 cases',
            'real_keys_removed_from_children':True,'non_loopback_python_network_blocked':True,
            'blocked_network_attempts':len(attempts),'new_deepseek_api_requests':0,
            'production_budget_and_live_evidence_unchanged':unchanged,'checked_file_count':len(hashes),'runs':results}
    (out/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    if not passed: raise SystemExit(1)


if __name__=='__main__': main()
