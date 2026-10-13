"""同环境小样本 Mock 开销对照；不是正式性能指标或真实模型测评。"""
import argparse
import json
import statistics
import sys
import tempfile
import time
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
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    out.mkdir(parents=True,exist_ok=False)
    inputs = ["查明天上海到杭州的高铁","那机票呢","还是高铁吧","后天呢","锁座后多久必须完成支付？"]
    rows = []
    clear_mutations()
    with tempfile.TemporaryDirectory() as tmp:
        for trial in range(3):
            for engine in ("legacy","langchain"):
                with (patch.object(config,"DB_PATH",Path(tmp)/f"{engine}-{trial}.db"),
                      patch.object(config,"TRACE_DIR",out/engine),patch.object(config,"PROVIDER","mock"),
                      patch.object(config,"LC_TOOLSET","read_only"),patch.object(config,"USE_HTTP_MOCK",False),
                      patch.object(config,"USE_VECTOR_RAG",False)):
                    build_db()
                    started = time.perf_counter()
                    agent = Agent(engine=engine)
                    init_ms = (time.perf_counter()-started)*1000
                    for index,message in enumerate(inputs):
                        started = time.perf_counter()
                        r = agent.chat(f"compare-{trial}",message)
                        elapsed = (time.perf_counter()-started)*1000
                        rows.append({"trial":trial,"engine":engine,"input":message,"turn":index+1,
                                     "init_ms":init_ms if index==0 else None,"chat_wall_ms":elapsed,
                                     "trace_latency_ms":r["total_latency_ms"],"tools":r["tool_sequence"]})
    summaries = {}
    for engine in ("legacy","langchain"):
        selected = [r for r in rows if r["engine"]==engine]
        summaries[engine] = {"turns":len(selected),"chat_wall_median_ms":statistics.median(r["chat_wall_ms"] for r in selected),
                             "chat_wall_min_ms":min(r["chat_wall_ms"] for r in selected),
                             "chat_wall_max_ms":max(r["chat_wall_ms"] for r in selected),
                             "init_ms":[r["init_ms"] for r in selected if r["init_ms"] is not None]}
    report = {"scope":"A 同环境本地 Mock 3组x5轮；非正式比赛性能结论",
              "engine_order":"each trial legacy then langchain, not randomized",
              "limitations":"首次框架延迟包含懒导入；无远端网络、并发压力、持久化检查点或内存测量；样本很小",
              "summaries":summaries,"rows":rows}
    (out/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summaries,ensure_ascii=False))


if __name__ == "__main__":
    main()
