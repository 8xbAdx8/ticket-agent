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
STATUS_LABELS = {"detected": "已检出", "missed": "漏检", "not_triggered": "未触发", "skipped": "跳过",
                 "not_applicable": "不适用", "not_run": "未执行", "not_verified": "未验证",
                 "indeterminate": "无法判定", "unknown": "未知", "missing": "证据缺失"}
CASE_STATUSES = ("passed", "failed", "skipped", "not_applicable", "not_run",
                 "not_verified", "indeterminate", "unknown", "missing")
CASE_STATUS_ALIASES = {"pass": "passed", "fail": "failed", "na": "not_applicable"}
MUTATION_SOURCES = {"选定矩阵": ("mutation.json", "rows"), "额外探测": ("probe_m6_m8.json", "details")}


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


def session_execution_events(trace_dir, session_id, *, limit=10000):
    """Read real events for one session, rejecting ambiguous event identities."""
    rows, status = read_jsonl(Path(trace_dir) / 'run_events.jsonl', limit=limit)
    owned = [row for row in rows if row.get('session_id') == session_id
             and isinstance(row.get('event_id'), str) and row['event_id']]
    occurrences = Counter(row['event_id'] for row in rows if isinstance(row.get('event_id'), str))
    return [row for row in owned if occurrences[row['event_id']] == 1], status


def verified_manifest():
    meta = read_json(B_SOURCE / "manifest.json")
    checks = {}
    for name, spec in meta["files"].items():
        try:
            checks[name] = hashlib.sha256((B_SOURCE / name).read_bytes()).hexdigest() == spec["sha256"]
        except OSError:
            checks[name] = False
    return meta, checks


def cases():
    return read_json(B_SOURCE / "case_catalog.json")


def case_status(value):
    key = value.strip().lower() if isinstance(value, str) else "unknown"
    key = CASE_STATUS_ALIASES.get(key, key)
    return key if key in CASE_STATUSES else "unknown"


def batch(engine="legacy"):
    name = "execution.jsonl" if engine == "legacy" else "execution_langchain.jsonl"
    raw, errors = read_jsonl(B_SOURCE / name)
    catalog = cases()
    applicable_ids = {case["id"] for case in catalog if engine in case.get("engines", ("legacy", "langchain"))}
    by_id = {}
    ambiguous = set()
    for record in raw:
        case_id = record.get("id")
        if not isinstance(case_id, str) or case_id not in applicable_ids:
            errors["invalid"] += 1
        elif case_id in by_id:
            ambiguous.add(case_id)
            errors["invalid"] += 1
        else:
            by_id[case_id] = record
    rows = []
    for case in catalog:
        case_id, dimension = case["id"], case["dimension"]
        record = by_id.get(case_id)
        if case_id not in applicable_ids:
            status, note = "not_applicable", "用例目录标明此引擎不适用"
        elif record is None:
            status, note = "missing", "目录中有适用用例，未找到对应执行记录"
        elif case_id in ambiguous or record.get("dimension") != dimension:
            status, note = "unknown", "记录重复或维度与目录不符，请核对原始文件"
        else:
            verdict = record.get("passed")
            fallback = "passed" if verdict is True else "failed" if verdict is False else "indeterminate"
            rows.append(dict(record, status=case_status(record.get("status", fallback))))
            continue
        rows.append({"id": case_id, "dimension": dimension, "status": status,
                     "checks": [], "executed": [], "note": note})
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
    return {"id":"b-"+name,"title":"B 独立测试 · "+kind.partition("（")[0],"owner":"B","mode":"Mock / 离线桩",
            "grain":"变异组合" if mutant else "专项检查（非模型对话）","source":"web/datasets/b_v32_20261020/"+name,
            "date":meta["execution_date"],"time":None,"commit":meta["code_commit"],"rows":rows,"seven_dimensions":False,
            "outcome_labels":("已检出","未检出") if mutant else ("通过","失败"),"original_generated":raw.get("generated")}


def summary(rows):
    counts = Counter(case_status(r.get("status", "missing")) for r in rows)
    executed = counts["passed"] + counts["failed"]
    applicable = len(rows) - counts["not_applicable"]
    return {"defined": len(rows), "applicable": applicable, "executed": executed,
            **{status: counts[status] for status in CASE_STATUSES},
            "coverage": executed / applicable if applicable else None,
            "rate": counts["passed"] / executed if executed else None}


