"""生成后核对文档/源码/实际附件；执行B的Python示例，解析PowerShell，不改旧证据。"""
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,required=True)
    args = parser.parse_args()
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    out.mkdir(parents=True,exist_ok=False)
    baseline = json.loads((ROOT/"docs/evidence/v3/v2_baseline/manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((ROOT/"docs/evidence/v3/final_framework/verification.json").read_text(encoding="utf-8"))
    docs = sorted((ROOT/"docs/handoff/v3").glob("*.md"))
    assert len(docs)==5
    texts = {p.name:p.read_text(encoding="utf-8") for p in docs}
    for text in texts.values():
        assert "有条件交接" in text and "真实大模型尚未联网实测" in text
        assert str(ROOT) not in text and str(Path.home()) not in text
        assert not any(ord(c)<32 and c not in "\n\r\t" for c in text),"文档含转义控制字符"
    protected = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in baseline["protected_sha256"].items()}
    assert all(protected.values())
    for p,h in evidence["source_sha256"].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
    tags = {}
    for tag,h in baseline["tags"].items():
        tags[tag] = subprocess.check_output(["git","rev-parse",tag+"^{commit}"],cwd=ROOT,text=True).strip()
        assert tags[tag]==h
    for line in (ROOT/"requirements-v3-lock.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith("#"):
            name,version = line.split("==",1)
            assert importlib.metadata.version(name)==version,"依赖和冻结不一致: "+name
    powershell = []
    for name,text in [*texts.items(),("README.md",(ROOT/"README.md").read_text(encoding="utf-8"))]:
        powershell += [{"file":name,"code":block} for block in re.findall(r"```powershell\n(.*?)```",text,re.S)]
    ps_file = out/"powershell_blocks.json"
    ps_file.write_text(json.dumps(powershell,ensure_ascii=False,indent=2),encoding="utf-8")
    ps_script = r'''param([string]$Blocks)
$items = Get-Content -LiteralPath $Blocks -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $items) {
    $parseTokens = $null
    $parseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseInput($item.code, [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { throw "PowerShell parse error" }
}
Write-Output "PowerShell blocks parsed"
'''
    script = out/"parse_examples.ps1"
    script.write_text(ps_script,encoding="utf-8-sig")
    parsed = subprocess.run(["powershell","-NoProfile","-File",str(script),"-Blocks",str(ps_file)],
                            text=True,encoding="utf-8",capture_output=True)
    assert parsed.returncode==0,parsed.stderr
    btext = texts["B_V3测试对接手册.md"]
    blocks = re.findall(r"```python\n(.*?)```",btext,re.S)
    assert len(blocks)==3
    for block in blocks:
        ast.parse(block)
    example_runs=[]
    with tempfile.TemporaryDirectory() as tmp:
        for i,block in enumerate(blocks):
            script = out/f"python_example_{i}.py"
            prefix = "import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()))\nfrom data.seed import build_db\nbuild_db()\n"
            if i==2:
                prefix += 'from target.agent import Agent\nAgent().chat("read-jsonl","查明天上海到杭州的高铁")\n'
            script.write_text(prefix+block,encoding="utf-8")
            env = dict(os.environ,PYTHONIOENCODING="utf-8",AGENT_ENGINE="langchain",AGENT_PROVIDER="mock",AGENT_LC_TOOLSET="all",
                       AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",AGENT_DB_PATH=str(Path(tmp)/f"{i}.db"),
                       AGENT_TRACE_DIR=str(Path(tmp)/f"trace-{i}"))
            env.pop("AGENT_API_KEY",None)
            run = subprocess.run([sys.executable,str(script)],cwd=ROOT,env=env,text=True,encoding="utf-8",capture_output=True,timeout=30)
            assert run.returncode==0,"Python 文档示例失败"
            log=run.stdout+run.stderr
            for value in (str(ROOT),str(Path.home()),str(tmp),sys.base_prefix):
                log=log.replace(value,"<local-path>").replace(value.replace("\\","\\\\"),"<local-path>")
            (out/f"python_example_{i}.txt").write_text(log,encoding="utf-8")
            example_runs.append({"example":i,"exit_code":run.returncode})
    actual = json.loads((ROOT/"docs/evidence/v3/final_framework/api_results.json").read_text(encoding="utf-8"))[0]
    json_block = re.findall(r"```json\n(.*?)```",btext,re.S)
    assert len(json_block)==1 and json.loads(json_block[0])==actual
    assert "task_id" in btext and "monitor_id" not in btext
    # 生成后的源码清单可点击路径必须存在；脚本本身也属于此次交付。
    source_list = re.findall(r"^- `([^`]+\.py)`$",texts["A_V3开发完成报告.md"],re.M)
    assert source_list and all((ROOT/p).exists() for p in source_list)
    for p in source_list:
        ast.parse((ROOT/p).read_text(encoding="utf-8-sig"),filename=p)
    report={"status":"passed","reports_count":len(docs),"python_examples":example_runs,
            "powershell_blocks_parsed":len(powershell),"json_example_matches_actual":True,
            "source_matches_final_evidence":True,"protected_files":len(protected),"protected_unchanged":True,
            "lock_matches_environment":True,"python_source_syntax_checked":len(source_list),"original_tags":tags,"real_model_tested":False,
            "report_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in docs},
            "draft_review_correction":"核对后将候补返回名纠正为实际task_id；源码路径表按真实文件名修正"}
    (out/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","reports_count","powershell_blocks_parsed","protected_files")},ensure_ascii=False))


if __name__ == "__main__":
    main()
