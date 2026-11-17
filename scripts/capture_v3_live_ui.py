"""隔离数据库/Trace 实测新界面；只停止本脚本创建的 Streamlit 进程。"""
import argparse
import hashlib
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="ticket-live-ui-") as tmp:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", AGENT_ENGINE="langchain", AGENT_PROVIDER="mock", AGENT_LC_TOOLSET="all",
                   AGENT_USE_HTTP="0", AGENT_VECTOR_RAG="0", AGENT_MAX_STEPS="8", AGENT_DB_PATH=str(Path(tmp)/"tickets.db"),
                   AGENT_TRACE_DIR=str(Path(tmp)/"traces"), STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
        for key in list(env):
            if key == "AGENT_API_KEY" or key.startswith("MOCK_MUTATION_"):
                env.pop(key, None)
        seed = subprocess.run([sys.executable,"data/seed.py"],cwd=ROOT,env=env,capture_output=True)
        assert seed.returncode == 0
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
            run = subprocess.run([args.node,"scripts/capture_v3_live_ui.cjs","--browser",args.browser,
                                  "--url",f"http://127.0.0.1:{port}","--out",str(out)],cwd=ROOT,env=env,
                                 capture_output=True,text=True,encoding="utf-8",timeout=120)
            (out/"browser_run.txt").write_text((run.stdout+run.stderr).replace(str(ROOT),"<project>"),encoding="utf-8")
            assert run.returncode==0, "浏览器检查失败，见新证据目录 browser_run.txt"
            trace_path = Path(tmp)/"traces/traces.jsonl"
            lines = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            assert len(lines)==5, "界面重绘/回放/下载不能再次执行业务"
            assert [r["tool_sequence"] for r in lines]==[["query_tickets"],["query_tickets","lock_seat","create_order"],
                                                       ["search_policy"],["pay_order"],["pay_order"]]
            assert all(r["provider"]=="langchain_mock" and all(c["ok"] for s in r["steps"] for c in s["calls"]) for r in lines)
            assert "P11" in lines[2]["reply"] and "没有重复扣款" in lines[-1]["reply"]
            assert json.loads((out/"downloaded-trace.json").read_text(encoding="utf-8"))==lines[-1]
            (out/"actual_mock_results.json").write_text(json.dumps(lines,ensure_ascii=False,indent=2),encoding="utf-8")
            shutil.copyfile(trace_path,out/"traces.jsonl")
            (out/"source_check.json").write_text(json.dumps({"provider":"langchain_mock", "toolset":"all",
                "model_config":env.get("AGENT_MODEL","glm-4-flash"), "real_model_tested":False,
                "source_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                 for p in ("web/app.py","web/presentation.py","web/theme.css")}},indent=2),encoding="utf-8")
            print(json.dumps({"status":"passed","actual_mock_turns":5,"real_model_tested":False}))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__=="__main__":
    main()
