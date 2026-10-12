"""B/C 可复现的 Python 入口示例，使用调用方配置的隔离数据库和 Trace。"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from target.agent import Agent
from target import providers


def run():
    providers.clear_mutations()
    agent = Agent(providers.MockProvider())
    examples = []
    for msg in ["查明天上海到杭州的高铁", "我要买一张", "支付", "帮我退掉", "退票手续费怎么算", "查我的订单"]:
        examples.append({"label": "normal", "result": agent.chat("handoff-normal", msg)})
    examples.append({"label":"normal-waitlist", "result":agent.chat("handoff-wait", "抢明天北京到上海的票")})
    for name in providers.MUTATION_NAMES:
        providers.clear_mutations()
        providers.set_mutation(name, 1 if name == "date_offset" else True)
        message = "退票手续费怎么算" if name in ("route_error", "no_citation") else (
            "抢明天北京到上海的票" if name == "infinite_loop" else "订明天上海到杭州的高铁")
        examples.append({"label": "injected:" + name, "result": agent.chat("handoff-"+name, message)})
    providers.clear_mutations()
    return examples


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
