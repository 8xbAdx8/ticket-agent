"""生成 V3.2 可回放对照证据。只有离线桩，无 --run 或在线入口。"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    # 在 config/SDK 导入前移除所有真实凭据，禁止非回环网络。
    for name in list(os.environ):
        if name.endswith(("_API_KEY","_TOKEN")) or name.startswith("DEEPSEEK_"):
            os.environ.pop(name,None)
    os.environ.update(AGENT_PROVIDER="mock",AGENT_ENGINE="legacy",AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",
        AGENT_MUTATIONS="{}",LANGSMITH_TRACING="false",LANGCHAIN_TRACING_V2="false",
        TICKET_OFFLINE_GUARD_LOG=str(out/"blocked_network.jsonl"))
    from run_deepseek_review_offline import GUARD
    exec(GUARD,{})
    import config
    from data.seed import build_db
    from target.agent import Agent
    from target.diagnostics import save_audit,metrics,detect_hallucinated_trains,sanitize
    from target.concurrency_probe import probe,SCENARIOS
    from tests.test_v32_audit import AuditSDKTests
    audits=[]

    def retain(name,audit,*,expected_defect=None):
        audit["evidence_kind"]="offline_sdk_stub" if audit.get("provider")=="deepseek_live" else "offline_mock_or_backend"
        audit["real_api_requests"]=0
        audit["test_case_label"]=name
        if expected_defect is not None:
            actual=audit["judgement"]["dimensions"]["platform_defect_detected"]
            audit["test_expectations"]={"platform_defect_should_detect":expected_defect}
            audit["judgement"]["test_verdict"]="pass" if actual is expected_defect else "fail"
        save_audit(audit,out/"cases"/name)
        audits.append(audit)

    # 真 SDK + 真框架 + 真业务后端；响应来自 MockTransport，绝非 Live 成绩。
    for name in ("date_offset","route_error","no_citation","repeat_call","hallucinated_train","infinite_loop","skip_lock"):
        case=AuditSDKTests()
        case.setUp()
        try:
            with contextlib.redirect_stdout(io.StringIO()):agent,_=case.execute(name)
            retain("sdk-"+name,agent.last_audit_report,expected_defect=True)
        finally:
            case.tearDown()
            case.doCleanups()

    # M7 关闭→开启→关闭，对比两个现有 Mock 引擎。
    for engine in ("legacy","langchain"):
        with tempfile.TemporaryDirectory() as temp,patch.multiple(config,PROVIDER="mock",ENGINE=engine,LC_TOOLSET="all",
                DB_PATH=Path(temp)/"tickets.db",TRACE_DIR=Path(temp)/"traces",USE_HTTP_MOCK=False,USE_VECTOR_RAG=False):
            with contextlib.redirect_stdout(io.StringIO()):build_db()
            agent=Agent(mutations={})
            for phase,mutations in (("baseline",{}),("mutant",{"hallucinated_train":True}),("restored",{})):
                agent.set_mutations(mutations)
                agent.chat("m7-"+engine,"查今天上海到杭州高铁二等座")
                retain(engine+"-m7-"+phase,agent.last_audit_report,expected_defect=phase=="mutant")

    # 七种正常并发业务场景 + 两线程/四线程重复变异 + 不同锁座负对照。
    for scenario in SCENARIOS:retain("concurrency-normal-"+scenario,probe(scenario),expected_defect=False)
    retain("concurrency-mutant-two",probe(mutant=True),expected_defect=True)
    for index in range(3):
        retain("concurrency-mutant-many-"+str(index+1),probe("same_lock_many",mutant=True),expected_defect=True)
    retain("concurrency-mutant-different-locks",probe("different_locks",mutant=True),expected_defect=False)

    labelled=[]
    samples=[("invented","查到G9999有余票",True),("valid","G7301有余票",False),
             ("user-quote","你输入的G9999，请确认",False),("negation","G9999不存在。没有查到G9999。查询不到G9999",False),
             ("quoted-then-affirmed","引用用户原话G9999，查到G9999有票",True),
             ("user-number-affirmed","G9999有余票",True),("ambiguous","也许G9999",None),
             ("hypothetical","例如G9999有票",None)]
    for name,reply,expected in samples:
        result=detect_hallucinated_trains(reply,["G7301"],user_message="G9999")
        labelled.append({"case_id":name,"reply":reply,"test_expectations":{"hallucination_should_detect":expected},
                         "judgement":{"hallucination":result},"expected_semantic_outcome":expected,
                         "test_verdict":"pass" if result["hallucination_detected"] is expected else "fail"})
    source={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("target","web","tests") for p in (ROOT/folder).glob("*.py")}
    failed=[a["test_case_label"] for a in audits if a["judgement"].get("test_verdict")=="fail"]
    failed += ["label-"+s["case_id"] for s in labelled if s["test_verdict"]!="pass"]
    report={"status":"failed" if failed else "passed","real_api_requests":0,"real_tokens":0,"api_cost":0,
        "sdk_token_values":"synthetic fixture usage, excluded from real token/cost totals",
        "agent_and_backend_records":len(audits),"labelled_detector_samples":len(labelled),
        "case_verdicts":{a["test_case_label"]:a["judgement"].get("test_verdict") for a in audits},
        "metrics":metrics(audits),"labelled_metrics":metrics(labelled)["hallucination_labelled_benchmark"],
        "labelled_samples":labelled,"failures":failed,"source_sha256":source,
        "source_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "source_manifest_note":"HEAD plus exact working source hashes; do not infer all source was already committed",
        "concurrency_resources_cleaned":all(a.get("resources_cleaned",True) for a in audits),
        "limits":["No new real-model result", "Unknown semantic recognition/recovery excluded from rates",
                  "Labelled sample accuracy describes only this tiny deterministic set", "SQLite native writes serialize"]}
    (out/"report.json").write_text(json.dumps(sanitize(report),ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","real_api_requests","agent_and_backend_records","labelled_detector_samples","failures")},ensure_ascii=False))
    return bool(failed)


if __name__=="__main__":raise SystemExit(main())
