"""创建全工具Live故障测试的全新隔离库；不读取Key、不发送API、不覆盖目录。"""
import argparse
import json
import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from data.seed import build_db


def create_sandbox(path=None):
    base=(ROOT/"artifacts/runtime").resolve()
    target=Path(path).resolve() if path else base/("v31-sandbox-"+uuid.uuid4().hex[:10])
    if not target.is_relative_to(base) or target == base:
        raise ValueError("沙箱必须位于项目artifacts/runtime的独立子目录")
    target.mkdir(parents=True,exist_ok=False)
    build_db(target/"tickets.db")
    (target/".ticket-agent-sandbox.json").write_text(json.dumps(
        {"purpose":"ticket-agent-fault-test","version":1,"simulated_only":True}),encoding="utf-8")
    return target


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir",type=Path)
    print(create_sandbox(parser.parse_args().dir))
