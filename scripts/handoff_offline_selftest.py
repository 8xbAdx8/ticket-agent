"""A 自测的离线交接入口；不是 B 正式 100 条，也不运行 Live。"""
import json, os, re, subprocess, sys, uuid
from pathlib import Path

GUARD="import socket, ipaddress, os, json\ndef _allowed(host):\n    if host is None: return True\n    if isinstance(host,bytes): host=host.decode('ascii','replace')\n    if str(host).lower()=='localhost': return True\n    try: return ipaddress.ip_address(str(host)).is_loopback\n    except ValueError: return False\ndef _deny(host):\n    with open(os.environ['TICKET_OFFLINE_GUARD_LOG'],'a',encoding='utf-8') as f:\n        f.write(json.dumps({'blocked_non_loopback':str(host)})+'\\n')\n    raise PermissionError('Offline evidence review prohibits non-loopback networking')\n_connect=socket.socket.connect\n_connect_ex=socket.socket.connect_ex\n_getaddrinfo=socket.getaddrinfo\ndef connect(self,address):\n    if isinstance(address,tuple) and not _allowed(address[0]): _deny(address[0])\n    return _connect(self,address)\ndef connect_ex(self,address):\n    if isinstance(address,tuple) and not _allowed(address[0]): _deny(address[0])\n    return _connect_ex(self,address)\ndef getaddrinfo(host,*args,**kwargs):\n    if not _allowed(host): _deny(host)\n    return _getaddrinfo(host,*args,**kwargs)\nsocket.socket.connect=connect\nsocket.socket.connect_ex=connect_ex\nsocket.getaddrinfo=getaddrinfo\n"
ROOT=Path(__file__).resolve().parent.parent
runtime=ROOT/'artifacts/runtime'/('B-offline-'+uuid.uuid4().hex[:10])
runtime.mkdir(parents=True,exist_ok=False)
(runtime/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
env=dict(os.environ)
for key in list(env):
    if key.endswith('_API_KEY') or key.endswith('_TOKEN') or key.startswith('DEEPSEEK_'):
        env.pop(key,None)
env.update(PYTHONIOENCODING='utf-8',PYTHONPATH=str(runtime)+os.pathsep+str(ROOT),
    AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_MODEL='mock-offline-handoff',
    AGENT_USE_HTTP='0',AGENT_VECTOR_RAG='0',AGENT_MAX_STEPS='8',AGENT_LC_TOOLSET='read_only',
    AGENT_DB_PATH=str(runtime/'test.db'),AGENT_TRACE_DIR=str(runtime/'traces'),
    DEEPSEEK_BUDGET_PATH=str(runtime/'offline-fixture-budget.db'),
    LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',
    TICKET_OFFLINE_GUARD_LOG=str(runtime/'blocked_network.jsonl'))
result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
    cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180)
log=(result.stdout+result.stderr).replace(str(ROOT),'<package>').replace(str(Path.home()),'<user>')
(runtime/'unit.txt').write_text(log,encoding='utf-8')
blocked=runtime/'blocked_network.jsonl'
attempts=len(blocked.read_text(encoding='utf-8').splitlines()) if blocked.exists() else 0
count=re.search(r'Ran (\d+) tests',log);skip=re.search(r'OK \(skipped=(\d+)\)',log)
summary={'status':'passed' if result.returncode==0 and not attempts and count and int(count[1])>0 else 'failed',
    'scope':'A offline selftest, not B official 100 cases','tests':int(count[1]) if count else None,
    'skipped':int(skip[1]) if skip else 0,'exit_code':result.returncode,'blocked_network_attempts':attempts,
    'new_deepseek_api_requests':0,'log':(runtime/'unit.txt').relative_to(ROOT).as_posix(),
    'uses_existing_installed_dependencies':True}
(runtime/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
raise SystemExit(0 if summary['status']=='passed' else 1)
