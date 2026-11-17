"""只读取源码和既有证据，生成当前 V3 的代码功能说明，不导入业务或模型模块。"""
import ast
import hashlib
import json
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/handoff/v3/Ticket_Agent_V3_代码与功能介绍_20261016.md"


def function_source(path, name, owner=None):
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner) if owner else tree
    node = next(n for n in scope.body if isinstance(n, ast.FunctionDef) and n.name == name)
    code = textwrap.dedent("\n".join(source.splitlines()[node.lineno - 1:node.end_lineno]))
    return f"[{path} 第 {node.lineno} 行](../../../{path}#L{node.lineno})", code


def build():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = ast.parse((ROOT / "target/tools.py").read_text(encoding="utf-8"))
    specs = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets))
    policies = re.findall(r"^## \[(P\d+)\]", (ROOT / "data/policies.md").read_text(encoding="utf-8"), re.M)
    assert len(specs) == 8 and len(policies) == 15
    regression = json.loads((ROOT / "docs/evidence/deepseek/readonly-freeze-20261016/final-regression/regression.json").read_text(encoding="utf-8"))
    assert regression["status"] == "passed" and regression["runs"][0]["tests"] == 102
    chat_link, chat_code = function_source("target/agent.py", "chat", "Agent")
    adapt_link, adapt_code = function_source("target/langchain_agent.py", "adapt_tool")
    trace_link, trace_code = function_source("target/trace.py", "record_call", "Trace")
    descriptions = {
        "query_tickets": ("按路线、日期、交通方式和席别查余票", "trains、count；班次内含价格、余票和时刻"),
        "monitor_seat": ("无票时返回模拟候补监控凭据", "task_id、status、current_seats；没有后台持续轮询"),
        "lock_seat": ("检查库存并占座，生成有期限的锁", "lock_id、expire_at、ttl_seconds、unit_price"),
        "create_order": ("凭有效锁创建待支付订单", "order_id、status、amount、idempotent_hit"),
        "pay_order": ("修改模拟订单的支付状态", "status、duplicate_pay；首次支付另含amount"),
        "cancel_order": ("取消未支付订单或模拟退票并释放库存", "status、fee、refund、fee_rate、policy_ref"),
        "query_order": ("查询固定模拟身份的订单", "指定order_id返回单个订单，否则orders、count"),
        "search_policy": ("检索虚构政策并提供可检查来源", "hits、count；片段含doc_id、source、content、score"),
    }
    tool_sections = []
    for tool in specs:
        fn = tool["function"]
        props = fn["parameters"]["properties"]
        required = fn["parameters"].get("required", [])
        optional = [k for k in props if k not in required]
        purpose, result = descriptions[fn["name"]]
        live = "已保存一个基础真实调用场景；改后提示词尚未联网回归" if fn["name"] in ("query_tickets", "search_policy") else "当前未开放 Live"
        tool_sections.append(f"### {fn['name']}\n\n{purpose}。\n\n必填参数：" +
                             ("、".join(f"`{k}`" for k in required) or "无；默认查询本人订单") +
                             "。可选参数：" + ("、".join(f"`{k}`" for k in optional) or "无") +
                             f"。\n\n成功返回重点：{result}。DeepSeek 状态：{live}。\n")
    text = r'''# Ticket Agent V3 代码与功能介绍

面向成员 A 的代码讲解、成员 B 的测试接入，以及成员 C 的作品介绍与答辩准备。

HTML版可以单独阅读或通过浏览器打印；文中的源码和证据链接需要保留项目的相对目录结构。

编写日期：2026 年 10 月 16 日。内容依据当前源码与已保存运行证据整理，源码基线为 `__SHA__`。业务质量修复提交为 e216fdf，最新交接材料随当前分支保存。

## 项目定位

Ticket Agent 是一个可以使用工具的模拟出行服务智能体。用户用自然语言提出查票、订票或政策问题，Agent 选择工具，Python 后端读取或修改本地虚构业务数据，模型再依据工具结果回答。项目的重点是让工具选择、参数、业务结果和失败过程都能被测试。

所有高铁、机票、库存、政策、订单和支付都是比赛用模拟数据，不连接真实 12306、航司或支付系统。DeepSeek Live 表示模型决策来自真实 API，不表示票务业务变成真实购票。

目前 Mock 模式能够演示八工具业务流程。DeepSeek Live 仅开放 query_tickets 和 search_policy，已有两个基础真实 Function Calling 场景；后续只读质量修复仅完成离线验证。当前可以冻结候选版本供 B 测试，尚无 B 对本版本的完整正式验收结论。

## 已实现的主要功能

| 功能 | 实际行为 | 实现与验证范围 |
|---|---|---|
| 高铁与机票查询 | 按城市、日期、席别、交通方式查虚构班次 | 【已实现并验证】Mock；高铁查询另有基础 Live 证据 |
| 多轮条件继承 | 继续使用路线、日期和交通方式，切换时校验席别 | 【已实现并验证】Mock及SDK消息协议；真实多轮质量待验证 |
| 模拟订票 | 查票后锁座，再创建 pending 订单 | 【已实现并验证】Mock；未开放 DeepSeek Live |
| 模拟支付与退票 | 支付幂等、订单状态检查、手续费与库存回收 | 【已实现并验证】Mock；未开放 DeepSeek Live |
| 订单查询 | 只返回固定模拟用户的订单 | 【已实现并验证】Mock；不提供生产登录系统 |
| 模拟候补 | 售罄时返回监控凭据 | 【部分实现】模拟凭据已验证；持续轮询抢票尚未实现 |
| 政策检索 | 从15条虚构政策检索片段，提供编号和来源 | 【已实现并验证】关键词检索；另有一个基础 Live 场景 |
| CLI与Web | 对话、工具结果、JSON、历史回放和处理动画 | 【已实现并验证】Mock与离线SDK桩；Live历史记录可回放 |
| Trace与失败旁证 | 保存实际调用、参数、结果、用量和失败类别 | 【已实现并验证】正常字段保留原契约 |
| 六变异 | 用故意错误检查测试能否识别缺陷 | 【已实现并验证】仅 legacy Mock |
| 向量检索 | 可选本地嵌入模型与FAISS | 【已实现但未验证】当前默认关闭，不作为完成成绩 |
| 真实八工具订票 | 由DeepSeek完成下单和支付等 | 【尚未实现】其余六工具未开放Live |

## 执行模式与框架关系

| 模式 | 决策来源 | 执行循环 | 当前范围 |
|---|---|---|---|
| legacy Mock | MockProvider规则 | 自研Python循环 | 八工具、六变异与稳定离线演示 |
| LangChain Mock | LangChainMockModel封装规则模型 | LangChain create_agent | all工具集可用八工具；不支持六变异 |
| DeepSeek Live | ChatDeepSeek请求官方模型 | LangChain create_agent | 仅查票、政策两个只读工具 |
| 旧OpenAI兼容接入 | 原Provider或ChatOpenAI | 取决于legacy/langchain配置 | 适配代码保留；不冒充本次DeepSeek实测 |

V3 不是把原生循环换个名字。target/langchain_agent.py 实际调用 create_agent，让框架执行模型和工具循环，并使用 LangGraph 的 InMemorySaver 保存会话检查点。原生循环仍保留为可选路径。项目没有另外维护一套重复票务业务系统，两条路径复用同一套工具与数据库。

## 源码目录与职责

| 文件或目录 | 主要职责 |
|---|---|
| target/agent.py | 对外Agent入口、输入校验、引擎选择、原生主循环与通用Prompt |
| target/langchain_agent.py | create_agent、StructuredTool适配、中间件、会话与契约转换 |
| target/langchain_model.py | 把Mock规则封装为标准BaseChatModel，不在模型内执行工具 |
| target/providers.py | 原Mock/OpenAI兼容Provider、日期与意图处理、六变异 |
| target/deepseek_runtime.py | DeepSeek配置、只读Prompt、请求预算、错误脱敏、最终文字守卫 |
| target/tools.py | 八工具Schema、参数校验、分发和成功标记 |
| target/mock_core.py | SQLite库存、锁、订单、模拟支付和退款状态机 |
| target/write_authorization.py | LangChain独立写操作授权，不能仅信任模型或Prompt |
| target/rag.py | 政策分块、关键词或可选向量检索、来源字段 |
| target/trace.py | 正常契约Trace与JSONL保存 |
| target/mock_api.py | 可选FastAPI外壳，默认不启用 |
| config.py | 环境配置、模型、数据库路径、时钟和开关 |
| data/seed.py 与 data/policies.md | 创建虚构数据；保存15条虚构政策 |
| cli.py | 单轮、交互、多例批量与最后一条Trace查看 |
| web/app.py | Streamlit实际运行页面、历史回放与源码导览 |
| web/presentation.py 与 web/theme.css | 将工具结果转为卡片；展示样式与文本转义 |
| tests/ | 成员A的自测；不是成员B的正式100条用例 |
| scripts/ | 离线验证、冒烟、证据核对、交接辅助入口 |
| docs/contract.md | B/C依赖的团队接口契约 |
| docs/evidence/ 与 docs/handoff/ | 实际证据、历史材料和交接说明 |

## Agent 主循环如何工作

一次 DeepSeek 查询的实际工程流程是：

```text
用户输入
  → CLI 或 Streamlit
  → Agent.chat 校验并转交 LangChainAgent
  → create_agent 调用 ChatDeepSeek
  → 模型返回带 id、name、args 的 tool_calls
  → StructuredTool 与中间件检查调用
  → tools.dispatch 校验参数并执行 SQLite 或 RAG
  → ToolMessage 携带同一调用 id 和真实结果回传
  → 模型生成最终文字
  → 只读能力与失败检查
  → 正常 Trace 或独立失败旁证
```

模型负责理解表达、选择工具和组织回答；LangChain 负责运行流程；Python 工具负责真正读取库存和检索政策。班次、价格、订单状态和政策出处应由工具提供，不能由模型编造。

以下为当前统一入口的实际源码。它先验证消息，然后在实例锁内选择引擎；使用 LangChain 时，不会再偷偷执行原生 _chat 冒充框架。

__CHAT_LINK__

```python
__CHAT_CODE__
```

原生 _chat 则显式循环：调用Provider、执行tool_calls、回填tool消息，再继续模型调用。直到最终回复或超过最大步数。它用于保留V1/V2基础与可重复Mock测试。

## 八个工具与参数

工具名称、必填/可选参数从 target/tools.py 的实际 Schema 自动提取。Mock全工具场景可复用全部八个；下列说明不代表八工具Live通过。工具失败返回 error 或抛异常时必须保留失败状态。

__TOOLS__

参数补充：date 使用 YYYY-MM-DD；高铁席别为二等座/一等座/商务座，机票为经济舱/公务舱。passengers、passenger_ids 在本模拟系统中是乘客姓名字符串列表，不代表已完成真实身份核验。query_order 的 order_id 和 phone 均为可选，全部省略时查询固定模拟用户。

## 工具如何接入 LangChain

适配器读取已有Schema，生成StructuredTool；执行时仍调用原tools.dispatch。不会让模型直接操作SQLite，也没有再实现另一套库存服务。

__ADAPT_LINK__

```python
__ADAPT_CODE__
```

这段代码明确保留后端ok标记。ok=false时抛BackendToolFailure，中间件转成失败ToolMessage并记录实际工具；不会因返回体缺少error字段就把失败误判成功。LangChain中间件另行限制模型轮数、工具调用次数、授权和实际结果记录。

## 模拟业务与安全约束

锁座成功时扣减库存并生成默认15分钟有效的lock_id；下单必须引用有效锁并保持乘客一致。同一lock_id重复创建订单返回原订单，idempotent_hit用于检查幂等。支付只改变本地状态，已支付订单再次支付返回duplicate_pay=true，不重复扣款。

未支付取消与已支付退票走不同状态。退票按虚构政策计算费用并回收库存，固定模拟身份限制只能操作本人订单。过期锁与未支付订单在业务访问时清理，没有后台定时任务。即使调用名是查询，访问后端也可能顺带清理过期状态，测试仍应使用隔离库。

LangChain模式另外用write_authorization.py检查当前用户是否明确授权、是否有本轮成功锁、订单是否来自明确输入或最近工具结果。“帮我订票”不自动授权支付；政策疑问和否定表达不应变成写操作。这个独立语言授权检查属于LangChain路径，不能据此声称原生路径拥有完全相同的安全实现。

DeepSeek更保守：注册与请求传输只允许两个只读工具，中间件也拒绝其他调用。最终文字若主动邀请锁座、下单、支付或声称完成未开放操作，会抛read_only_capability_violation；原文字留在model_final旁证中，不替换成成功回答。该守卫是有限词语规则，可能误拒或漏检，不是通用语义安全证明。

## RAG 政策检索原理

data/policies.md含P01至P15共15条虚构政策。load_chunks按政策标题拆分，保存doc_id、title和content。默认检索把中文按字、英文数字按词切分，以匹配次数除以文本长度平方根打分，返回最多TOP_K条，默认3条。

这是一种轻量关键词检索，不是BM25。模型通过search_policy拿到命中片段，再依据片段组织回复并引用真实doc_id。source字段指向data/policies.md#政策编号，B可以核对内容是否支持答案。

可选向量路径使用本地嵌入模型与FAISS，首次可能下载模型；当前关闭且未完成本轮实测，异常时会退回关键词搜索。不能把默认关键词检索描述成已验证向量RAG，也不能把虚构政策说成官方票务规定。

## 会话记忆与数据隔离

原生路径把消息存在Agent.sessions字典；LangChain路径用InMemorySaver，以session_id映射thread_id。同一Agent实例、同一session可以多轮；进程退出后内存不会自动持久化恢复。历史JSONL回放只读记录，不重建推理会话。

DeepSeek失败后会清理该会话内存，避免残留没有配对结果的tool_call，下一条需要重新提供完整条件。agent.reset不还原库存/订单。不同测试用例除了不同session，还应隔离数据库与Trace；多个浏览器会话也可能使用同一个服务器数据库。

## Trace 与异常返回

正常Agent.chat返回session_id、provider、model、user_msg、steps、tool_sequence、reply、finish_reason、tokens、total_latency_ms共10个顶层字段。steps.calls每项保留tool、args、ok、latency_ms、result_preview。以下是当前实际记录函数：

__TRACE_LINK__

```python
__TRACE_CODE__
```

result_preview默认截取200字符，完整结果需查工具事件。tool_sequence是实际工具的扁平顺序；total_latency_ms是整轮经过的时间，包含模型/框架/工具开销，不等于所有工具耗时简单相加。finish_reason=stop只表示循环结束，max_steps_exceeded表示触及循环限制。

正常记录追加到配置的traces.jsonl。DeepSeek另存deepseek_runs.jsonl，包含模型tool_calls、tool_start/tool_end、模型名、用量及最终文字事件；不记录原始内部思维链。

DeepSeek API错误、超时、预算耗尽、未知Token、工具失败或越界回复会抛脱敏DeepSeekError。失败不创建伪正常Trace，而保留error、tool_attempts、tool_sequence和model_final；完整tokens为null，observed_tokens仅是已确认部分。CLI错误退出2，诊断JSON不是正常契约。B必须捕获异常，不能假定每次chat都返回字典。本说明不修改docs/contract.md。

## CLI 与 Web 功能

CLI支持once单轮、chat交互、多例batch和trace查看。多轮必须复用同一进程/实例，多次once不会保存上一进程的上下文。

Streamlit页面包括对话与工具、历史记录回放、核心代码导览。余票/订单/政策卡片来自本轮实际工具结果，完整结果与公共Trace逐项核对后才显示，不额外查询库存来装饰界面。页面提供JSON查看/下载和通用“正在处理请求”动画；动画不是模型内部思维展示，也没有伪造细粒度执行阶段。

DeepSeek页面的快捷场景和能力说明仅包含查票与政策咨询。验证提示说明的是历史上两个工具已真实跑过，不等于本轮调用成功。旧HTML效果图属于独立设计材料，当前真实应用入口仍为web/app.py。

## 六种预设缺陷注入

这些是为测试故意加入的规则变异，代码位于target/providers.py，仅legacy Mock可用。它们用于验证测试能否发现问题，不代表真实模型一定存在同类缺陷。

| 开关 | 故意改变的行为 | 可观察的测试点 |
|---|---|---|
| date_offset=1 | 将解析后的日期再偏移一天 | 工具日期与用户需求不一致 |
| skip_lock | 直接尝试用虚假锁ID创建订单 | 跳过必要前置工具，后端应拒绝 |
| repeat_call | 重复发送同一查票请求 | 冗余工具调用与重复开销 |
| infinite_loop | 候补后继续重复监控 | 是否触及max_steps_exceeded |
| route_error | 将政策问题错误路由到查票工具 | 工具选择与用户意图不符 |
| no_citation | 组织政策回复时省略出处编号 | 回答无法检查来源 |

Web可在legacy Mock中开启；Python用providers.set_mutation，结束后clear_mutations。不同用例还要隔离会话和数据库，不能把清除变异误认为恢复库存。

## 已有运行证据与验证边界

| 证据 | 实际结果 | 能证明什么 |
|---|---|---|
| 两个历史DeepSeek场景 | 查票query_tickets与政策search_policy各一次完整闭环 | 基础真实Function Calling，不证明真实多轮与八工具 |
| 最近A离线回归 | 新环境102项通过；旧V3 78通过/24跳过；旧环境35通过/67跳过 | A工程自测，不是B正式100条用例 |
| Mock冒烟 | 10项入口/服务检查与六变异通过 | 本地模拟流程与变异仍可触发 |
| 新只读Prompt/失败守卫 | 确定性SDK桩及旧回复文本回放通过 | 改后离线行为；尚未联网回归 |

历史真实查票参数为上海到杭州、2026-10-17、高铁二等座，结果包含G7301/G7302/G7303，价格均73元、余票35/47/51；政策场景最终引用P11/P12。这些是当时隔离虚构库存的记录，不代表今天还有这些余票。

历史累计5次生成请求，另1次余额GET，输入Token4796、输出563，实际费用未知。预算剩余0；本次文档整理没有新增模型请求。不要为了讲解或截图重跑--run，不删除账本或换路径绕过预算。

证据位置：

- [历史真实运行](../../evidence/deepseek/api-20261016-001224-2c3484/report.json)
- [原始证据离线复核](../../evidence/deepseek/review-20261016/audit.json)
- [最近完整离线回归](../../evidence/deepseek/readonly-freeze-20261016/final-regression/regression.json)
- [交接入口离线自测](../../evidence/deepseek/B-package-20261016/portable_selftest_result.json)

## 如何阅读和演示代码

建议按Agent.chat → LangChainAgent初始化/中间件 → tools的Schema/dispatch → mock_core业务状态 → rag → trace → web的顺序读。先确定是谁发起调用、谁执行、结果去哪里，再看日期识别和授权细节。

不需要Key的自测入口：

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/handoff_offline_selftest.py
```

它会限制测试子进程外部网络并使用离线桩，不运行B正式判定器。完整安装、Mock启动与Key配置请看[B安装运行详解](B_安装运行与APIKey配置详解.md)。当前配置Key不等于批准真实请求，网页Live发送仍须等待预算授权。

可以这样向队长或评委介绍：我们开发了一个可测试的模拟票务智能体。用户用自然语言提出需求，Agent通过规范工具读取虚构库存和政策，记录实际参数、结果及失败。V3保留原生循环，并增加真实LangChain调度和DeepSeek接入；八工具Mock流程可以演示，真实模型目前只验证了查票、政策两个基础场景。最新版本修复了只读能力误导和失败留证问题，离线自测通过后交B做正式测试。

## 团队分工与尚未完成事项

成员A负责被测Agent、模拟业务、工具、RAG、Provider、CLI/Web、Trace与本模块自测。成员B负责正式用例、判定器、指标、缺陷评价与回归。成员C结合B真实结果负责验收、作品文档、截图与视频，不能把A的自测数字替代比赛成绩。

尚未完成：DeepSeek其余六工具开放；改后Prompt的真实回归；真实多轮/边界/安全的系统性质量验证；可选向量RAG实测；持续候补服务；生产级登录、身份核验和真实票务/支付。API成本控制按请求预算和观测用量限制，不能保证精确金额上限。当前状态是可供B测试的只读候选，而不是生产售票系统。
'''
    replacements = {"__SHA__": sha, "__CHAT_LINK__": chat_link, "__CHAT_CODE__": chat_code,
                    "__ADAPT_LINK__": adapt_link, "__ADAPT_CODE__": adapt_code,
                    "__TRACE_LINK__": trace_link, "__TRACE_CODE__": trace_code,
                    "__TOOLS__": "\n".join(tool_sections)}
    for key, value in replacements.items():
        text = text.replace(key, value)
    assert "__" not in text
    OUT.write_text(text, encoding="utf-8")
    return {"output": str(OUT), "source_commit": sha, "tools": [s["function"]["name"] for s in specs],
            "policies": len(policies), "snippets": [chat_link, adapt_link, trace_link],
            "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(), "new_model_requests": 0}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
