"""可直接运行的 Agent().chat 示例；独立模拟库、独立 Trace，不使用 API Key。"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="ticket-v2-api-") as tmp:
        os.environ.update(AGENT_PROVIDER="mock", AGENT_USE_HTTP="0", AGENT_VECTOR_RAG="0",
                          AGENT_DB_PATH=str(Path(tmp)/"tickets.db"), AGENT_TRACE_DIR=str(out))
        # 环境设置在 import 前生效，唯一对外调用与 V1 契约相同。
        from data.seed import build_db
        from target.agent import Agent
        build_db()
        agent = Agent()
        inputs = ["订明天上海到杭州的高铁", "锁座后多久必须完成支付？", "支付我刚才的订单。", "支付"]
        results = [agent.chat("v2-api-example", message) for message in inputs]
        (out/"results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"provider": "mock", "turns": len(results),
                          "tool_sequences": [r["tool_sequence"] for r in results],
                          "duplicate_reply": results[-1]["reply"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
