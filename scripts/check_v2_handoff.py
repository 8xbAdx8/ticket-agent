"""检查 V2 报告可再生成、实际 JSON、代码语法、Schema 名称和本机敏感路径。"""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from generate_v2_handoff import NAMES

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT/args.output
    if output.exists():
        raise FileExistsError("检查证据已存在，请换新文件")
    example = json.loads((ROOT/"docs/evidence/v2/api_example/results.json").read_text(encoding="utf-8"))[1]
    results = []
    with tempfile.TemporaryDirectory() as temp:
        generated = Path(temp)/"generated"
        subprocess.run([sys.executable, str(ROOT/"scripts/generate_v2_handoff.py"),
                        "--source-commit", args.source_commit, "--output-dir", str(generated)],
                       cwd=ROOT, check=True, capture_output=True)
        for name in NAMES:
            path = ROOT/"docs/handoff"/name
            body = path.read_text(encoding="utf-8")
            assert body == (generated/name).read_text(encoding="utf-8"), name+" 与生成器不一致"
            assert args.source_commit in body and "95/100" in body and "28" in body
            assert "待验证" in body or "未完成" in body
            assert not re.search(r"(?:[CD]:\\|Users\\|sk-[A-Za-z0-9]{16,}|Bearer\s+\S+)", body)
            assert not any(ord(c) < 32 and c not in "\t\r\n" for c in body)
            assert body.count("```") % 2 == 0
            blocks = re.findall(r"```python\n(.*?)\n```", body, re.S)
            for block in blocks:
                ast.parse(block)
            for block in re.findall(r"```json\n(.*?)\n```", body, re.S):
                assert json.loads(block) == example
            results.append({"file": path.relative_to(ROOT).as_posix(), "reproducible": True,
                            "python_blocks_syntax_valid": len(blocks), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"source_commit": args.source_commit, "reports": results,
              "actual_json_matches_api_example": True, "sensitive_local_paths_found": False,
              "scope": "文档一致性检查，不是功能测试或 B 评价"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "reports": len(results), "actual_json_matches": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