def dimension_rows(rows):
    return [dict(dimension=d, **summary([r for r in rows if r.get("dimension") == d])) for d in DIMENSIONS]


def latency_rows(rows):
    return [{"case": r["id"], "turn": i+1, "latency_ms": t["total_latency_ms"], "dimension": r.get("dimension")}
            for r in rows for i, t in enumerate(r.get("executed", [])) if isinstance(t.get("total_latency_ms"), (int, float))]


def _mutation_status(row, probe):
    if "status" in row:
        value = row["status"]
        key = value.strip().lower() if isinstance(value, str) else "unknown"
        key = CASE_STATUS_ALIASES.get(key, key)
        return key if key in STATUS_LABELS else "unknown"
    # The frozen B probe records R01's policy-only run as inapplicable to train injection.
    if probe and row["case_id"] == "R01" and row.get("G9999_进入回复") is False and row.get("killed") is False:
        return "not_applicable"
    if row.get("killed") is True:
        return "detected"
    if row.get("killed") is False:
        return "missed"
    return "unknown" if "killed" in row else "missing"


def mutation_group(origin):
    """Load one evidence population and account for absent or unreadable records."""
    name, field = MUTATION_SOURCES[origin]
    path = B_SOURCE / name
    source = f"web/datasets/{B_SOURCE.name}/{name}"
    try:
        payload = read_json(path)
        raw = payload[field]
        if not isinstance(raw, list):
            raise ValueError("invalid evidence list")
    except (OSError, ValueError, KeyError, TypeError):
        return {"source": source, "rows": [], "missing_records": None}

    rows = []
    probe = field == "details"
    for record in raw:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str) or not record["case_id"]:
            continue
        mutation = "hallucinated_train" if probe else record.get("mutation")
        if mutation not in MUTATIONS:
            continue
        rules = record.get("failed_rules")
        rules = rules if isinstance(rules, list) else []
        rows.append(dict(record, mutation=mutation, origin=origin, status=_mutation_status(record, probe),
                         failed_rules=rules, c5="C5" in rules, original=record))
    total = payload.get("total")
    expected = max(total, len(raw)) if type(total) is int else len(raw)
    return {"source": source, "rows": rows, "missing_records": expected - len(rows)}


def mutation_summary(rows, missing_records=0):
    counts = Counter(row.get("status") for row in rows)
    total = len(rows) + (missing_records or 0)
    applicable = total - counts["not_applicable"]
    return {"total": total, "applicable": applicable, **{key: counts[key] for key in STATUS_LABELS},
            "missing": counts["missing"] + (missing_records or 0),
            "rate": counts["detected"] / applicable if applicable else None}


def mutation_rows(include_probe=True):
    return [row for origin in MUTATION_SOURCES if include_probe or origin == "选定矩阵"
            for row in mutation_group(origin)["rows"]]


def mutation_totals():
    rows = mutation_rows(False)
    result=[]
    for name in MUTATIONS:
        selected=[r for r in rows if r["mutation"]==name]
        counts = mutation_summary(selected)
        result.append({"mutation":name,"detected":counts["detected"] if selected else None,
                       "tested":counts["applicable"] if selected else None})
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


def _evidence_scope(record, provider, historical=False):
    fault = record.get("fault_report")
    events = record.get("mutation_events")
    has_fault = (isinstance(fault, dict) and bool(fault.get("mutations"))) or (
        isinstance(events, list) and any(isinstance(event, dict) and event.get("enabled") is True for event in events))
    if record.get("test_only") is True or record.get("test_case_label") or has_fault:
        return "TEST_ONLY"
    if historical or record.get("evidence_kind") in ("offline_sdk_stub", "mock_transport") or provider in (
        "mock", "langchain_mock", "backend_concurrency",
    ):
        return "离线 Mock / 替身"
    if provider in ("deepseek_live", "bailian_live"):
        return "Live 配置（请求见 Trace）"
    return "来源待核对"


