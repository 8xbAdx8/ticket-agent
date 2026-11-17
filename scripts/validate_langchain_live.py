"""V3 Live 独立预检；只有 --run 且有效配置才调用远端（可能收费）。

所有业务在临时虚构数据库内；保留输入、框架事件、真实响应与消息回传。
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import config
from data.seed import build_db
from target.agent import Agent
from target import tools, providers


def save(path, record):
    text = json.dumps(record,ensure_ascii=False,indent=2,default=str)
    for value in (config.API_KEY,str(ROOT),str(Path.home())):
        if value:
            text = text.replace(value,"<redacted>").replace(value.replace("\\","\\\\"),"<redacted>")
    path.write_text(text,encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--run",action="store_true")
    args = parser.parse_args()
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    out.mkdir(parents=True,exist_ok=False)
    url = urlsplit(config.BASE_URL)
    metadata = {"engine":"langchain","provider":config.PROVIDER,"model":config.MODEL_NAME,
                "endpoint":{"scheme":url.scheme,"host":url.hostname,"path":url.path},
                "api_key_present":bool(config.API_KEY),"real_api_attempted":False,
                "real_model_tested":False,"real_trace_count":0,"status":"真实大模型尚未联网实测",
                "scope":"成员 A 接入验证，非 B 正式评分；全部业务虚构"}
    if not args.run or not config.API_KEY or config.PROVIDER != "openai":
        metadata["reason"] = "未执行 --run" if not args.run else "缺少 API Key" if not config.API_KEY else "AGENT_PROVIDER 必须为 openai"
        save(out/"preflight.json",metadata)
        print(json.dumps(metadata,ensure_ascii=False))
        return
    providers.clear_mutations()
    scenarios = {
        "single_query":["查明天上海到杭州的高铁二等座"],
        "transport_switch":["查明天上海到杭州的高铁","那机票呢","还是高铁吧","后天呢"],
        "tool_roundtrip":["调用工具查明天上海到杭州的高铁，依据实际工具结果回复"],
        "purchase":["订明天上海到杭州的高铁，乘客张三，不要支付"],
        "rag":["锁座后多久必须完成支付？请引用政策来源"],
        "tool_failure":["查明天上海到杭州的高铁；工具报错就说明失败，不要重试或编造结果"],
        "normal_stop":["查明天上海到杭州的高铁"],
        "bounded_steps":["必须调用工具查明天上海到杭州的高铁"],
    }
    original_dispatch = tools.dispatch
    rows = []
    with tempfile.TemporaryDirectory(prefix="ticket-v3-live-") as tmp:
        for name,inputs in scenarios.items():
            folder = out/name
            folder.mkdir()
            with patch.object(config,"DB_PATH",Path(tmp)/(name+".db")),patch.object(config,"TRACE_DIR",folder), \
                 patch.object(config,"USE_HTTP_MOCK",False),patch.object(config,"USE_VECTOR_RAG",False), \
                 patch.object(config,"MAX_STEPS",1 if name=="bounded_steps" else config.MAX_STEPS), \
                 patch.object(config,"LC_TOOLSET","all" if name=="purchase" else "read_only"):
                build_db()
                agent = Agent(engine="langchain")
                injected = [False]
                def dispatch(tool,arguments):
                    if name=="tool_failure" and tool=="query_tickets" and not injected[0]:
                        injected[0] = True
                        return {"error":"A 接入验证：模拟查询服务不可用"},False,0
                    return original_dispatch(tool,arguments)
                turns,events = [],[]
                try:
                    metadata["real_api_attempted"] = True
                    with patch.object(tools,"dispatch",dispatch):
                        for message in inputs:
                            turns.append(agent.chat("live-"+name,message))
                            events.append({"input":message,"events":agent.langchain_engine.last_events})
                    state = agent.langchain_engine.graph.get_state({"configurable":{"thread_id":"live-"+name}})
                    messages = [m.model_dump(mode="json") for m in state.values.get("messages",[])]
                    received = any(e["event"]=="model_end" for t in events for e in t["events"])
                    row = {"scenario":name,"inputs":inputs,"turns":turns,"framework_events":events,"messages":messages,
                           "remote_response_observed":received,"fault_injected":injected[0],
                           "task_completion":"待人工按原始输入、工具结果和模型回复确认",
                           "errors":[r["reply"] for r in turns if "模型调用未完成" in r["reply"]],
                           "total_latency_ms":sum(r["total_latency_ms"] for r in turns)}
                    save(folder/"result.json",row)
                    rows.append({k:row[k] for k in ("scenario","remote_response_observed","errors","total_latency_ms","task_completion")})
                    metadata["real_trace_count"] += len(turns)
                finally:
                    agent.provider.root_client.close()
    metadata.update(real_model_tested=any(r["remote_response_observed"] for r in rows),
                    status="已尝试远端 API，业务完成情况待人工确认",scenarios=rows)
    save(out/"verification.json",metadata)
    print(json.dumps({k:metadata[k] for k in ("status","real_api_attempted","real_model_tested","real_trace_count")},ensure_ascii=False))


if __name__ == "__main__":
    main()
