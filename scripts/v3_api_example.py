"""B/C 可运行的八工具 Mock 示例；输出目录必须是新的，不覆盖旧数据。"""
import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import config
from data.seed import build_db
from target.agent import Agent
from target.providers import clear_mutations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,required=True)
    args = parser.parse_args()
    folder = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    folder.mkdir(parents=True,exist_ok=False)
    clear_mutations()
    with patch.object(config,"DB_PATH",folder/"tickets.db"),patch.object(config,"TRACE_DIR",folder/"langchain_mock"), \
         patch.object(config,"PROVIDER","mock"),patch.object(config,"LC_TOOLSET","all"), \
         patch.object(config,"USE_HTTP_MOCK",False),patch.object(config,"USE_VECTOR_RAG",False):
        build_db()
        agent = Agent(engine="langchain")
        messages = ["订明天上海到杭州的高铁","锁座后多久必须完成支付？","支付我刚才的订单。",
                    "支付","帮我退掉","查我的订单","抢明天北京到上海的票"]
        results = [agent.chat("v3-example",message) for message in messages]
        assert set(t for r in results for t in r["tool_sequence"]) == set(agent.langchain_engine.tool_names)
        assert "没有重复扣款" in results[3]["reply"]
        (folder/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"provider":"langchain_mock","turns":len(results),"tools":[r["tool_sequence"] for r in results]},ensure_ascii=False))


if __name__ == "__main__":
    main()
