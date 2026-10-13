import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from data.seed import build_db
build_db()
from target.agent import Agent
Agent().chat("read-jsonl","查明天上海到杭州的高铁")
import json
from pathlib import Path
import config
records = [json.loads(line) for line in (config.TRACE_DIR / "traces.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
