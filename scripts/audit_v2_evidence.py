"""审计现有 V2 证据与源码/原始 V1 文件的一致性；不是正式测试评估。"""
import argparse
import ast
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT/"docs/evidence/v2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def schemas(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("TOOLS schema missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT/args.output
    if output.exists():
        raise FileExistsError("审计记录已存在，请指定新文件")
    manifest = read(BASE/"v1_snapshot/manifest.json")
    protected = {p: digest(ROOT/p) == h for p, h in manifest["protected_files_sha256"].items()}
    assert all(protected.values()), "原始 V1/合同/B 资料发生变化"
    tag_ok = git("rev-list", "-n", "1", manifest["v1_tag"]) == manifest["v1_tag_sha"]
    assert tag_ok
    regression = read(BASE/"regression/verification.json")
    verified_source = {p: digest(ROOT/p) == h for p, h in regression["source_files_sha256"].items()}
    assert all(verified_source.values()), "源码与已运行回归时的哈希不符"
    assert all(r["exit_code"] == 0 for r in regression["runs"])
    log = (BASE/"regression/unit.txt").read_text(encoding="utf-8")
    unit_count = int(re.search(r"Ran (\d+) tests", log)[1])
    assert "\nOK" in log
    old_schema = schemas(git("show", manifest["v1_tag"]+":target/tools.py"))
    new_schema = schemas((ROOT/"target/tools.py").read_text(encoding="utf-8"))
    assert old_schema == new_schema, "工具 Schema 契约发生变化"
    examples = read(BASE/"regression/python_examples.json")
    injected = {e["label"].split(":")[1]: e["result"] for e in examples if e["label"].startswith("injected:")}
    normal = next(e["result"] for e in examples if e["label"] == "normal")
    def calls(r):
        return [c for s in r["steps"] for c in s["calls"]]
    days = (date.fromisoformat(calls(injected["date_offset"])[0]["args"]["date"]) -
            date.fromisoformat(calls(normal)[0]["args"]["date"])).days
    mutations = {
        "date_offset=1": days == 1,
        "skip_lock": injected["skip_lock"]["tool_sequence"] == ["query_tickets", "create_order"] and not calls(injected["skip_lock"])[-1]["ok"],
        "repeat_call": injected["repeat_call"]["tool_sequence"].count("query_tickets") == 2,
        "infinite_loop": injected["infinite_loop"]["finish_reason"] == "max_steps_exceeded" and len(injected["infinite_loop"]["tool_sequence"]) == 8,
        "route_error": injected["route_error"]["tool_sequence"] == ["query_tickets"],
        "no_citation": injected["no_citation"]["tool_sequence"] == ["search_policy"] and not re.search(r"P\d+", injected["no_citation"]["reply"]),
    }
    assert all(mutations.values())
    v1, v2 = [read(BASE/(name+"/observations.json")) for name in ("v1_reproduction", "v2_reproduction")]
    assert v2["providers_sha256"] == digest(ROOT/"target/providers.py")
    assert not any(o["a_observed_target_satisfied"] for o in v1["observations"])
    assert all(o["a_observed_target_satisfied"] for o in v2["observations"])
    records = [json.loads(line) for line in (BASE/"regression/mock_traces.jsonl").read_text(encoding="utf-8").splitlines()]
    top = {"session_id", "provider", "model", "user_msg", "steps", "tool_sequence", "reply", "finish_reason", "tokens", "total_latency_ms"}
    for r in records:
        assert set(r) == top and r["provider"] == "mock"
        assert r["tool_sequence"] == [c["tool"] for c in calls(r)]
        for c in calls(r):
            assert set(c) == {"tool", "args", "ok", "latency_ms", "result_preview"}
    preflight = read(BASE/"real_preflight/preflight.json")
    assert preflight["real_model_tested"] is False and preflight["real_trace_count"] == 0
    report = {"scope": "A evidence audit, not B scoring", "branch": git("branch", "--show-current"),
              "audit_head": git("rev-parse", "HEAD"), "v1_tag_unchanged": tag_ok,
              "protected_files_count": len(protected), "protected_files_unchanged": protected,
              "source_matches_executed_regression": verified_source, "tools_schema_unchanged": True,
              "contract_sha256": digest(ROOT/"docs/contract.md"), "unit_tests_passed": unit_count,
              "smoke_commands_passed": len(regression["runs"]), "mock_trace_count": len(records),
              "mutations_observed": mutations, "v1_a_targets": 0, "v2_a_targets": 5,
              "real_model_tested": False, "b_judge_available": (ROOT/"judge").exists(),
              "b_formal_rerun": "待成员 B 独立回归",
              "evidence_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in BASE.rglob("*") if p.is_file()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "protected": len(protected), "unit_tests": unit_count,
                      "six_mutations": mutations, "tools_schema_unchanged": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