def audit_batch(runtime_dirs=(),historical=False):
    entries=audit_catalog(() if historical else runtime_dirs)
    entries=[e for e in entries if e["kind"]==("历史离线自测" if historical else "当前工作空间")]
    if not historical:
        entries=[e for e in entries if not str(e["record"].get("provider","")).endswith("_live")]
    rows=[]
    for e in entries:
        r=e["record"];j=r.get("judgement",{})
        from target.execution_config import run_identity
        identity=run_identity(r.get('trace_id'),(r.get('public_trace') or {}).get('session_id'))
        if identity and identity.get('execution_mode')=='developer_custom':continue
        verdict=j.get("test_verdict") or j.get("quality_verdict")
        state={"pass":"passed","fail":"failed","not_applicable":"not_applicable"}.get(verdict,"indeterminate")
        rows.append({"id":r.get("trace_id","缺少 ID"),"dimension":"独立审计","status":state,
                     "scope":_evidence_scope(r, r.get("provider"), historical),
                     "executed":[],"checks":j.get("assertions",[]),"original":r})
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


def recent_lab_records(runtime_dirs, *, max_bytes=4*1024*1024, max_records=300):
    """Read recent isolated lab audits only; never rewrite evidence or invoke a model."""
    records=[]; invalid=0; truncated=False
    for directory in dict.fromkeys(Path(p) for p in runtime_dirs):
        path=directory/'audit_runs.jsonl'
        if not path.is_file() or path.is_symlink():
            continue
        try:
            with path.open('rb') as stream:
                size=stream.seek(0,2)
                offset=max(0,size-max_bytes)
                stream.seek(offset)
                if offset:
                    stream.readline()  # discard a partial line
                    truncated=True
                lines=stream.read().splitlines()
            if len(lines)>max_records:
                truncated=True
                lines=lines[-max_records:]
            for line in lines:
                try:
                    record=json.loads(line.decode('utf-8-sig'))
                    if not isinstance(record,dict): raise ValueError('not an object')
                    ref=record.get('full_evidence') or {}
                    if ref.get('available'):
                        blob=(directory/ref['path']).resolve()
                        if not blob.is_relative_to(directory.resolve()) or blob.stat().st_size>4*1024*1024:
                            raise ValueError('invalid blob')
                        data=blob.read_bytes()
                        if hashlib.sha256(data).hexdigest()!=ref['sha256']:
                            raise ValueError('digest mismatch')
                        record=json.loads(data)
                        if not isinstance(record,dict): raise ValueError('invalid blob object')
                    records.append(record)
                except (ValueError,TypeError,UnicodeError,KeyError,OSError):
                    invalid+=1
        except OSError:
            invalid+=1
    records.sort(key=lambda r: str(r.get('timestamp') or ''),reverse=True)
    if len(records)>max_records:
        truncated=True
        records=records[:max_records]
    return records, {'invalid':invalid,'truncated':truncated}


def lab_record_rows(records):
    """One audit record is one run, never a B test case or overall pass rate."""
    rows=[]
    for r in records:
        trace=r.get('public_trace') if isinstance(r.get('public_trace'),dict) else {}
        judgement=r.get('judgement') if isinstance(r.get('judgement'),dict) else {}
        provider=r.get('provider') or trace.get('provider') or 'unknown'
        model=r.get('model') or trace.get('model') or 'unknown'
        scope = _evidence_scope(r, provider)
        quality=judgement.get('quality_verdict')
        reasons=judgement.get('failure_reasons') or []
        if r.get('error') or r.get('contract_returned') is False:
            state='执行异常'
        elif quality=='fail' and reasons:
            state='审计发现问题'
        elif quality=='pass' and judgement.get('assertions'):
            state='有限规则未发现问题'
        else:
            state='待判定'
        rows.append({'trace_id':r.get('trace_id') or '未知', 'time':r.get('timestamp') or '未知',
                     'provider':provider,'model':model,'scope':scope,'status':state,
                     'test_verdict':judgement.get('test_verdict') or '未提供',
                     'latency_ms':trace.get('total_latency_ms'), 'tokens':trace.get('tokens'),
                     'error':(r.get('error') or {}).get('category') if isinstance(r.get('error'),dict) else None})
    return rows
