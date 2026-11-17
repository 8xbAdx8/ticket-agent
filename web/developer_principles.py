# -*- coding: utf-8 -*-
"""开发者工作台 · Agent 设计原理介绍页（B 端独占，纯静态只读）。

本页只介绍「我们怎么把这个 Agent 设计出来」：思路理论、提示词设计内容、
工具与内核源码。不连接任何会话、不读运行记录、不展示测试结果或成绩
（那些属于测试控制台）。所有代码块在渲染时按符号名从真实源码读取，
保证页面展示与仓库实现一致，不手写副本、不编造。
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import streamlit as st

from target.agent import SYSTEM_PROMPT
from target.tools import TOOLS
from target.write_authorization import WRITE_TOOLS
from web.design import escape

ROOT = Path(__file__).resolve().parent.parent

# 七个模块各一色，同一板块内色调相近
PALETTE = {
    1: ("#4f46e5", "#eef2ff"),
    2: ("#2563eb", "#eff6ff"),
    3: ("#0891b2", "#ecfeff"),
    4: ("#059669", "#ecfdf5"),
    5: ("#0d9488", "#f0fdfa"),
    6: ("#d97706", "#fffbeb"),
    7: ("#e11d48", "#fff1f2"),
}

ORDER = [
    (1, "思考分析"), (2, "提示词"), (3, "工具配置"), (4, "知识库"),
    (5, "记忆多轮"), (6, "工作流"), (7, "边界风控"),
]

SECTIONS = [
    ("I", "决策内核", "模块 1–3 · Agent 怎么想、被什么约束、怎么动手", "#4f46e5", (1, 3)),
    ("II", "认知支撑", "模块 4–5 · 知识从哪来、跨轮状态怎么留", "#059669", (4, 5)),
    ("III", "运行保障", "模块 6–7 · 一次请求怎么编排、哪些红线不能碰", "#d97706", (6, 7)),
]


# ---------------------------------------------------------------- UI 基础件

def chain_bar():
    cards = []
    for number, name in ORDER:
        color, tint = PALETTE[number]
        cards.append(
            f'<div style="border:1px solid {color}55;border-top:3px solid {color};'
            f'background:{tint};border-radius:8px;padding:9px 6px;text-align:center;">'
            f'<div style="color:{color};font-size:17px;font-weight:800;line-height:1;">{number}</div>'
            f'<div style="color:#334155;font-size:12px;font-weight:600;margin-top:5px;">{name}</div></div>')
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin:6px 0 4px 0;">'
        + "".join(cards) + '</div>', unsafe_allow_html=True)
    st.caption("阅读顺序 ① → ⑦：先讲决策，再讲知识，最后讲编排与安全边界。本页只讲设计，不显示任何运行结果。")


def section_head(roman, name, note, color):
    st.markdown(
        f'<div style="border-left:4px solid {color};'
        f'background:linear-gradient(90deg,{color}18,rgba(255,255,255,0));'
        f'border-radius:8px;padding:10px 14px;margin:24px 0 10px 0;">'
        f'<b style="color:{color};font-size:15px;">板块 {roman} · {name}</b>'
        f'<span style="color:#64748b;font-size:12px;margin-left:12px;">{note}</span></div>',
        unsafe_allow_html=True)


def card_head(number, title, lead):
    color, tint = PALETTE[number]
    st.markdown(
        f'<div style="border-left:4px solid {color};background:linear-gradient(90deg,{tint},#ffffff);'
        f'border-radius:8px;padding:9px 14px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<span style="display:inline-flex;width:26px;height:26px;border-radius:7px;'
        f'background:{color};color:#fff;font-weight:700;font-size:13px;'
        f'align-items:center;justify-content:center;">{number}</span>'
        f'<b style="color:#111827;font-size:16px;">{escape(title)}</b></div>'
        f'<div style="color:#475569;font-size:12.5px;line-height:1.55;margin-top:6px;">{escape(lead)}</div>'
        '</div>', unsafe_allow_html=True)


def label(text, number):
    color = PALETTE[number][0]
    st.markdown(
        f'<span style="display:inline-block;background:{color}18;color:{color};'
        f'border:1px solid {color}44;border-radius:6px;padding:2px 9px;'
        f'font-size:12px;font-weight:700;margin:12px 0 2px 0;">{escape(text)}</span>',
        unsafe_allow_html=True)


def flow(steps, number):
    color = PALETTE[number][0]
    parts = []
    for index, step in enumerate(steps):
        parts.append(
            f'<div style="flex:1;min-width:0;padding:8px 8px;border:1px solid {color}55;'
            f'background:{color}0d;border-radius:8px;text-align:center;'
            f'font-size:12px;font-weight:600;color:#1f2937;">{escape(step)}</div>')
        if index < len(steps) - 1:
            parts.append(f'<div style="align-self:center;color:{color};font-size:15px;">→</div>')
    st.markdown('<div style="display:flex;gap:5px;align-items:stretch;margin:8px 0 10px 0;">'
                + "".join(parts) + '</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- 真实源码展示

def _find_symbol(tree, symbol):
    if "." in symbol:
        cls, name = symbol.split(".", 1)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
                        return child
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
            return node
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == symbol for target in node.targets):
            return node
    return None


def source(rel, symbol=None, *, first=None, last=None, max_lines=None,
           caption=None, expanded=True, language="python"):
    """Render a real code block, located by symbol name instead of hardcoded lines."""
    path = ROOT / rel
    try:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if symbol:
            node = _find_symbol(ast.parse(text), symbol)
            if node is None:
                st.caption(f"源码符号未找到：{rel} · {symbol}")
                return
            chunk = lines[node.lineno - 1:node.end_lineno]
        else:
            chunk = lines[(first or 1) - 1:(last or len(lines))]
        omitted = 0
        if max_lines and len(chunk) > max_lines:
            omitted = len(chunk) - max_lines
            chunk = chunk[:max_lines]
        code = "\n".join(chunk)
        if omitted:
            code += f"\n\n# … 其余 {omitted} 行省略；完整实现见 {rel}"
    except (OSError, SyntaxError) as exc:
        st.caption(f"源码读取失败：{rel}（{type(exc).__name__}）")
        return
    head = caption or f"{rel} · {symbol or f'{first}–{last} 行'}"
    if expanded:
        st.caption("源码 · " + head)
        st.code(code, language=language)
    else:
        with st.expander("源码 · " + head, expanded=False):
            st.code(code, language=language)


def policy_docs():
    try:
        text = (ROOT / "data/policies.md").read_text(encoding="utf-8")
        return re.findall(r"(?m)^##\s*\[([^\]]+)\]\s*(.+)$", text)
    except OSError:
        return []


# ---------------------------------------------------------------- 七个模块

def _m1():
    card_head(1, "Agent 思考分析思路原理",
              "讲清一句话如何变成一次工具决策。这里只讲可观测的决策依据与思路，不叙述、不推测模型内部思维链——不可核验的「AI 在想什么」本身就是一种断言。")
    label("思路 / 原理", 1)
    flow(["输入归一", "意图判定", "工具提议", "结果回灌", "回复 / 澄清"], 1)
    st.markdown(
        "1. **输入归一** — 相对时间先换算成 `YYYY-MM-DD`、城市先解析成 `stop_id`；同名站返回候选让用户选，不猜测。\n"
        "2. **意图判定** — 两条路径共用一套工具声明：离线 Legacy Mock 由 `target/v39/planner.py` 的正则规则决定调哪个工具；在线 Live 由模型按 function calling Schema 选工具。\n"
        "3. **结果回灌** — 工具结果作为 `role=tool` 消息进入下一轮，Agent 据此继续提议工具或收敛为回复；`tool_calls=[]` 即本轮结束。\n"
        "4. **结束判定** — `finish_reason`、`tool_sequence`、确定性断言是三类可观测信号；语义理解未验证时保持 `indeterminate`，不写成通过。")
    st.caption("设计取舍：把「思维链路」做成可观测的阶段与事件，而不是拟人化叙述；这样测试才能按「卡在哪一步」设计用例。")
    label("源码 / 两条决策路径", 1)
    source("target/v39/planner.py", "RailwayDemoProvider.chat", max_lines=28,
           caption="离线规则路由：相对时间归一 → 意图匹配 → 提议工具")
    source("target/agent.py", "Agent.chat", max_lines=22, expanded=False,
           caption="在线主循环入口")


def _m2():
    card_head(2, "提示词设计",
              "把真实的基础提示词完整摆出来：四层结构、13 条硬规则按风险归类、只读模式提示词，以及用 SHA-256 锁版本的做法。")
    label("设计内容 / 四层结构", 2)
    st.markdown(
        "① **身份与业务范围** — 出行服务助手，限定在查票 / 下单 / 退改签 / 政策咨询。\n"
        "② **13 条硬规则** — 每条都能落到具体工具调用或断言，不写「要准确」这类无法验证的要求。\n"
        "③ **工具与参数约束** — 由 `target/tools.py` 的 Schema 声明，模型与测试共用同一份定义。\n"
        "④ **运行时注入** — 每轮追加当前日期与上下文；所以下面展示的是「基础提示词」，不是当轮完整 Prompt。")
    label("设计内容 / 13 条规则按风险归类", 2)
    groups = [
        ("防编造", "#4f46e5", "1 / 5 / 7 / 10", "具体车次余票必须调工具、余票 0 只能候补、不知道就说不知道、区分售罄与无班次"),
        ("参数正确性", "#2563eb", "2 / 9", "相对时间先换算 YYYY-MM-DD；高铁只用二等/一等/商务，机票只用经济/公务"),
        ("引用可核验", "#0891b2", "3 / 12", "政策问题调 search_policy 并注明 doc_id；锁座支付时效属政策咨询"),
        ("交易安全", "#d97706", "4 / 11 / 13", "下单前先 lock_seat；重复支付明确告知；疑问或否定语句不触发写操作"),
        ("多轮沿用", "#059669", "8", "未指定方式/日期/路线时沿用已知上下文，含糊时澄清"),
        ("隐私", "#e11d48", "6", "不得查询或泄露其他用户的订单信息"),
    ]
    columns = st.columns(2)
    for index, (name, color, rules, note) in enumerate(groups):
        with columns[index % 2]:
            st.markdown(
                f'<div style="border:1px solid {color}44;border-left:3px solid {color};'
                f'background:{color}0d;border-radius:7px;padding:7px 10px;margin:4px 0;">'
                f'<b style="color:{color};font-size:12.5px;">{name}</b>'
                f'<span style="color:#64748b;font-size:11.5px;margin-left:8px;">规则 {rules}</span>'
                f'<div style="color:#475569;font-size:12px;line-height:1.5;margin-top:4px;">{note}</div></div>',
                unsafe_allow_html=True)
    label("设计内容 / 基础提示词原文", 2)
    st.caption(f"来源 `target/agent.py::SYSTEM_PROMPT` · 共 13 条规则 · SHA-256 "
               f"`{hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest()}`")
    st.code(SYSTEM_PROMPT, language=None)
    st.caption("哈希用于锁定版本：改动一个字哈希就变，历史测试结论只对同一哈希有意义。")
    source("target/deepseek_runtime.py", "READ_ONLY_PROMPT", max_lines=30, expanded=False,
           caption="在线只读 Live 模式使用的另一份提示词")


def _m3():
    card_head(3, "工具配置与原理",
              "Schema、参数校验、写操作权限、分发执行、结果回传集中在这一块；直接摆出真实源码与全部工具定义。")
    label("思路 / 调用链", 3)
    flow(["Schema 声明", "参数校验", "权限判定", "dispatch 执行", "tool_result 回传"], 3)
    st.markdown(
        "1. **声明** — `target/tools.py` 用 function calling Schema 定义 "
        f"{len(TOOLS)} 个工具；`description` 说明何时调用，`required` 定最小参数，`enum` 约束席别与交通方式。\n"
        "2. **校验** — `validate()` 检查必填与类型；`write_authorization` 判断写操作需要确认还是直接拒绝。\n"
        "3. **执行** — `dispatch()` 走本地模拟或静态库查询，结果带 `status / duration_ms` 写入 `run_events.jsonl`。\n"
        "4. **不等于业务成功** — 工具回 succeeded 还要看页面操作回执与 SQLite 核验；失败返回结构化状态，Agent 不补造余票或订单。")
    label("源码 / 校验与分发", 3)
    source("target/tools.py", "TOOLS", max_lines=24,
           caption="TOOLS 声明（节选 query_tickets：description / required / enum）")
    source("target/tools.py", "validate", max_lines=40,
           caption="参数校验")
    source("target/tools.py", "dispatch", max_lines=32, expanded=False,
           caption="工具分发")
    label(f"设计内容 / 全部 {len(TOOLS)} 个工具定义", 3)
    for entry in TOOLS:
        spec = entry["function"]
        is_write = spec["name"] in WRITE_TOOLS
        tag = "写操作 · 需页面确认" if is_write else "查询"
        with st.expander(f"{spec['name']} · {tag}", expanded=False):
            st.caption(spec.get("description", ""))
            st.json(spec["parameters"])
    st.caption(f"依据 `target/tools.py::TOOLS` 与 `target/write_authorization.py::WRITE_TOOLS`（{len(WRITE_TOOLS)} 个写工具）。"
               "Schema 是模型选工具和测试判参数的共同依据，不是功能名翻译。")


def _m4():
    card_head(4, "Agent 知识库原理",
              "政策知识怎么切块、检索、注入、被引用校验；把「回答是否靠谱」变成可判定的引用问题。车次数据血缘由用户端产出，本模块只讲 Agent 的知识机制。")
    label("思路 / 检索链路", 4)
    flow(["政策语料切块", "关键词 / 向量检索", "质量过滤与投影", "注入上下文", "引用 doc_id 校验"], 4)
    st.markdown(
        "1. **语料** — `data/policies.md` 按 `## [doc_id] 标题` 切块，每块带稳定 `doc_id` 与版本；回答引用的是块，不是整篇文档。\n"
        "2. **检索** — 政策类提问触发 `search_policy(question)`；离线包默认关键词检索，向量依赖不可用时降级，不联网。\n"
        "3. **引用** — 提示词第 3 / 12 条要求回答注明 `doc_id`；`citation_check()` 把回答里的引用与命中集合比对，越界引用直接标出。\n"
        "4. **边界** — `citation_check()` 只校验 doc_id 归属，`citation_support` 仍为 `indeterminate`；引用存在不等于引用内容支持了每条结论。")
    label("设计内容 / 政策语料清单", 4)
    docs = policy_docs()
    if docs:
        columns = st.columns(3)
        for index, (doc_id, title) in enumerate(docs):
            with columns[index % 3]:
                st.markdown(
                    f'<div style="border:1px solid #a7f3d0;background:#f0fdf4;border-radius:6px;'
                    f'padding:5px 8px;margin:3px 0;font-size:12px;color:#065f46;">'
                    f'<b>{escape(doc_id)}</b> {escape(title.strip())}</div>', unsafe_allow_html=True)
        st.caption(f"共 {len(docs)} 个政策块，来自 `data/policies.md`。")
    else:
        st.caption("政策语料文件未读取到。")
    label("源码 / 切块、检索与引用校验", 4)
    source("target/rag.py", "load_chunks", max_lines=18,
           caption="按 doc_id 切块")
    source("target/rag.py", "keyword_search", max_lines=22, expanded=False,
           caption="离线关键词检索")
    source("target/rag.py", "search_policy", max_lines=26, expanded=False,
           caption="统一检索入口与事件记录")
    source("target/rag_service.py", "citation_check", max_lines=12,
           caption="引用归属校验")
    st.caption("待补：车次数据来源（静态 GTFS / 模拟余票 / 本地快照）的血缘说明由用户工作空间产出，到位后接入本模块；本期不编造该数据。")


def _m5():
    card_head(5, "记忆存储 / 多轮交互能力",
              "四类状态各自存什么、跨轮沿用与重置的边界、以及为什么上一轮的授权不能拿到这一轮用。")
    label("思路 / 四类状态", 5)
    items = [
        ("对话历史", "#0d9488", "session.history", "每轮用户输入与回复，按会话归属"),
        ("工具结果", "#0891b2", "session.results", "每轮工具返回值，供下一轮决策回灌"),
        ("运行审计", "#4f46e5", "session.audits", "每次运行的 audit 报告，与对话轮一一对应"),
        ("待确认提案", "#d97706", "pending_actions / followups", "页面确认卡与追问，绑定 run_id 与配置哈希"),
    ]
    columns = st.columns(2)
    for index, (name, color, field, note) in enumerate(items):
        with columns[index % 2]:
            st.markdown(
                f'<div style="border:1px solid {color}44;border-left:3px solid {color};'
                f'background:{color}0d;border-radius:7px;padding:7px 10px;margin:4px 0;">'
                f'<b style="color:{color};font-size:12.5px;">{name}</b>'
                f'<code style="color:#475569;font-size:11.5px;margin-left:8px;">{field}</code>'
                f'<div style="color:#475569;font-size:12px;margin-top:4px;">{note}</div></div>',
                unsafe_allow_html=True)
    st.markdown(
        "**沿用与重置**：提示词规则 8 要求未指定日期 / 路线 / 交通方式时沿用已知上下文；规则 9 要求明确切换高铁 / 机票时重置不兼容席别。"
        "多轮不是「记住所有话」，而是有边界的条件继承。\n\n"
        "**安全设计**：`multiturn_selection()` 只从用户自己说过的话里恢复选择，疑问、假设、否定、带引号的语句一律不提供授权；"
        "Assistant 的输出永远不能补充乘客或授权。历史回放只读，不恢复旧确认。")
    label("设计内容 / 规则 8、9 原文", 5)
    lines = [line for line in SYSTEM_PROMPT.splitlines() if line.startswith(("8.", "9."))]
    st.code("\n".join(lines), language=None)
    label("源码 / 沿用条件与确认隔离", 5)
    source("target/write_authorization.py", "multiturn_selection", max_lines=24,
           caption="跨轮选择的安全过滤")
    source("web/runtime.py", "Conversation.pending_action", max_lines=8, expanded=False,
           caption="提案只从引擎的 pending_actions 取")
    source("web/runtime.py", "Conversation.confirm_action", max_lines=14, expanded=False,
           caption="没有提案就报错，绝不隐式执行")


def _m6():
    card_head(6, "工作流编排",
              "一次请求被拆成 6 个可观测阶段，事件按 run_id 落盘；缺阶段只能记为「未记录」，不能补成「已通过」。")
    label("思路 / 六阶段状态机", 6)
    flow(["用户输入", "模型 / 规则选工具", "RAG 检索", "工具与权限", "用户确认", "回复与结束"], 6)
    st.markdown(
        "1. **阶段划分** — `web/run_view.py::EXECUTION_STAGES` 把 `event_type` 归到六个阶段；阶段序列就是思维链路的可观测投影。\n"
        "2. **事件落盘** — `target/run_events.py` 的 `bind()` / `emit()` / `finish()` 在入口、每一步、结束时写 `run_events.jsonl`，带 `event_id / parent_event_id / sequence / run_id`。\n"
        "3. **运行隔离** — 读取时只取 run_id 与会话都匹配的行；不同运行、调试运行的事件永不混在一起。\n"
        "4. **缺失语义** — 只有带 `coverage_version=p1/1` 的完整插桩运行才允许把空阶段判为「未发生」，否则一律「未记录」。")
    label("源码 / 阶段定义与事件写入", 6)
    source("web/run_view.py", "EXECUTION_STAGES", max_lines=10,
           caption="阶段 → event_type 映射常量")
    source("target/run_events.py", "bind", max_lines=16, expanded=False,
           caption="绑定 run_id 并写入入口事件")
    source("target/run_events.py", "finish", max_lines=8, expanded=False,
           caption="结束事件带插桩版本，决定是否允许判「未发生」")
    source("target/run_events.py", "emit", max_lines=24, expanded=False,
           caption="事件字段与链路 id")


def _m7():
    card_head(7, "Agent 边界 / 风险控制",
              "写操作白名单、页面确认、隐私、证据库不可变、无密钥离线——每一条都有对应代码，不是口头承诺。")
    label("设计内容 / 六条硬边界", 7)
    items = [
        ("#e11d48", "写操作白名单", f"WRITE_TOOLS 单独归类 {len(WRITE_TOOLS)} 个写工具，其余只查询；Override 只能收紧，不能授予新工具"),
        ("#d97706", "人机确认", "模型只提出提案，页面生成确认卡；没有提案时 confirm_action 直接抛错，不隐式执行"),
        ("#4f46e5", "隐私", "提示词规则 6 禁止查询或泄露他人订单；query_order 不传 phone 时只返回当前用户订单"),
        ("#0891b2", "证据库不可变", "静态 GTFS 库整库 SHA256 强校验，不符抛 STATIC_DATA_IDENTITY_MISMATCH；不裁表、不 VACUUM、不重建"),
        ("#059669", "无密钥离线", "离线启动清除所有 *_API_KEY / *_TOKEN 并强制 TICKET_WEB_OFFLINE_ONLY=1，交付包不含密钥"),
        ("#2563eb", "失败不编造", "工具失败返回结构化状态，Agent 不补造余票或订单；确定性断言未验证保持 indeterminate"),
    ]
    columns = st.columns(2)
    for index, (color, name, note) in enumerate(items):
        with columns[index % 2]:
            st.markdown(
                f'<div style="border:1px solid {color}44;border-left:3px solid {color};'
                f'background:{color}0d;border-radius:7px;padding:7px 10px;margin:4px 0;">'
                f'<b style="color:{color};font-size:12.5px;">{name}</b>'
                f'<div style="color:#475569;font-size:12px;line-height:1.5;margin-top:4px;">{note}</div></div>',
                unsafe_allow_html=True)
    label("源码 / 白名单、确认与离线隔离", 7)
    source("target/write_authorization.py", "WRITE_TOOLS", max_lines=6,
           caption="写工具白名单常量")
    source("web/runtime.py", "Conversation.confirm_action", max_lines=13,
           caption="没有待确认提案就拒绝执行")
    source("scripts/launch_app.py", "build_environment", max_lines=18,
           caption="离线启动移除密钥并固定隔离环境")
    source("target/v39/static.py", "RailwayStatic.__init__", max_lines=14, expanded=False,
           caption="静态库整库 SHA256 校验")
    source("target/write_authorization.py", "denial", max_lines=20, expanded=False,
           caption="写操作拦截规则")


MODULES = {1: _m1, 2: _m2, 3: _m3, 4: _m4, 5: _m5, 6: _m6, 7: _m7}


def render():
    """Seven modules in the required order, grouped into three coloured sections."""
    chain_bar()
    for roman, name, note, color, (first, last) in SECTIONS:
        section_head(roman, name, note, color)
        for number in range(first, last + 1):
            with st.container(border=True):
                MODULES[number]()
    st.caption("以上 7 个模块的代码与提示词均直接读取当前源码；本页不连接会话、不展示运行结果。")
