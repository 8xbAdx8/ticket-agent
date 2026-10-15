"""生成明确标注的离线 SDK 桩证据；不访问官方 API、不读取真实密钥。"""
import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import config
import httpx
from data.seed import build_db
from target.agent import Agent
from target.deepseek_runtime import Settings, make_model, RequestBudget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    requests, records = [], []
    responses = []
    for tool,arguments,reply in (("query_tickets",{"from_city":"上海","to_city":"杭州","date":config.today().isoformat(),"kind":"高铁","seat_type":"二等座"},"[离线SDK桩] 查询工具已执行。"),
                                 ("search_policy",{"question":"锁座后多久必须完成支付？"},"[离线SDK桩] 模拟锁座 15 分钟，来源 P11。")):
        responses.extend([{"content":None,"tool_calls":[{"id":"offline-"+tool,"type":"function","function":{"name":tool,"arguments":json.dumps(arguments,ensure_ascii=False)}}]},
                          {"content":reply}])

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        message = responses[len(requests)-1]
        return httpx.Response(200,json={"id":"offline-sdk-only","object":"chat.completion","created":1,"model":"deepseek-flash",
            "choices":[{"index":0,"message":{"role":"assistant",**message},"finish_reason":"tool_calls" if message.get("tool_calls") else "stop"}],
            "usage":{"prompt_tokens":13,"completion_tokens":5,"total_tokens":18}})

    with patch.multiple(config,PROVIDER="deepseek",ENGINE="langchain",API_KEY="offline-sdk-placeholder",MODEL_NAME="deepseek-flash",
                        BASE_URL="https://api.deepseek.com",LC_TOOLSET="read_only",USE_HTTP_MOCK=False,USE_VECTOR_RAG=False,
                        DB_PATH=out/"tickets.db",TRACE_DIR=out/"traces"), \
         patch.dict(os.environ,{"DEEPSEEK_BUDGET_PATH":str(out/"offline-budget.db"),"DEEPSEEK_THINKING":"disabled"}):
        build_db()
        model = make_model(Settings.from_env(),transport=httpx.MockTransport(transport))
        try:
            agent = Agent(model=model)
            for message in ("查询今天上海到杭州的高铁二等座","锁座后多久必须完成支付？"):
                record = agent.chat("offline-sdk-only",message)
                records.append({"contract":record,"events":agent.langchain_engine.last_events})
        finally:
            model.root_client.close()
        assert [r["contract"]["tool_sequence"] for r in records]==[["query_tickets"],["search_policy"]]
        for i,tool in ((1,"query_tickets"),(3,"search_policy")):
            result = next(m for m in reversed(requests[i]["messages"]) if m["role"]=="tool")
            assert result["tool_call_id"]=="offline-"+tool
            assert json.loads(result["content"])["count"]>0
        assert len(requests)==4
        proof = {"source":"offline_sdk_stub","real_api_verified":False,"real_function_calling_verified":False,
                 "remote_api_requests":0,"stubbed_http_requests":4,"do_not_use_as_live_evidence":True,
                 "contract_provider_note":"deepseek_live identifies the adapter; this file uses MockTransport, not the remote model",
                 "records":records,"sdk_payloads":requests,"offline_ledger":RequestBudget(Settings.from_env()).snapshot()}
        (out/"offline_evidence.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":"passed","source":"offline_sdk_stub","remote_api_requests":0,"stubbed_http_requests":4}))


if __name__=="__main__":
    main()
