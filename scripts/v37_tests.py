"""Reproducible offline pytest executor. A tests are not B formal competition scores."""
import argparse,json,os,sys,subprocess,socket,ipaddress
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))

def execute(out,case=None):
    import pytest
    os.chdir(ROOT)
    out=out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated output required')
    out.mkdir(parents=True,exist_ok=False)
    for name in ('DEEPSEEK_API_KEY','DASHSCOPE_API_KEY','LANGCHAIN_API_KEY','LANGSMITH_API_KEY'):os.environ[name]=''
    os.environ.update(TICKET_DISABLE_LOCAL_SECRETS='1',LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false')
    original=socket.socket.connect;original_ex=socket.socket.connect_ex
    def allowed(addr):
        if not isinstance(addr,tuple):return True
        try:return ipaddress.ip_address(addr[0]).is_loopback
        except ValueError:return False
    def connect(s,a):
        if not allowed(a):raise OSError('offline executor blocked external network')
        return original(s,a)
    def connect_ex(s,a):
        if not allowed(a):raise OSError('offline executor blocked external network')
        return original_ex(s,a)
    socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
    rows=[]
    class Recorder:
        def pytest_runtest_logreport(self,report):
            if report.when=='call' or report.when in ('setup','teardown') and (report.failed or report.skipped):
                rows.append({'case_id':report.nodeid,'stage':report.when,'status':report.outcome,
                    'is_subtest':type(report).__name__.lower()=='subtestreport',
                    'duration_s':report.duration,'assertion_evidence':str(report.longrepr) if report.longrepr else None,
                    'run_id':None,'trace_id':'not_recorded_by_test'})
    started=datetime.now(timezone.utc).isoformat()
    args=[case or 'tests','-q','-p','no:cacheprovider','--junitxml='+str(out/'junit.xml')]
    if case and (not case.startswith('tests/') or '..' in case.split('/')):raise ValueError('test node must be within tests/')
    with (out/'pytest.log').open('w',encoding='utf8') as log:
        import contextlib
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):code=pytest.main(args,plugins=[Recorder()])
    try:
        git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,stderr=subprocess.DEVNULL).decode().strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,stderr=subprocess.DEVNULL))
    except (OSError,subprocess.SubprocessError):git_sha=dirty=None
    result={'owner':'A_offline_not_B_formal','command':args,'exit_code':int(code),'started':started,
        'ended':datetime.now(timezone.utc).isoformat(),'git_sha':git_sha,
        'dirty':dirty,
        'python':sys.version,'real_api_requests':0,'results':rows}
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'exit_code':int(code),'recorded_tests':sum(not r['is_subtest'] for r in rows),
        'recorded_subtests':sum(r['is_subtest'] for r in rows),'output':str(out)}));return int(code)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--case')
    a=p.parse_args();raise SystemExit(execute(a.out,a.case))
