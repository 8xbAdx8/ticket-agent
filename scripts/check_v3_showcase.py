"""检查展示材料、源码摘录、图片和V3基线一致性，不生成正式测试成绩。"""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT/"docs/showcase/v3"


def main():
    data = json.loads((FOLDER/"数据与源码索引.json").read_text(encoding="utf-8"))
    assert data["code"][0]["line"]==61,"必须摘录Agent.chat而不是模块级同名包装函数"
    for item in data["code"]:
        lines = (ROOT/item["path"]).read_text(encoding="utf-8").splitlines()
        assert item["code"]=="\n".join(lines[item["line"]-1:item["end"]])
        ast.parse(item["code"].lstrip())
    for p,h in data["evidence_sha256"].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
    browser = json.loads((FOLDER/"效果图验证.json").read_text(encoding="utf-8"))
    actual = json.loads((FOLDER/"真实截图/实际Mock运行.json").read_text(encoding="utf-8"))
    assert browser["status"]=="passed" and browser["javascript_errors"]==0 and browser["external_requests"]==0
    assert len(actual)==3 and [r["tool_sequence"] for r in actual]==[["query_tickets"],["query_tickets","lock_seat","create_order"],["search_policy"]]
    assert all(r["provider"]=="langchain_mock" for r in actual)
    pngs = sorted(FOLDER.rglob("*.png"))
    assert len(pngs)==9
    dimensions = {}
    for p in pngs:
        with Image.open(p) as picture:
            dimensions[p.relative_to(FOLDER).as_posix()]=list(picture.size)
            picture.verify()
    for p in FOLDER.glob("*.md"):
        for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)",p.read_text(encoding="utf-8")):
            if not link.startswith(("http:","https:")):
                assert (p.parent/link.split("#")[0]).resolve().exists(),"文档链接不存在: "+link
    baseline = json.loads((ROOT/"docs/evidence/v3/v2_baseline/manifest.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in baseline["protected_sha256"].items())
    for tag,sha in baseline["tags"].items():
        assert subprocess.check_output(["git","rev-parse",tag+"^{commit}"],cwd=ROOT,text=True).strip()==sha
    assert not subprocess.check_output(["git","diff","--name-only",data["source_commit"],"--","target","web","config.py","cli.py","docs/contract.md","requirements-lock.txt"],cwd=ROOT,text=True).strip()
    for p in (ROOT/"scripts").glob("*v3*showcase*.py"):
        ast.parse(p.read_text(encoding="utf-8"))
    report = {"status":"passed","design_png_count":6,"actual_mock_png_count":3,"code_excerpts_match_source":4,
              "excerpt_agent_chat_line":61,"image_dimensions":dimensions,"markdown_links_exist":True,
              "protected_original_files_unchanged":len(baseline["protected_sha256"]),"agent_source_unchanged":True,
              "v1_v2_tags_unchanged":True,"real_model_tested":False,"formal_b_score_generated":False}
    (FOLDER/"材料核对结果.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","design_png_count","actual_mock_png_count","protected_original_files_unchanged")},ensure_ascii=False))


if __name__ == "__main__":
    main()
