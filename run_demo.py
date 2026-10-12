# -*- coding: utf-8 -*-
"""零依赖演示：不需要任何 pip 包、不需要 key，直接跑通全链路。

运行： python run_demo.py
"""
import json
import sys
import os
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 默认每次演示隔离数据，避免重建团队库或污染正式 Trace。
DEMO_DIR = Path(__file__).resolve().parent / "artifacts" / "runtime" / ("demo-" + uuid.uuid4().hex[:8])
os.environ.setdefault("AGENT_DB_PATH", str(DEMO_DIR / "tickets.db"))
os.environ.setdefault("AGENT_TRACE_DIR", str(DEMO_DIR / "traces"))
import config
from data.seed import build_db
from target.agent import Agent
from target import providers

CASES = [
    ("S1", "帮我查后天北京到上海的高铁"),
    ("S1", "我要买一张"),
    ("S1", "支付"),
    ("S2", "开车前两天退票扣多少手续费"),
    ("S3", "查一下我的订单"),
    ("S4", "帮我抢后天北京到广州的票"),
]


def main():
    print("=" * 70)
    print(f"抢票智能体 · 演示（{config.PROVIDER} 模式，全部为自建虚构数据）")
    print("=" * 70)
    if not config.DB_PATH.exists():
        build_db()
    agent = Agent()
    for sid, msg in CASES:
        r = agent.chat(sid, msg)
        print(f"\n[{sid}] 你：{msg}")
        print(f"      工具序列：{r['tool_sequence'] or '（未调用任何工具）'}")
        print(f"      回复：{r['reply']}")
        print(f"      结束原因：{r['finish_reason']}　耗时：{r['total_latency_ms']}ms")

    if config.PROVIDER != "mock":
        print("真实模型模式不运行 Mock 变异。")
        return
    print("\n" + "=" * 70)
    print("变异测试演示：注入 date_offset=1（日期解析偏移一天）")
    providers.set_mutation("date_offset", 1)
    r = agent.chat("S5", "帮我查明天北京到上海的高铁")
    print(f"工具调用：{json.dumps([c['args'] for s in r['steps'] for c in s['calls']], ensure_ascii=False)}")
    providers.clear_mutations()

    print("\n变异测试演示：注入 infinite_loop（无票时反复监控不退出）")
    providers.set_mutation("infinite_loop")
    r = agent.chat("S6", "帮我抢明天北京到上海的票")
    print(f"工具序列：{r['tool_sequence']}")
    print(f"结束原因：{r['finish_reason']}  <- 期望为 max_steps_exceeded，供成员 B 的 R6 规则捕获")
    providers.clear_mutations()
    print("\n演示结束。Trace 已追加至 AGENT_TRACE_DIR 下（默认 artifacts/runtime/demo-*）。")


if __name__ == "__main__":
    main()
