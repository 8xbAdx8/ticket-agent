"""把已有真实 Mock 附件和源码摘录用于展示；不运行或改写原 Agent。"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/"docs/showcase/v3"


def snippet(path, name, owner=None):
    text = (ROOT/path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    scope = next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name==owner) if owner else tree
    node = next(n for n in ast.walk(scope) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
    lines = text.splitlines()
    return {"path":path,"line":node.lineno,"end":node.end_lineno,
            "code":"\n".join(lines[node.lineno-1:node.end_lineno])}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    traces = ROOT/"docs/evidence/v3/final_framework/api_results.json"
    events = ROOT/"docs/evidence/v3/final_framework/framework_events.json"
    records = json.loads(traces.read_text(encoding="utf-8"))
    event_records = json.loads(events.read_text(encoding="utf-8"))
    mapping = {"query":0,"order":5,"policy":4}
    scenes = {}
    for key,index in mapping.items():
        r = records[index]
        actual = [e for e in event_records[index]["events"] if e["event"]=="tool_end"]
        scenes[key] = {"trace":r,"tools":actual}
        assert r["tool_sequence"]==[e["tool"] for e in actual]
    codes = [
        {"title":"统一对话入口","purpose":"选择legacy或LangChain，保留B依赖的chat接口。",**snippet("target/agent.py","chat",owner="Agent")},
        {"title":"标准工具适配","purpose":"复用原工具Schema与dispatch，不重复实现数据库业务。",**snippet("target/langchain_agent.py","adapt_tool")},
        {"title":"真实工具轨迹","purpose":"独立授权后由框架执行工具，再记录参数、结果、耗时并返回ToolMessage。",**snippet("target/langchain_agent.py","wrap_tool_call")},
        {"title":"写操作授权","purpose":"当前用户原文、成功锁与订单引用决定是否放行，不只依赖模型Prompt。",**snippet("target/write_authorization.py","denial")},
    ]
    data = {"label":"界面设计稿 · 历史LangChain Mock数据 · 不连接Agent服务",
            "evidence_date":"2026-10-13","source_commit":"a4d6d62f88f796b39f4f27f239eaa6308d4143b2",
            "scenes":scenes,"code":codes,
            "evidence_sha256":{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (traces,events)}}
    text = json.dumps(data,ensure_ascii=False,indent=2)
    (OUT/"demo-data.js").write_text("window.TICKET_DEMO = "+text+";\n",encoding="utf-8")
    (OUT/"数据与源码索引.json").write_text(text,encoding="utf-8")
    print(json.dumps({"scenes":len(scenes),"code_excerpts":len(codes),"real_model_tested":False},ensure_ascii=False))


if __name__ == "__main__":
    main()
