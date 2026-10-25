"""V3.3 reproducible offline acceptance. Never sends model or telemetry requests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from run_deepseek_review_offline import GUARD


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    allowed=[(ROOT/"artifacts/runtime").resolve(),(ROOT/"docs/evidence/v33").resolve()]
    if not any(out.is_relative_to(p) and out!=p for p in allowed):
        raise ValueError("Output must be a new child of artifacts/runtime or docs/evidence/v33")
    out.mkdir(parents=True,exist_ok=False)
    guard=out/"guard";guard.mkdir()
    (guard/"sitecustomize.py").write_text(GUARD,encoding="utf-8")
    protected=[]
    for base in ("target","data","traces","docs/evidence"):
        protected.extend(p for p in (ROOT/base).rglob("*") if p.is_file() and "__pycache__" not in p.parts and not p.resolve().is_relative_to(out))
    protected.extend((ROOT/"artifacts/runtime").rglob("requests.db"))
    protected.append(ROOT/"docs/contract.md")
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    env=dict(os.environ)
    for name in list(env):
        if name.endswith(("_API_KEY","_TOKEN")) or name.startswith("DEEPSEEK_"):
            env.pop(name,None)
    env.update(PYTHONIOENCODING="utf-8",PYTHONPATH=str(guard)+os.pathsep+str(ROOT),
        TICKET_OFFLINE_GUARD_LOG=str(out/"blocked_network.jsonl"),TICKET_WEB_OFFLINE_ONLY="1",
        AGENT_PROVIDER="mock",AGENT_ENGINE="legacy",AGENT_LC_TOOLSET="all",AGENT_MODEL="mock-offline",
        AGENT_MUTATIONS="{}",AGENT_MAX_STEPS="8",AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",
        AGENT_DB_PATH=str(out/"unused.db"),AGENT_TRACE_DIR=str(out/"unused-traces"),
        LANGSMITH_TRACING="false",LANGCHAIN_TRACING_V2="false")
    runs=[]
    def run(name,command,expected=0,extra=None):
        result=subprocess.run(command,cwd=ROOT,env=dict(env,**(extra or {})),capture_output=True,text=True,encoding="utf-8",timeout=300)
        log=(result.stdout+result.stderr).replace(str(ROOT),"<project>").replace(str(Path.home()),"<user>")
        (out/(name+".txt")).write_text(log,encoding="utf-8")
        runs.append({"name":name,"exit_code":result.returncode,"expected_exit_code":expected,"passed":result.returncode==expected})
    run("all_environments",[sys.executable,"scripts/run_deepseek_review_offline.py","--out",str(out/"regression")])
    run("v32_audit_matrix",[sys.executable,"scripts/verify_v32_offline.py","--out",str(out/"audit-matrix")])
    run("offline_preflight",[sys.executable,"scripts/launch_app.py","--mode","offline","--check-only"])
    run("live_missing_key_preflight",[sys.executable,"scripts/launch_app.py","--mode","live","--check-only"],expected=2)
    run("live_fake_key_preflight",[sys.executable,"scripts/launch_app.py","--mode","live","--check-only"],extra={"DEEPSEEK_API_KEY":"offline-v33-preflight-placeholder"})
    changed=[name for name,digest in hashes.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    attempts=sum(len(p.read_text(encoding="utf-8").splitlines()) for p in out.rglob("*blocked*network*.jsonl"))
    regression=json.loads((out/"regression/regression.json").read_text(encoding="utf-8")) if (out/"regression/regression.json").is_file() else None
    matrix=json.loads((out/"audit-matrix/report.json").read_text(encoding="utf-8")) if (out/"audit-matrix/report.json").is_file() else None
    source=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    passed=all(r["passed"] for r in runs) and not changed and not attempts
    report={"status":"passed" if passed else "failed","tested_source_head":source,"timestamp":datetime.now(timezone.utc).isoformat(),
        "scope":"A offline validation; not B V3.3 formal acceptance or new Live evidence",
        "credentials_removed_from_children":True,"external_python_network_blocked":True,"blocked_network_attempts":attempts,
        "real_api_requests":0,"real_api_tokens":None,"new_api_cost":0,"cost_basis":"No remote generation requests",
        "protected_files":len(hashes),"protected_files_unchanged":not changed,"changed_original_files":changed,"runs":runs,
        "environment_regression":regression,"audit_matrix_records":matrix.get("agent_and_backend_records") if matrix else None,
        "labelled_detector_samples":matrix.get("labelled_detector_samples") if matrix else None,
        "limits":["Fake Key preflight is not credential or account validation","SDK stubs are not Live runs","B raw assertions and evidence not executed or changed","Browser screenshots are recorded separately"]}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("environment_regression","limits")},ensure_ascii=False))
    return 0 if passed else 1


if __name__=="__main__":
    raise SystemExit(main())
