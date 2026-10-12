"""成员 A 对 B 报告五个输入的可复现观察，不代替 B 的正式判定器。"""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from datetime import date, datetime
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from data.seed import build_db
from target.agent import Agent
from target.providers import MockProvider

SCENARIOS = {
    "DEF-01": ("F03", ["帮我查明天北京到成都的高铁", "那机票呢"]),
    "DEF-02": ("M11", ["帮我查明天上海到杭州的高铁", "那机票呢", "还是高铁吧"]),
    "DEF-03": ("F14", ["帮我查明天北京到上海的高铁二等座"]),
    "DEF-04": ("F13", ["帮我查明天上海到杭州的高铁", "我要买一张", "支付", "支付"]),
    "DEF-05": ("T25", ["锁座后必须在多久内完成支付"]),
}


def observes_fixed(defect, results):
    result = results[-1]
    args = [c["args"] for s in result["steps"] for c in s["calls"] if c["tool"] == "query_tickets"]
    if defect == "DEF-01":
        return bool(args and args[-1].get("kind") == "机票" and args[-1].get("seat_type") == "经济舱")
    if defect == "DEF-02":
        return bool(args and args[-1].get("kind") == "高铁" and args[-1].get("seat_type") == "二等座")
    if defect == "DEF-03":
        return "售罄" in result["reply"] and "一等座" in result["reply"]
    if defect == "DEF-04":
        return "已支付" in result["reply"] and "没有重复扣款" in result["reply"]
    return result["tool_sequence"] == ["search_policy"] and "P11" in result["reply"]


def run(out, label):
    out = Path(out)
    if out.exists():
        raise FileExistsError("证据目录已存在；使用新的 --output-dir，不能覆盖历史")
    out.mkdir(parents=True)
    old_db, old_trace = config.DB_PATH, config.TRACE_DIR
    observations = []
    try:
        with patch("config.today", return_value=date(2026, 10, 13)), patch("config.now", return_value=datetime(2026, 10, 13, 10, 0)), tempfile.TemporaryDirectory() as temp:
            for defect, (case_id, inputs) in SCENARIOS.items():
                config.DB_PATH = Path(temp)/f"{defect}.db"
                config.TRACE_DIR = out/defect
                build_db()
                agent = Agent(MockProvider(mutations={}))
                results = [agent.chat(defect, message) for message in inputs]
                observations.append({"defect":defect, "b_case_id":case_id, "inputs":inputs,
                                     "a_observed_target_satisfied":observes_fixed(defect, results), "results":results,
                                     "trace_path":f"{defect}/traces.jsonl"})
    finally:
        config.DB_PATH, config.TRACE_DIR = old_db, old_trace
    summary = {"label":label, "scope":"A implementation reproduction, not B official rerun", "provider":"mock",
               "frozen_business_date":"2026-10-13", "observations":observations,
               "providers_sha256":hashlib.sha256((config.BASE_DIR/"target/providers.py").read_bytes()).hexdigest()}
    (out/"observations.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"label":label,"a_targets_satisfied":sum(o["a_observed_target_satisfied"] for o in observations),"observed_defects":len(observations)},ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    run(args.output_dir, args.label)
