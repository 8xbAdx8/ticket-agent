"""仅离线读取变异旁证；可合并B独立判定，不修改任何原始Trace。"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from target.fault_injection import summarize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces",nargs="+",type=Path)
    parser.add_argument("--assessments",type=Path,help="独立JSON：run_id→agent_defect_detected/agent_recovered布尔值")
    args=parser.parse_args()
    reports=[]
    for path in args.traces:
        reports.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if len({r["run_id"] for r in reports}) != len(reports):
        parser.error("输入包含重复run_id，请勿重复统计同一旁证")
    if args.assessments:
        assessments=json.loads(args.assessments.read_text(encoding="utf-8"))
        if not isinstance(assessments,dict) or set(assessments)-{r["run_id"] for r in reports}:
            parser.error("判定必须引用输入旁证中存在的run_id")
        for report in reports:
            values=assessments.get(report["run_id"],{})
            if not isinstance(values,dict) or set(values)-{"agent_defect_detected","agent_recovered"} or any(type(v) is not bool for v in values.values()):
                parser.error("判定仅支持两个字段和JSON布尔值")
            report["assessment"]={**report["assessment"],**values}
    print(json.dumps(summarize(reports),ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
