import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from data.seed import build_db
build_db()
from target.agent import Agent
agent = Agent()
result = agent.chat("B-case-001", "订明天上海到杭州的高铁")
print(result["tool_sequence"])
result = agent.chat("B-case-001", "支付我刚才的订单。")
agent.reset("B-case-001")
