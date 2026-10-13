"""V3 独立框架执行证据、CLI/Web 验证及原文件保护；不产生正式比赛成绩。"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import config
from data.seed import build_db
from target.agent import Agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--toolset",choices=("read_only","all"),default="read_only")
    args = parser.parse_args()
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    out.mkdir(parents=True,exist_ok=False)
    baseline = json.loads((ROOT/"docs/evidence/v3/v2_baseline/manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        db, trace = Path(tmp)/"tickets.db",out/"langchain_mock"
        with (patch.object(config,"DB_PATH",db),patch.object(config,"TRACE_DIR",trace),
              patch.object(config,"PROVIDER","mock"),patch.object(config,"ENGINE","langchain"),
              patch.object(config,"USE_HTTP_MOCK",False),patch.object(config,"USE_VECTOR_RAG",False),
              patch.object(config,"MAX_STEPS",8),patch.object(config,"LC_TOOLSET",args.toolset)):
            build_db()
            agent = Agent()
            inputs = ["查明天上海到杭州的高铁","那机票呢","还是高铁吧","后天呢","锁座后多久必须完成支付？"]
            turns,events = [],[]
            for message in inputs:
                turns.append(agent.chat("v3-demo",message))
                events.append({"input":message,"events":agent.langchain_engine.last_events})
            assert [r["tool_sequence"] for r in turns] == [["query_tickets"]]*4+[["search_policy"]]
            assert "P11" in turns[-1]["reply"]
            if args.toolset == "all":
                for message in ("订明天上海到杭州的高铁","支付我刚才的订单。","支付","帮我退掉","查我的订单","抢明天北京到上海的票"):
                    turns.append(agent.chat("v3-orders",message))
                    events.append({"input":message,"events":agent.langchain_engine.last_events})
                assert [r["tool_sequence"] for r in turns[5:]] == [
                    ["query_tickets","lock_seat","create_order"],["pay_order"],["pay_order"],
                    ["cancel_order"],["query_order"],["query_tickets","monitor_seat"]]
                assert "没有重复扣款" in turns[7]["reply"]
                assert {t for r in turns for t in r["tool_sequence"]}==set(agent.langchain_engine.tool_names)
            assert all(c["ok"] for r in turns for s in r["steps"] for c in s["calls"])
            assert all(r["finish_reason"]=="stop" for r in turns)
            (out/"api_results.json").write_text(json.dumps(turns,ensure_ascii=False,indent=2),encoding="utf-8")
            (out/"framework_events.json").write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding="utf-8")
            from streamlit.testing.v1 import AppTest
            app = AppTest.from_file(str(ROOT/"web/app.py"),default_timeout=30).run()
            app.text_input[0].set_value("查明天上海到杭州的高铁")
            next(b for b in app.button if b.label=="发送").click().run()
            assert len(app.exception)==0
            assert app.session_state["history"][-1]["provider"]=="langchain_mock"
            assert all(c.disabled for c in app.checkbox)
            assert len(app.json)>0 and len(app.dataframe)>0
            app.text_input[0].set_value("锁座后多久必须完成支付？")
            next(b for b in app.button if b.label=="发送").click().run()
            assert "P11" in app.session_state["history"][-1]["reply"]
            env = dict(os.environ,PYTHONIOENCODING="utf-8",AGENT_ENGINE="langchain",AGENT_PROVIDER="mock",
                       AGENT_LC_TOOLSET=args.toolset,AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",AGENT_MAX_STEPS="8",
                       AGENT_DB_PATH=str(db),AGENT_TRACE_DIR=str(out/"cli_mock"))
            env.pop("AGENT_API_KEY",None)
            runs=[]
            for label,command,input_text in (("once",["cli.py","once","查明天上海到杭州的高铁"],None),
                                             ("chat",["cli.py","chat"],"查明天上海到杭州的高铁\n后天呢\nq\n")):
                result = subprocess.run([sys.executable,*command],cwd=ROOT,env=env,input=input_text,
                                        text=True,encoding="utf-8",capture_output=True,timeout=60)
                text = result.stdout+result.stderr
                for path in (str(ROOT),str(Path.home()),str(tmp),sys.base_prefix):
                    text=text.replace(path,"<local-path>")
                (out/(label+".txt")).write_text(text,encoding="utf-8")
                assert result.returncode==0
                cli_records = [json.loads(line) for line in (out/"cli_mock/traces.jsonl").read_text(encoding="utf-8").splitlines()]
                assert cli_records[-1]["provider"]=="langchain_mock"
                runs.append({"name":label,"command":"python "+" ".join(command),"exit_code":result.returncode})
    protected = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in baseline["protected_sha256"].items()}
    assert all(protected.values()),"V2 原始证据变化"
    report={"scope":"A LangChain Mock prototype verification, not B official testing",
            "toolset":args.toolset,"tools":list(agent.langchain_engine.tool_names),"api_turns":len(turns),
            "web_apptest_passed":True,"cli_runs":runs,"protected_files_count":len(protected),
            "protected_files_unchanged":True,"real_model_tested":False,
            "versions":{n:importlib.metadata.version(n) for n in ("langchain","langchain-core","langchain-openai","langgraph","streamlit","openai")},
            "source_sha256":{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                             for folder in ("target","web") for p in (ROOT/folder).glob("*.py")}}
    (out/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":"passed","api_turns":len(turns),"tools":report["tools"],
                      "web_passed":True,"protected":len(protected)},ensure_ascii=False))


if __name__ == "__main__":
    main()
