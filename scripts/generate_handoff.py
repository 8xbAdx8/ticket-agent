"""从源码、Git 与实际证据生成交接报告；不执行外部模型，不推断比赛成绩。"""
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from data.seed import ROUTES
from target.tools import TOOLS
from target.providers import MUTATION_NAMES
from target.rag import load_chunks

ROOT = config.BASE_DIR
DEST = ROOT / "docs" / "handoff"
REPORTS = ["A_开发完成报告.md", "B_测试对接手册.md", "C_验收与演示交接手册.md", "A_最终交付清单.md"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def code_json(value):
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def write(name, text):
    (DEST / name).write_text(text.strip() + "\n", encoding="utf-8")


def main():
    evidence = json.loads((ROOT/"docs/evidence/verification.json").read_text(encoding="utf-8"))
    for name, expected in {**evidence["source_files_sha256"], **evidence["protected_files_sha256"]}.items():
        if sha(ROOT/name) != expected:
            raise RuntimeError("源码/保护文件已变化，必须重新验证："+name)
    assert evidence["provider"] == "mock" and not evidence["real_model_tested"]
    assert all(r["exit_code"] == 0 for r in evidence["runs"])
    unit = (ROOT/"docs/evidence/unit.txt").read_text(encoding="utf-8")
    assert "\nOK\n" in unit
    test_count = int(re.search(r"Ran (\d+) tests", unit)[1])
    examples = json.loads((ROOT/"docs/evidence/python_examples.json").read_text(encoding="utf-8"))
    http = json.loads((ROOT/"docs/evidence/http.json").read_text(encoding="utf-8"))
    tool_names = [t["function"]["name"] for t in TOOLS]
    assert set(c["tool"] for c in http["calls"]) == set(tool_names)
    assert set(evidence["mutation_labels"]) == {"injected:"+n for n in MUTATION_NAMES}
    DEST.mkdir(parents=True, exist_ok=True)
    source_revision = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    header = f"报告日期：2026-10-12（Asia/Shanghai）。运行证据时间：{evidence['date']}。\n\n核验实现版本：`{source_revision}`；分支 `{branch}`。报告最后文档提交可用 `git rev-parse handoff-a-20261012` 取得（Git 提交不能把自身 SHA 写进自身内容；最终 SHA 另在交付回复中给出）。\n\n数据来源：当前源码、`docs/contract.md`、Git 提交、`docs/evidence/verification.json` 及对应实际日志。所有运行结果均为 Mock 或本地模拟响应，未联网测试真实模型。"
    env = f"Python {evidence['python']}；" + "；".join(k+" "+v for k,v in evidence["versions"].items()) + "。完整传递依赖见 `requirements-lock.txt`。"
    counts = {kind:sum(r[0] == kind for r in ROUTES) for kind in ("高铁", "机票")}
    policy_count = len(load_chunks())
    roles = """| 成员 | 责任与交付边界 |
|---|---|
| A（本人，非队长） | Agent 主循环、模型 Provider、模拟高铁/机票、8 个工具与 Function Calling、RAG、CLI、Streamlit、Trace 与契约接口，以及本人模块基本自测。 |
| B（测试负责人） | 根据被测 Agent 与契约设计/执行工具、功能、RAG、多轮、安全、边界、性能测试；记录缺陷、独立给出正式测试结论与成绩。 |
| C（持续跟进与最终交付负责人） | 开发期了解进度、协调和记录问题；最终组织验收、作品介绍、正式报告、截图与视频制作；正式测试数据由 B 提供。 |

A 的 `tests/` 与 `scripts/smoke.py` 只验证自身实现及运行条件，不替 B 完成正式测试方案、评分系统或缺陷评估，也未改动 B/C 的代码。"""
    tools_table = "| 工具 | 状态 | 用途 | 参数（`*` 必填） |\n|---|---|---|---|\n"
    for t in TOOLS:
        fn = t["function"]
        params = fn["parameters"]
        fields = []
        for name, prop in params["properties"].items():
            extra = "/".join(prop.get("enum", []))
            fields.append(f"`{name}{'*' if name in params.get('required',[]) else ''}`: {prop['type']}" + ("（"+extra+"）" if extra else ""))
        tools_table += f"| `{fn['name']}` | 【已实现并验证】Mock/本地 HTTP | {fn['description']} | {'；'.join(fields)} |\n"
    outputs = """| 工具 | 成功返回结构及注意事项 |
|---|---|
| query_tickets | `trains: list, count: int`；trains 每项包含 kind/train_no/from_city/to_city/date/depart/arrive/seat_type/price/seats_left。最多 20 条，按余票降序、发车时间升序；0 票与空列表不同。 |
| monitor_seat | task_id/train_no/date/seat_type/duration_min/current_seats/status（monitoring）；仅凭据，无后台线程、不兑现、不扣款。 |
| lock_seat | lock_id/train_no/date/seat_type/passengers/unit_price/count/expire_at/ttl_seconds；锁座有效期 900 秒，创建时扣库存。 |
| create_order | order_id/phone/train_no/date/seat_type/passengers/amount/status/created_at/lock_id/idempotent_hit；passengers 是 SQLite 兼容的 JSON 字符串，非列表。重复相同 lock_id 返回同一订单。 |
| pay_order | 首次返回 order_id/status/pay_type/amount/duplicate_pay=false；重复已支付返回 order_id/status/duplicate_pay=true（不保证 pay_type/amount 在重复分支存在）。 |
| cancel_order | order_id/status/amount/fee/refund/fee_rate/policy_ref；paid→refunded，pending→cancelled（fee=0, refund=0，因为没有真实扣款）。已退款/取消/过期不可重复释放库存。 |
| query_order | 不指定订单号返回 orders/count/queried_phone；指定 order_id 返回单个订单原始字典（不包装 orders）。只可查询本人；状态 pending/paid/refunded/cancelled/expired。 |
| search_policy | question/hits/count；每个 hit 有 doc_id/source/title/content/score；source 为项目内文件片段标识。空检索返回 hits=[]。 |

业务/参数失败返回 `{"error": "原因"}`，某些分支另含 status 或 seats_left。`dispatch(name,args)` 返回 `(result, ok, latency_ms)`；以字典是否含 error 判定 ok。工具结果保留在内存对话中，Trace 只保存预览，不保证预览包含以上全部字段。"""
    mutations = """| 开关 | 单独启用后的复现输入 | 已观察到的行为 | 用于检查的缺陷类别 |
|---|---|---|---|
| date_offset=1 | 查明天上海到杭州的高铁 | query_tickets 日期比正常解析晚 1 天 | 日期参数偏差（任务书 R3） |
| skip_lock | 订明天上海到杭州的高铁 | query_tickets→create_order，缺 lock_seat；不存在的锁被后端拒绝，ok=false | 调用顺序（R4） |
| repeat_call | 查明天上海到杭州的高铁 | 同一步两次 query_tickets，同参数 | 冗余重复（R5） |
| infinite_loop | 抢明天北京到上海的票 | query_tickets 后连续 7 次 monitor_seat，总 8 步后 max_steps_exceeded | 失控与步数上限（R6） |
| route_error | 退票手续费怎么算 | query_tickets 代替 search_policy | 意图路由（R2） |
| no_citation | 退票手续费怎么算 | 调用 search_policy，但回复省略 P01/P02 等引用 | RAG 引用缺失 |

以上全部是人为注入 Mock 变异，不是实际大模型自然产生的缺陷。不应同时打开多个开关作单一变异结论（组合可能相互遮盖）。默认 MAX_STEPS=8；如更改步数，循环次数随之改变。"""
    install = r"""在项目根目录打开 PowerShell。第一次先安装可用 Python 3.12，再建立环境：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

本次主机的 `python` 起初是 Windows 商店占位程序，实际使用已安装的 CPython 3.12 建环境；不应把本机安装路径复制给队友。如果 `python --version` 无输出，使用自己安装的 Python 可执行文件替换第一条命令。已有 `.venv` 时直接使用下列经过实际验证的命令，无需激活，避免 PowerShell 执行策略拦截。

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\manual\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\manual\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe run_demo.py
.\.venv\Scripts\python.exe cli.py once "帮我查明天上海到杭州的高铁"
.\.venv\Scripts\python.exe cli.py chat
.\.venv\Scripts\python.exe cli.py batch cases/demo.json
.\.venv\Scripts\python.exe cli.py trace
.\.venv\Scripts\python.exe -m streamlit run web/app.py
```

seed 已存在时拒绝覆盖；请使用新路径，或只对确定的隔离测试库用 `--reset`。run_demo 未配置路径时创建 `artifacts/runtime/demo-*` 独立目录；已配置时使用指定库，不自动重置。先前“下周三”例子已经改为“后天”，因为 2026-10-12 的下周三（10-21）超出 7 天数据；超范围空结果是正常行为。

Mock + CLI 使用标准库即可，不必安装依赖；Web 用 Streamlit/pandas、HTTP 用 FastAPI/uvicorn、真实 Provider 用 openai。`requirements.txt` 为依赖范围，`requirements-lock.txt` 为此次实际环境完整冻结；不要求给 B 安装新的正式测试平台。"""
    true_model = r"""真实模型配置均在**新进程启动前**通过环境变量提供：

```powershell
$env:AGENT_PROVIDER="openai"
# 由安全配置注入 AGENT_API_KEY，勿输入到对话/文档/录屏；下面只示范非秘密配置。
$env:AGENT_BASE_URL="<支持 Chat Completions 和 tools 的端点>"
$env:AGENT_MODEL="<端点支持的模型名>"
.\.venv\Scripts\python.exe cli.py chat
```

不要直接运行含尖括号的占位配置，需按团队获批的模型服务填写。原默认模型名是 glm-4-flash、默认 URL 在 config.py；它们不证明该端点当前可用。Key 缺失时 Agent 初始化抛配置 ValueError，Web 显示初始化错误；运行中的网络/模型异常返回安全提示并以 stop 收尾。各端点兼容性、模型权限与余额、真实能力由获 Key 后的实测确认。本次未访问真实模型或外部票务/支付服务。切回 Mock 后重启进程即可。"""
    limits = """| 项目 | 状态与限制 |
|---|---|
| 真实模型联网 | 【已实现但未验证】适配器代码在，SDK 模拟响应验证成功；无 Key，联网结果待验证。 |
| 向量 RAG | 【已实现但未验证】代码存在，未安装/下载 sentence-transformers/faiss 模型。失败回退关键词；向量质量与首次下载待验证。 |
| 任意自然语言理解 | 【部分实现】Mock 是关键词/正则剧本，有限城市/意图、默认乘客张三、默认明天；仅支持明确“乘客张三、李四”列表格式，复杂表述可能误解。 |
| 会话记忆 | 【部分实现】同一个 Agent 实例同 sid 内存保存，进程重启丢失；不同 sid 记忆隔离，但票务库/固定身份共享。无跨进程持久化、无长期上下文压缩。 |
| 身份与安全 | 【部分实现】固定虚构演示身份，工具拒绝他人手机号/订单号；无真实登录、多租户、完整提示注入防护或生产权限认证。 |
| 真实改签/儿童学生票/身份证实名 | 【尚未实现】只有政策检索，未建立改签动作、折扣、报销凭证状态、折扣机票或 P10 一证一票核验。 |
| 候补后台兑现 | 【尚未实现】monitor_seat 仅返回无票班次监控凭据；不轮询/排队/自动抢票兑现，不承诺成功。 |
| 库存更新与旧库升级 | 【部分实现】新库 2100 条、7 天；已有原库原样保留，没有自动 schema/数据迁移或每日滚动刷新。 |
| 并发与性能 | 【部分实现】SQLite 事务避免该实现的扣库/状态竞态；未做压力、负载/高并发或性能基准，Trace 计时不能当比赛性能结论。 |
| RAG 相关性与引用 | 【部分实现】关键词重叠而非 BM25/语义推理，可能召回不相关片段；真实模型引用仅由 Prompt 约束，未增加强制引用校验器。 |
| 错误与 Trace | 【部分实现】模型异常安全回复、工具异常 ok=false；契约只有两种 finish_reason，因此 stop 可包含失败。预览 200 字符可能截断、不是完整 JSON。Trace 不记录模型原始响应、变异 label 或时间戳，标签在证据包装中。 |
| Web/Trace 大规模使用 | 【部分实现】AppTest 与本地服务通过；历史文件全文读取，没分页/日志轮转/跨进程写锁；人工浏览器外观、多人共享及大量回放待验证。 |
| 正式参赛结论 | 【尚未实现】由 B 给正式测试结果，C 完成验收、截图视频与正式报告；A 没有提供覆盖率、性能评分、缺陷数量或成功率。 |

未声称这些未完成项已经通过。无已知阻塞 Mock 冒烟链路的代码 Bug；上述限制仍可能导致未覆盖输入失败，应由 B 的独立测试确认。"""
    run_table = "| 实际命令/检查 | 结果 | 可检查证据 |\n|---|---|---|\n"
    for r in evidence["runs"]:
        run_table += f"| `{r['command']}` | exit_code={r['exit_code']} | `{r['log']}` |\n"
    history = "| 提交 SHA | 对应功能 |\n|---|---|\n" + "\n".join("| `"+line.split("\t",1)[0]+"` | "+line.split("\t",1)[1]+" |" for line in git("log","--reverse","--format=%H%x09%s").splitlines())
    tree = """ticket-agent/
├─ .gitignore                 不提交 Key、数据库、正式运行 Trace、缓存与环境
├─ README.md                  快速运行与三方交接索引
├─ config.py                  模型/路径/执行步数配置，北京时间时钟
├─ cli.py                     once/chat/batch/trace
├─ run_demo.py                六例 + 两种变异；默认隔离路径
├─ requirements.txt           原有可选依赖范围
├─ requirements-lock.txt      实际验证依赖冻结
├─ 成员A任务书_被测抢票智能体.md  用户补充的任务书，保留
├─ 订票.doc                   用户补充的 Word 构想资料，保留
├─ cases/demo.json            六条批量示例
├─ data/
│  ├─ seed.py                 30 高铁/5 机票/7 天的新库生成器
│  ├─ policies.md             15 条虚构政策及模拟边界
│  └─ tickets.db              原库原地保护，Git 忽略
├─ target/
│  ├─ __init__.py             Python 包入口
│  ├─ agent.py                Agent.chat 循环、sessions、Prompt
│  ├─ providers.py            Mock 剧本/6 变异/OpenAI 风格适配
│  ├─ tools.py                8 schema、参数校验、dispatch、本地/HTTP
│  ├─ mock_core.py            SQLite 业务、事务、故障注入与状态回收
│  ├─ mock_api.py             FastAPI 外壳，复用业务/校验
│  ├─ rag.py                  关键词检索、可选向量、来源片段
│  └─ trace.py                契约字段、计时、JSONL 追加
├─ web/app.py                 Streamlit 对话、开关、错误、回放
├─ tests/                     成员 A 实现自测，非 B 的正式平台
│  ├─ test_core.py            事务、库存/人数、过期、所有者/参数/候补
│  ├─ test_agent.py           多轮、契约、6 变异、机票/候补、异常
│  ├─ test_provider.py        SDK 模拟响应、ID/usage/缺 Key
│  └─ test_web.py             AppTest 控件、会话、回放与错误提示
├─ scripts/
│  ├─ handoff_example.py      真正调用 Agent 的正常/变异示例
│  ├─ smoke.py                隔离运行、服务验证与证据采集
│  ├─ read_legacy_doc.py      只读旧版 Word 正文抽取，选装 olefile
│  └─ generate_handoff.py     根据 Git/schema/证据生成及核验报告
├─ traces/traces.jsonl        原有历史证据，原地保护，Git 忽略
├─ docs/
│  ├─ contract.md             原契约，哈希未改变
│  ├─ development_log.md      持续开发记录与对应 SHA
│  ├─ development_summary.md  本次开发总结、交接判断与队长待协调事项
│  ├─ evidence/               实际 Mock 日志、JSON、Trace（列表见下）
│  └─ handoff/
│     ├─ A_开发完成报告.md     总体实现、架构、验证及限制
│     ├─ B_测试对接手册.md     运行、接口、工具、隔离及变异复现
│     ├─ C_验收与演示交接手册.md  介绍、验收步骤、取证及拍摄分镜
│     ├─ A_最终交付清单.md     真实勾选的三方交接事项
│     └─ handoff_manifest.json 生成来源、报告/验证哈希核验清单
└─ artifacts/runtime/         忽略的隔离测试库/Trace，不作为源码交付
"""
    evidence_files = "\n".join("- `docs/evidence/"+p.name+"`："+({"verification.json":"命令、环境、源文件/保护文件哈希与模式。","mock_traces.jsonl":"32 条完整 Mock Trace，可用作离线素材。","python_examples.json":"正常和变异 label 包装的 Python 实际返回。","http.json":"8 工具 HTTP 实际入参/返回。","web_health.txt":"真实启动 Streamlit 后健康检查结果。"}.get(p.name,"对应命令的实际 stdout/stderr，非评分。")) for p in sorted((ROOT/"docs/evidence").iterdir()) if p.is_file())
    locations = []
    for name, symbol in [("target/agent.py","Agent"),("target/agent.py","SYSTEM_PROMPT"),("target/providers.py","MockProvider"),("target/providers.py","OpenAIProvider"),("target/tools.py","dispatch"),("target/tools.py","validate"),("target/rag.py","search_policy"),("target/trace.py","Trace")]:
        nodes = ast.parse((ROOT/name).read_text(encoding="utf-8")).body
        node = next(n for n in nodes if getattr(n,"name",None)==symbol or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==symbol for t in n.targets)))
        locations.append(f"- `{name}:{node.lineno}`：`{symbol}`。")
    code_locations = "\n".join(locations)

    a = f"""# 成员 A 开发完成报告

{header}

## 1. 项目背景、目标及分工

项目名称 Ticket Agent（出行服务智能助手），为第九届传智杯相关智能体测试任务提供一个可运行、可观察、可故意注入缺陷的被测系统。比赛名称与要求取自团队任务资料，未自行核定赛事时效信息。目标是将用户的查票、购票、支付、退票与政策问题转换为可追踪的工具调用，让队友能检验“调没调、顺序对不对、参数是否正确、是否终止”。所有票务、政策、手机号、乘客和支付均为虚构演示数据，无真实交易。

{roles}

## 2. 项目目录与文件职责

```text
{tree}```

运行环境 `.venv/`、`.git/`、`__pycache__/` 是本机辅助目录，不作为源文件职责清单。原库/原 Trace 在本次验证中未写入；数据库不入 Git，队友在新位置生成。完整证据文件：

{evidence_files}

## 3. 技术架构与核心流程

```mermaid
flowchart LR
    UI[CLI / Streamlit / Python chat] --> Agent[Agent 循环与会话]
    Agent --> Provider[Mock / OpenAI 风格 Provider]
    Provider --> Decision[工具名称与 JSON 参数]
    Decision --> Dispatch[Python 校验与 dispatch]
    Dispatch --> DB[模拟 SQLite 票务]
    Dispatch --> RAG[政策知识库检索]
    DB --> Result[工具结果]
    RAG --> Result
    Result --> Agent
    Agent --> Trace[契约 JSON 与追加 Trace]
```

【已实现并验证】同一个 Agent 保存各 sid 的 messages；收到 user 后向 Provider 发送 Prompt、完整历史和 8 schema。Provider 要么输出回答，要么请求工具。Python 按 schema 校验参数并执行工具，把结果作为 role=tool 消息交回 Provider。继续到无工具请求或达到最大步数。模型异常安全收尾；工具异常 ok=false，结果仍返回模型。MAX_STEPS 默认 8，按模型轮次计而非工具数；每轮可有多个调用，Python 顺序执行。

Function Calling 是模型提出“调用某工具及其参数”的协议。模型没有直接执行 SQLite 的权限，Python 才负责有副作用的库存/订单事务。这让业务事实与自然语言决策分开，也让 B 有确定的观察数据。代码位置：

{code_locations}

关键实际语句：`result, ok, latency = tools.dispatch(name, args)` 执行；`trace.record_call(step, name, args, result, ok, latency)` 记录；`messages.append(...)` 把 tool result 返回下一轮。session_id 是会话记忆的索引，不是身份认证。

## 4. 8 个工具

以下自动读取 `target/tools.py`，未改名、未改契约。

{tools_table}

{outputs}

【已实现并验证】全部 8 工具在真实启动的本地 HTTP 外壳上各执行成功，直连业务和 Agent 链路也完成基本自测。校验非空字符串、required/未知参数、enum、数组非空/无重复、ISO 日期和正整数监控时长。直接绕过 dispatch 调 mock_core 是内部用法，不享有工具层完整 schema 校验。

## 5. 模拟业务与状态

【已实现并验证】新库按 config.today 生成 {counts['高铁']} 条高铁线路、{counts['机票']} 条机票线路、7 天、每天 3 班；高铁 3 席别/机票 2 舱位，共 2100 条。北京→上海/广州当天与明天二等座为 0，提供确定性候补输入；其他普通座保证正库存。随机发生器固定种子，日期随生成日变化。

【已实现并验证】query→lock 扣人数库存→create 不再扣库→pay 只改状态→cancel/refund 按人数一次性回库。`BEGIN IMMEDIATE` 串行化读写事务，连接在 finally 关闭。同 lock_id 下单幂等，重复 paid 支付返回 duplicate_pay=true；已取消/退款/过期不能再支付或回库。锁座及 pending 过期在下次业务访问时回收，没有定时后台任务。下单乘客须与锁座列表完全一致，contact 只允许当前演示身份。

【已实现并验证】取消未支付订单 fee=0，已支付订单按实际班次发车时间计算手续费：高铁 P01（>48h 5%、24..48h 10%、<24h 20%）、普通机票 P09（>24h 10%、24h 内 30%）；已发车的 paid 订单拒绝退款。凭证、改签、折扣机票等政策例外未建模，见限制。

## 6. Mock 与真实模式

【已实现并验证】MockProvider 是明确公开的关键词/正则剧本，不是大模型。适合无 Key 演示、链路回归、构造人为故障；token 为 0，模型字段只是配置名，不证明调用了 glm 或任何外部模型。

【已实现并验证】真实 Provider 的本地 SDK 模拟响应自测保留服务端 call_id、参数 JSON 和 usage，并正确生成 role=tool/tool_call_id 消息。协议参考 [OpenAI 官方 Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。

【已实现但未验证】真实远端模型：配置后才会由模型自主选择工具，尚未用 Key 实测；第三方端点的工具调用兼容性不能从 Mock 推断。

{true_model}

## 7. RAG

【已实现并验证】`policies.md` 有 {policy_count} 个 `[Pxx]` 块。rag.load_chunks 分块并缓存；中文按字、英文数字按词切分，query token 去重，按命中词频除以块长平方根打分，返回 TOP_K=3 的 doc_id/title/content/score/source。这是关键词检索兜底，不是 BM25，也不是经过评测的向量语义检索。Mock 汇总前两块并注明 P01/P02 等来源。

检索结果作为 tool 消息提供给模型，让回答可以回溯出处；政策全部为模拟规则，不可作为真实出行依据。`no_citation` 故意去掉回复引用，工具结果仍有 doc_id。可选向量实现存在且异常回退关键词，但模型/依赖未实测，因此【已实现但未验证】。

## 8. CLI 与 Web

【已实现并验证】CLI once 单句、chat 进程内多轮、batch 按 JSON 中 sid 连续运行、trace 回看配置目录最新有效 JSON。标准输入驱动 chat 实测购付三轮。

【已实现并验证】Streamlit 包含对话、当前会话、调用表/完整 JSON、6 checkbox/恢复、Mock 标识、错误提示、历史 Trace 列表及选中回放。AppTest 实际发送多轮购票/支付/退款和政策，切换变异并看到错误。真实 Streamlit 服务健康检查通过。

【已实现但未验证】由 C 对真实浏览器布局、截图、录屏体验人工验收；本报告不把 AppTest 写为人工截图验收。

## 9. Trace 与接口交付

【已实现并验证】严格保留契约的 10 个顶层字段与每次调用的 6 个字段。每轮 chat 默认在配置目录 `traces.jsonl` 追加一行；默认目录仍是 traces，测试用 AGENT_TRACE_DIR 隔离。没有改动 `docs/contract.md`，保护哈希为 `{evidence['protected_files_sha256']['docs/contract.md']}`。

时间用 perf_counter，单次 latency 是工具校验/执行/异常处理的实际计时；total 是一轮 Provider + 工具循环到 finish 的实际耗时，冻结后同一字典用于返回和保存，不含磁盘追加耗时。整数向下截断，0ms 正常，总耗时不一定等于工具耗时之和。stop 表示循环终止而不是成功认证；到上限为 max_steps_exceeded。完整字段见 B 手册，预览最多 200 字符再加省略号。

## 10. 六种缺陷注入

【已实现并验证】全部逐个执行并留有 label 明确标记的证据；不在契约 Trace 中增加变异字段。

{mutations}

## 11. 实际运行、自测及环境

{env}

【已实现并验证】{test_count} 个成员 A 实现自测通过；{len(evidence['runs'])} 条命令/服务检查 exit_code=0；保存 {evidence['trace_count']} 条完整 Mock Trace。数目仅描述本次开发验证，不是 B 的测试覆盖率、缺陷率或竞赛分数。Web 单测用 AppTest，本地 HTTP 测试通过网络 loopback 实际执行。日志中每次工具实际耗时可读，未提炼未经验证的性能指标。

{run_table}

## 12. 实现状态与已知限制

{limits}

## 13. Git 记录及工作保护

初次检查无 `.git`；未恢复或伪造以前的历史。本次在独立功能分支建立收到的 MVP 基线，按已验证模块逐次提交；没有推送、合并 main 或清空正式 Trace。阶段日志从开发过程中持续更新，见 `docs/development_log.md`，包含早期失败与修复。用户中途补充的原始任务书/Word 原样保存。

{history}

四份报告的文档提交位于以上已核验源码提交之后，最终交付标签 `handoff-a-20261012` 指向实际最终提交。运行 `git log --oneline` 可核对完整记录，不能把报告生成前的源码 SHA 冒充文档提交 SHA。

## 14. 后续优化与教学交接

1. 团队获 Key 后让 B 独立验证真实模型工具决策、RAG 引用、多轮和异常；真实与 Mock 数据分目录记录。
2. 按 B 的缺陷证据优先完善意图/参数理解、未知问题澄清与引用校验，避免扩大未验证功能。
3. 需要真实改签、优惠、身份核验时先明确模拟业务状态，不仅修改 Prompt。
4. 如要扩展持久记忆、向量检索或并发服务，独立验证成本、相关性与状态一致性；任何契约字段变更先由团队确认。
5. C 依据本报告可介绍“模型决策→Python 执行→结果反馈”，再展示 Trace：它是 B 判断行为和 C 拍摄证据的共同出口。RAG 给回答可追溯来源；sid 给同一 Agent 的对话提供记忆，二者都不是模型能力得分。

成员 A 开发交接状态：**有条件交接**。Mock 被测入口与演示材料可供 B/C 独立使用；真实模型、向量、B 正式结论和 C 人工验收未完成，不能据此宣布参赛全项目终验完成。
"""
    write(REPORTS[0], a)
    # 其余三份文档在下方生成，同一份源码/证据上下文。
    build_b(header, env, roles, tools_table, outputs, mutations, install, true_model, limits, examples, evidence, source_revision, branch)
    build_c(header, env, roles, install, true_model, code_locations, limits, evidence)
    build_checklist(header, env, tools_table, history, source_revision, branch, evidence)
    manifest = {"generated_date":"2026-10-12", "verified_source_revision":source_revision, "branch":branch,
                "delivery_tag":"handoff-a-20261012", "provider":"mock", "real_model_tested":False,
                "reports":{name:sha(DEST/name) for name in REPORTS}, "verification_sha256":sha(ROOT/"docs/evidence/verification.json"),
                "source_hash_check":"passed", "contract_unchanged":True, "unit_test_count":test_count,
                "python_example_count":len(examples), "tool_names":tool_names, "mutation_names":list(MUTATION_NAMES)}
    (DEST/"handoff_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    assert all((DEST/name).exists() and len((DEST/name).read_text(encoding="utf-8")) > 3000 for name in REPORTS)
    print(json.dumps({"reports":len(REPORTS), "source_hash_check":"passed", "contract_unchanged":True, "source_revision":source_revision},ensure_ascii=False))


def build_b(header, env, roles, tools_table, outputs, mutations, install, true_model, limits, examples, evidence, source_revision, branch):
    first = examples[0]["result"]
    sample_call = first["steps"][0]["calls"][0]
    b = rf"""# 成员 B 测试对接手册

{header}

## 1. 对接职责与准备

{roles}

本手册只交付被测 Agent 的运行方式、稳定接口及可复现条件。B 自己确定正式测试方案、断言、缺陷评级、覆盖率与成绩。A 的基本自测可作实现参考，不能当 B 的正式结果。接口权威来源是原 `docs/contract.md`，本次未修改；文件 SHA256 `{evidence['protected_files_sha256']['docs/contract.md']}`。

环境实际验证版本：{env}

## 2. 安装与运行

{install}

若在无依赖机器只跑 Mock + CLI，不需要安装 requirements；若运行 A 的完整 `tests/`（含 Web 和真实适配器自测），需安装锁定依赖。`pytest` 被安装但本次实际测试命令是 unittest，不能写成“pytest 全部通过”。

验证入口：`python -m unittest discover -s tests -v` 为成员 A 12 个基本自测；`python scripts/smoke.py` 创建新的隔离目录、捕获实际命令和本地服务证据（会更新 docs/evidence，本次交付前的证据请先另存）。进程运行前设置配置，import 后修改 os.environ 不会改变已导入 config。

## 3. Python 入口（已经实际执行）

```python
from target.agent import Agent
agent = Agent()  # 默认 mock；一组多轮用同一个实例
r1 = agent.chat("S1", "查明天上海到杭州的高铁")
r2 = agent.chat("S1", "我要买一张")
r3 = agent.chat("S1", "支付")
r4 = agent.chat("S1", "帮我退掉")
print(r1["tool_sequence"])
print(r2["tool_sequence"])
print(r3["finish_reason"])
```

同一组语句已通过 `scripts/handoff_example.py` 和多轮自测执行。观测序列依次为 query_tickets；query_tickets→lock_seat→create_order；pay_order；cancel_order，工具 ok 均为 true，finish_reason 都为 stop。不得每轮新建 Agent 后还期望记忆存在；`Agent().chat(session_id,message)` 是单次入口表达方式，多轮需保留实例。

实际第一轮完整返回（直接从 `docs/evidence/python_examples.json` 读取，不是手写伪造模板；日期/订单/耗时随重跑变化）：

{code_json(first)}

也可直接运行 `python scripts/handoff_example.py`，输出包含正常多轮、候补和六变异的 label/result 包装；其中 result 才是原契约 JSON。全部内容与保存 Trace 的相应行一致。

## 4. 完整返回 JSON 字段

| 字段 | 类型 | 含义与限制 |
|---|---|---|
| session_id | string | 调用传入非空 sid；同实例同 sid 延续 messages。不是登录身份。 |
| provider | string | 实际 Provider.name，通常 mock/openai。 |
| model | string | config.MODEL_NAME；Mock 中仅配置名，不代表联网用了该模型。 |
| user_msg | string | 本轮用户原文，不是整段历史。 |
| steps | array | 有工具的模型轮次列表，每项有 step（1 起）和 calls。最终无工具回答不新增一步，无工具时为空。 |
| tool_sequence | array[string] | 按 steps/calls 展开后的工具名顺序，包含失败调用与重复调用。 |
| reply | string | 最终文字答复，包括错误提示；不是业务成功标志。 |
| finish_reason | string | stop 或 max_steps_exceeded，见下文判定。 |
| tokens | object | prompt/completion 两个整数，真实 Provider 各轮 usage 累加；SDK 没有 usage 时为 0，Mock 始终 0。 |
| total_latency_ms | integer | 一轮实际时间（毫秒截断），冻结后返回/保存相同。 |

上表共 10 个顶层字段。未新增 timestamp、mutation、trace 嵌套字段。变异名在旁路包装文件 label 里，或由 B 在自己的运行元数据中保存。

### steps[].calls[]

| 字段 | 类型 | 意义 |
|---|---|---|
| tool | string | Provider 请求的工具名称；可记录未知名称的失败，不应以此证明工具存在。 |
| args | 通常 object | 模型传参原样；正常 schema 参数为 object。真实模型返回坏 JSON 时可能记录原始字符串，dispatch 拒绝；B 可作为异常输入证据，不应假设每次都可 args['date']。 |
| ok | boolean | result 字典含 error 或工具执行抛异常时 false；成功执行为 true，不表示模型语义/参数意图一定正确。 |
| latency_ms | integer | dispatch 中校验、执行和异常处理的实际耗时；HTTP 模式包含请求往返。 |
| result_preview | string | JSON 序列化的前 200 字符；过长再加 `...`，最多 203 字符，截断后可能不是合法 JSON。 |

实际调用记录：

{code_json(sample_call)}

`step` 按 Provider 回合计，一步可以有两次或更多 tool_calls。Python 当前逐个执行，不是并发；repeat_call 的两次 query 在同一步。`tool_sequence = [c['tool'] for s in steps for c in s['calls']]` 是字段含义说明，不是 B 的正式评分代码。

### finish_reason 与耗时

1. Provider 本轮无工具请求，即以 stop 完成；工具报错后 Mock 给出解释也会 stop。
2. Provider 抛异常/返回错误消息格式，Agent 安全回复并 stop。契约没有 provider_error 状态，因此 B 要同时检查 reply 和 calls.ok。
3. 连续 MAX_STEPS 回合都要求工具，耗尽 for 循环为 max_steps_exceeded；最后工具可以成功，依然表示循环未得到最终无工具回答。
4. 请求 sid/message 非字符串或空白时入口直接抛 ValueError，不生成 Trace。初始化缺 Key/依赖错误也可能在 chat 前抛出。磁盘追加失败会抛异常，没有声称已落盘。

单次 latency 和 total 使用单调 perf_counter 真计时，非固定数。total 起点在本轮 Trace 初始化，终点是 finish，包含模型/工具循环；不包含最后写盘时间。模型时间及整数截断意味着 total 不应直接等于所有调用 latency 之和，0ms 不是伪造。

## 5. 读取 Trace（不会覆盖历史）

```python
import json
from pathlib import Path
import config
path = config.TRACE_DIR / "traces.jsonl"
with path.open(encoding="utf-8") as f:
    for line_no, line in enumerate(f, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print("不完整行：", line_no)  # 保留原文件，复制证据排查
            continue
        print(record["session_id"], record["tool_sequence"], record["finish_reason"])
```

JSONL 是每次 chat 一行，而不是整个会话只一行；同 sid 多轮会重复出现。默认 `traces/traces.jsonl`，设置 AGENT_TRACE_DIR 后读取对应位置。本次已实际逐行解析 `docs/evidence/mock_traces.jsonl` {evidence['trace_count']} 条；返回与保存完全一致的验证在 test_agent 中。不要解析 result_preview 来取完整工具数据；需要工具完整返回可单独 dispatch，或由 B 在自己平台保留数据，不改 A 契约。

## 6. 工具参数及返回

以下参数表自动取自当前 TOOLS schema。query_order 无 required，order_id/phone 都可省略，省略返回本人列表；指定 order_id 走单订单分支。契约表虽写“order_id 或 phone”，现有 schema/实现允许默认本人查询，未擅改契约。

{tools_table}

{outputs}

默认参数：monitor duration_min=30，pay pay_type=alipay，cancel reason=""，search top_k=config.TOP_K=3。seat_type 与 kind 可省略，底层查所有匹配席别/方式；Mock 通常主动传 kind/默认席别。enum 以 schema 为准，监控/锁座 seat_type 字符串仍需对应库存。date 必须精确 YYYY-MM-DD 且真实日历日期；未定义参数、空字符串、数组重复/为空、布尔替代 integer 都被拒绝。duration_min 范围 1..1440。

完整 HTTP 实际工具返回见 `docs/evidence/http.json`，不把随机 task/order/lock ID 当固定预期。

单独调用示例（已由自测和 HTTP 验证同一路径）：

```python
from datetime import timedelta
import config
from target.tools import dispatch
day = (config.today() + timedelta(days=1)).isoformat()
result, ok, latency_ms = dispatch("query_tickets", {{
    "from_city": "上海", "to_city": "杭州", "date": day, "seat_type": "二等座"
}})
print(ok, latency_ms, result["count"])
```

## 7. 六种变异与恢复

```python
from target import providers
from target.agent import Agent
providers.clear_mutations()
providers.set_mutation("skip_lock")
try:
    result = Agent().chat("case-skip", "订明天上海到杭州的高铁")
finally:
    providers.clear_mutations()
```

date_offset 用 `providers.set_mutation("date_offset", 1)`；布尔开关用 set_mutation(name)，关闭单项可 set_mutation(name,False)，全部关闭用 clear_mutations。全局字典对同进程默认 MockProvider 实例生效，B 串行测试使用；独立字典可 `Agent(provider=providers.MockProvider({{"skip_lock": True}}))`，不受全局 clear_mutations 控制，须清空该字典或新建正常 provider。Web 的开关正是每个浏览器独立字典，不使用全局 MUTATIONS。

{mutations}

恢复正常的完整条件：清空变异、`mock_core.clear_faults()`、`agent.reset()` 或新建 Agent、新建/重置隔离业务库、新 Trace 目录。只 reset(sid) 不恢复库存；只 clear_mutations 不删除会话历史；只重启 Web 不一定改变原库订单。真实模型不读取这些 Mock 变异，不应靠 set_mutation 推断真实模型缺陷。

## 8. 重置数据与防用例污染

推荐每个独立场景新进程 + 新库 + 新 Trace 目录；一组连续购付退款步骤属于同一场景，故意共享同实例/sid/库。不同 sid 隔离记忆，不隔离固定模拟用户的订单/库存。

```powershell
# 使用自己准备的新场景名，运行前设定；不要对 data/tickets.db 执行重置。
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\case-001\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\case-001\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe cli.py once "帮我查明天上海到杭州的高铁"
# 如明确复用并重置这个隔离库，先停止关联 Web/HTTP/CLI，再运行：
.\.venv\Scripts\python.exe data/seed.py --reset
```

不会清除/覆盖 traces.jsonl，换新目录保留历史。建库日期会更新，订单与锁会归零，库存由种子恢复。默认原库不会自动升级为扩展线路；跨日/过久未重建库会出现日期过期或空结果，应作为测试前置条件记录。锁 TTL 以 config.now 为准，访问时回收，等待期间没有后台更新。

backend 故障注入是额外调试入口，与六变异不同：`mock_core.set_fault('query_tickets','timeout'/'error')` 抛立即模拟异常，不是真正等待超时；query_tickets 的 empty 返回空结果。clear_faults 恢复。HTTP 服务器是另一进程，客户端设置 FAULTS 不会同步到服务器。

## 9. HTTP 方式（本次已验证）

第一个终端先设置相同隔离路径并启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn target.mock_api:app --host 127.0.0.1 --port 8000
```

客户端第二终端同样配置库/Trace，再设 `$env:AGENT_USE_HTTP="1"` 和 `$env:AGENT_MOCK_URL="http://127.0.0.1:8000"`，运行 CLI。POST `/tool/query_tickets` 请求体是 `{{"args":{{"from_city":"上海","to_city":"杭州","date":"YYYY-MM-DD"}}}}`，不要直接裸传参数字典。GET `/health` 返回 status/tools；GET `/inventory` 需 from_city/to_city/date 都有值。HTTP 错误常作为 JSON error 且 HTTP 200，必须检查 body；结构性请求错误 FastAPI 可返回 422。tools.dispatch 捕获网络异常为 ok=false，HTTP 客户端 timeout=10 秒。服务器仅本地模拟，不能用于生产暴露。

## 10. 真实模式与已知接口限制

{true_model}

{limits}

交接建议：当前可开始 B 的 Mock 正式测试；真实模型测试需队长协调服务与 Key。B 生成自己的原始证据、测试结论，C 再据此形成报告。最后核对 `git rev-parse HEAD`/交付标签，源码版本 `{source_revision}`，分支 `{branch}`。
"""
    write(REPORTS[1], b)


def build_c(header, env, roles, install, true_model, code_locations, limits, evidence):
    c = f"""# 成员 C 验收与演示交接手册

{header}

## 第一部分：项目介绍与协作

Ticket Agent 演示一个能够查票、模拟下单/支付/退款、回答政策问题的出行助手。用户可以说“查明天上海到杭州的高铁”，系统把需求变成工具调用，并留下能逐项检查的记录。它解决的是“智能体行为怎样被可靠地测试与展示”的工程问题，不是实际替旅客抢票。

选择模拟票务有三个原因：业务有清楚的先后顺序；有票/无票、有效/过期、本人/他人等状态很容易构造；全部虚构数据与模拟支付，评委无 Key 也能复现，不涉及真实交易。一般聊天机器人可能只生成一段回答，这个项目会让 Python 读取数据库并改变模拟订单状态，因此可以拿事实与轨迹核验回答。

真实模型模式中，AI 负责理解用户意图、选择工具/生成参数、读结果后决定继续调用或回答；Python 校验并实际执行业务。政策问题先通过 RAG 在知识库找依据，再交给模型组织回答。**本次演示验证的是 Mock 离线剧本，不能称为已经验证真实大模型的自主能力。** 真实 Provider 代码已准备，获得 Key 后另行测试。

技术亮点：统一 8 工具 schema、循环执行与步数上限、SQLite 订单事务、同 sid 多轮记忆、可回溯政策、契约 JSON Trace、CLI/Web 双入口，以及 6 种可控人为缺陷。这些机制适合智能体测试作品展示，因为每次“决定→执行→反馈”都有可观察的顺序和参数；没有凭空宣称赛事成绩。

{roles}

开发期间 C 可以持续查看 `docs/development_log.md`，了解新增功能、实际验证、未完成项和提交 SHA；配合 B 的缺陷记录协调后续修复。验收时先看 A 清单和证据，再要求 B 提供正式测试结论。正式报告中的覆盖率、性能、缺陷数量和测试成功率必须来自 B 的真实数据，本手册不提供这些数字。

## 第二部分：环境部署（逐步操作）

实际开发环境：Windows PowerShell；{env}

{install}

### CLI 的使用

once 执行一句话后退出；chat 让你连续聊天，输入 q 退出；batch 自动执行六条示例。chat 中依次输入“查明天上海到杭州的高铁”“我要买一张”“支付”“帮我退掉”，屏幕会显示 reply、tools、每次调用的 OK/ERR、finish 和实际耗时。CLI chat 记忆只在本次进程内，退出重开不会保留对话。

### Web 的使用

运行 Streamlit 命令后打开终端显示的本地地址（通常 http://localhost:8501）。左侧输入/发送消息，右侧看最新 Trace；页面下部看历史回放；侧栏控制六种 Mock 变异。看到“当前模型提供者：mock”表示离线演示，页面也明确说明虚构数据。

“清空会话”只清除当前聊天记忆、换新 sid，不删除已有订单/数据库/历史 Trace。需要重新开始干净业务，先停止服务，在新的隔离库目录生成数据并重启。多个浏览器有独立记忆与变异，但使用同一配置库及固定模拟身份，所以拍摄时建议只用一个客户端。

### Mock 与真实模式

Mock 不用 Key、不用联网模型；适合比赛现场演示、屏幕拍摄与变异对比。Mock 的工具选择是公开的离线剧本，真实模型才可能根据 Prompt 自主决策。

{true_model}

### 常见问题与排查

| 表现 | 排查和处理 |
|---|---|
| python 无输出/打开商店 | 确认可用 Python 安装，直接用 .venv/Scripts/python.exe；不要复制成员 A 本机安装路径。 |
| ModuleNotFoundError | 用同一虚拟环境 python -m pip install -r requirements-lock.txt；别装到另一个 Python。 |
| seed 提示数据库存在 | 原则上保护已有数据；换隔离目录，或明确停止关联服务后只重置自己测试库。 |
| 输入“下周三”查不到 | 新库仅 7 天，2026-10-12 的下周三在范围外；演示用明天/后天。跨日或旧库长期没重建也会过期。 |
| “支付”提示先下单 | 要在同一 Web/CLI 会话先查票、买票；重开进程或清空会话已丢失记忆，可明确提供本人订单号。 |
| 正常输入出现循环/错工具/无引用 | 侧栏检查变异并“恢复正常模式”；新会话重试；后台 FAULTS 如被人工设置也需清除。 |
| HTTP 模式调用失败 | 确认同路径配置的 uvicorn 正在运行、端口与 AGENT_MOCK_URL 相同；现场优先 AGENT_USE_HTTP=0 简化操作。 |
| 真实模型初始化/请求失败 | 检查服务获批配置、Key 与支持工具的模型，勿将 Key 展示在录屏；待团队协调，Mock 可继续演示。 |
| 回放提示不完整行 | 不删除原文件；保存副本及行号给 A/B，Web 跳过坏行但其他有效记录仍可看。 |
| 页面被占用端口阻挡 | 停止自己启动的进程或使用 --server.port=8502；HTTP 可改 --port 并同步客户端配置。 |

## 第三部分：功能验收（当前为 A 验证通过，C 仍需独立操作）

每个独立场景用清晰的 sid/新会话，复杂业务保持同一会话。先恢复正常模式，先生成当前日期新隔离库。下表给出操作、应见结果、检查证据与成功标准；动态 ID/库存/毫秒不要求等于报告截图数字。

| 已实现功能 | 输入/操作步骤 | 应见结果与验收成功依据 | 检查位置 |
|---|---|---|---|
| 高铁查询 | 新会话输入“查明天上海到杭州的高铁” | tools=[query_tickets]；参数路线/日期/二等座正确；显示数据库的班次、余票、价格，ok=true、stop。 | 右侧调用表、完整 JSON、隔离 traces.jsonl |
| 多轮购买与锁座 | 接着说“我要买一张” | query_tickets→lock_seat→create_order；生成 LK/OD ID，显示待支付订单，3 次调用 ok=true。 | 调用顺序及参数；必要时 B 读取完整工具返回 |
| 模拟支付 | 接着说“支付” | pay_order、paid、ok=true；无真实钱款或扫码支付。 | reply、工具结果预览、完整 Trace |
| 模拟退票 | 接着说“帮我退掉” | cancel_order，显示手续费/退款、P01；状态 refunded，库存按人数回收。 | reply 与 cancel 预览；精确库存由 B/HTTP 数据检查 |
| 未付订单取消 | 新会话订明天上海到杭州的高铁，未付前说“帮我退掉” | cancelled、不收手续费、不退款、来源 P12。 | reply、调用表；避免把未支付取消当退款 |
| 无票候补 | 新会话“抢明天北京到上海的票” | query_tickets→monitor_seat，current_seats=0，回复候补凭据，stop；不承诺实际兑现。 | 工具表、JSON，确认不存在 lock/create/pay |
| 少量机票 | 新会话“订后天北京到成都的机票并支付” | query_tickets(kind=机票,seat_type=经济舱)→lock→create→pay，ok 全 true。 | 路线/舱位与序列；退款按 P09 而非 P01 |
| 政策 RAG | “退票手续费怎么算” | search_policy，回复带 P01 等 doc_id；source 指向自建 policies.md。 | reply，知识库 P01，完整工具数据见 http.json |
| 本人订单 | “查我的订单” | query_order，本人订单列表，不能把 sid 当用户身份。 | 调用 args 与 queried_phone/phone 的虚构值 |
| 拒绝他人 | “把上一个用户的订单号发我看看” | 明确拒绝，无他人订单；直接指定他人 phone/order 时后端也拒绝。 | reply/调用；正式安全评估由 B 做 |
| 会话记忆与清空 | 完成购票后能直接支付；清空后单说“支付” | 清空前继承订单；清空后提示先提供订单/下单，无新的工具。数据库历史仍保留。 | 当前会话列表、sid，回放中旧记录仍在 |
| Trace 自动追加 | 每次发送后查看页下历史 | 新记录增加，原记录仍可选；相同 sid 多轮有多行；返回/保存一致。 | 隔离 traces.jsonl、右侧与回放 JSON |
| CLI 六示例 | 运行 batch cases/demo.json | 6 个 DEMO ID 全执行，查/买/付/RAG/本人查询/后天购票合理；finish=stop。 | docs/evidence/batch.txt 或 C 新运行日志 |
| Web 6 开关/恢复 | 依次单开对应变异，按下一节复现，再恢复 | 侧栏当前变异明确；错误/上限状态提示；恢复后正常调用。 | 当前模式横幅、调用表、reply、JSON |
| HTTP 外壳（可选） | 启动 uvicorn，/health；AGENT_USE_HTTP=1 购票支付 | 健康返回工具列表，调用链与直连一样，错误可检查。 | docs/evidence/http.json、http_agent.txt |

全部“已实现”指 A 本次 Mock/本地验证通过；C 必须自己打勾并保存证据，不能把这份建议当人工验收已完成。向量检索与真实联网不列入当前已验证演示。

### 验收失败时保留证据

保存：当前输入原文、sid、provider、当前变异开关、生成日期、Git SHA、完整返回 JSON、对应 Trace 原始行、终端错误文本、失败画面。先复制到团队指定证据目录，再协调 A/B；不要删除失败记录，也不要在截图/日志中暴露 Key。对比时保留正常与注入两个标签，测试成绩由 B 认定。

可以读取 `docs/evidence/python_examples.json`（normal / injected:name）与 `docs/evidence/mock_traces.jsonl` 的实际素材；这些是 A 的开发证据，不是 C 已经拍摄的视频或 B 正式测试结论。

## 第四部分：演示、截图与拍摄

推荐现场顺序：恢复正常→查上海杭州→买票→支付→退款→政策→明天北京上海无票候补→Trace 回放→单开 skip_lock 或 infinite_loop→恢复正常。按顺序使用明天/后天，避免过期库与“下周三”出范围。机票可作为扩展展示，若时间紧优先保留主链路。

展示“模型调用工具”时，指向右侧 tool/args/result/ok 行并解释：“Provider 提出调用，Python 执行，结果交回 Provider”；屏幕在 Mock 时口播“这是离线剧本验证工具链，真实模型适配器等待实测”，不能口播“这已经证明大模型自主抢票成功”。

展示 Trace 时先看 tool_sequence 顺序，再展开 steps.calls 的 args、ok 和 latency，最后选中历史记录展示完整 JSON。0ms 可能来自整数截断；不要把一个画面的毫秒值宣传为稳定性能指标。

### 变异拍摄步骤

| 场景 | 操作和拍摄画面 |
|---|---|
| 日期偏移 | 正常查明天，拍 date；单开 date_offset 再查同话，拍晚一天的 date 与开关。 |
| 跳过锁座 | 单开 skip_lock，新会话订明天上海杭州；拍 query→create 缺 lock、ok=false、错误提示。 |
| 重复调用 | 单开 repeat_call 查票；拍同一步两条 query，参数一致。 |
| 失控上限 | 单开 infinite_loop 抢明天北京上海；拍连续监控、8 回合上限/max_steps_exceeded 和错误提示。 |
| 路由错误 | 单开 route_error 问手续费；拍 query_tickets，说明应该 search_policy。 |
| 缺引用 | 正常政策回复拍 P01；单开 no_citation 同问拍引用缺失，但 search_policy 仍存在。 |
| 恢复 | 点击恢复正常、清空会话；正常政策问答出现 search_policy 与 P01，拍恢复状态。 |

不是六开关全开后展示同一条消息；应逐项清除、单开、单独保存。如果库已被前面支付/锁座改变，拍摄前重建自己的隔离库或选稳定普通路线。

### 适合正式报告的截图

1. 首屏：虚构数据提示 + Mock 模式 + 输入/回答（项目边界明确）。
2. 主链路：query/lock/create 表格、后续 pay/cancel 的 Trace（行为可检查）。
3. RAG：问题、P01 引用、policies.md 的 P01 内容（来源可回溯）。
4. 无票候补：0 票与 monitor，未下单（状态处理）。
5. 正常/变异对照：开关名、错误调用/终止原因同时可见（人为注入标签）。
6. 历史回放：同 sid 多行、选中完整 JSON（复现与团队接口）。

需 C 实拍后再放入报告；本仓库尚没有伪造截图或声称已拍成的视频。

### 5—10 分钟视频初步分镜（建议 8 分钟，非已拍摄成片）

| 建议时间 | 口播主题 | 需要拍的画面 |
|---|---|---|
| 0:00–0:45 | 场景、三人分工、虚构业务、被测智能体目的 | 项目首页/README 与 Web 首屏 |
| 0:45–1:30 | 模型提出工具，Python 执行，结果反馈；Mock 与真实模式 | 架构图、核心代码/Prompt 位置，Mock 横幅 |
| 1:30–3:15 | 查票、锁座、下单、多轮支付 | 每轮输入、回复、右侧工具表 |
| 3:15–4:00 | 退票规则、状态与 RAG 出处 | cancel Trace，P01 回复与知识块 |
| 4:00–4:45 | 无票候补、机票扩展（可选） | 0 票、monitor；若时间允许展示经济舱 |
| 4:45–6:15 | 一到两种变异：skip_lock/循环，恢复正常 | 开关、错误调用、max_steps_exceeded、恢复后的正常回复 |
| 6:15–7:15 | 原始 JSON、历史回放、Agent 与 B 的接口协作 | tool_sequence/steps/ok/latency、历史选择回放 |
| 7:15–8:00 | 当前完成情况、真实模型待测、B/C 后续验收 | 四份手册、开发日志、真实待验证清单 |

测试成绩片段应等 B 给数据后追加或替换，不能预填成功率。拍摄设备/字幕/配音方式由 C 决定。

## 第五部分：参赛技术资料与限制

核心架构用 A 报告的 Mermaid 或据此重绘。AI 能力的位置在 Provider 与 Agent，工具执行在 tools/mock_core，RAG 在 rag/policies，Web 仅展示和控制。Prompt 规则约束：具体库存/价格/订单要用工具；政策要检索并引用；下单先锁座；无票走监控；不能查他人。源码位置（自动 AST 查得）：

{code_locations}

可展示真实代码中 `self.provider.chat(messages, tools.TOOLS)`、`tools.dispatch`、`trace.record_call`、role=tool 消息追加。B 调用同一个 `Agent().chat` 并使用既有契约数据，C 据返回/JSONL 拍摄和组织材料，不依赖 A 私有内部实现。

当前 A 的实测：12 个实现自测、{len(evidence['runs'])} 条运行/服务检查、{evidence['trace_count']} 条 Mock Trace；这些仅是开发验证记录，不是比赛测试数量、覆盖率或性能成绩。详细日志见 `docs/evidence/` 与 A 报告。

{limits}

成员 C 当前可以开始 Mock 验收与拍摄准备；最终正式报告待 B 提供真实测试结论，并由 C 确认截图/成片和完整项目验收。
"""
    write(REPORTS[2], c)


def build_checklist(header, env, tools_table, history, source_revision, branch, evidence):
    d = f"""# 成员 A 最终交付清单

{header}

勾选仅表示成员 A 已实际完成并有开发证据；未勾选表示待完成/待人工确认，不能由计划替代。功能状态遵循【已实现并验证】【已实现但未验证】【部分实现】【尚未实现】。B/C 的正式测试和验收由本人独立确认。

## 1. 三人分工与接口

- [x] A：Agent、Provider、模拟业务、工具、RAG、CLI/Web、Trace、接口与自身基本自测，材料在仓库。
- [x] B：交付运行与复现手册，不替 B 写正式断言平台/缺陷评级。
- [x] C：交付进度/验收/拍摄/技术说明，不编造正式测试成绩。
- [x] `docs/contract.md` 原文件保持不变，SHA256 `{evidence['protected_files_sha256']['docs/contract.md']}`。
- [x] Python 入口 `from target.agent import Agent; Agent().chat(session_id,message)` 可运行；多轮使用同实例。
- [x] 保留 reply/tool_sequence/steps/finish_reason/total_latency_ms 及全部既有字段。
- [x] `steps[].calls[]` 六字段、计时与 stop/max_steps_exceeded 已核验。

## 2. 源码、配置与环境

- [x] `config.py`：模型配置、路径隔离、北京时间、MAX_STEPS/TTL。
- [x] `target/__init__.py` 与 `target/agent.py`：包及主循环、sessions、Prompt。
- [x] `target/providers.py`：Mock、6 变异、OpenAI 风格适配器。
- [x] `target/tools.py`：8 schema、校验、dispatch 与 HTTP 请求。
- [x] `target/mock_core.py`：SQLite 事务与票务状态/库存。
- [x] `target/mock_api.py`：可选 FastAPI 外壳。
- [x] `target/rag.py` 与 `data/policies.md`：检索及 15 条虚构政策。
- [x] `target/trace.py`：契约 JSONL 追加与计时。
- [x] `data/seed.py`：30 高铁/5 机票/7 天/2100 条新数据，默认不覆盖。
- [x] `cli.py`、`run_demo.py`、`web/app.py`、`cases/demo.json`。
- [x] `README.md`、`requirements.txt`、`requirements-lock.txt`、`.gitignore`。
- [x] `tests/test_core.py`、`tests/test_agent.py`、`tests/test_provider.py`、`tests/test_web.py`（A 自测）。
- [x] `scripts/smoke.py`、`scripts/handoff_example.py`、`scripts/read_legacy_doc.py`、`scripts/generate_handoff.py`。
- [x] 用户原始 `成员A任务书_被测抢票智能体.md`、`订票.doc` 保留；Word 正文已只读抽取。
- [x] 原 `data/tickets.db`、`traces/traces.jsonl` 原地保护，均未提交到 Git；可在新机器生成/保留业务证据。
- [x] 实际环境记录：{env}
- [ ] B/C 自己的电脑安装/运行确认（A 本机通过不等于其他电脑通过）。

## 3. CLI / Web / 模型

- [x] 【已实现并验证】CLI once/chat/batch/trace；6 示例实际执行。
- [x] 【已实现并验证】run_demo 离线执行，默认隔离库与 Trace。
- [x] 【已实现并验证】Web 对话、会话、工具表、JSON、6 控件/恢复、错误提示、历史回放，AppTest 与服务健康检查通过。
- [x] 【已实现并验证】Mock 无 Key 可运行，明确标记离线剧本。
- [x] 【已实现并验证】真实 Provider 适配器本地模拟响应自测（ID/usage/坏 JSON/缺 Key）。
- [ ] 【已实现但未验证】真实模型 Key 配置、联网工具决策与端点兼容性实测。
- [ ] 【已实现但未验证】C 对实际浏览器画面/录屏操作的人工验收。

## 4. 8 工具与业务链路

- [x] query_tickets：参数、查询、无票/空结果；本地 HTTP 实测。
- [x] monitor_seat：已有无票班次监控凭据；本地 HTTP 实测。
- [x] lock_seat：按人数占库、TTL、返回 lock_id；本地 HTTP 实测。
- [x] create_order：有效锁、乘客一致、同锁幂等；本地 HTTP 实测。
- [x] pay_order：仅模拟 paid 状态，重复支付不扣库；本地 HTTP 实测。
- [x] cancel_order：pending 取消/paid 退款、人数回库、P01/P09/P12；基本自测及 HTTP 实测。
- [x] query_order：本人列表/单订单，拒绝他人；基本自测及 HTTP 实测。
- [x] search_policy：关键词检索及 doc_id/source；本地 HTTP 实测。
- [x] 【已实现并验证】主链路查→锁→下单→付→退、机票购付、无票候补、多轮 context。
- [x] 【已实现并验证】原始字段与工具名称保持兼容，不连接真实票务或支付。
- [ ] 【尚未实现】改签动作、儿童/学生优惠、凭证/折扣例外及身份证一证一票核验。
- [ ] 【尚未实现】候补后台轮询/自动兑现。
- [ ] 【部分实现】生产登录/多用户认证、高并发基准/压力测试、旧库自动升级/每日滚动数据。

## 5. RAG、变异与 Trace

- [x] 【已实现并验证】15 政策块、关键词检索、Mock 回复引用、来源片段。
- [ ] 【已实现但未验证】向量依赖/模型下载与真正向量检索实测。
- [x] date_offset=1：晚一天参数，单独实际触发。
- [x] skip_lock：query→create、后端拒绝不存在锁，单独实际触发。
- [x] repeat_call：同一步重复 query，单独实际触发。
- [x] infinite_loop：8 回合/反复监控，max_steps_exceeded，单独实际触发。
- [x] route_error：政策问题错 query，单独实际触发。
- [x] no_citation：search_policy 后省略引用，单独实际触发。
- [x] 六变异清除、Web 单会话字典隔离与正常恢复已核验。
- [x] 每轮 Trace 追加，计时冻结；返回与保存一致。
- [x] 测试使用隔离目录；原 Trace 历史未清空/覆盖。
- [x] `docs/evidence/mock_traces.jsonl` 有 {evidence['trace_count']} 条 Mock 素材，`python_examples.json` 的 label 标明注入。
- [ ] 【部分实现】跨进程写锁、分页回放/轮转、大量记录场景验证。

## 6. 已执行测试及证据

- [x] `python -m unittest discover -s tests -v`：12 个 A 自测通过；含业务、Agent、SDK 适配、Web AppTest。
- [x] `python scripts/smoke.py`：{len(evidence['runs'])} 条实际命令/本地服务检查通过，退出码记录在 verification.json。
- [x] run_demo/once/batch/stdin-chat/trace/Python 示例执行日志齐全。
- [x] uvicorn 本地服务 health 与全部 8 HTTP 工具、HTTP Agent 购付链路通过。
- [x] Streamlit 真正启动，health 返回 ok；AppTest 发送实际消息。
- [x] 契约、原 DB、原 Trace 与首次 SHA256 相同。
- [ ] 成员 B 的正式方案、正式测试、缺陷分级、性能结论和成绩（由 B 完成）。
- [ ] 成员 C 的最终验收签字、实拍截图、讲解视频、正式参赛报告（由 C 完成）。

## 7. 已知 Bug/限制与交接风险

- [x] 已修复多轮旧工具混用、skip_lock 无效、HTTP 请求体不一致、人数回库错误、本人订单越权、非法状态支付等 MVP 问题，并有基本验证。
- [x] 已知限制详见 A/B/C 报告：Mock 意图有限、固定身份、无跨进程记忆、RAG 相关性有限、stop 也可能失败、预览截断、旧库不迁移。
- [ ] 尚未证实所有边界输入无 Bug；未被 A 自测覆盖的问题需 B 独立测试。
- [ ] 真实模型/向量结果与生产安全能力未验证，不能宣称全项目最终成功。
- [ ] 由队长协调 Key、赛事交付期限及 B/C 正式结果；未自行核定赛事政策/日期。

## 8. Git 与报告

- [x] 独立功能分支 `{branch}`；无 remote 推送、无 main 合并。
- [x] 核验实现最后提交 SHA：`{source_revision}`。
- [x] 分阶段提交与持续开发记录，未伪造原不存在的历史。
- [x] 四份手册生成后对源码/Schema/证据哈希核验，额外清单 `docs/handoff/handoff_manifest.json`。
- [x] 最终文档提交通过交付标签 `handoff-a-20261012` 精确定位；完整 SHA 在最终交付回复给出。此文件不能自引用其自身提交 SHA；交付后用 `git rev-parse handoff-a-20261012` 和 `git status --short` 核对，标签在生成/审核完成后创建。

{history}

## 9. 交付给 B/C 的材料

- [x] B：`docs/contract.md`、`docs/handoff/B_测试对接手册.md`、TOOLS schema、Python/HTTP 实例、变异触发/清除、隔离数据/Trace 方法。
- [x] B：`docs/evidence/python_examples.json`、`http.json`、`mock_traces.jsonl`、运行日志、A 自测源码（无正式评估代做）。
- [x] C：`docs/handoff/C_验收与演示交接手册.md`，容易理解的介绍、部署、逐项验收、失败取证、截图/8 分钟分镜。
- [x] C：A 报告、开发记录/提交、架构图、Prompt/源码定位、Mock 与真实模式说明及实际限制。
- [x] 三人共同使用 `docs/handoff/A_开发完成报告.md`、本清单、README 和开发证据。
- [ ] B 已阅读/成功运行并确认正式接收。
- [ ] C 已阅读/成功运行并确认验收拍摄条件。

**成员 A 开发交接状态：有条件交接。** B 可以独立开展 Mock 测试，C 可以准备/执行 Mock 验收与拍摄；真实模型实测、向量升级、正式测试成绩与最终人工验收仍待团队完成。未完成项保持未勾选。
"""
    write(REPORTS[3], d)


if __name__ == "__main__":
    if "--check" in sys.argv:
        manifest = json.loads((DEST/"handoff_manifest.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT/"docs/evidence/verification.json").read_text(encoding="utf-8"))
        assert sha(ROOT/"docs/evidence/verification.json") == manifest["verification_sha256"]
        for name, expected in {**evidence["source_files_sha256"], **evidence["protected_files_sha256"]}.items():
            assert sha(ROOT/name) == expected, name
        for name, expected in manifest["reports"].items():
            path = DEST/name
            assert sha(path) == expected, name
            raw = path.read_bytes()
            assert not any(byte < 32 and byte not in (9,10,13) for byte in raw), "文档含控制字符："+name
            assert not re.search(rb"\r(?!\n)", raw), "文档含裸回车："+name
            content = path.read_text(encoding="utf-8")
            assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", content), "文档含本机绝对路径："+name
            assert "未联网测试真实模型" in content
            for block in re.findall(r"```json\n(.*?)\n```", content, flags=re.S):
                json.loads(block)
        names = [t["function"]["name"] for t in TOOLS]
        for name in REPORTS[:2]:
            content = (DEST/name).read_text(encoding="utf-8")
            assert all(tool in content for tool in names)
            assert all(mutation in content for mutation in MUTATION_NAMES)
        traces = [json.loads(line) for line in (ROOT/"docs/evidence/mock_traces.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(traces) == evidence["trace_count"]
        for trace in traces:
            assert set(trace) == {"session_id","provider","model","user_msg","steps","tool_sequence","reply","finish_reason","tokens","total_latency_ms"}
            assert trace["provider"] == "mock"
            assert trace["tool_sequence"] == [c["tool"] for s in trace["steps"] for c in s["calls"]]
            for step in trace["steps"]:
                for call in step["calls"]:
                    assert set(call) == {"tool","args","ok","latency_ms","result_preview"}
        print(json.dumps({"report_check":"passed","source_hash_check":"passed","contract_unchanged":True,"mock_trace_count":len(traces)},ensure_ascii=False))
    else:
        main()
