"""Actual Windows entry points, isolated local services and no remote API requests."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent


def clean_env():
    env={k:v for k,v in os.environ.items() if not k.endswith(('_API_KEY','_TOKEN'))
         and not k.startswith(('AGENT_','DEEPSEEK_','DASHSCOPE_','TICKET_','RAG_','LANGCHAIN_','LANGSMITH_'))}
    env.pop('PYTHONPATH',None)
    env.update(TICKET_DISABLE_LOCAL_SECRETS='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
               LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false')
    return env


def is_descendant(child,ancestor):
    """Verify process ownership before stopping a listener created by the test."""
    import ctypes
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                  ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                  ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                  ('name',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    snapshot=kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot==ctypes.c_void_p(-1).value:return False
    parents={};entry=Entry();entry.size=ctypes.sizeof(entry)
    try:
        present=kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while present:
            parents[int(entry.pid)]=int(entry.parent)
            present=kernel.Process32NextW(snapshot,ctypes.byref(entry))
    finally:kernel.CloseHandle(snapshot)
    visited=set()
    while child and child not in visited:
        if child==ancestor:return True
        visited.add(child);child=parents.get(child,0)
    return False


@unittest.skipUnless(os.name=='nt','Windows launcher')
class WindowsEntrypointTests(unittest.TestCase):
    def preflight(self,name,extra=None):
        env=clean_env();env.update(extra or {})
        run=subprocess.run(['cmd.exe','/c',str(ROOT/name),'-CheckOnly'],cwd=ROOT,env=env,
            capture_output=True,text=True,encoding='utf-8',timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertNotIn('offline-key-for-check-only',run.stdout+run.stderr)
        state=next((json.loads(line) for line in run.stdout.splitlines() if line.startswith('{')),None)
        return run,state

    def test_both_cmd_preflights_without_pythonpath_or_external_calls(self):
        for name,extra,provider in (
            ('启动_离线模式.cmd',{},'mock'),
            ('启动_在线模式.cmd',{'DEEPSEEK_API_KEY':'offline-key-for-check-only'},'deepseek'),
            ('启动_在线模式.cmd',{'DASHSCOPE_API_KEY':'offline-key-for-check-only',
                'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1'},'bailian')):
            with self.subTest(provider=provider):
                run,state=self.preflight(name,extra)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertEqual(state['provider'],provider)
                self.assertEqual(state['status'],'passed')
                self.assertEqual(state['model_requests_sent'],0)

    def test_qwen_without_endpoint_fails_preflight_without_request(self):
        run,state=self.preflight('启动_在线模式.cmd',{'DASHSCOPE_API_KEY':'offline-key-for-check-only'})
        self.assertEqual(run.returncode,2)
        self.assertEqual(state['status'],'missing_bailian_base_url')
        self.assertEqual(state['model_requests_sent'],0)

    def test_missing_key_fails_preflight_without_request(self):
        run,state=self.preflight('启动_在线模式.cmd')
        self.assertEqual(run.returncode,2)
        self.assertEqual(state['status'],'missing_key')
        self.assertEqual(state['model_requests_sent'],0)

    def test_broken_first_virtualenv_uses_next_usable_environment(self):
        site=ROOT/'.venv-v35/Lib/site-packages'
        if not site.is_dir():self.skipTest('V3.5 environment not installed')
        with tempfile.TemporaryDirectory(prefix='ticket-launch-probe-') as folder:
            root=Path(folder);scripts=root/'scripts';scripts.mkdir()
            shutil.copy2(ROOT/'scripts/Start-TicketAgent.ps1',scripts/'Start-TicketAgent.ps1')
            (scripts/'launch_app.py').write_text('import sys; print("SELECTED="+sys.executable)\n',encoding='utf-8')
            first=root/'.venv-v35/Scripts';first.mkdir(parents=True)
            (first/'python.exe').write_bytes(b'broken executable fixture')
            second=root/'.venv-deepseek/Scripts';second.mkdir(parents=True)
            shutil.copy2(ROOT/'.venv-v35/Scripts/python.exe',second/'python.exe')
            shutil.copy2(ROOT/'.venv-v35/pyvenv.cfg',root/'.venv-deepseek/pyvenv.cfg')
            env=clean_env();env['PYTHONPATH']=str(site)
            run=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
                '-File',str(scripts/'Start-TicketAgent.ps1'),'-Mode','offline','-CheckOnly'],
                cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('.venv-deepseek',run.stdout)

    def test_both_local_streamlit_services_start_with_isolated_data(self):
        # Tests health only; no model is called and each process tree is ours.
        base=ROOT/'artifacts/runtime';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='launcher-regression-',dir=base) as directory:
            root=Path(directory).resolve();self.assertTrue(root.is_relative_to(base.resolve()))
            from scripts.run_deepseek_review_offline import GUARD
            guard=root/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
            for mode in ('offline','live'):
                with self.subTest(mode=mode),socket.socket() as port_probe:
                    port_probe.bind(('127.0.0.1',0));port=port_probe.getsockname()[1]
                env=clean_env();env.update(TICKET_API_USAGE_DIR=str(root/'usage'),
                    TICKET_OFFLINE_GUARD_LOG=str(root/'blocked-network.jsonl'),PYTHONPATH=str(guard))
                if mode=='live':env['DEEPSEEK_API_KEY']='offline-key-for-check-only'
                command=['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
                    '-File',str(ROOT/'scripts/Start-TicketAgent.ps1'),'-Mode',mode,'-NoBrowser',
                    '-RuntimeRoot',str(root/mode),'-Port',str(port)]
                log=root/(mode+'.txt')
                with log.open('w',encoding='utf-8') as stream:
                    process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
                    try:
                        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        deadline=time.monotonic()+40;healthy=False
                        while time.monotonic()<deadline and process.poll() is None:
                            try:
                                with opener.open(f'http://127.0.0.1:{port}/_stcore/health',timeout=1) as response:
                                    healthy=response.status==200
                                if healthy:break
                            except (OSError,urllib.error.URLError):pass
                            time.sleep(.2)
                        self.assertTrue(healthy,'Local Streamlit did not become healthy')
                        self.assertFalse((root/'usage').exists(),'No model dispatch should occur during startup')
                    finally:
                        # Stop the listener we just started. taskkill /T needs
                        # WMI access on some Windows installations and may fail.
                        ports=subprocess.run(['netstat','-ano','-p','tcp'],capture_output=True,text=True,
                            timeout=10,creationflags=subprocess.CREATE_NO_WINDOW).stdout.splitlines()
                        for line in ports:
                            columns=line.split()
                            if len(columns)>=5 and columns[1]==f'127.0.0.1:{port}' and columns[3]=='LISTENING':
                                listener=int(columns[-1])
                                self.assertTrue(is_descendant(listener,process.pid),'Refusing to stop an unrelated service')
                                os.kill(listener,signal.SIGTERM)
                        try:process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            process.terminate();process.wait(timeout=5)
                self.assertNotIn('offline-key-for-check-only',log.read_text(encoding='utf-8'))
            self.assertFalse((root/'blocked-network.jsonl').exists())


class DotEnvPreflightTests(unittest.TestCase):
    def test_live_project_dotenv_is_loaded_without_printing_key(self):
        from scripts import launch_app
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.env').write_text('DEEPSEEK_API_KEY=offline-key-for-check-only\n',encoding='utf-8')
            env={'TICKET_API_USAGE_DIR':str(root/'usage')}
            with patch.object(launch_app,'ROOT',root),patch.dict(os.environ,env,clear=True),\
                 patch.object(launch_app,'missing_dependencies',return_value=[]):
                if os.name=='nt':
                    import winreg
                    registry=patch.object(winreg,'OpenKey',side_effect=OSError('fixture'))
                else:registry=contextlib.nullcontext()
                with registry,contextlib.redirect_stdout(io.StringIO()) as output:
                    code=launch_app.main(['--mode','live','--check-only'])
            state=json.loads(output.getvalue())
            self.assertEqual(code,0);self.assertTrue(state['api_key_configured'])
            self.assertEqual(state['model_requests_sent'],0)
            self.assertNotIn('offline-key-for-check-only',output.getvalue())


if __name__=='__main__':unittest.main()
