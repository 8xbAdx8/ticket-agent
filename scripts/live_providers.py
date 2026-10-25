"""Explicit multi-provider entry. Default is local preflight; --run alone authorizes generation."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


SCENARIOS={"text":"请用一句话说明你是模拟出行咨询助手，不要查询具体班次。",
           "tickets":"查明天上海到杭州的高铁二等座，请列出有余票的车次。",
           "policy":"锁座后多久必须完成支付？请检索政策并引用实际来源。"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider",choices=("deepseek","bailian"),required=True)
    action=parser.add_mutually_exclusive_group()
    action.add_argument("--run",action="store_true",help="Explicitly send real model requests, within the initial total-three ceiling")
    action.add_argument("--serve",action="store_true",help="Start localhost; opening a page does not generate")
    parser.add_argument("--scenario",choices=tuple(SCENARIOS),default="tickets")
    parser.add_argument("--case-id")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--upload-langsmith",action="store_true")
    parser.add_argument("--confirm-upload",action="store_true",help="Consent to the printed filtered upload scope")
    parser.add_argument("--port",type=int,default=8503)
    parser.add_argument("--no-browser",action="store_true")
    args=parser.parse_args(argv)
    from target.live_providers import configuration,isolated_environment
    from target.deepseek_runtime import RequestBudget,Settings,safe_error
    from target.diagnostics import sanitize
    import config
    out=(args.out or ROOT/"artifacts/runtime/v33-live-providers"/(args.provider+"-"+uuid.uuid4().hex[:10])).resolve()
    formal=ROOT/"artifacts/runtime/deepseek-budget/requests.db"
    formal_hash=hashlib.sha256(formal.read_bytes()).hexdigest() if formal.exists() else None
    execution_started=False
    try:
        env=isolated_environment(args.provider,out)
        os.environ.update(env)
        os.environ["TICKET_CASE_ID"]=args.case_id or args.scenario
        importlib.reload(config)
        from target import bailian_runtime,deepseek_runtime
        runtime=bailian_runtime if args.provider=="bailian" else deepseek_runtime
        runtime.validate_configuration()
        settings=runtime.Settings.from_env()
        state=sanitize(configuration(args.provider))
        state.update(engine="langchain",tools=["query_tickets","search_policy"],max_retries=0,
            provider_budget=RequestBudget(settings).snapshot(),
            initial_total_budget=RequestBudget(Settings(max_requests=3,ledger_path=Path(env["TICKET_INITIAL_LIVE_BUDGET"]))).snapshot(),
            model_requests_this_command=0)
        from target.observability import configuration_status,UPLOAD_SCOPE
        state["langsmith"]=configuration_status()
        print(json.dumps(state,ensure_ascii=False),flush=True)
        if not args.run and not args.serve: return 0
        if args.upload_langsmith and (not args.confirm_upload or state["langsmith"]["state"]!="configured_unverified"):
            print("LangSmith 导出需要环境显式启用、有效配置及 --confirm-upload。没有发送模型请求。")
            return 2
        if args.upload_langsmith: print("已确认上传范围："+UPLOAD_SCOPE,flush=True)
        if state["initial_total_budget"]["reserved_requests"]>=3 or state["provider_budget"]["reserved_requests"]>=settings.max_requests:
            print("初次验证预算已耗尽；停止，不重置账本、不增加额度。")
            return 2
        if args.serve:
            from scripts.launch_app import prepare_database,serve
            prepare_database(dict(os.environ))
            return serve(dict(os.environ),args.port,open_browser=not args.no_browser)
        # Configuration import creates only this trace directory. Reject pre-existing evidence.
        if (out/"report.json").exists() or (out/"tickets.db").exists() or list(config.TRACE_DIR.glob("*.jsonl")):
            raise ValueError("new_evidence_directory_required")
        from data.seed import build_db
        build_db(config.DB_PATH)
        from target.agent import Agent
        agent=Agent()
        before=state["provider_budget"]["reserved_requests"]
        result=None; error=None
        execution_started=True
        try: result=agent.chat("live-"+uuid.uuid4().hex,SCENARIOS[args.scenario])
        except Exception as exc: error=safe_error(exc)
        evidence=agent.langchain_engine.last_live_run
        after=RequestBudget(settings).snapshot()
        expected={"tickets":"query_tickets","policy":"search_policy"}.get(args.scenario)
        tool_ok=bool(result and expected and expected in result["tool_sequence"] and all(c["ok"] for s in result["steps"] for c in s["calls"]))
        events=(evidence or {}).get("events",[])
        last_tool=max((i for i,e in enumerate(events) if e.get("event")=="tool_end"),default=-1)
        returned=last_tool>=0 and any(e.get("event")=="model_final" for e in events[last_tool+1:])
        complete=bool(result and result["finish_reason"]=="stop" and not error)
        receipt=None
        if args.upload_langsmith and evidence:
            from target.observability import export_run
            receipt=export_run(evidence,consent=True,trace_dir=config.TRACE_DIR)
        report={"status":"passed" if complete and (not expected or tool_ok and returned) else "failed",
            "provider":args.provider,"scenario":args.scenario,"case_id":os.environ["TICKET_CASE_ID"],
            "real_model_response_received":bool((evidence or {}).get("model_response_received")),
            "function_calling_verified":tool_ok and returned and complete,"business_success":None,
            "validation_scope":"HTTP/model/tool protocol closure; semantic business accuracy requires B review",
            "reply_data_consistency_verified":None,"policy_grounding_verified":None,
            "reserved_generation_attempts_this_command":after["reserved_requests"]-before,
            "tokens":(evidence or {}).get("tokens"),"cost":None,"cost_basis":"No reliable billing/price evidence",
            "error":error,"public_trace":result,"live_evidence":evidence,"langsmith_receipt":receipt,
            "formal_deepseek_ledger_unchanged":formal_hash==(hashlib.sha256(formal.read_bytes()).hexdigest() if formal.exists() else None)}
        (out/"report.json").write_text(json.dumps(sanitize(report),ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(sanitize({k:v for k,v in report.items() if k not in ("public_trace","live_evidence")}),ensure_ascii=False))
        return 0 if report["status"]=="passed" else 1
    except Exception as exc:
        print(json.dumps({"status":"incomplete" if execution_started else "not_run","error":safe_error(exc),
                          "new_generation_requests":None if execution_started else 0},ensure_ascii=False))
        return 2


if __name__=="__main__": raise SystemExit(main())
