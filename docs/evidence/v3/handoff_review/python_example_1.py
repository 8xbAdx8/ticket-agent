import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from data.seed import build_db
build_db()
from target import providers
from target.agent import Agent
providers.set_mutation("date_offset", 1)
agent = Agent(engine="legacy")
# 运行用例后恢复；已有会话可能已含错参数，重新建Agent
providers.clear_mutations()
agent = Agent(engine="legacy")
