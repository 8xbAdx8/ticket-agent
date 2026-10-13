"""启动自己的隔离 Mock 实例并截图；不会占用/停止用户原有服务或改写旧DB/Trace。"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/"docs/showcase/v3/真实截图"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser",required=True)
    parser.add_argument("--node",default=shutil.which("node"))
    args = parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="ticket-v3-screen-") as tmp:
        env = dict(os.environ,PYTHONIOENCODING="utf-8",AGENT_ENGINE="langchain",AGENT_PROVIDER="mock",AGENT_LC_TOOLSET="all",
                   AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",AGENT_MAX_STEPS="8",AGENT_DB_PATH=str(Path(tmp)/"tickets.db"),
                   AGENT_TRACE_DIR=str(Path(tmp)/"traces"),STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
        env.pop("AGENT_API_KEY",None)
        seed = subprocess.run([sys.executable,"data/seed.py"],cwd=ROOT,env=env,capture_output=True)
        assert seed.returncode==0
        process = subprocess.Popen([sys.executable,"-m","streamlit","run","web/app.py","--server.address","127.0.0.1",
                                    "--server.port",str(port),"--server.headless","true","--browser.gatherUsageStats","false"],
                                   cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        try:
            deadline = time.monotonic()+30
            while time.monotonic()<deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health",timeout=2) as response:
                        if response.read()==b"ok":
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("隔离服务未就绪")
            run = subprocess.run([args.node,"scripts/capture_v3_streamlit.cjs","--browser",args.browser,
                                  "--url",f"http://127.0.0.1:{port}"],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",timeout=90)
            assert run.returncode==0,"截图检查失败: "+run.stderr.splitlines()[0] if run.stderr else "截图检查失败"
            lines = [json.loads(line) for line in (Path(tmp)/"traces/traces.jsonl").read_text(encoding="utf-8").splitlines()]
            assert len(lines)==3
            assert [r["tool_sequence"] for r in lines]==[["query_tickets"],["query_tickets","lock_seat","create_order"],["search_policy"]]
            assert all(r["provider"]=="langchain_mock" and all(c["ok"] for s in r["steps"] for c in s["calls"]) for r in lines)
            assert "P11" in lines[-1]["reply"]
            (OUT/"实际Mock运行.json").write_text(json.dumps(lines,ensure_ascii=False,indent=2),encoding="utf-8")
            (OUT/"traces.jsonl").write_text("\n".join(json.dumps(r,ensure_ascii=False) for r in lines)+"\n",encoding="utf-8")
            print(json.dumps({"status":"passed","actual_screenshots":3,"actual_mock_turns":3,"real_model_tested":False},ensure_ascii=False))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
