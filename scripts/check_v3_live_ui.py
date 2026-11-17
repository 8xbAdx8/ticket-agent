"""检查当前源码、真实 UI 证据和保护文件一致性；不输出正式 B 评分。"""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/evidence/v3_live_ui"


def main():
    baseline = json.loads((ROOT/"docs/evidence/v3/v2_baseline/manifest.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in baseline["protected_sha256"].items())
    for tag, sha in baseline["tags"].items():
        assert subprocess.check_output(["git","rev-parse",tag+"^{commit}"],cwd=ROOT,text=True).strip()==sha
    assert subprocess.check_output(["git","rev-parse","handoff-a-langchain-v3-20261013^{commit}"],cwd=ROOT,text=True).strip()=="a4d6d62f88f796b39f4f27f239eaa6308d4143b2"
    assert not subprocess.check_output(["git","diff","--name-only","5b606203a06f8b600f90978a6a35f76b55db9355","--",
        "target","config.py","cli.py","docs/contract.md","requirements.txt","requirements-lock.txt","requirements-v3.txt","requirements-v3-lock.txt"],cwd=ROOT,text=True).strip()
    browser = EVIDENCE/"delivery_browser"
    source = json.loads((browser/"source_check.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in source["source_sha256"].items())
    report = json.loads((browser/"browser_check.json").read_text(encoding="utf-8"))
    assert report["status"]=="passed" and report["javascript_errors"]==0 and not report["mobile_horizontal_overflow"]
    lines = [json.loads(x) for x in (browser/"traces.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(lines)==5 and all(r["provider"]=="langchain_mock" for r in lines)
    assert json.loads((browser/"downloaded-trace.json").read_text(encoding="utf-8"))==lines[-1]
    assert [r["tool_sequence"] for r in lines]==[["query_tickets"],["query_tickets","lock_seat","create_order"],["search_policy"],["pay_order"],["pay_order"]]
    assert "Ran 67 tests" in (EVIDENCE/"complete_unit.txt").read_text(encoding="utf-8")
    assert "\nOK\n" in (EVIDENCE/"complete_unit.txt").read_text(encoding="utf-8")
    framework = json.loads((EVIDENCE/"complete_framework/verification.json").read_text(encoding="utf-8"))
    assert framework["api_turns"]==11 and len(framework["tools"])==8 and framework["web_apptest_passed"]
    pngs = list(browser.glob("*.png"))
    assert len(pngs)==6
    for p in pngs:
        with Image.open(p) as image:
            image.verify()
    for p in (ROOT/"docs/handoff/v3/V3真实前端使用说明.md",ROOT/"docs/v3_live_ui_development_log.md"):
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",p.read_text(encoding="utf-8")):
            if not target.startswith(("http:","https:")):
                assert (p.parent/target.split("#")[0]).resolve().exists(), target
    output = {"status":"passed","protected_original_files_unchanged":len(baseline["protected_sha256"]),
              "v1_v2_v3_tags_unchanged":True,"backend_and_contract_unchanged":True,
              "ui_source_matches_browser_capture":True,"a_unit_tests_passed":67,"actual_browser_mock_turns":5,
              "actual_screenshots":6,"markdown_links_exist":True,"real_model_tested":False,"formal_b_score_generated":False}
    (EVIDENCE/"delivery_check.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(output,ensure_ascii=False))


if __name__=="__main__":
    main()
