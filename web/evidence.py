"""Read-only evidence adapters. A/B, Mock/Live and data grains stay separate."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B_SOURCE = ROOT / "web/datasets/b_v32_20261020"
AUDIT_SOURCE = ROOT / "docs/evidence/v32/20261018-negation-fix"
DIMENSIONS = ("功能准确性", "工具调用", "RAG", "多轮", "安全", "边界", "性能")
MUTATIONS = ("date_offset", "skip_lock", "repeat_call", "infinite_loop", "route_error", "no_citation", "hallucinated_train", "concurrent_duplicate_order")
STATUS_LABELS = {"detected": "已检出", "missed": "未检出", "not_triggered": "未触发", "not_applicable": "不适用", "not_verified": "未验证", "indeterminate": "无法判定"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def read_jsonl(path, limit=1000):
    path = Path(path)
    if not path.is_file():
        return [], {"missing": True, "invalid": 0, "truncated": False}
    records, invalid, truncated = [], 0, False
    # Bounded read without repairing or rewriting any original line.
    with path.open(encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream):
            if index >= limit:
                truncated = True
                break
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError()
                records.append(value)
            except (ValueError, TypeError):
                invalid += 1
    return records, {"missing": False, "invalid": invalid, "truncated": truncated}


def verified_manifest():
    meta = read_json(B_SOURCE / "manifest.json")
    return meta, {name: hashlib.sha256((B_SOURCE/name).read_bytes()).hexdigest() == spec["sha256"]
                  for name, spec in meta["files"].items()}


def cases():
    return read_json(B_SOURCE / "case_catalog.json")


def batch(engine="legacy"):
    name = "execution.jsonl" if engine == "legacy" else "execution_langchain.jsonl"
    raw, errors = read_jsonl(B_SOURCE / name)
    rows = [dict(r, status="passed" if r.get("passed") is True else "failed" if r.get("passed") is False else "indeterminate") for r in raw]
    ids = {r["id"] for r in rows}
    for case in cases():
        if engine not in case.get("engines", ("legacy", "langchain")):
            rows.append({"id": case["id"], "dimension": case["dimension"], "status": "not_applicable", "checks": [], "executed": [], "note": "原用例 engines 明确不适用；未计入已执行用例分母"})
        elif case["id"] not in ids:
            rows.append({"id": case["id"], "dimension": case["dimension"], "status": "not_verified", "checks": [], "executed": []})
    meta = read_json(B_SOURCE / "manifest.json")
    return {"id": "b-"+engine, "title": "B 独立测试 · "+("Legacy Mock" if engine == "legacy" else "LangChain Mock"),
            "owner": "B", "mode": "Mock", "engine": engine, "grain": "正式功能用例", "source": "web/datasets/b_v32_20261020/"+name,
            "date": meta["execution_date"], "time": None, "commit": meta["code_commit"], "rows": rows, "read_errors": errors,"seven_dimensions":True}


def b_aux_batch(kind):
    names={"新增代码专项（47 检查）":"newcode_check.json","M8 并发幂等（10 检查）":"m8_idempotent.json","选定变异矩阵（69 组合）":"mutation.json"}
    name=names[kind];raw=read_json(B_SOURCE/name)
    mutant=name=="mutation.json"
    records=raw.get("rows",raw.get("records",[]))
    rows=[]
    for i,r in enumerate(records):
        value=r.get("killed") if mutant else r.get("passed")
        state="passed" if value is True else "failed" if value is False else "not_applicable"
        rows.append({"id":r.get("id",r.get("mutation","")+" / "+r.get("case_id",str(i))),
                     "dimension":r.get("group","并发检查" if name.startswith("m8") else "变异组合"),"status":state,
                     "checks":[],"executed":[],"note":r.get("detail",""),"original":r})
    meta=read_json(B_SOURCE/"manifest.json")
    return {"id":"b-"+name,"title":"B 独立测试 · "+kind,"owner":"B","mode":"Mock / 离线桩",
            "grain":"变异组合" if mutant else "专项检查（非模型对话）","source":"web/datasets/b_v32_20261020/"+name,
            "date":meta["execution_date"],"time":None,"commit":meta["code_commit"],"rows":rows,"seven_dimensions":False,
            "outcome_labels":("已检出","未检出") if mutant else ("通过","失败"),"original_generated":raw.get("generated")}


def summary(rows):
    counts = Counter(r.get("status", "missing") for r in rows)
    executed = counts["passed"] + counts["failed"]
    return {"defined": len(rows), "executed": executed, **{s: counts[s] for s in ("passed", "failed", "skipped", "not_applicable", "not_verified", "indeterminate", "missing")},
            "rate": counts["passed"] / executed if executed else None}


def dimension_rows(rows):
    return [dict(dimension=d, **summary([r for r in rows if r.get("dimension") == d])) for d in DIMENSIONS]


def latency_rows(rows):
    return [{"case": r["id"], "turn": i+1, "latency_ms": t["total_latency_ms"], "dimension": r.get("dimension")}
            for r in rows for i, t in enumerate(r.get("executed", [])) if isinstance(t.get("total_latency_ms"), (int, float))]


def mutation_rows(include_probe=True):
    raw = read_json(B_SOURCE / "mutation.json")["rows"]
    result = [dict(r, status="detected" if r.get("killed") else "missed", origin="选定矩阵", c5="C5" in r.get("failed_rules", [])) for r in raw]
    if include_probe:
        probe = read_json(B_SOURCE / "probe_m6_m8.json")
        # Separate diagnostic population: never change the selected matrix denominator.
        for r in probe["details"]:
            state = "not_applicable" if r["case_id"] == "R01" and not r.get("G9999_进入回复") else "detected" if r["killed"] else "missed"
            result.append({"mutation": "hallucinated_train", "case_id": r["case_id"], "killed": r["killed"], "status": state,
                           "origin": "额外探测", "failed_rules": r["failed_rules"], "c5": "C5" in r["failed_rules"], "original": r})
    return result


def mutation_totals():
    rows = mutation_rows(False)
    result=[]
    for name in MUTATIONS:
        selected=[r for r in rows if r["mutation"]==name]
        result.append({"mutation":name,"detected":sum(r["killed"] for r in selected) if selected else None,
                       "tested":len(selected) if selected else None})
    return result


def diff_values(before, after, path="$", missing="<字段缺失>"):
    if isinstance(before, dict) and isinstance(after, dict):
        return [r for key in sorted(set(before) | set(after)) for r in diff_values(before.get(key, missing), after.get(key, missing), path+"."+str(key))]
    if isinstance(before, list) and isinstance(after, list):
        return [r for i in range(max(len(before), len(after))) for r in diff_values(before[i] if i<len(before) else missing, after[i] if i<len(after) else missing, path+"["+str(i)+"]")]
    return [] if before == after else [{"字段": path, "原始": before, "变异后": after}]


def read_audit_records(path):
    """Resolve only bounded, digest-verified blobs beside the selected audit."""
    records, errors=read_jsonl(path)
    resolved=[]
    for record in records:
        ref=record.get("full_evidence",{})
        if ref.get("available"):
            try:
                blob=(Path(path).parent/ref["path"]).resolve()
                if not blob.is_relative_to(Path(path).parent.resolve()) or blob.stat().st_size>4*1024*1024:
                    raise ValueError()
                data=blob.read_bytes()
                if hashlib.sha256(data).hexdigest()!=ref["sha256"]:
                    raise ValueError()
                value=json.loads(data)
                if not isinstance(value,dict):
                    raise ValueError()
                record=value
            except (OSError,ValueError,KeyError,TypeError):
                record=dict(record,display_warning="完整旁证缺失、越界、超限或哈希不符；仅显示保存摘要，完整内容无法判定")
        resolved.append(record)
    return resolved,errors


def audit_catalog(runtime_dirs=()):
    catalog = []
    for folder, owner, source_kind in [(AUDIT_SOURCE/"cases", "A", "历史离线自测"), *[(Path(p), "A", "当前工作空间") for p in runtime_dirs]]:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("audit_runs.jsonl")):
            if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                continue
            records, errors = read_audit_records(path)
            for r in records:
                catalog.append({"record": r, "source": path, "owner": owner, "kind": source_kind, "read_errors": errors})
    return catalog


def audit_batch(runtime_dirs=(),historical=False):
    entries=audit_catalog(() if historical else runtime_dirs)
    entries=[e for e in entries if e["kind"]==("历史离线自测" if historical else "当前工作空间")]
    if not historical:
        entries=[e for e in entries if e["record"].get("provider")!="deepseek_live"]
    rows=[]
    for e in entries:
        r=e["record"];j=r.get("judgement",{})
        verdict=j.get("test_verdict") or j.get("quality_verdict")
        state={"pass":"passed","fail":"failed","not_applicable":"not_applicable"}.get(verdict,"indeterminate")
        rows.append({"id":r.get("trace_id","缺少 ID"),"dimension":"独立审计","status":state,"executed":[],"checks":j.get("assertions",[]),"original":r})
    report=read_json(AUDIT_SOURCE/"report.json") if historical else {}
    return {"id":"a-historical" if historical else "a-current","title":"A 历史离线自测" if historical else "A 当前隔离实验",
            "owner":"A","mode":"离线 Mock / SDK 桩 / 后端" if historical else "本地 Mock / 后端",
            "engine":"multiple","grain":"审计记录（非 B 正式用例）","source":"docs/evidence/v32/20261018-negation-fix/" if historical else "当前浏览器隔离工作空间",
            "date":"2026-10-18" if historical else "以各记录实际 timestamp 为准","time":None,"commit":report.get("source_head"),"rows":rows}


def historical_live():
    paths = [ROOT/"docs/evidence/deepseek/live-complete-20261017-01/result.json",
             ROOT/"docs/evidence/deepseek/v31-live-faults-20261018/live-selected-02/normal_purchase_selected/case.json"]
    return [{"path": p, "data": read_json(p), "kind": "历史真实 DeepSeek；非 V3.3 回归"} for p in paths if p.is_file()]


def export_rows(rows):
    from target.diagnostics import sanitize
    return json.dumps(sanitize(rows), ensure_ascii=False, indent=2, default=str)
