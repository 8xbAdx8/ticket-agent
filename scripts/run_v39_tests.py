"""Isolated offline V3.9 suite. Does not execute or score the B formal 103."""
import argparse,contextlib,hashlib,ipaddress,json,os,socket,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(out):
    out=out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime') or not out.relative_to(ROOT/'artifacts/runtime').parts[0].startswith(('v39-implementation-','v391-d9-lifecycle-','v394-implementation-','v310-','full-system-audit-','e2e-user-journey-','v3101-e2e-')):
        raise ValueError('V39_ISOLATED_OUTPUT_REQUIRED')
    out.mkdir(parents=True,exist_ok=False)
    sys.dont_write_bytecode=True
    for name in list(os.environ):
        if name.endswith(('_API_KEY','_TOKEN')) or name.startswith(('AGENT_','TICKET_','RAILWAY_','DEEPSEEK_','DASHSCOPE_','RAG_','LANGCHAIN_','LANGSMITH_')):os.environ.pop(name,None)
    from scripts.regression_center import GUARD
    guard=out/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf8')
    os.environ.update(TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='1',AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_DB_PATH=str(out/'unused-legacy.sqlite'),AGENT_TRACE_DIR=str(out/'unused-legacy-traces'),LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',RAILWAY_SIMULATION_ENABLED='0',RAILWAY_SIM_DB_PATH=str(out/'ui-simulation.sqlite'),RAG_ALLOW_NETWORK='0',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(guard)+os.pathsep+str(ROOT),TICKET_REGRESSION_NETWORK_LOG=str(out/'network-blocks.jsonl'))
    protected_db=ROOT/'data/v39/simulation.sqlite'
    protected_db_before=hashlib.sha256(protected_db.read_bytes()).hexdigest() if protected_db.exists() else None
    current_db=ROOT/'data/v39/simulation-v391.sqlite'
    current_db_before=hashlib.sha256(current_db.read_bytes()).hexdigest() if current_db.exists() else None
    original=socket.socket.connect;original_ex=socket.socket.connect_ex
    def allow(address):
        if not isinstance(address,tuple):return
        try:ok=ipaddress.ip_address(address[0]).is_loopback
        except ValueError:ok=False
        if not ok:
            with (out/'network-blocks.jsonl').open('a',encoding='utf8') as f:f.write('{"event":"external_connection_blocked"}\n')
            raise OSError('V39_OFFLINE_NETWORK_BLOCKED')
    def connect(s,a):allow(a);return original(s,a)
    def connect_ex(s,a):allow(a);return original_ex(s,a)
    socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
    import pytest
    rows=[]
    class Recorder:
        def pytest_runtest_logreport(self,report):
            if report.when=='call' or report.when in ('setup','teardown') and (report.failed or report.skipped):
                rows.append(dict(case_id=report.nodeid,stage=report.when,status=report.outcome,is_subtest=type(report).__name__.lower()=='subtestreport',duration_s=report.duration,evidence=str(report.longrepr) if report.longrepr else None))
    paths=list((ROOT/'target/v39').glob('*'))+list((ROOT/'tests/v39').glob('*.py'))
    paths+=list((ROOT/'tests/v39').rglob('*.json'))
    paths += [ROOT/n for n in ('target/agent.py','target/langchain_agent.py','web/app.py','web/railway_simulation.py','scripts/run_v39_tests.py')]
    manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    (out/'source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    args=['tests/v39','-q','-p','no:cacheprovider','--tb=short','--basetemp='+str(out/'temp'),'--junitxml='+str(out/'junit.xml')]
    start=datetime.now(timezone.utc).isoformat()
    try:
        with (out/'pytest.log').open('x',encoding='utf8') as log:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):code=pytest.main(args,plugins=[Recorder()])
    finally:socket.socket.connect=original;socket.socket.connect_ex=original_ex
    protected_db_after=hashlib.sha256(protected_db.read_bytes()).hexdigest() if protected_db.exists() else None
    if protected_db_before!=protected_db_after:raise RuntimeError('V39_DEFAULT_DATABASE_CHANGED_DURING_TEST')
    current_db_after=hashlib.sha256(current_db.read_bytes()).hexdigest() if current_db.exists() else None
    if current_db_before!=current_db_after:raise RuntimeError('V391_DEFAULT_DATABASE_CHANGED_DURING_TEST')
    result=dict(owner='Codex_development_not_independent_not_B_formal',command=args,started=start,ended=datetime.now(timezone.utc).isoformat(),python=sys.version,sqlite_version=__import__('sqlite3').sqlite_version,external_connections_blocked=True,real_api_requests=0,default_database_before_sha256=protected_db_before,default_database_after_sha256=protected_db_after,default_database_unchanged=protected_db_before==protected_db_after,v391_default_database_unchanged=current_db_before==current_db_after,ui_database_path=str(out/'ui-simulation.sqlite'),exit_code=int(code),results=rows)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(exit_code=int(code),output=str(out),counts={s:sum(r['status']==s for r in rows) for s in ('passed','failed','skipped')})))
    return int(code)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();os.chdir(ROOT);sys.path.insert(0,str(ROOT));raise SystemExit(run(a.out))
