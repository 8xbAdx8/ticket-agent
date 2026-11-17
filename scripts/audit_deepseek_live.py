"""仅审查本地 Live 证据；不导入 Agent、不调用模型，SQLite 只读打开。"""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT/"docs/evidence/deepseek/api-20261016-001224-2c3484"
REVIEW = ROOT/"docs/evidence/deepseek/review-20261016"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def ro_connect(path):
    connection = sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def audit(out=REVIEW):
    out.mkdir(parents=True,exist_ok=True)
    report = json.loads((LIVE/"report.json").read_text(encoding="utf-8"))
    public = read_jsonl(LIVE/"traces/traces.jsonl")
    detailed = read_jsonl(LIVE/"traces/deepseek_runs.jsonl")
    baseline = json.loads((ROOT/"docs/evidence/deepseek/baseline.json").read_text(encoding="utf-8"))
    ledger_path = ROOT/"artifacts/runtime/deepseek-budget/requests.db"
    assert ledger_path.exists(),"未找到已运行的预算账本；不要创建或补造账本"
    protected = {p:digest(ROOT/p)==h for p,h in baseline["protected_sha256"].items()}
    assert all(protected.values()),"接手前保护文件发生变化，需要人工审查，不能自动恢复"
    tags = {t:subprocess.check_output(["git","rev-parse",t+"^{commit}"],cwd=ROOT,text=True).strip() for t in baseline["tags"]}
    assert tags==baseline["tags"]
    hashes = {p.relative_to(ROOT).as_posix():digest(p) for p in [LIVE/"report.json",LIVE/"tickets.db",
        LIVE/"traces/traces.jsonl",LIVE/"traces/deepseek_runs.jsonl",ROOT/"data/tickets.db",ROOT/"traces/traces.jsonl",ledger_path]}
    ledger = ro_connect(ledger_path)
    try:
        rows = [dict(r) for r in ledger.execute("SELECT * FROM requests ORDER BY id")]
    finally:
        ledger.close()
    assert rows==report["shared_budget"]["requests"]
    assert len(rows)==report["online_generation_requests_this_run"]==report["shared_budget"]["limit"]==5
    assert all(r["status"]==200 and r["model"]=="deepseek-flash" for r in rows)
    assert report["status"]=="passed" and report["real_api_verified"] and report["function_calling_verified"]
    assert report["thinking"]=="disabled" and report["balance_http_requests"]==1
    hello = next(c for c in report["cases"] if c["name"]=="hello")
    cases = [c for c in report["cases"] if "trace" in c]
    assert len(cases)==len(public)==len(detailed)==2
    assert [c["trace"] for c in cases]==public
    execution_date = (datetime.fromisoformat(rows[0]["created"])+timedelta(hours=8)).date()
    summaries = []
    for i,case in enumerate(cases):
        trace,events = case["trace"],case["events"]
        sidecar = detailed[i]
        for key in ("session_id","reply","tokens","finish_reason"):
            assert sidecar[key]==trace[key]
        assert sidecar["events"]==events and sidecar["error"] is None
        assert set(trace)=={"session_id","provider","model","user_msg","steps","tool_sequence","reply","finish_reason","tokens","total_latency_ms"}
        assert trace["provider"]=="deepseek_live" and trace["model"]=="deepseek-flash"
        calls = [c for step in trace["steps"] for c in step["calls"]]
        models = [e for e in events if e["event"]=="model_response"]
        declared = [c for m in models for c in m["tool_calls"]]
        starts = [e for e in events if e["event"]=="tool_start"]
        ends = [e for e in events if e["event"]=="tool_end"]
        assert len(models)==2 and len(calls)==len(declared)==len(starts)==len(ends)==1
        assert models[0]["finish_reason"]=="tool_calls" and models[1]["finish_reason"]=="stop" and not models[1]["tool_calls"]
        assert events.index(ends[0]) < events.index(models[1])
        assert trace["tokens"]=={"prompt":sum(m["usage"]["input_tokens"] for m in models),
                                "completion":sum(m["usage"]["output_tokens"] for m in models)}
        call,start,end,declared_call = calls[0],starts[0],ends[0],declared[0]
        assert declared_call["id"]==start["call_id"]==end["call_id"]
        assert declared_call["name"]==start["tool"]==end["tool"]==call["tool"]==case["name"]
        assert declared_call["args"]==start["args"]==call["args"]
        assert set(call)=={"tool","args","ok","latency_ms","result_preview"}
        assert call["ok"]==end["ok"] is True and call["latency_ms"]==end["latency_ms"]
        preview=json.dumps(end["result"],ensure_ascii=False)
        assert call["result_preview"]==preview[:200]+("..." if len(preview)>200 else "")
        assert trace["tool_sequence"]==[case["name"]] and trace["finish_reason"]=="stop"
        summaries.append({"tool":case["name"],"call_id":declared_call["id"],"args":call["args"],
            "tool_latency_ms":call["latency_ms"],"agent_latency_ms":trace["total_latency_ms"],"tokens":trace["tokens"],
            "actual_response_models":[m["response_model"] for m in models],"trace_and_events_match":True})
    query_case = next(c for c in cases if c["name"]=="query_tickets")
    query = summaries[0]["args"]
    assert query["date"]==(execution_date+timedelta(days=1)).isoformat()
    assert (query["from_city"],query["to_city"],query["kind"],query["seat_type"])==("上海","杭州","高铁","二等座")
    live_db = ro_connect(LIVE/"tickets.db")
    try:
        selected=[dict(r) for r in live_db.execute(
            "SELECT kind,train_no,from_city,to_city,date,depart,arrive,seat_type,price,seats_left FROM inventory WHERE from_city LIKE ? AND to_city LIKE ? AND date=? AND seat_type=? AND kind=? ORDER BY seats_left DESC,depart ASC LIMIT 20",
            ("%"+query["from_city"]+"%","%"+query["to_city"]+"%",query["date"],query["seat_type"],query["kind"]))]
        live_counts={t:live_db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("inventory","locks","orders")}
    finally:
        live_db.close()
    query_result=next(e["result"] for e in query_case["events"] if e["event"]=="tool_end")
    assert query_result=={"trains":selected,"count":len(selected)}
    assert live_counts=={"inventory":2100,"locks":0,"orders":0}
    reply_rows=[line.strip().strip("|").split("|") for line in query_case["trace"]["reply"].splitlines() if re.match(r"\|\s*G\d+",line)]
    assert len(reply_rows)==len(selected)==3
    for values in reply_rows:
        train,depart,arrive,duration,price,stock=[s.strip() for s in values]
        fact=next(r for r in selected if r["train_no"]==train)
        assert fact["depart"]==depart and fact["arrive"]==arrive
        assert float(price.lstrip("¥"))==fact["price"] and int(re.search(r"\d+",stock)[0])==fact["seats_left"]
        assert duration=="1小时"
    assert set(re.findall(r"\bG\d+\b",query_case["trace"]["reply"]))=={r["train_no"] for r in selected}
    policy_case=next(c for c in cases if c["name"]=="search_policy")
    policy_result=next(e["result"] for e in policy_case["events"] if e["event"]=="tool_end")
    assert policy_result["question"]==summaries[1]["args"]["question"]
    policies=(ROOT/"data/policies.md").read_text(encoding="utf-8")
    chunks={}
    for block in re.split(r"\n## ",policies):
        match=re.match(r"\[(P\d+)\]\s*(.*)",block.strip())
        if match:
            chunks[match[1]]={"title":match[2].strip(),"content":block.split("\n",1)[1].strip()}
    for hit in policy_result["hits"]:
        assert hit["source"]=="data/policies.md#"+hit["doc_id"]
        assert hit["title"]==chunks[hit["doc_id"]]["title"] and hit["content"]==chunks[hit["doc_id"]]["content"]
    cited=set(re.findall(r"\bP\d{2}\b",policy_case["trace"]["reply"]))
    assert cited=={"P11","P12"} and cited<={h["doc_id"] for h in policy_result["hits"]}
    assert "15 分钟" in policy_case["trace"]["reply"] and "不收取手续费" in policy_case["trace"]["reply"]
    prompt=sum(r["prompt"] for r in rows); completion=sum(r["completion"] for r in rows)
    assert report["token_usage"]=={"prompt":prompt,"completion":completion}
    assert prompt==sum(c["trace"]["tokens"]["prompt"] for c in cases)+hello["usage"]["prompt_tokens"]
    assert completion==sum(c["trace"]["tokens"]["completion"] for c in cases)+hello["usage"]["completion_tokens"]
    cache=hello["usage"]["prompt_cache_hit_tokens"]+sum(m["usage"].get("input_token_details",{}).get("cache_read",0) for c in cases for m in c["events"] if m["event"]=="model_response")
    assert cache==2944
    for relative,h in hashes.items():
        assert digest(ROOT/relative)==h,"审查期间文件变动，需要人工确认"
    result={"status":"passed","review_date":"2026-10-16","review_type":"offline_existing_live_evidence",
        "review_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "live_folder":LIVE.relative_to(ROOT).as_posix(),"execution_beijing_date":execution_date.isoformat(),
        "review_added_api_requests":0,"recorded_generation_requests":5,"recorded_balance_gets":1,
        "budget_limit":5,"budget_used":5,"budget_remaining":0,"ledger_matches_saved_report":True,
        "tokens":{"prompt":prompt,"completion":completion,"total":prompt+completion,"cache_hit_input":cache,"cache_miss_input":prompt-cache},
        "actual_fee":None,"actual_fee_status":"unknown_no_provider_receipt_or_balance_delta",
        "tools_verified":["query_tickets","search_policy"],"all_eight_tools_live_verified":False,
        "public_traces":2,"independent_sessions":len({c["trace"]["session_id"] for c in cases}),"multiturn_quality_verified":False,
        "cases":summaries,"query_rows":selected,"policy_citations":sorted(cited),"live_database_counts":live_counts,
        "original_protected_files_unchanged":len(protected),"original_db_and_history_trace_unchanged":True,
        "tags":tags,"file_sha256":hashes,
        "findings":[{"id":"LIVE-REVIEW-01","kind":"readonly_capability_wording","status":"needs_B_triage",
            "description":"查询回复末尾询问是否办理订票；当前只读，可能误导能力边界；实际无写工具执行。"}],
        "limits":["应用层事件与落盘一致；未保存完整原始 HTTP 工具结果回传报文。",
                  "实际模型返回名称为 deepseek-flash，服务端内部构建版本未知。",
                  "只有两个独立只读场景，不代表100条正式测试、真实多轮或8工具Live通过。"]}
    (out/"audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"budget_snapshot.json").write_text(json.dumps({"source":"read_only_existing_sqlite_ledger","limit":5,"used":len(rows),"remaining":0,"requests":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","review_added_api_requests","recorded_generation_requests","tokens","budget_remaining","original_protected_files_unchanged")},ensure_ascii=False))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=REVIEW)
    audit(parser.parse_args().out)
