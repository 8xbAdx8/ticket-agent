"""核对 DeepSeek 文档/源码/证据/基线，不进行任何网络请求。"""
import ast
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT/"docs/evidence/deepseek"
REPORTS = ["A_DeepSeek真实API接入报告.md","B_DeepSeek真实模型测试对接说明.md","C_DeepSeek真实模型演示说明.md",
           "Mock与DeepSeek真实模型对照.md","DeepSeek_API安全与费用记录.md"]


def main():
    baseline = json.loads((EVIDENCE/"baseline.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in baseline["protected_sha256"].items()),"接手时文件发生变化"
    for tag, sha in baseline["tags"].items():
        assert subprocess.check_output(["git","rev-parse",tag+"^{commit}"],cwd=ROOT,text=True).strip()==sha
    def pins(name):
        return dict(line.strip().split("==",1) for line in (ROOT/name).read_text(encoding="utf-8").splitlines() if "==" in line)
    old, new = pins("requirements-v3-lock.txt"),pins("requirements-deepseek-lock.txt")
    assert all(new.get(k)==v for k,v in old.items())
    assert set(new)-set(old)=={"langchain-deepseek"} and new["langchain-deepseek"]=="1.1.1"
    summary = json.loads((EVIDENCE/"handoff_summary.json").read_text(encoding="utf-8"))
    assert summary["tests"]=={"deepseek":{"total":88,"passed":88,"skipped":0},
                             "v3":{"total":88,"passed":78,"skipped":10},"v2":{"total":88,"passed":35,"skipped":53}}
    for name, skipped in (("final_unit.txt",0),("final_v3_compatibility.txt",10),("final_v2_compatibility.txt",53)):
        content = (EVIDENCE/name).read_text(encoding="utf-8")
        assert "Ran 88 tests" in content and re.search(r"^OK",content,re.M)
        if skipped:
            assert f"skipped={skipped}" in content
    online = json.loads((EVIDENCE/"missing_key_run/report.json").read_text(encoding="utf-8"))
    assert online["status"]=="skipped_missing_key" and online["online_generation_requests_this_run"]==0
    assert not online["real_api_verified"] and not online["function_calling_verified"]
    offline = json.loads((EVIDENCE/"offline_sdk/offline_evidence.json").read_text(encoding="utf-8"))
    assert offline["source"]=="offline_sdk_stub" and offline["remote_api_requests"]==0 and offline["stubbed_http_requests"]==4
    assert [r["contract"]["tool_sequence"] for r in offline["records"]]==[["query_tickets"],["search_policy"]]
    framework = json.loads((EVIDENCE/"mock_framework_fixed/verification.json").read_text(encoding="utf-8"))
    assert framework["protected_files_count"]==len(baseline["protected_sha256"]) and framework["protected_files_unchanged"]
    assert framework["api_turns"]==11 and len(framework["tools"])==8
    browser = EVIDENCE/"mock_browser_final"
    source = json.loads((browser/"source_check.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in source["source_sha256"].items())
    for image in browser.glob("*.png"):
        with Image.open(image) as picture:
            picture.verify()
    markdown_files = [ROOT/"docs/handoff/v3"/name for name in REPORTS]+[ROOT/"docs/deepseek_development_log.md"]
    blocks = []
    for path in markdown_files:
        content = path.read_text(encoding="utf-8")
        assert not any(ord(c)<32 and c not in "\n\r\t" for c in content),"文档有控制字符"
        assert summary["source_commit"] in content or path.name=="DeepSeek_API安全与费用记录.md"
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)",content):
            if not link.startswith(("https:","http:")):
                assert (path.parent/link.split("#")[0]).resolve().exists(),link
        for language,block in re.findall(r"```(\w+)\n(.*?)```",content,re.S):
            if language=="python":
                ast.parse(block)
            if language=="powershell":
                blocks.append(block)
    script_path = ROOT/"artifacts/runtime/deepseek-doc-check/blocks.json"
    script_path.parent.mkdir(parents=True,exist_ok=True)
    script_path.write_text(json.dumps(blocks,ensure_ascii=False),encoding="utf-8")
    command = r'''$blocks = Get-Content -LiteralPath artifacts/runtime/deepseek-doc-check/blocks.json -Raw -Encoding utf8 | ConvertFrom-Json
$count = 0
foreach ($block in $blocks) {
  $parseTokens = $null
  $parseErrors = $null
  [void][System.Management.Automation.Language.Parser]::ParseInput($block, [ref]$parseTokens, [ref]$parseErrors)
  if ($parseErrors.Count -gt 0) { exit 1 }
  $count++
}
Write-Output $count
'''
    parsed = subprocess.run(["powershell.exe","-NoProfile","-Command",command],cwd=ROOT,capture_output=True,text=True)
    assert parsed.returncode==0,"PowerShell 文档示例解析失败"
    for path in (ROOT/"target/deepseek_runtime.py",ROOT/"target/langchain_agent.py",ROOT/"scripts/check_deepseek_api.py",
                 ROOT/"scripts/verify_deepseek_offline.py",ROOT/"scripts/generate_deepseek_handoff.py"):
        ast.parse(path.read_text(encoding="utf-8-sig"))
    secret = os.getenv("DEEPSEEK_API_KEY","")
    for path in list(EVIDENCE.rglob("*.json"))+list(EVIDENCE.rglob("*.jsonl"))+markdown_files:
        content = path.read_text(encoding="utf-8")
        assert not secret or secret not in content,"交付物含当前密钥"
        assert not re.search(r'"Authorization"\s*:',content),"交付物含认证请求头"
        assert not re.search(r'"reasoning_content"\s*:',content),"交付物含推理字段"
        assert not re.search(r'sk-[A-Za-z0-9_-]{20,}',content),"疑似硬编码令牌"
    result = {"status":"passed","source_commit":summary["source_commit"],"reports":REPORTS,
              "protected_files_unchanged":len(baseline["protected_sha256"]),"tags_unchanged":True,
              "old_dependency_pins_preserved":True,"only_added_dependency":"langchain-deepseek==1.1.1",
              "normal_agent_contract_unchanged":True,"powershell_blocks_parsed":int(parsed.stdout.strip()),
              "python_examples_parsed":True,"report_links_exist":True,"real_generation_requests":0,
              "live_api_verified":False,"secrets_and_reasoning_fields_absent":True}
    (EVIDENCE/"delivery_check.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
