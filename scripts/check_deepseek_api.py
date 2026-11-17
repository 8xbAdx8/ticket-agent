"""预检默认不联网；--run 才尝试余额、Hello 和两个只读 Agent 场景。

累计调用次数不限，逐次记录用量。没有 Key 时不创建 Mock 替代结果。
"""
import argparse
import importlib.metadata
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run",action="store_true",help="显式访问官方API，可能产生费用；无本地累计请求上限")
    parser.add_argument("--connection-only",action="store_true")
    parser.add_argument("--out",type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    out = args.out or ROOT/"docs/evidence/deepseek"/("api-"+stamp+"-"+uuid.uuid4().hex[:6])
    out.mkdir(parents=True,exist_ok=False)
    # 本脚本专测官方 DeepSeek，而非继承终端中可能遗留的 GLM/Mock 配置。
    os.environ.update(AGENT_PROVIDER="deepseek",AGENT_ENGINE="langchain",AGENT_MODEL="deepseek-flash",
                      AGENT_BASE_URL="https://api.deepseek.com",AGENT_LC_TOOLSET="read_only",AGENT_MAX_STEPS="2",
                      DEEPSEEK_MAX_MODEL_CALLS="2",AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",
                      AGENT_DB_PATH=str(out/"tickets.db"),AGENT_TRACE_DIR=str(out/"traces"))
    import config
    from target.deepseek_runtime import (Settings,RequestBudget,guarded_client,safe_error,safe_text,
                                         validate_configuration,DeepSeekError)
    settings = Settings.from_env()
    budget = RequestBudget(settings)
    before = budget.snapshot()["reserved_requests"]
    report = {"source":"deepseek_official_remote_validation","mode":"live_requested" if args.run else "preflight",
        "model_requested":config.MODEL_NAME,"base_url":config.BASE_URL,"thinking":"disabled",
        "key_present":bool(config.API_KEY.strip()),"real_api_verified":False,"function_calling_verified":False,
        "online_generation_requests_this_run":0,"balance_http_requests":0,"cases":[],
        "token_usage":None,"actual_cost":None,"versions":{}}
    for package in ("langchain","langchain-core","langchain-deepseek","langchain-openai","openai","httpx"):
        try:
            report["versions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["versions"][package] = "not_installed"

    def write():
        state = budget.snapshot()
        count=state['request_count']
        report["online_generation_requests_this_run"] = count-before if type(count) is int and type(before) is int else None
        report["usage_log"] = state
        report["usage_policy"] = 'unlimited_usage_only'
        if report["online_generation_requests_this_run"] == 0:
            report["actual_cost"] = {"amount":0,"reason":"no_generation_request_sent"}
        (out/"report.json").write_text(safe_text(json.dumps(report,ensure_ascii=False,indent=2)),encoding="utf-8")
        print(json.dumps({k:report[k] for k in ("status","key_present","real_api_verified","function_calling_verified","online_generation_requests_this_run")},ensure_ascii=False))

    if not config.API_KEY.strip() or not args.run:
        report["status"] = "skipped_missing_key" if not config.API_KEY.strip() else "ready_not_run"
        report["cases"] = [{"name":name,"status":"skipped","reason":report["status"]}
                           for name in ("balance","hello","query_tickets","search_policy")]
        write()
        return
    current_stage = "configuration"
    try:
        validate_configuration()
        with guarded_client(settings) as client:
            current_stage = "balance"
            started = time.perf_counter()
            report["balance_http_requests"] += 1
            response = client.get(config.BASE_URL+"/user/balance",headers={"Authorization":"Bearer "+config.API_KEY})
            response.raise_for_status()
            available = response.json().get("is_available")
            # 仅保存是否可用，不存账户余额/认证头。
            report["cases"].append({"name":"balance","status":"passed" if available is True else "failed",
                "is_available":available,"latency_ms":int((time.perf_counter()-started)*1000)})
            if available is not True:
                raise DeepSeekError("insufficient_balance")
            current_stage = "hello"
            started = time.perf_counter()
            response = client.post(config.BASE_URL+"/chat/completions",headers={"Authorization":"Bearer "+config.API_KEY},
                json={"model":config.MODEL_NAME,"messages":[{"role":"user","content":"Reply only: Hello"}],
                      "max_tokens":16,"thinking":{"type":"disabled"},"stream":False})
            response.raise_for_status()
            body = response.json()
            usage = body.get("usage") or {}
            if not all(type(usage.get(k)) is int for k in ("prompt_tokens","completion_tokens")):
                raise DeepSeekError("token_usage_unknown")
            reply = body["choices"][0]["message"].get("content")
            if not reply or not body.get("model"):
                raise DeepSeekError("invalid_hello_response")
            report["cases"].append({"name":"hello","status":"passed","response_model":body["model"],
                "reply":safe_text(reply),"usage":usage,"latency_ms":int((time.perf_counter()-started)*1000)})
            report["real_api_verified"] = True
        if not args.connection_only:
            from data.seed import build_db
            from target.agent import Agent
            build_db()
            agent = Agent()
            try:
                for name,message in (("query_tickets","查明天上海到杭州的高铁二等座，请查询工具结果后列出有余票的车次。"),
                                     ("search_policy","锁座后多久必须完成支付？请检索政策并标注来源。")):
                    current_stage = name
                    record = agent.chat("deepseek-"+name+"-"+uuid.uuid4().hex[:8],message)
                    events = agent.langchain_engine.last_events
                    actual = [e for e in events if e["event"]=="tool_end" and e["tool"]==name and e["ok"]]
                    last_response = [e for e in events if e["event"]=="model_response"][-1]
                    closed = bool(actual) and record["finish_reason"]=="stop" and not last_response["tool_calls"]
                    report["cases"].append({"name":name,"status":"passed" if closed else "failed",
                        "protocol_closed":closed,"task_quality":"requires_member_B_review","trace":record,"events":events})
                    if not closed:
                        raise DeepSeekError("tool_call_loop_not_completed")
                report["function_calling_verified"] = True
            finally:
                agent.provider.root_client.close()
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = safe_error(exc)
        if current_stage not in {c["name"] for c in report["cases"]}:
            report["cases"].append({"name":current_stage,"status":"failed","error":report["error"]})
    performed = {c["name"] for c in report["cases"]}
    for name in ("hello","query_tickets","search_policy"):
        if name not in performed:
            report["cases"].append({"name":name,"status":"skipped","reason":"earlier_stage_not_passed_or_connection_only"})
    rows = budget.snapshot()["requests"][before if type(before) is int else 0:]
    if rows and all(r["prompt"] is not None and r["completion"] is not None for r in rows):
        report["token_usage"] = {"prompt":sum(r["prompt"] for r in rows),"completion":sum(r["completion"] for r in rows)}
        report["actual_cost"] = {"amount":None,"reason":"consult_provider_billing; tokens_are_not_a_receipt"}
    write()
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__=="__main__":
    main()
