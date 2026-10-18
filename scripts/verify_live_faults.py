"""V3.1真实API小规模变异验证；不带--run只预检，绝不伪造或回退Mock。"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

SCENARIOS = {
    "normal_query":({},False,"查明天上海到杭州的高铁二等座，请查询工具后列出有余票的车次。"),
    "normal_policy":({},False,"锁座后多久必须完成支付？请检索政策并给出来源。"),
    "date_offset":({"date_offset":1},False,"查明天上海到杭州的高铁二等座，请查询工具后列出有余票的车次。"),
    "route_error":({"route_error":True},False,"锁座后多久必须完成支付？请检索政策并给出来源。"),
    "no_citation":({"no_citation":True},False,"锁座后多久必须完成支付？请检索政策并给出来源；没有来源时明确说明，不得编造。"),
    "repeat_call":({"repeat_call":True},False,"查明天上海到杭州的高铁二等座，请查询工具后列出有余票的车次。"),
    "normal_purchase":({},True,"帮我订明天上海到杭州的高铁二等座，乘客张三，仅创建模拟订单，不要支付。"),
    "skip_lock":({"skip_lock":True},True,"帮我订明天上海到杭州的高铁二等座，乘客张三，仅创建模拟订单，不要支付。"),
    "infinite_loop":({"infinite_loop":True},True,"帮我抢明天北京到上海的高铁二等座，无票时请候补监控余票，不要支付。"),
}


def run_case(name, out):
    # 每个case运行在独立进程；配置在导入Agent前设置。
    mutations,sandbox,message=SCENARIOS[name]
    root=out/name
    root.mkdir()
    os.environ.update(AGENT_PROVIDER="deepseek",AGENT_ENGINE="langchain",AGENT_MODEL="deepseek-flash",
        AGENT_BASE_URL="https://api.deepseek.com",AGENT_LC_TOOLSET="all" if sandbox else "read_only",
        AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",AGENT_MAX_STEPS="3" if name=="infinite_loop" else "4",
        AGENT_DB_PATH=str(root/"tickets.db"),AGENT_TRACE_DIR=str(root/"traces"),AGENT_MUTATIONS="{}",
        DEEPSEEK_BUDGET_PATH=str(root/"requests.db"),DEEPSEEK_MAX_REQUESTS="5",DEEPSEEK_TIMEOUT="20",
        DEEPSEEK_MAX_MODEL_CALLS="4",DEEPSEEK_MAX_TOOL_CALLS="4" if name=="infinite_loop" else "8",
        DEEPSEEK_THINKING="disabled",DEEPSEEK_LIVE_TEST_PROFILE="full_sandbox" if sandbox else "read_only",
        DEEPSEEK_SANDBOX_DIR=str(root),LANGSMITH_TRACING="false",LANGCHAIN_TRACING_V2="false")
    import config
    from data.seed import build_db
    from target.agent import Agent
    from target.deepseek_runtime import RequestBudget, Settings, safe_error, safe_text
    build_db()
    if sandbox:
        (root/".ticket-agent-sandbox.json").write_text(json.dumps(
            {"purpose":"ticket-agent-fault-test","version":1,"simulated_only":True}),encoding="utf-8")
    settings=Settings.from_env()
    db_before=hashlib.sha256(config.DB_PATH.read_bytes()).hexdigest()
    result,error=None,None
    agent=None
    started=time.perf_counter()
    try:
        agent=Agent(mutations=mutations)
        result=agent.chat("live-v31-"+name,message)
    except Exception as exc:
        error=safe_error(exc)
    finally:
        if agent is not None:
            client=getattr(agent.provider,"root_client",None)
            if client is not None: client.close()
    with closing(sqlite3.connect(config.DB_PATH)) as c:
        db_counts={table:c.execute("select count(*) from "+table).fetchone()[0] for table in ("inventory","locks","orders")}
    ledger=RequestBudget(settings).snapshot()
    report={"case":name,"source":"real_deepseek_api","model":config.MODEL_NAME,"profile":settings.profile,
            "input":message,"mutations":mutations,"result":result,"error":error,
            "fault_report":agent.last_fault_report if agent else None,
            "framework_events":agent.langchain_engine.last_events if agent else [],
            "request_count":ledger["reserved_requests"],"requests":ledger["requests"],
            "known_tokens":{"prompt":sum(r["prompt"] or 0 for r in ledger["requests"]),
                            "completion":sum(r["completion"] or 0 for r in ledger["requests"])},
            "usage_complete":all(r["prompt"] is not None and r["completion"] is not None for r in ledger["requests"]),
            "database_counts":db_counts,"database_unchanged":hashlib.sha256(config.DB_PATH.read_bytes()).hexdigest()==db_before,
            "latency_ms":int((time.perf_counter()-started)*1000),"max_retries":0,"actual_fee":None,
            "judgement":"A运行证据；Agent缺陷检出与恢复由B独立判定"}
    (root/"case.json").write_text(safe_text(json.dumps(report,ensure_ascii=False,indent=2)),encoding="utf-8")
    print(json.dumps({"case":name,"requests":report["request_count"],"error":error},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--cases",nargs="+",choices=list(SCENARIOS),default=list(SCENARIOS))
    parser.add_argument("--child",choices=list(SCENARIOS),help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not args.run:
        print(json.dumps({"status":"preflight_only","key_configured":bool(os.getenv("DEEPSEEK_API_KEY")),
                          "cases":args.cases,"new_api_requests":0,"max_generation_requests_per_case":5},ensure_ascii=False))
        return
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY 未配置；未发送请求。")
        raise SystemExit(2)
    if args.out is None:
        parser.error("--run需要显式--out新隔离目录")
    out=args.out.resolve()
    if not out.is_relative_to((ROOT/"artifacts/runtime").resolve()):
        parser.error("在线证据必须位于artifacts/runtime独立目录")
    if args.child:
        run_case(args.child,out)
        return
    out.mkdir(parents=True,exist_ok=False)
    all_reports=[]
    for name in args.cases:
        done=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--run","--child",name,"--out",str(out)],
                            cwd=ROOT,timeout=180,check=False)
        if done.returncode:
            raise SystemExit(done.returncode)
        report=json.loads((out/name/"case.json").read_text(encoding="utf-8"))
        all_reports.append(report)
        if report["error"] and report["error"]["category"] in ("authentication_failed","insufficient_balance","network_connection","timeout","rate_limited","server_error","service_unavailable"):
            break  # 不重试，也不在已知外部故障后连续消耗预算。
    from target.fault_injection import summarize
    summary={"source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
             "source":"real_deepseek_api","cases_run":[r["case"] for r in all_reports],
             "actual_generation_requests":sum(r["request_count"] for r in all_reports),
             "known_tokens":{k:sum(r["known_tokens"][k] for r in all_reports) for k in ("prompt","completion")},
             "usage_complete":all(r["usage_complete"] for r in all_reports),"actual_fee":None,
             "injection_statistics":summarize([r["fault_report"] for r in all_reports if r["fault_report"]]),
             "cases":[{"case":r["case"],"requests":r["request_count"],"error":r["error"]} for r in all_reports]}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == "__main__": main()
