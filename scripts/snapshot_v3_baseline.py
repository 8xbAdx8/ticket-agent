"""保留 V2 接手时的不可变证据指纹和运行核心文本。"""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    out = ROOT/"docs/evidence/v3/v2_baseline"
    out.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    protected = [p for p in paths if p and (p.startswith(("docs/evidence/", "docs/handoff/", "docs/v2_", "docs/development_"))
                 or p in ("docs/contract.md", "requirements-lock.txt", "B_缺陷分析报告.md", "B的总结_测试层.docx"))]
    protected += [p for p in ("data/tickets.db", "traces/traces.jsonl") if (ROOT/p).exists()]
    hashes = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in protected}
    for name in ("target/agent.py", "target/providers.py", "target/tools.py", "target/trace.py", "target/rag.py", "config.py", "web/app.py"):
        dest = out/(name.replace("/", "_")+".txt")
        dest.write_bytes((ROOT/name).read_bytes())
    tags = {name:subprocess.check_output(["git", "rev-list", "-n", "1", name],cwd=ROOT).decode().strip()
            for name in ("handoff-a-20261012", "handoff-a-v2-20261013")}
    report = {"date":"2026-10-13", "source_head":head, "tags":tags, "protected_sha256":hashes,
              "b_judge_available":(ROOT/"judge").exists(), "b_v2_official_results_available":False,
              "real_api_key_present":bool(__import__("os").getenv("AGENT_API_KEY")),
              "langchain_before_v3":False}
    (out/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"head":head,"protected_count":len(hashes),"b_judge_available":report["b_judge_available"]}))


if __name__ == "__main__":
    main()
