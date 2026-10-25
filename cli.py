# -*- coding: utf-8 -*-
"""命令行入口（CLI）：跑对话、跑批量用例、看 trace。

用法：
    python cli.py chat                      交互式对话（直接打字）
    python cli.py once "帮我查下周三北京到上海的高铁"
    python cli.py batch cases/demo.json     批量执行并打印工具序列
    python cli.py trace                     打印最近一条 trace
"""
import json
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target.agent import Agent
import config


def make_agent(args):
    return Agent(mutations=json.loads(args.mutations) if args.mutations is not None else None)


def print_faults(agent):
    if agent.last_fault_report:
        print("[fault injection] " + json.dumps(agent.last_fault_report,ensure_ascii=False))


def capability_notice():
    return ("全工具模拟沙箱：仅允许独立本地库中的明确授权操作。" if os.getenv("DEEPSEEK_LIVE_TEST_PROFILE") == "full_sandbox"
            else "当前仅支持模拟查票和政策咨询。")


def print_result(r, show_trace=True):
    print(f"[engine] {config.ENGINE}  [provider] {r['provider']}")
    if r["provider"] == "deepseek_live":
        from target.deepseek_runtime import VALIDATION_NOTICE
        print("[validation] " + VALIDATION_NOTICE)
        print("[capability] " + capability_notice())
        print(f"[model] {r['model']}  [tokens reported by API] {json.dumps(r['tokens'])}")
    print(f"\n[reply] {r['reply']}")
    if show_trace:
        print(f"[tools] {r['tool_sequence']}")
        for s in r["steps"]:
            for c in s["calls"]:
                flag = "OK " if c["ok"] else "ERR"
                print(f"  step{s['step']} {flag} {c['tool']}({json.dumps(c['args'], ensure_ascii=False)}) "
                      f"{c['latency_ms']}ms")
        print(f"[finish] {r['finish_reason']}  {r['total_latency_ms']}ms")


def cmd_chat(args):
    agent = make_agent(args)
    sid = "cli"
    print(f"出行服务智能助手（{config.PROVIDER} 模式，虚构票务，输入 q 退出）")
    if config.PROVIDER == "deepseek":
        from target.deepseek_runtime import VALIDATION_NOTICE
        print(VALIDATION_NOTICE + capability_notice())
    while True:
        try:
            msg = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in ("q", "quit", "exit"):
            break
        if not msg:
            continue
        print_result(agent.chat(sid, msg), show_trace=not args.quiet)
        print_faults(agent)


def cmd_once(args):
    agent = make_agent(args)
    print_result(agent.chat("once", args.text), show_trace=not args.quiet)
    print_faults(agent)


def cmd_batch(args):
    cases = json.loads(Path(args.file).read_text(encoding="utf-8"))
    agent = make_agent(args)
    for c in cases:
        r = agent.chat(c.get("session_id", "batch"), c["input"])
        print(f"\n== {c.get('id','')} {c['input']}")
        print(f"   tools: {r['tool_sequence']}  finish: {r['finish_reason']}")
        print(f"   reply: {r['reply'][:120]}")
        print_faults(agent)


def cmd_trace(args):
    p = config.TRACE_DIR / "traces.jsonl"
    if not p.exists():
        print("还没有 trace 记录，先跑一次对话。")
        return
    lines = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            print(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
            return
        except json.JSONDecodeError:
            continue
    print("没有完整 JSON 记录，请检查 trace 文件。")


def main():
    ap = argparse.ArgumentParser(description="抢票智能体 CLI")
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("chat"); p1.add_argument("--quiet", action="store_true"); p1.set_defaults(func=cmd_chat)
    p2 = sub.add_parser("once"); p2.add_argument("text"); p2.add_argument("--quiet", action="store_true"); p2.set_defaults(func=cmd_once)
    p3 = sub.add_parser("batch"); p3.add_argument("file"); p3.set_defaults(func=cmd_batch)
    p4 = sub.add_parser("trace"); p4.set_defaults(func=cmd_trace)
    for parser in (p1,p2,p3):
        parser.add_argument("--mutations",help='显式JSON对象，如 {"date_offset":1}；默认关闭')
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help(); return
    try:
        args.func(args)
    except Exception as exc:
        if config.PROVIDER not in ("deepseek", "bailian"):
            raise
        from target.deepseek_runtime import safe_error
        error = safe_error(exc)
        from target.reply_consistency import failure_notice
        note=failure_notice(error["category"]) or "本轮未返回正常契约记录；未自动重试。"
        print(json.dumps({"provider":config.PROVIDER+"_live","status":"failed","error":error,
                          "tokens":None,"note":note+" 检查 provider_runs.jsonl 的原 model_final 与字段证据；错误后会话记忆清空，重新查询须提供完整条件。"},ensure_ascii=False))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
