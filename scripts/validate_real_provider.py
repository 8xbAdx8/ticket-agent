"""真实 Provider 验证入口。默认仅预检；--run 才会调用付费远端 API。

仅使用新建临时模拟数据库；结果在独立目录，不改变团队契约。
无 Key 时只记录待验证，不生成冒充真实模型的 Trace。
"""
import argparse
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config
from data.seed import build_db
from target.agent import Agent
from target.providers import OpenAIProvider
from target import tools


def safe_endpoint(url):
    parsed = urlsplit(url)
    return {"scheme": parsed.scheme, "host": parsed.hostname,
            "path": parsed.path}  # 排除密码、查询串、令牌


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    for secret in (config.API_KEY, str(ROOT), str(Path.home())):
        if secret:
            text = text.replace(secret, "<redacted>")
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="调用已配置的真实模型，可能收费")
    args = parser.parse_args()
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    metadata = {"provider": config.PROVIDER, "model": config.MODEL_NAME,
                "endpoint": safe_endpoint(config.BASE_URL), "api_key_present": bool(config.API_KEY),
                "max_steps": config.MAX_STEPS, "backend": "isolated fictional mock_core",
                "vector_rag": False, "real_model_tested": False, "real_trace_count": 0,
                "status": "待验证", "scope": "A 的接入验证，不是 B 正式测试评分"}
    if not args.run or not config.API_KEY or config.PROVIDER != "openai":
        metadata["reason"] = ("未执行 --run" if not args.run else
                              "没有 AGENT_API_KEY" if not config.API_KEY else "AGENT_PROVIDER 不是 openai")
        save(out/"preflight.json", metadata)
        print(json.dumps({"status": "待验证", "api_key_present": bool(config.API_KEY),
                          "real_model_tested": False, "reason": metadata["reason"]}, ensure_ascii=False))
        return
    scenarios = {
        "single_query": ["查明天上海到杭州的高铁二等座"],
        "transport_switch": ["查明天上海到杭州的高铁", "那机票呢", "还是高铁吧", "后天呢"],
        "tool_roundtrip": ["调用工具查明天上海到杭州的高铁，依据工具的实际结果回复"],
        "purchase": ["查明天上海到杭州的高铁", "选一个有票的班次，给张三订一张，不要支付"],
        "rag": ["锁座后多久必须完成支付？请引用政策来源"],
        "tool_failure": ["查明天上海到杭州的高铁；如果工具报错请说明失败，不要重试或编造结果"],
        "normal_stop": ["查明天上海到杭州的高铁"],
        "bounded_steps": ["必须先调用工具查明天上海到杭州的高铁"],
    }
    original_dispatch = tools.dispatch
    results = []
    with tempfile.TemporaryDirectory(prefix="ticket-v2-real-") as tmp:
        with patch.object(config, "USE_HTTP_MOCK", False), patch.object(config, "USE_VECTOR_RAG", False):
            for label, inputs in scenarios.items():
                case_dir = out/label
                case_dir.mkdir()
                with patch.object(config, "DB_PATH", Path(tmp)/(label+".db")), \
                     patch.object(config, "TRACE_DIR", case_dir), \
                     patch.object(config, "MAX_STEPS", 1 if label == "bounded_steps" else config.MAX_STEPS):
                    build_db()
                    provider = OpenAIProvider()
                    agent = Agent(provider)
                    injected = [False]
                    def dispatch(name, arguments):
                        if label == "tool_failure" and name == "query_tickets" and not injected[0]:
                            injected[0] = True
                            return {"error": "A 验证注入：模拟查询服务暂不可用"}, False, 0
                        return original_dispatch(name, arguments)
                    try:
                        with patch.object(tools, "dispatch", dispatch):
                            turns = [agent.chat("real-"+label, text) for text in inputs]
                        # 完整工具结果和服务器 call_id 保存在独立验证附件，不加到契约字段。
                        record = {"scenario": label, "inputs": inputs, "turns": turns,
                                  "messages": agent.sessions["real-"+label],
                                  "fault_injected": injected[0], "max_steps": config.MAX_STEPS,
                                  "remote_response_observed": any(r["tokens"]["prompt"] or r["tool_sequence"] for r in turns),
                                  "total_latency_ms": sum(r["total_latency_ms"] for r in turns),
                                  "errors": [r["reply"] for r in turns if "模型调用未完成" in r["reply"]],
                                  "task_completion": "待人工按输入、工具结果和实际回复确认"}
                        save(case_dir/"result.json", record)
                        results.append({k: record[k] for k in ("scenario", "remote_response_observed", "total_latency_ms", "errors", "task_completion")})
                        metadata["real_trace_count"] += len(turns)
                    finally:
                        provider.client.close()
    metadata.update(real_model_tested=True, status="已尝试真实 API；完成情况待人工确认", scenarios=results)
    save(out/"verification.json", metadata)
    print(json.dumps({"status": metadata["status"], "real_trace_count": metadata["real_trace_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
