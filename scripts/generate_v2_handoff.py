"""根据实际源码、Git 和 A 运行证据生成新的 V2 手册，拒绝覆盖已有文档。"""
import argparse
import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT/"docs/evidence/v2"
NAMES = ["A_V2开发完成报告.md", "B_V2测试对接说明.md", "C_V2验收演示说明.md",
         "V1_V2缺陷修复对照.md", "A_V2最终交付清单.md"]


def read(name):
    return json.loads((EVIDENCE/name).read_text(encoding="utf-8"))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"docs/handoff")
    args = parser.parse_args()
    source = git("rev-parse", args.source_commit)
    branch = git("branch", "--show-current")
    baseline = read("v1_snapshot/manifest.json")
    regression = read("regression/verification.json")
    audit = read("audit_first.json")
    v1, v2 = read("v1_reproduction/observations.json"), read("v2_reproduction/observations.json")
    preflight = read("real_preflight/preflight.json")
    api = read("api_example/results.json")
    assert audit["unit_tests_passed"] == 28 and audit["tools_schema_unchanged"]
    assert all(audit["mutations_observed"].values()) and not preflight["real_model_tested"]
    assert all(o["a_observed_target_satisfied"] for o in v2["observations"])
    commits = [line.split("\t", 1) for line in git("log", "--reverse", "--format=%H%x09%s", baseline["baseline_head"]+".."+source).splitlines()]
    commit_table = "\n".join(f"| `{sha}` | {title} |" for sha, title in commits)
    fixes = {f"DEF-{i:02}": next(sha for sha, title in commits if f"DEF-{i:02}" in title) for i in range(1, 6)}
    changed = git("diff", "--name-only", baseline["baseline_head"], source).splitlines()
    changed_code = "\n".join("- `"+p+"`" for p in changed if p.endswith(".py"))
    versions = "、".join(f"{k} {v}" for k, v in regression["versions"].items())
    schemas = None
    for node in ast.parse((ROOT/"target/tools.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in node.targets):
            schemas = ast.literal_eval(node.value)
    returns = {
        "query_tickets": "trains/count；行含 kind、seat_type、seats_left、价格/路线/班次",
        "monitor_seat": "task_id/status/duration_min 等监控凭据（无后台监控守护进程）",
        "lock_seat": "lock_id/expire_at/ttl_seconds；unit_price/count 和锁座信息",
        "create_order": "order_id/status/amount/train_no/date；重复创建标记可能返回",
        "pay_order": "order_id/status；重复支付另有 duplicate_pay=true",
        "cancel_order": "status；已支付退款含 fee/fee_rate/refund/policy_ref，未支付直接取消",
        "query_order": "指定 ID 返回单个订单；按本人查询返回 orders 列表",
        "search_policy": "hits；每条含 doc_id/content/score",
    }
    http_results = {call["tool"]: call["result"] for call in read("regression/http.json")["calls"]}
    tool_table = []
    for schema in schemas:
        func = schema["function"]
        params = func["parameters"]
        required = params.get("required", [])
        optional = [k for k in params["properties"] if k not in required]
        observed_fields = ", ".join(http_results[func["name"]])
        tool_table.append(f"| `{func['name']}` | {', '.join(required) or '无'} | {', '.join(optional) or '无'} | {returns[func['name']]}；本次 HTTP 实际字段：{observed_fields} |")
    tool_table = "\n".join(tool_table)
    run_table = "\n".join(f"| {r['name']} | `{r['command']}` | 0 | `{r['log']}` |" for r in regression["runs"])
    rows = []
    descriptions = [
        ("交通切换后席别未重置", "沿用二等座查询机票", "按 kind 校验席别，隐式旧席别重置；显式冲突先澄清", "显式席别冲突现在无工具调用，B 需接受澄清语义"),
        ("机票不能切回高铁", "第三轮仍查询机票", "明确方式覆盖、省略沿用、含糊澄清；路线日期只覆盖明确部分", "复杂否定与城市别名仍受 Mock 规则限制"),
        ("无票回复不准确", "0 票行也被统一列为查询成功", "按库存区分售罄/可售/空匹配；建议其他席别但不承诺余量", "没有增加其他席别工具调用；是否要主动查询需 B 确认需求口径"),
        ("重复支付话术错误", "duplicate_pay=true 仍说支付成功", "读取已有幂等标记，明确已支付且没有重复扣款", "只验证虚构后端，没有真实资金流水"),
        ("支付政策咨询误路由", "支付关键字挡住政策检索", "咨询走 search_policy 并引用；明确支付/取消才允许操作", "保守规则可能对未列出的自然问法要求澄清；真实模型尚未验证"),
    ]
    for i, (name, old, new, risk) in enumerate(descriptions, 1):
        code = f"DEF-{i:02}"
        observation = next(o for o in v2["observations"] if o["defect"] == code)
        rows.append(f"| {code} / {observation['b_case_id']} | {name}：{old} | {new} | A Mock 复现目标通过；待 B 确认 | `{fixes[code]}` |")
    fix_table = "\n".join(rows)
    common = f"""生成日期：2026-10-13（Asia/Shanghai）。分支：`{branch}`。
经过回归的源码提交：`{source}`；本手册是该源码之上的文档提交。
最终交付提交用 `git rev-parse HEAD` 确认；交付标签计划为 `handoff-a-v2-20261013`，仅在检查通过后建立，解析标签可得到最终 SHA，避免文档声称包含自身的提交哈希。
V1 标签保留：`{baseline['v1_tag']}` → `{baseline['v1_tag_sha']}`。
所有运行结果均为 A 自测；业务虚构。成员 B 报告的 V1 95/100 是其提供的结论，A 未获得完整 judge/用例/原始 execution.jsonl，不能宣称 V2 正式 100/100。
"""
    setup = r"""```powershell
# 在项目根目录执行；新机器先建立环境并安装冻结依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$v2Run = "v2-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0,6)
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\$v2Run\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\$v2Run\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe cli.py chat
```

已有虚拟环境时跳过前两条；系统 python 若打开商店，改用已安装 Python 3.12 的实际可执行文件建立环境。`seed.py` 遇到已有库拒绝覆盖，新目录无需 --reset。每次全新独立用例换新运行目录，环境变量在导入 config 或启动程序前设置。
"""
    commands = r"""```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke.py
# 输出目录必须不存在；时间后缀避免覆盖历史
$v2Evidence = "artifacts/runtime/v2-proof-" + [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts/reproduce_v2_defects.py --output-dir "$v2Evidence/defects" --label "v2-local-rerun"
.\.venv\Scripts\python.exe scripts/v2_api_example.py --output-dir "$v2Evidence/api"
.\.venv\Scripts\python.exe scripts/validate_real_provider.py --output-dir "$v2Evidence/real-preflight"
```
"""
    real = r"""当前没有 API Key。`preflight.json` 明确 api_key_present=false、real_model_tested=false、real_trace_count=0：**真实模型待验证**。

已实现 OpenAI 风格 Chat Completions 适配器，SDK 测试桩检查调用 ID/工具结果回传、错误和最大步数，不能算模型自主决策测试。Prompt 已增加 V2 规则，第三方端点是否支持全部协议需实测。

有合法有效 Key 时，由使用者通过安全环境注入 `AGENT_API_KEY`，不要写入源码、文档、录屏或聊天。配置 `AGENT_PROVIDER=openai`、服务方提供的 `AGENT_BASE_URL` 和支持工具调用的 `AGENT_MODEL` 后，重启进程并显式运行：

```powershell
$v2Real = "artifacts/runtime/real-" + [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts/validate_real_provider.py --output-dir $v2Real --run
```

这是实际远端 API 调用，可能产生服务方费用。没有 --run / 没有 Key / provider 不是 openai 时仅预检。8 个独立场景覆盖单轮、多轮交通切换、工具回传、查锁下单、RAG、工具故障、正常停止、强制 MAX_STEPS=1；每个场景使用临时虚构库。上限场景是人为缩小步数的验证，不能据此称模型自然死循环。
每个 result.json 保存输入、完整消息（含工具参数/结果和服务器 call_id）、实际回复/Trace、耗时、调用错误与“完成情况待确认”；finish_reason=stop 不保证业务成功。模型认证/网络失败也会保存失败回复，不能当作成功。Mock 与真实附件放在不同目录，不与 V1 Trace 混用。
协议参考：[OpenAI Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。本次未迁移 API 或新增契约字段。
"""
    a = f"""# 成员 A：Ticket Agent V2 开发完成报告

{common}

## 开发范围与实际成果

项目用于智能体测试比赛：在可控的虚构票务环境中观察工具选择、参数、顺序、多轮状态及异常处理。A 负责被测 Agent/Provider/8 工具/模拟业务/RAG/CLI/Web/Trace 和本模块自测；B 负责正式用例、断言、指标、缺陷判定；C 跟进问题、最终验收、报告与录屏。

V2 沿用 V1 的架构，逐项修复 5 个报告缺陷，没有重写业务、测试层或契约。

| 状态 | 实际内容 | 证据或限制 |
|---|---|---|
| 【已实现并验证】 | DEF-01..05 的 Mock 行为修复 | 13 个缺陷自测 + 五个同输入复现目标通过 |
| 【已实现并验证】 | 原入口、8 工具、主循环、CLI、HTTP 模拟服务、默认 RAG、Trace | 28 自测、10 项冒烟、32 Mock Trace；工具 Schema 不变 |
| 【已实现并验证】 | Web 对话、回放、变异恢复及本地启动 | Streamlit AppTest + health；人工验收仍待 C |
| 【已实现并验证】 | 六变异保留、V1 文件保护与证据隔离 | audit_first.json；25 原文件哈希一致 |
| 【已实现并验证】 | 真实 Provider 本地传输适配与预检入口 | 3 项新增 SDK 桩检查；远端调用未执行 |
| 【已实现但未验证】 | 真实远端模型 Function Calling / V2 Prompt 的模型遵守效果 | 无 Key，待验证；不等于 Mock 结果 |
| 【已实现但未验证】 | 可选本地向量 RAG 分支 | 当前默认字/词重叠打分；未装模型做实测 |
| 【部分实现】 | 候补监控与身份控制 | 仅任务凭据、固定模拟用户；无持续监控/生产登录 |
| 【尚未实现】 | 实际票务/资金/改签、B 正式 V2 评价、C 最终作品与录屏 | 前两项业务不在本次模拟范围；后两项由 B/C 负责 |

## 架构与核心代码说明

CLI/Web/Python → Agent.chat → Provider.chat → 工具调用 → dispatch 校验 → mock_core/HTTP 或 RAG → 工具结果回传 Provider → 最终回复与 Trace 追加。默认 MAX_STEPS=8；每轮可有多个工具调用，工具次数不等于模型步数。

`target/agent.py` 保留主循环：接收消息、维护 session 历史、累计工具步骤、把结果以 tool_call_id 交还模型、停止或截断；SYSTEM_PROMPT 是行为约束，不是正确性的形式保证。
`target/providers.py`：Mock 是规则剧本，OpenAIProvider 才请求远端模型。`_transport_kind` 处理明确选择/省略继承/含糊澄清；`_seat_for_kind` 避免二等座混入机票；`_write_intents` 和 `_policy_question` 区分咨询与操作；`_summarize` 按真实工具结果区分售罄和幂等支付。
`target/tools.py`：原 Schema 不变，在 dispatch 的既有校验通路中新增 kind/seat_type 一致性检查，异常继续用 error/ok=false 表示。
`target/mock_core.py`、`target/rag.py`、`target/trace.py` 在 V2 未修改。SQLite 事务/锁座有效期/幂等订单和支付沿用 V1；RAG 按政策段落 doc_id 分块并以字/词重叠排序，返回 TOP_K=3；不是 BM25，也不是本次验证过的向量检索。
Trace 每次 chat 保存一行 JSONL，默认 traces/traces.jsonl，可用 AGENT_TRACE_DIR 隔离；耗时用 perf_counter，单位整毫秒，不包括写盘耗时。Mock tokens=0；model 字段的默认名称不代表调用过该真实模型。

## 五项修复及对应提交

| 缺陷/用例 | V1 现象 | V2 最小修改 | 实际状态 | 源码提交 |
|---|---|---|---|---|
{fix_table}

根因、逐轮实际回复与风险见 `V1_V2缺陷修复对照.md`。DEF-03 未增额外工具调用；DEF-04 沿用已存在 duplicate_pay 字段；DEF-05 不把关键字直接当作写操作授权。

## 文件位置与职责

| 文件/目录 | 职责 |
|---|---|
| config.py / requirements*.txt | 环境开关、模型配置与实际依赖冻结 |
| target/agent.py / providers.py | 主循环、会话和两种模型提供者 |
| target/tools.py / mock_core.py / mock_api.py | 工具 Schema/校验、模拟票务业务、可选 HTTP |
| target/rag.py / data/policies.md | 政策检索与虚构知识库 |
| target/trace.py / data/seed.py | 执行记录、隔离模拟库初始化 |
| cli.py / web/app.py / run_demo.py / cases/demo.json | 命令行、网页、离线演示与原示例输入 |
| tests/test_v2_defects.py | 13 个 V2 缺陷自测；每例独立库/Trace |
| tests/test_v2_provider.py | 3 个 SDK 桩自测，不是远端模型测试 |
| scripts/reproduce_v2_defects.py | B 五个报告输入的 A 对照观察，冻结业务日期 |
| scripts/run_v2_selftests.py / smoke.py | 实际运行日志与全入口冒烟；拒绝覆盖证据 |
| scripts/validate_real_provider.py / v2_api_example.py | 真实预检/显式验证、经过运行的原 API 示例 |
| scripts/audit_v2_evidence.py / generate_v2_handoff.py / check_v2_handoff.py | 哈希/契约审计、实际资料生成 V2 文档、再生成与 JSON/示例一致性检查 |
| docs/contract.md | 原团队契约，未修改 |
| docs/v2_development_log.md / docs/evidence/v2/ | 连续 V2 开发记录、复现与验证原始证据 |
| docs/handoff/*_V2*.md / V1_V2缺陷修复对照.md | A/B/C 新交接材料；V1 文档仍保留 |

本轮源码/脚本修改由 Git 自动整理（相对于 V2 接手起点）：

{changed_code}

文档生成脚本在本次交接文档提交新增。完整 V1 项目目录职责仍见原 `A_开发完成报告.md`，该历史报告不能当作最新 V2 成绩。

## 8 工具接口（由实际 Schema 整理）

| 工具 | 必填 | 可选 | 主要返回/语义 |
|---|---|---|---|
{tool_table}

任何失败通过既有 error 表示；长 result_preview 截断，不能假定能 json.loads；完整后端结果可查看 http.json 或 API 回传历史。

## 实际验证与证据

环境：Python {regression['python']}；{versions}。完整冻结见 requirements-lock.txt。
28 个 A 自测=保留 V1 12 + 新增缺陷 13 + SDK 桩 3。首次 DEF-03/05 开发自测失败日志保留，修正源码后复验通过，没有为通过而改 B 规则。

| 检查 | 实际执行命令（当时使用 .venv Python） | exit | 日志 |
|---|---|---|---|
{run_table}

其他真实执行：`run_v2_selftests.py --log docs/evidence/v2/full_unit.txt --pattern 'test*.py'`、`reproduce_v2_defects.py --output-dir docs/evidence/v2/v2_reproduction --label v2-after-fixes`、`v2_api_example.py --output-dir docs/evidence/v2/api_example`、`validate_real_provider.py --output-dir docs/evidence/v2/real_preflight`、`audit_v2_evidence.py --output docs/evidence/v2/audit_first.json`。
六变异仍按原入口开启：日期偏移 +1、跳过锁座、重复查询、候补循环直到 8 步、政策误路由、引用删除；详细实际参数/回复在 regression/python_examples.json。恢复开关后用新 Agent/会话/库，不能只换 session_id 隔离库存。

## 真实模型状态与限制

{real}

目前 5 个报告问题在 A Mock 复現与单元测试层已修复，但仍待 B 回归判定。Mock 自然语言是有限规则，不支持任意复杂否定、城市别名或多意图；保守写操作识别可能澄清。数据只覆盖初始化当天到后六天，旧库不会自动刷新。finish_reason=stop 也可能是错误回复；不能作为成功率。
后续建议：B 先独立确认五个 xfail 与售罄建议口径；配置真实工具调用模型后执行隔离验证；再按真实失败样本扩展 Mock 或 Prompt。向量检索/生产认证/持续候补是后续范围，不用来替代本次修复。

## Git 对应记录

| SHA | 实际提交内容 |
|---|---|
{commit_table}

成员 A 开发交接状态：**有条件交接**。被测 V2 的 Mock 运行与原契约可交给 B 独立回归，C 可验收/拍摄 Mock；正式测试成绩、真实模型段落和最终作品需相应责任人确认。
"""
    b = f"""# 成员 B：V2 测试对接说明

{common}

## 获取、安装与隔离启动

V2 使用独立分支 `{branch}`，不要把它覆盖到 V1 标签。仓库协作者获取已发布的 V2 分支后，先确认 `git log -1` 与交付标签；已有本地修改时先自行保留，再切换。测试层是否与此分支组合由 B 决定，A 没有复制 judge 或改正式断言。

私有仓库需要协作者权限；权限由团队协调，不共享访问令牌。新机器可运行 `git clone --branch feat/a-ticket-v2 https://github.com/8xbAdx8/ticket-agent.git` 后进入 ticket-agent。已有 checkout 可以 `git fetch origin --tags`、`git switch feat/a-ticket-v2`；已有同名本地分支时先检查差异，不能直接 reset 覆盖队友修改。最终交付标识用 `git rev-parse handoff-a-v2-20261013` 确认。

{setup}

CLI `once` 每次是新 Agent；多轮请用 `cli.py chat` 或同一个 Python Agent 实例与 session_id。CLI `batch cases/demo.json` 是已有演示用例，不是 B 的 100 用例。网页用 `.venv\\Scripts\\python.exe -m streamlit run web/app.py`。

## 已运行的 Python 入口与真实 JSON

直接执行 `scripts/v2_api_example.py --output-dir <新的证据目录>`。已运行版本在 `docs/evidence/v2/api_example/`，四轮序列为订票 query→lock→create、政策 search_policy、pay_order、重复 pay_order。
核心调用如下（先按上面的环境初始化独立库）：

```python
from target.agent import Agent
agent = Agent()
for message in ["订明天上海到杭州的高铁", "锁座后多久必须完成支付？", "支付我刚才的订单。", "支付"]:
    result = agent.chat("v2-api-example", message)
    print(result["tool_sequence"], result["reply"])
```

以下为该示例实际政策轮返回，未改字段或数值；运行时间及模型字段只是本机 Mock 记录：

```json
{json.dumps(api[1], ensure_ascii=False, indent=2)}
```

## 契约字段与判定注意

| 字段 | 原语义（V2 保持） |
|---|---|
| session_id / user_msg | 调用方 ID / 本轮原始输入 |
| provider / model | 提供者名称 / 配置模型名；Mock 默认模型名不证明真实调用 |
| steps | 模型工具步骤；step 从 1 起；无工具回复可为空 |
| steps[].calls[] | 每次调用的 **5 个字段**：tool、args、ok、latency_ms、result_preview |
| tool_sequence | 按 steps/calls 顺序扁平化的工具名列表，真实重复调用仍保留 |
| reply | 最终回复或错误说明；不能只看关键词/stop 判业务成功 |
| finish_reason | 无后续工具调用或模型错误处理时 stop；用完 MAX_STEPS 时 max_steps_exceeded |
| tokens | prompt/completion 累计；Mock=0，SDK 桩仅验证累加逻辑 |
| total_latency_ms | 进入 Trace 到 finish/abort 的 perf_counter 差值整毫秒，含模型/工具执行，不含保存 JSONL；不是工具耗时相加 |

calls.ok=false 表示 error/异常；模型返回错误仍可能 stop。result_preview 超过 200 字符会截断并加 ...，不能当作完整 JSON 解析。顶层仍是 10 个字段，无新 trace 嵌套，无新增 duplicate_pay 契约字段；重复标记来自已有 pay_order 后端结果。参数 Schema 与 V1 全部相同，仅 kind/seat 错配现在得到校验错误。
`Agent.reset` 清会话、不重置 SQLite；`清空会话` 不恢复库存/订单。不同测试独立 Agent+session_id+数据库+Trace目录；改变环境后重启或导入前设置 config；并行进程共享库仍会相互影响。

读取当前目录 JSONL 的例子：

```python
import json
from pathlib import Path
import config
for line in (Path(config.TRACE_DIR) / "traces.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        print(row["session_id"], row["tool_sequence"], row["finish_reason"])
```

原路径默认 traces/traces.jsonl，新测试应使用 AGENT_TRACE_DIR。出现坏行保存原文件并记录行号，不删除失败记录。

## 工具 Schema 与返回

| 工具 | 必填 | 可选 | 主要返回/语义 |
|---|---|---|---|
{tool_table}

成功返回随业务分支略有不同，以 tools.py、mock_core.py 和 regression/http.json 的真实响应为准；失败原结构 error 不变。席别与交通方式必须一致，日期 YYYY-MM-DD；订单只允许模拟本人，未对接真实支付。

## 六变异开关与恢复

推荐用实例级字典，不污染其他用例：

```python
from target.agent import Agent
from target.providers import MockProvider, clear_mutations
clear_mutations()
agent = Agent(MockProvider(mutations={{"date_offset": 1}}))
result = agent.chat("isolated-offset", "查明天上海到杭州的高铁")
# 恢复时新建正常实例，同时换全新库/Trace，不能沿用刚才错误日期的历史
normal = Agent(MockProvider(mutations={{}}))
```

既有全局方式 `set_mutation(name, True)` / `clear_mutations()` 保留，date_offset 使用值 1；clear_mutations 只清全局字典，实例自带字典需清空或换新实例。Web 开关仅本浏览器会话，“恢复正常模式”后“清空会话”，写业务测试还要换隔离库并重启。

| 开关 | 已观察行为 | 可检测缺陷维度 |
|---|---|---|
| date_offset=1 | 查询日期比正常值 +1 天 | 相对日期与参数准确性 |
| skip_lock | query→create，创建失败且没有 lock | 业务顺序/前置条件 |
| repeat_call | query_tickets 连续 2 次 | 重复调用/效率 |
| infinite_loop | query 后连续 monitor，8 步 max_steps_exceeded | 循环/最大步数 |
| route_error | 政策咨询改调用 query_tickets | 意图工具路由 |
| no_citation | search_policy 存在但回复无 doc_id | RAG 引用可检查性 |

这只是 A 提供可复现条件，不是 B 的正式判定规则/变异分数。六项实际证据见 regression/python_examples.json 与 audit_first.json。
重置业务时优先换新目录；若要清空自己已有隔离库，先停 CLI/Web/HTTP 并确认 AGENT_DB_PATH 指向该测试库，再 `data/seed.py --reset`。不要指向 V1 原始库。日期过期时也用新库；初始化覆盖当天和后六天。

## 回归入口与 B 下一步

{commands}

本仓库不存在 judge/ 或 B 原始 execution.jsonl。`python -m judge.executor` / `python -m judge.metrics` 没在 A 仓库执行；B 在自己的完整测试层中按原配置执行并保留新的结果目录。不要用 A 的 28 自测或 5 个观察目标替换正式 100 用例。

请重点重新确认 F03/M11/F14/F13/T25，连带多轮省略日期/路线/席别、含糊澄清、否定支付、取消咨询、复合订票支付、正常退票和所有六变异。**原五个 xfail 由 B 重新处理**：若修复已确认，应取消或更新预期失败条件，并检查 XPASS/strict 设置，避免把已修复成功用例统计为失败或漏算。不由 A 修改断言换通过率。
DEF-03 仅建议其他席别，明确尚未查询其库存；如果正式用例要求实际查出其他席别，需先对齐额外调用口径。本轮保持单次查询与原工具序列。

## 真实模式与限制

{real}

A 可交付稳定 Mock V2 和证据。正式通过率/覆盖率/缺陷关闭/耗时统计由 B 提供；目前全量正式 V2 成绩待确认。
字节 SHA256 审计用于 A 原始工作区的保护与证据绑定；换行转换会改变文件字节。跨机器先按 Git 提交/标签确认源码，再把新机器的运行证据另存，不能把换行造成的哈希差异当作 Agent 缺陷。
"""
    c = f"""# 成员 C：V2 验收与演示说明

{common}

## 项目是什么、实际 AI 在哪里

这是在虚构高铁/航班环境里运行的出行助手。它需要查库存、锁住座位、创建订单、查询政策，执行过程可追踪。相比只生成文字的聊天机器人，它会执行工具，并把工具结果用于下一步决策；测试比赛可以据此检查选错工具、错误参数、重复调用、忘记锁座、无来源回答等问题。
模拟环境让输入、库存与错误可重现，不涉及真实票务/资金。Mock 模式由人工规则决定动作，不能说它是实际大模型自主推理；真实模式由远端模型选择工具，当前没有 Key，尚未实测。RAG 帮助提供有编号的虚构政策依据。主循环/工具/业务与模型分开，测试层只读约定 JSON，便于三人并行。

## 环境部署

实际验证 Python {regression['python']}；{versions}，安装 requirements-lock.txt。以下在项目根目录的 Windows PowerShell 运行，不要把 Key 显示到镜头：

{setup}

退出 CLI 输入 q，再启动 Web：

```powershell
.\\.venv\\Scripts\\python.exe -m streamlit run web/app.py
```

首次出现 Email 可留空回车。浏览器打开终端给出的 localhost 地址；默认 8501。终端保持运行，Ctrl+C 停止。端口占用可加 --server.port=8502。页面顶部应该显示 mock，左侧变异“无”；Mock 不需要 Key。
找不到模块时确认在根目录、使用 .venv 的 Python；库已存在就换新目录；无票先看日期/路线/席别与真实 Trace，不能把所有空结果都当作缺陷；页面没有记录先发送消息，离线回放读取配置 Trace 目录，标题仍写默认 traces/traces.jsonl。

## 验收操作（以下功能均已通过 A 自测，人工逐步验收仍待你确认）

每一行发送文字后，检查右侧工具表、args、ok、完整 JSON；连续多轮保持同一会话。换场景可清空会话，但订单/库存不会随之恢复，购买场景重复太多时停服务、换全新运行目录并 seed。

| 场景 | 输入与顺序 | 应看到的结果 | 成功依据/日志 |
|---|---|---|---|
| 有票查询 | 查明天上海到杭州的高铁 | 列出有余票的班次 | query_tickets，kind=高铁/二等座，ok=true |
| 交通切换 | 上条后发送 那机票呢 → 还是高铁吧 → 后天呢 | 机票经济舱，再高铁二等座；后天沿用路线/方式 | 比较连续 3 条 trace 的 kind/seat_type/date |
| 含糊请求 | 换个交通方式 | 询问选择何种方式 | 不执行猜测查询；tool_sequence 为空 |
| 售罄提示 | 清空会话后：查明天北京到上海的高铁二等座 | 目标二等座售罄，建议查其他席别但不承诺有票 | 单次 query，结果余票 0，reply 区别于空匹配 |
| 无匹配 | 清空会话后：查明天上海到成都的高铁 | 没有符合条件班次 | query 返回空，不能说已售罄 |
| 订票 | 订明天上海到杭州的高铁 | 创建待支付模拟订单 | query→lock→create，均 ok，保存 order_id |
| 政策 | 上条后问 锁座后多久必须完成支付？ | 15 分钟并引用 P11 | search_policy，不能 pay/cancel |
| 重复支付 | 支付我刚才的订单。 → 支付 | 首次支付成功，第二次“订单已支付，本次没有重复扣款。” | 两次 pay，第二次预览 duplicate_pay=true |
| 取消与退款 | 在已支付订单后 帮我退掉 | 模拟退款并带政策来源 | cancel_order、手续费/退款/P01；不是实际资金退回 |
| 候补 | 清空会话后：抢明天北京到上海的票 | 虚构监控任务 | query→monitor，正常 stop；只生成凭据 |
| 订单查询 | 查我的订单 | 本人订单列表 | query_order，不能显示其他用户订单 |
| Trace 回放 | 页面下方选择回放记录 | 展示完整历史 JSON | 与发送后的 session/input/tools 相符 |
| 六变异 | 每次只勾一个，按 B 手册对应输入 | 看到日期错误/跳锁座/重复/循环/误路由/缺引用 | 对照 B 手册的实际序列；恢复后新会话 |

stop 只表示循环结束，操作成功还要看 ok、结果与回复。错误时截图保存输入、会话 ID、模式、开关、右侧 JSON；复制当前隔离目录的 traces.jsonl，注明对应行/日期、branch/SHA。保存失败证据，不编辑原记录。页面“完整 JSON”是最终契约记录，长工具预览可截断。

## 5—10 分钟视频分镜建议（这是建议，尚未拍摄）

| 时间 | 操作/画面 | 讲解重点 |
|---|---|---|
| 0:00–0:45 | 标题、模拟环境与团队分工 | A 被测 Agent，B 正式测试，C 验收作品；Mock 边界 |
| 0:45–1:30 | 展示启动命令和页面 provider=mock | 依赖冻结、独立库、零 Key 离线运行 |
| 1:30–2:45 | 查询→机票→高铁→后天 | V2 交通/席别和多轮继承修复，聚焦右侧参数 |
| 2:45–3:30 | 北京上海二等座售罄 | 不把 0 票当可售；其他席别只是待查询建议 |
| 3:30–5:15 | 订票→政策→支付→重复支付 | 工具顺序、政策 P11、模拟幂等；拍 reply+trace |
| 5:15–6:15 | infinite_loop 开关并抢无票班次 | max_steps_exceeded 及 monitor 重复，证明注入仍存在 |
| 6:15–7:00 | 恢复正常、清会话、正常政策检索 | 开关恢复后引用回归，保存独立记录 |
| 7:00–8:00 | 离线回放、V1/V2 对照和真实预检 | 真实待验证，B 正式 V2 成绩待提供 |

适合报告的截图：交通切换前后 args、售罄回复、P11 引用、重复支付 duplicate_pay、8 步截断、完整 Trace 回放、A 自测运行摘要。请截取你实际操作的画面，不能把本文建议称为已经验收/拍摄。
若要展示真实模型，先完成有效 Key 配置及真实隔离测试，再使用实际 trace；不得把 SDK 桩或 Mock 模型字段截图解释为真实模型性能。

## 参赛技术资料的位置与当前完成情况

- 架构和 8 工具：A_V2开发完成报告.md、target/agent.py、target/tools.py。
- Prompt：target/agent.py 的 SYSTEM_PROMPT；Mock/远端协议：target/providers.py。
- 政策与检索：data/policies.md、target/rag.py；支付后端：target/mock_core.py（V2 沿用）。
- 轨迹机制：target/trace.py；接口合作：docs/contract.md（未修改）。
- 五缺陷原因/提交/风险：V1_V2缺陷修复对照.md；过程：docs/v2_development_log.md。
- A 实际证据：docs/evidence/v2/regression/、v2_reproduction/、api_example/。
- 当前完成：A 28 自测、10 冒烟、32 Mock Trace、5 个对照目标及六变异通过；是 A 结果，不能换算 B 正式得分。

{real}

当前可做 Mock 验收与录屏；正式比赛通过率、测试覆盖率、性能指标和缺陷关闭数必须由 B 给出。C 结合 B 的真实回归结论形成最终作品，不能写“V2 已 100/100”。可选向量 RAG、生产登录、持续候补、真实支付/改签并非本轮完成项。
"""
    detail = []
    for i, (title, old, new, risk) in enumerate(descriptions, 1):
        code = f"DEF-{i:02}"
        before = next(o for o in v1["observations"] if o["defect"] == code)
        after = next(o for o in v2["observations"] if o["defect"] == code)
        inputs = " → ".join(before["inputs"])
        final = after["results"][-1]
        detail.append(f"""## {code} / {before['b_case_id']}：{title}

- 原输入：{inputs}。
- B 原始材料：根目录 B_缺陷分析报告.md、B的总结_测试层.docx；原始 B execution.jsonl 未提供。本库的 V1 复现由 A 在未修复代码上实际运行，不冒称 B 原 Trace。
- V1 现象：{old}。原结果在 `docs/evidence/v2/v1_reproduction/{code}/traces.jsonl`；汇总 observations.json 保存逐轮参数/回复。
- 原因与代码：见对应开发记录；修复位于 target/providers.py，DEF-01 还包括 target/tools.py 的既有参数校验。
- V2 修改：{new}。源码提交 `{fixes[code]}`；对应 tests/test_v2_defects.py 的 test_def{str(i).zfill(2)}_* 自测。
- V2 实际观察：工具序列 `{json.dumps(final['tool_sequence'], ensure_ascii=False)}`、finish_reason=`{final['finish_reason']}`；回复：“{final['reply']}”。对照目标 true。
- V2 证据：`docs/evidence/v2/v2_reproduction/{code}/traces.jsonl`；对应 observations.json。A 缺陷测试累计日志在 def0{i}_unit*.txt；最终回归 28 自测均通过。
- 新风险/限制：{risk}。
- 是否需要 B 确认：**是**。B 用原正式规则独立回归并重新处理该用例 xfail；A 未改 B 的评估标准。
""")
    compare = f"""# V1/V2 缺陷修复对照

{common}

## 证据可比性与保护

V2 接手点 `{baseline['baseline_head']}` 的运行核心与 V1 标签一致。先保存原文档/证据快照和 SHA256，再逐项修复；没有修改 V1 失败 Trace 或 95/100 报告。`v1_snapshot/manifest.json` 定义 25 个受保护原文件，audit_first.json 确認全部相同。
V1 与 V2 的 A 复现使用同样五个输入、各自独立模拟库、冻结业务日期 2026-10-13（锁座业务时刻 10:00），工具 Trace 耗时仍用实际 perf_counter。它们是可复现的 A 工程对照，不是 B 的正式基线/全量评估。
所有本轮对照 provider=mock；SDK 桩与真实预检另存。V1 五个 A 目标 0/5，V2 5/5；这只是针对报告现象的检查，不能推导正式成功率或其他缺陷数量。

| 缺陷/用例 | V1 现象 | V2 修改 | 结果范围 | Git |
|---|---|---|---|---|
{fix_table}

{"\n".join(detail)}

## 原始失败、后续验证和待协调项

DEF-03/05 开发中的首次 A 单元失败日志仍保留在 def03_unit.txt / def05_unit.txt，后续 retry 日志和源码修正分别入对应提交。没有删除失败结果或改 B 正式规则。
正常/六变异/CLI/HTTP/Web 的实际 V2 回归见 regression/verification.json 和 audit_first.json；完整源码提交 `{source}`。契约与工具 Schema 相同，调用数量没有因 DEF-03 建议而增加。
待 B：重跑正式 100 条与自然语义边界；五个原 xfail 是否关闭；售罄建议是否满足 F14 的测试口径；提供新的执行 JSONL/指标和缺陷关闭结论。待 C：依据 B 结论验收/截图/视频。待模型配置：合法有效 Key 和支持工具调用的端点；当前真实待验证，不可把 Mock 修复结论外推到大模型。
"""
    checklist = f"""# 成员 A：V2 最终交付清单

{common}

## 已有可核查的交付

- [x] 保留 V1 标签、源文档/开发记录、原库/Trace、B 原始资料；25 文件哈希核对通过。
- [x] 独立 V2 分支，五缺陷分别提交，不修改/合并主分支。
- [x] DEF-01 kind/席别一致性；DEF-02 双向切换与上下文；DEF-03 库存分类回复。
- [x] DEF-04 duplicate_pay 提示且业务幂等不变；DEF-05 政策与明确写请求区分。
- [x] 原入口 Agent().chat 与 10 顶层/5 calls 字段、finish_reason/tool_sequence 语义兼容。
- [x] 8 工具实现保持，Schema 对比一致；query kind/seat 不兼容用既有 error 拒绝。
- [x] Mock/SQLite 虚构业务、默认政策检索及引用，原 CLI 全入口与 HTTP 8 工具冒烟通过。
- [x] Web AppTest 对话/回放/变异恢复、本地 health 启动通过。
- [x] 六缺陷注入仍可复现，恢复后正常政策引用通过。
- [x] 13 新缺陷自测、3 新 SDK 桩自测，连同 V1 12 共 28 自测通过。
- [x] 10 项冒烟检查，32 条独立 Mock Trace；五项 A 对照目标符合。
- [x] 已运行的原 Python API 四轮示例及完整 JSON/JSONL。
- [x] Python/依赖冻结与 PowerShell 独立运行说明；seed 默认拒绝覆盖。
- [x] 真实模式配置/显式验证入口与无 Key 预检；真实 Trace 0 条，未冒称联网验证。
- [x] V2 持续开发记录、A 报告、B 对接、C 演示、V1/V2 对照和本清单。
- [x] 文档由实际代码/Git/证据生成，声明 A/B/C 责任和未完成边界。

## 仍需确认或未完成

- [ ] B 正式 100 条 V2 回归结果、测试指标、缺陷关闭判定；95/100 是 V1 的 B 报告值。
- [ ] B 五个 xfail 的更新与 XPASS/统计规则核查。
- [ ] DEF-03 “建议查询”与 B 正式 F14 期望口径最终确认。
- [ ] 合法 API Key/端点/模型配置及 7 类真实模型验证，模型 Prompt 遵守效果待验证。
- [ ] 可选向量 RAG 实测；生产认证、持续候补、真实票务/资金/实际改签（未在本轮范围完成）。
- [ ] C 人工验收、真实截图、5—10 分钟视频与依据 B 成绩的最终参赛报告。
- [ ] 三人共同确认最终验收；A 自测通过不等于团队验收签字。

## 文件、证据与 Git 定位

V2 运行核心 target/providers.py / tools.py / agent.py；其余 mock_core、rag、trace、CLI、Web 和 seed 沿用原实现。测试新增 tests/test_v2_defects.py / test_v2_provider.py；执行和生成脚本位置见 A 报告。接口契约为未修改 docs/contract.md。
分支 `{branch}`；已验证源码 SHA `{source}`；最终完整交付 HEAD 由标签 handoff-a-v2-20261013 解析（检查通过后建立）。V1 原标签 `{baseline['v1_tag_sha']}` 不移动。
B 材料：B_V2测试对接说明.md、原 contract、api_example、defects 对照、regression 原 Trace 和连续开发记录；B 的正式 judge/cases 未混入。
C 材料：C_V2验收演示说明.md、A 技术报告、对照和可回放 Mock Trace；录屏分镜是建议，尚未制作。

| 证据 | 实际路径 |
|---|---|
| V1 文档/日志快照与保护清单 | docs/evidence/v2/v1_snapshot/ |
| V1 五问题 A 原复现 | docs/evidence/v2/v1_reproduction/ |
| V2 五修复 A 实际复现 | docs/evidence/v2/v2_reproduction/ |
| 28 自测与 10 冒烟/32 Trace | docs/evidence/v2/full_unit.txt、regression/ |
| 原 API 四轮真实 Mock 示例 | docs/evidence/v2/api_example/ |
| 无 Key 真实预检 | docs/evidence/v2/real_preflight/preflight.json |
| 保护/源码/Schema/六变异一致性 | docs/evidence/v2/audit_first.json；后续 final 审计另存 |

已知限制详见 A/B 手册：Mock 有限语法、旧库日期窗口、预览截断、stop 不等于成功、会话重置不恢复库存。尚无 B 的 V2 新缺陷清单，不能写“零 Bug”。交接文档自身不重复运行核心测试，只有源代码变化才需重跑。

成员 A 开发交接状态：**有条件交接**。B 可开始正式回归，C 可开始 Mock 验收/演示；远端真实模型验证、正式成绩和最终验收未完成。
"""
    out = args.output_dir if args.output_dir.is_absolute() else ROOT/args.output_dir
    paths = [out/name for name in NAMES]
    if any(p.exists() for p in paths):
        raise FileExistsError("V2 文档已存在，请用新的 --output-dir，不能覆盖历史")
    out.mkdir(parents=True, exist_ok=True)
    for path, body in zip(paths, [a, b, c, compare, checklist]):
        path.write_text(body, encoding="utf-8")
    print(json.dumps({"source_commit": source, "documents": NAMES, "unit_tests": audit["unit_tests_passed"], "real_model_tested": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
