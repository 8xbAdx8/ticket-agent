"""A 定向修复离线复核；在隔离副本运行 B 原判据，不改 B 文件或原证据。"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from run_deepseek_review_offline import GUARD

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--b-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    b_root = args.b_root.resolve()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = ROOT/"artifacts/runtime"/("def06-def07-"+uuid.uuid4().hex[:8])
    runtime.mkdir(parents=True)
    (runtime/"sitecustomize.py").write_text(GUARD, encoding="utf-8")
    sandbox = runtime/"b-rerun"
    sandbox.mkdir()
    code_files = [ROOT/"config.py", Path(__file__)]
    for folder in ("target", "tests"):
        code_files.extend((ROOT/folder).glob("*.py"))
    source_hashes = {p.relative_to(ROOT).as_posix():sha(p) for p in code_files}
    # 仅复制业务源码和 B 的判定器；不复制密钥、库、账本和旧 results。
    for folder in ("target", "data"):
        for source in (ROOT/folder).rglob("*"):
            if source.is_file() and source.suffix in (".py", ".md"):
                dest = sandbox/source.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
    shutil.copyfile(ROOT/"config.py", sandbox/"config.py")
    originals = []
    for folder, pattern in (("judge", "*.py"), ("cases", "cases_*.json"), ("tests", "test_*.py")):
        for source in (b_root/folder).glob(pattern):
            dest = sandbox/source.relative_to(b_root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            originals.append({"path":source.relative_to(b_root).as_posix(), "sha256":sha(source),
                              "copied_sha256":sha(dest)})
    source = b_root/"verify_newcode_V3frozen.py"
    shutil.copyfile(source, sandbox/source.name)
    originals.append({"path":source.name,"sha256":sha(source),"copied_sha256":sha(sandbox/source.name)})
    evidence = Path("docs/evidence/deepseek/api-20261016-001224-2c3484/report.json")
    (sandbox/evidence).parent.mkdir(parents=True)
    shutil.copyfile(ROOT/evidence, sandbox/evidence)
    (out/"b_test_source_manifest.json").write_text(json.dumps(originals,indent=2),encoding="utf-8")
    env = dict(os.environ)
    for key in list(env):
        if key.endswith(("_API_KEY", "_TOKEN")) or key.startswith("DEEPSEEK_"):
            env.pop(key, None)
    env.update(PYTHONIOENCODING="utf-8", PYTHONPATH=str(runtime),
        AGENT_PROVIDER="mock", AGENT_ENGINE="legacy", AGENT_USE_HTTP="0", AGENT_VECTOR_RAG="0",
        AGENT_MAX_STEPS="8", AGENT_LC_TOOLSET="all", LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false", TICKET_OFFLINE_GUARD_LOG=str(runtime/"blocked_network.jsonl"))
    deep = str(ROOT/".venv-deepseek/Scripts/python.exe")
    legacy = str(ROOT/".venv/Scripts/python.exe")
    v3 = str(ROOT/".venv-v3/Scripts/python.exe")
    jobs = [
        ("a_deepseek_unit", ROOT, deep, ["-m","unittest","discover","-s","tests","-v"], "legacy"),
        ("a_v3_unit", ROOT, v3, ["-m","unittest","discover","-s","tests","-v"], "legacy"),
        ("a_legacy_unit", ROOT, legacy, ["-m","unittest","discover","-s","tests","-v"], "legacy"),
        ("a_smoke", ROOT, deep, ["scripts/smoke.py","--output-dir",str(out/"smoke")], "legacy"),
        ("b_legacy", sandbox, deep, ["-m","judge.executor"], "legacy"),
        ("b_langchain", sandbox, deep, ["-m","judge.executor"], "langchain"),
        ("b_mutation", sandbox, deep, ["tests/test_mutation.py"], "legacy"),
        # B 此脚本的 Client.kwargs/HTTPStatusError 桩接口依赖无 httpx 环境。
        ("b_newcode", sandbox, legacy, ["verify_newcode_V3frozen.py"], "legacy"),
        ("b_pytest", sandbox, deep, ["-m","pytest","tests/test_all.py","-q","-p","no:cacheprovider"], "legacy"),
        ("a_behavior_examples", ROOT, deep, ["-c", '''import contextlib,io,json
from target.agent import Agent
from target.deepseek_runtime import validate_read_only_reply,DeepSeekError
with contextlib.redirect_stdout(io.StringIO()):
    agent=Agent(engine="langchain")
    traces=[agent.chat("def06",text) for text in (
        "帮我查明天上海到杭州的高铁","我要买一张，不要锁座直接给我下单","好，那就先锁座吧")]
checks=[]
for text in ("政策规定锁座后需在15分钟内办理支付。","我无法为您办理退票，您可以通过12306官方渠道办理退票。","我可以为您办理退票","已为您办理退票"):
    try:
        validate_read_only_reply(text)
        actual="ACCEPT"
    except DeepSeekError as exc:
        actual=exc.category
    checks.append({"text":text,"actual":actual})
print(json.dumps({"mode":"LangChain Mock and offline text validation; not Live","traces":traces,"guard_checks":checks},ensure_ascii=False,indent=2))'''], "langchain"),
    ]

    def run(job):
        name, cwd, python, command, engine = job
        child = dict(env, AGENT_ENGINE=engine, AGENT_DB_PATH=str(runtime/name/"tickets.db"),
                     AGENT_TRACE_DIR=str(runtime/name/"traces"))
        # 这里只是离线 SDK 桩的测试账本；真实账本不传给任何子进程。
        child["DEEPSEEK_BUDGET_PATH"] = str(runtime/name/"offline-fixture-budget.db")
        result = subprocess.run([python,*command], cwd=cwd, env=child,
            text=True, encoding="utf-8", capture_output=True, timeout=600)
        text = result.stdout+result.stderr
        for local in (str(runtime), str(ROOT), str(Path.home())):
            text = text.replace(local, "<local-path>")
        (out/(name+".txt")).write_text(text,encoding="utf-8")
        match = re.search(r"Ran (\d+) tests",text)
        skipped = re.search(r"OK \(skipped=(\d+)\)",text)
        display = "python -c <offline behavior example>" if name == "a_behavior_examples" else "python "+" ".join(command)
        record = {"name":name,"exit_code":result.returncode,"command":display,
                  "tests":int(match[1]) if match else None,"skipped":int(skipped[1]) if skipped else 0}
        record["command"] = record["command"].replace(str(out),"<new-evidence-directory>")
        print(json.dumps(record,ensure_ascii=False),flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(run, jobs))
    results = sandbox/"results"
    for source in results.glob("*"):
        if source.is_file():
            (out/"b_rerun_results").mkdir(exist_ok=True)
            shutil.copyfile(source,out/"b_rerun_results"/source.name)
    counts = {}
    for name in ("execution", "execution_langchain"):
        rows = [json.loads(line) for line in (results/(name+".jsonl")).read_text(encoding="utf-8").splitlines()]
        counts[name] = {"passed":sum(r["passed"] for r in rows),"total":len(rows),
                        "failed_ids":[r["id"] for r in rows if not r["passed"]]}
    mutation = json.loads((results/"mutation.json").read_text(encoding="utf-8"))
    counts["mutation"] = {k:mutation[k] for k in ("killed","total")}
    rows = json.loads((results/"newcode_check.json").read_text(encoding="utf-8"))["records"]
    counts["newcode"] = {"passed":sum(r["passed"] is True for r in rows),
                         "failed":sum(r["passed"] is False for r in rows),
                         "na":sum(r["passed"] is None for r in rows)}
    changed_project = [p for p,h in baseline["project"].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    changed_b = [p for p,h in baseline["b_files"].items() if not (b_root/p).is_file() or sha(b_root/p)!=h]
    blocked = runtime/"blocked_network.jsonl"
    attempts = len(blocked.read_text(encoding="utf-8").splitlines()) if blocked.exists() else 0
    source_stable = all(sha(ROOT/p)==h for p,h in source_hashes.items())
    passed = (all(r["exit_code"]==0 for r in runs) and not changed_project and not changed_b and not attempts and source_stable
              and counts["execution"] == {"passed":101,"total":101,"failed_ids":[]}
              and counts["execution_langchain"] == {"passed":100,"total":100,"failed_ids":[]}
              and counts["mutation"] == {"killed":55,"total":55} and counts["newcode"]["failed"]==0)
    report = {"status":"passed" if passed else "failed", "scope":"A rerun with unchanged B assertions; B independent verdict pending",
              "base_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
              "runs":runs,"counts":counts,"new_real_api_requests":0,"blocked_external_network_attempts":attempts,
              "original_budget_modified":False if not any("deepseek-budget" in p for p in changed_project) else True,
              "protected_project_files":len(baseline["project"]),"protected_B_files":len(baseline["b_files"]),
              "changed_project_evidence":changed_project,"changed_B_originals":changed_b,
              "source_sha256":source_hashes,"source_unchanged_during_run":source_stable,
              "b_sources_copied_byte_identically":all(r["sha256"]==r["copied_sha256"] for r in originals)}
    (out/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False),flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
