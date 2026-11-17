"""运行 A 自测并保留新证据文件；拒绝覆盖已有日志。"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--pattern", default="test_v2_defects.py")
    args = parser.parse_args()
    target = ROOT/args.log
    if target.exists():
        raise FileExistsError("验证日志已存在，请指定新文件")
    command = [sys.executable,"-m","unittest","discover","-s","tests","-p",args.pattern,"-v"]
    result = subprocess.run(command,cwd=ROOT,text=True,encoding="utf-8",capture_output=True)
    text = result.stdout + result.stderr
    for path in (str(ROOT),str(Path.home()),sys.base_prefix):
        text = text.replace(path,"<local-path>")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(text,encoding="utf-8")
    print(json.dumps({"command":"python -m unittest discover -s tests -p "+args.pattern+" -v","exit_code":result.returncode,"log":args.log},ensure_ascii=False))
    if result.returncode:
        print(text)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
