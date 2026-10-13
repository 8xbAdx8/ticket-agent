"""成员 A 的入口冒烟与证据采集；不产生比赛评分或 B 的缺陷评估。"""
import hashlib
import argparse
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description="A 的 Mock 全入口回归，使用新证据目录")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    OUT = args.output_dir or (ROOT/"docs/evidence/v2"/("smoke-"+stamp+"-"+uuid.uuid4().hex[:6]))
    if not OUT.is_absolute():
        OUT = ROOT/OUT
    OUT.mkdir(parents=True, exist_ok=False)
    def log_path(name):
        try:
            return (OUT/name).relative_to(ROOT).as_posix()
        except ValueError:
            return name  # 不将本机绝对路径写入报告
    runtime = ROOT / "artifacts" / "runtime" / ("verify-" + uuid.uuid4().hex[:8])
    runtime.mkdir(parents=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", AGENT_ENGINE="legacy", AGENT_PROVIDER="mock", AGENT_USE_HTTP="0", AGENT_VECTOR_RAG="0",
               AGENT_DB_PATH=str(runtime / "tickets.db"), AGENT_TRACE_DIR=str(runtime / "traces"))
    def sanitize(text):
        for path in (str(ROOT), str(Path.home()), str(Path(sys.base_prefix))):
            text = text.replace(path, "<local-path>")
        if env.get("AGENT_API_KEY"):
            text = text.replace(env["AGENT_API_KEY"], "<redacted>")
        return text
    env.pop("AGENT_API_KEY", None)
    baseline = {name: digest(ROOT / name) for name in ("docs/contract.md", "data/tickets.db", "traces/traces.jsonl")}
    runs = []
    def run(label, args, input=None):
        result = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, input=input,
                                text=True, encoding="utf-8", capture_output=True, timeout=90)
        (OUT / (label+".txt")).write_text(sanitize(result.stdout + result.stderr), encoding="utf-8")
        record = {"name":label, "command":"python " + " ".join(args), "exit_code":result.returncode,
                  "log":log_path(label+".txt")}
        runs.append(record)
        if result.returncode:
            raise RuntimeError("命令失败，见 " + record["log"])
        return result.stdout
    run("unit", ["-m", "unittest", "discover", "-s", "tests", "-v"])
    run("demo", ["run_demo.py"])
    run("once", ["cli.py", "once", "帮我查明天上海到杭州的高铁"])
    run("batch", ["cli.py", "batch", "cases/demo.json"])
    run("chat", ["cli.py", "chat"], "查明天上海到杭州的高铁\n我要买一张\n支付\nq\n")
    run("trace", ["cli.py", "trace"])
    example = json.loads(run("python_example", ["scripts/handoff_example.py"]))
    (OUT / "python_examples.json").write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
    # 真正启动本地 HTTP 服务，通过 HTTP 走所有 8 个工具。
    api_port = port()
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "target.mock_api:app", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def get(url):
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.read().decode("utf-8")
    def ready(url):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                return get(url)
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("本地服务启动未通过")
    try:
        base = f"http://127.0.0.1:{api_port}"
        health = json.loads(ready(base + "/health"))
        responses = []
        def post(name, args):
            req = urllib.request.Request(base+"/tool/"+name, data=json.dumps({"args":args}).encode(), headers={"Content-Type":"application/json"})
            result = json.loads(get_request(req))
            responses.append({"tool":name, "args":args, "result":result})
            if "error" in result:
                raise RuntimeError("HTTP 工具失败 " + name)
            return result
        day = (datetime.now(timezone(timedelta(hours=8))).date() + timedelta(days=1)).isoformat()
        row = post("query_tickets", dict(from_city="上海", to_city="杭州", date=day, seat_type="二等座"))["trains"][0]
        lock = post("lock_seat", dict(train_no=row["train_no"], date=day, seat_type="二等座", passengers=["张三"]))
        order = post("create_order", dict(lock_id=lock["lock_id"], passenger_ids=["张三"], contact="13800000001"))
        post("pay_order", dict(order_id=order["order_id"]))
        post("cancel_order", dict(order_id=order["order_id"]))
        post("query_order", dict(order_id=order["order_id"]))
        post("monitor_seat", dict(train_no="G101", date=day, seat_type="二等座"))
        post("search_policy", dict(question="退票手续费怎么算"))
        (OUT / "http.json").write_text(json.dumps({"health":health, "calls":responses}, ensure_ascii=False, indent=2), encoding="utf-8")
        env["AGENT_USE_HTTP"] = "1"
        env["AGENT_MOCK_URL"] = base
        run("http_agent", ["cli.py", "once", "订明天上海到杭州的高铁并支付"])
        env["AGENT_USE_HTTP"] = "0"
        runs.append({"name":"http", "command":"python -m uvicorn target.mock_api:app --host 127.0.0.1 --port <free-port>; HTTP 8 tools", "exit_code":0, "log":log_path("http.json")})
    finally:
        api.terminate()
        api.wait(timeout=10)
    web_port = port()
    web = subprocess.Popen([sys.executable,"-m","streamlit","run","web/app.py","--server.headless=true", "--server.address=127.0.0.1", "--server.port="+str(web_port), "--browser.gatherUsageStats=false"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        status = ready(f"http://127.0.0.1:{web_port}/_stcore/health")
        (OUT / "web_health.txt").write_text(status, encoding="utf-8")
        runs.append({"name":"web_health", "command":"python -m streamlit run web/app.py --server.headless=true --server.port=<free-port>", "exit_code":0, "log":log_path("web_health.txt")})
    finally:
        web.terminate()
        web.wait(timeout=10)
    trace = runtime / "traces" / "traces.jsonl"
    records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    (OUT / "mock_traces.jsonl").write_text(trace.read_text(encoding="utf-8"), encoding="utf-8")
    current = {name:digest(ROOT / name) for name in baseline}
    if baseline != current:
        raise RuntimeError("原数据库/历史 Trace/契约保护检查失败")
    summary = {"date":datetime.now(timezone(timedelta(hours=8))).isoformat(), "provider":"mock", "version_scope":"V2 A self-validation",
               "real_model_tested":False, "vector_tested":False, "runs":runs,
               "trace_count":len(records), "protected_files_sha256":current,
               "python":sys.version.split()[0], "versions":{name:importlib.metadata.version(name) for name in ["openai","streamlit","fastapi","uvicorn","pandas","pytest"]},
               "source_files_sha256":{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [*ROOT.glob("*.py"), *(p for folder in ["target","web","tests","scripts","data"] for p in (ROOT/folder).glob("*.py"))]},
               "mutation_labels":[x["label"] for x in example if x["label"].startswith("injected:")]}
    (OUT / "verification.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2), encoding="utf-8")
    print(json.dumps({"status":"passed", "commands":len(runs), "mock_trace_count":len(records), "protected_files_unchanged":True,"evidence_dir":log_path("verification.json")},ensure_ascii=False))


def get_request(req):
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")


if __name__ == "__main__":
    main()
