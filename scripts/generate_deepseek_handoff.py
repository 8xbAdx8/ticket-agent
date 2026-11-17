"""依据已保存的实际结果生成 DeepSeek 交接；不调用模型或读取密钥内容。"""
import importlib.metadata
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/"docs/handoff/v3"
EVIDENCE = ROOT/"docs/evidence/deepseek"


def main():
    # 只用于 10 月 15 日缺 Key 的历史快照，不能覆盖后续实际验证报告。
    if (EVIDENCE/"review-20261016/audit.json").exists():
        raise SystemExit("已有真实 API 审查证据；历史生成器已停用，禁止用 missing_key 快照覆盖当前交接。")
    def read(relative):
        return json.loads((EVIDENCE/relative).read_text(encoding="utf-8"))
    online, baseline = read("missing_key_run/report.json"), read("baseline.json")
    assert online["status"]=="skipped_missing_key" and online["online_generation_requests_this_run"]==0
    def stats(name):
        text = (EVIDENCE/name).read_text(encoding="utf-8")
        assert re.search(r"^OK",text,re.M)
        total = int(re.search(r"Ran (\d+) tests",text)[1])
        skipped = re.search(r"OK \(skipped=(\d+)\)",text)
        skipped = int(skipped[1]) if skipped else 0
        return {"total":total,"passed":total-skipped,"skipped":skipped}
    results = {"deepseek":stats("final_unit.txt"),"v3":stats("final_v3_compatibility.txt"),"v2":stats("final_v2_compatibility.txt")}
    sha = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    branch = subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip()
    versions = {p:importlib.metadata.version(p) for p in ("langchain","langchain-core","langchain-deepseek","langchain-openai","langgraph","openai","httpx","streamlit")}
    changed = subprocess.check_output(["git","diff","--name-only",baseline["baseline_head"],sha],cwd=ROOT,text=True).splitlines()
    sources = [p for p in changed if not p.startswith("docs/")]
    summary = {"client_date":"2026-10-15","source_commit":sha,"branch":branch,"baseline_head":baseline["baseline_head"],
               "versions":versions,"tests":results,"online_generation_requests":0,"balance_requests":0,
               "real_api_verified":False,"real_function_calling_verified":False,"thinking_mode_supported":False,
               "deepseek_tools":["query_tickets","search_policy"],"existing_tools_retained":8,"source_files":sources,
               "protected_files":len(baseline["protected_sha256"]),"handoff":"有条件交接"}
    (EVIDENCE/"handoff_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    common = f"""日期：2026-10-15（Asia/Shanghai）。分支 `{branch}`，已验证源码与证据提交 `{sha}`，接手基线 `{baseline['baseline_head']}`。本批文档会形成后续提交；最终 SHA 用 `git rev-parse HEAD` 获取。本轮未推送远程分支。

**真实 API 尚未验证。** 实际没有检测到可用环境密钥，生成请求 **0 次**，余额 HTTP 请求 **0 次**。连通性、密钥有效性、余额、实际返回模型 ID、真实 Function Calling 均跳过；真实 Token 为“不适用/未知”，本轮无 API 调用费用，不代表账户总账单为零。

**成员 A 开发交接状态：有条件交接。** A 的代码与离线验证可以交 B 接入回归；DeepSeek 实际效果和 C 的真实模型演示暂不能验收。A 不提供 B 正式成绩，不把 SDK 桩或 LangChain Mock 当作真实模型结果。
"""
    status = """| 标记 | 本次实际情况 |
|---|---|
| 【真实 API 已验证】 | 否；缺少密钥，未发送请求 |
| 【LangChain Mock 已验证】 | 原 8 工具、六变异、CLI/Web 回归通过 |
| 【仅代码实现】 | ChatDeepSeek 官方接入；两个只读工具具备离线 SDK 协议证据 |
| 【尚未验证】 | DeepSeek 联网、真实工具选择、多轮任务与安全表现 |
| 【存在问题】 | 当前 SDK 不回传思考字段；思考模式被明确禁用；输入 Token 与费用只能受有限约束 |
"""
    dependencies = "\n".join(f"- `{p}=={v}`" for p,v in versions.items())
    tests = f"""- `.venv-deepseek`：{results['deepseek']['passed']}/{results['deepseek']['total']} 项 A 自测通过，{results['deepseek']['skipped']} 跳过，见 [final_unit.txt](../../evidence/deepseek/final_unit.txt)。
- 原 `.venv-v3`：{results['v3']['passed']} 项通过、{results['v3']['skipped']} 项明确跳过，见 [日志](../../evidence/deepseek/final_v3_compatibility.txt)。
- 原 `.venv`：{results['v2']['passed']} 项通过、{results['v2']['skipped']} 项明确跳过，见 [日志](../../evidence/deepseek/final_v2_compatibility.txt)。跳过由缺少 httpx/LangChain/DeepSeek SDK 决定，不算通过。
- `scripts/smoke.py --output-dir docs/evidence/deepseek/mock_smoke`：10 项入口/服务检查通过，32 条 legacy Mock Trace；包含六种故意缺陷注入，见 [证据](../../evidence/deepseek/mock_smoke/verification.json)。
- `scripts/verify_v3.py --toolset all --baseline-manifest docs/evidence/deepseek/baseline.json --output-dir docs/evidence/deepseek/mock_framework_fixed`：11 轮 LangChain Mock API、8 工具及 CLI/Web 通过，见 [证据](../../evidence/deepseek/mock_framework_fixed/verification.json)。
- `scripts/capture_v3_live_ui.py --browser <本机浏览器> --out docs/evidence/deepseek/mock_browser_final`：5 轮实际 Mock 浏览器操作、JSON 下载/回放/代码/清空通过；这是 Mock 页面证据，不是 DeepSeek 页面成功截图。
- `scripts/check_deepseek_api.py --run --out docs/evidence/deepseek/missing_key_run`：实际结果为跳过，见 [report.json](../../evidence/deepseek/missing_key_run/report.json)。
- `scripts/verify_deepseek_offline.py --out docs/evidence/deepseek/offline_sdk`：4 次 MockTransport 桩请求，执行查询与政策两个闭环，远端请求 0；见 [明确标注的离线证据](../../evidence/deepseek/offline_sdk/offline_evidence.json)。
"""
    settings = r"""```powershell
# 以下命令均在项目根目录运行；只设置 Ticket Agent，不修改 Codex 配置。
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="deepseek"
$env:AGENT_ENGINE="langchain"
$env:AGENT_MODEL="deepseek-flash"
$env:AGENT_BASE_URL="https://api.deepseek.com"
$env:AGENT_LC_TOOLSET="read_only"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:DEEPSEEK_THINKING="disabled"
$env:DEEPSEEK_MAX_REQUESTS="5"
$env:DEEPSEEK_MAX_MODEL_CALLS="2"
```

密钥只从 `DEEPSEEK_API_KEY` 读取，`AGENT_API_KEY` 不作为 DeepSeek 的备用密钥，也不会自动转成 Mock。若终端已有旧的 AGENT_MODEL/BASE_URL，以上配置会明确替换成官方参数。

在自己的 PowerShell 中安全输入密钥，不要发到聊天或截图：

```powershell
$deepseekSecret = Read-Host "DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", $deepseekSecret).Password
Remove-Variable deepseekSecret
```

环境变量只影响该终端及其子进程；在其他终端设置后，本聊天的执行进程不会自动继承。配置好后可在那个终端运行检查脚本，把脱敏 `report.json` 交给团队，不要交密钥。
"""
    safety = """| 限制 | 当前实现 |
|---|---|
| 官方地址/模型 | 只允许 HTTPS api.deepseek.com，模型 deepseek-flash；不自动降级或换模型 |
| 思考模式 | 请求明确 `thinking.type=disabled`，配置 enabled 会拒绝 |
| HTTP 超时 | 默认 20 秒，可在 1–60 秒范围配置 |
| 自动重试 | 0；连接/超时/限流也不自动重试 |
| 可计费生成请求 | 同一持久 SQLite 账本累计最多 5 次；第 6 次在传输前被挡住 |
| 模型轮数 | 默认每轮最多 3 次，并与 AGENT_MAX_STEPS 取较小值；接入脚本限制为 2 次 |
| 工具执行 | 默认每轮最多执行 4 次，仅 query_tickets/search_policy；超限调用记录失败，不执行业务 |
| 输出 Token | 每请求显式 max_tokens，默认 512，上限配置 1024 |
| 输入与总 Token | 请求体默认最多 32000 UTF-8 字节；已观察总 Token 默认阈值 12000。输入 tokenizer 未本地精确计量，阈值是下一次请求前的软限制，单次响应可能越过它，不是严格费用上限 |
| 写操作 | DeepSeek 当前注册和传输两层都只读；中间件仍独立拒绝错误写调用，原业务状态机/支付授权/幂等未改 |
"""
    api_errors = """400 invalid_format；401 authentication_failed；402 insufficient_balance；422 invalid_parameters；429 rate_limited；500 server_error；503 service_unavailable；连接错误 network_connection；超时 timeout。还单独报告 missing_DEEPSEEK_API_KEY、request_budget_exhausted、token_usage_unknown、dependency_missing 等本地错误。只存类别和状态码，不存响应错误正文、Authorization、原始异常堆栈或内部推理。
"""
    docs = {}
    docs["A_DeepSeek真实API接入报告.md"] = "# A：DeepSeek 真实 API 接入报告\n\n"+common+"\n## 完成状态\n\n"+status+f"""
## 实现与依赖

在既有 LangChain Agent 上增加 ChatDeepSeek，并未重建业务系统。实际安装独立 `.venv-deepseek`，Python 3.12.14，pip check 通过。原环境与旧锁文件保留，新 requirements-deepseek-lock.txt 只比原 V3 锁新增 langchain-deepseek，不升级旧包。

{dependencies}

实际改动源文件（从 Git 基线差异整理）：

"""+"\n".join("- `"+p+"`" for p in sources)+"""

## 工作流程与教学说明

DeepSeek 是决策者：接收提示词、历史消息和工具 Schema，返回服务端 tool_calls。LangChain create_agent 是调度者：把调用交给已有 StructuredTool，再将 ToolMessage（含同一调用 ID 和真实工具 JSON）送回模型。Python tools/mock_core 负责模拟库存与状态校验，RAG 仍检索原 15 条政策。模型不会直接操作数据库。

`Agent.chat → ChatDeepSeek → 官方 HTTPS API → AIMessage.tool_calls → LangChain 工具节点 → tools.dispatch → SQLite/RAG → ToolMessage → ChatDeepSeek → 最终回复`。

中间件记录实际模型响应元数据、声明的 tool_calls、工具开始/结束/参数/结果/耗时。它不从回复文字推测调用。只有发起 `/chat/completions` 的请求才进入生成请求预算；每次工具执行本身不产生模型 API Token 费用，模型读工具结果和作最终答复会再次请求 API。

## 接口与兼容性

`Agent().chat(session_id, message)` 保留，正常返回仍是原 10 顶层字段，calls 仍是原 5 字段；provider 新值为 `deepseek_live`，model 是请求配置，服务端实际模型 ID 在旁路事件 `model_response.response_model`。没有改 docs/contract.md，也未改原八工具、数据库业务、RAG、Trace 类或成员 B 的正式规则。

Token 用量未知或请求失败时，DeepSeek 路径抛出脱敏 DeepSeekError，并在 deepseek_runs.jsonl 保存失败；不创建含假 0 用量的普通成功 Trace。原契约未定义错误返回形状，因此不擅自添加字段/nullable Token。CLI 的错误 JSON 是诊断信息，不是 Agent 成功契约。B 若要求所有失败也返回完整契约，需先由团队确认未知 Token 的兼容表示。

默认 DeepSeek Trace 单独存入 traces/deepseek_live；建议每次显式指定隔离目录。已有会话隔离/重置、Web 卡片、历史 JSONL 回放、CLI 保留。DeepSeek 不支持 legacy 引擎，不允许把 MockProvider 注入成真实模式；六变异仍只供 legacy Mock 使用。

## 已执行验证

"""+tests+"""
## 风险和未完成

缺密钥导致在线四组场景均未验证；SDK 桩不能证明真实模型选择工具、处理缺失条件或拒绝攻击的能力。原 B 的 95/100 基线没有更新，本次不生成覆盖率、成功率或正式成绩。6 个其余工具尚未向 DeepSeek 开放，需只读 Live 验证通过后另行评估，不能仅改 all 绕过保护。

当前 ChatDeepSeek 1.1.1 的离线载荷检查不回传 reasoning_content。非思考模式显式禁用该协议；不提供 enabled 演示。后续须采用支持真实字段保留/回传的版本或审查过的适配器，并单独验证，不补造空思考内容。

原 V2 保护快照中的 DB/Trace 与接手时数据已不同；本次使用接手时新清单，356 文件哈希保持。没有恢复/覆盖用户数据。早期 Windows SQLite 连接未关闭、旧环境依赖导入和历史基线失败证据均保留，最终结果见 final_* 与 mock_framework_fixed。

未修改 Codex 自身配置、认证或全局模型，没有推送主分支/强推/移动旧标签。源代码、离线验证具备交接条件，真实模型验收暂不具备。
"""
    docs["B_DeepSeek真实模型测试对接说明.md"] = "# B：DeepSeek 真实模型测试对接说明\n\n"+common+"\n## 安装与选择模式\n\n"+r"""首次安装可复用已有 Python，保持原环境：

```powershell
.\.venv-v3\Scripts\python.exe -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt
.\.venv-deepseek\Scripts\python.exe -m pip check
```

本机本次已经安装，不要在运行服务时重复创建环境。Mock：AGENT_PROVIDER=mock，AGENT_ENGINE=langchain，AGENT_LC_TOOLSET=all，清除遗留 AGENT_MODEL/BASE_URL 或明确换回对应 Mock 配置；legacy Mock 变异用 AGENT_ENGINE=legacy。DeepSeek Live 配置如下。

"""+settings+r"""
## 先验证连通性和两个工具

```powershell
# 不加 --run 只做本地预检，没有联网效果证明。
.\.venv-deepseek\Scripts\python.exe scripts/check_deepseek_api.py
# 该命令在有 Key 时会消耗共享预算，输出目录必须不存在。
$dsRun = Get-Date -Format "yyyyMMdd-HHmmss-ffff"
.\.venv-deepseek\Scripts\python.exe scripts/check_deepseek_api.py --run --out "docs/evidence/deepseek/live-$dsRun"
```

顺序为余额 GET → 短 Hello POST → 查询（通常两 POST）→ 政策（通常两 POST）。预计最多 5 次；模型没有完成闭环、出现错误或预算耗尽就停止，不自动重试。余额查询只记录可用布尔值，服务端实际模型 ID、用量、耗时保存在 report.json。缺 Key 是 skipped，失败是 failed，只有 status=passed 与对应 verified=true 才是完成该阶段。退出码 0 本身不能说明通过（缺 Key 跳过也为 0）。失败退出码为 1。

## 接口与证据读取

环境配置必须在导入 Agent 前完成。以下代码会触发可能计费的请求，先确认剩余额度，不要在验证已用完 5 次后继续运行：

```python
from target.agent import Agent
from target.deepseek_runtime import DeepSeekError
agent = Agent()
try:
    result = agent.chat("B-deepseek-case-001", "查明天上海到杭州的高铁二等座")
    print(result["provider"], result["tool_sequence"], result["tokens"])
except DeepSeekError as exc:
    print({"status": "failed", "category": exc.category, "tokens": None})
```

本例的导入/错误处理与相同调用路径在离线 SDK 测试中实际验证；这里的真实模型查询尚未执行。不可把示例当成功结果。

普通 traces.jsonl 保持 contract：steps[].calls[].args 是实际入参，ok 是工具执行结果；tool_sequence 是实际调用顺序；finish_reason=stop 只是循环结束；total_latency_ms 是 Agent 整轮耗时，单步 latency_ms 是工具调用耗时。tokens.prompt/completion 汇总 API usage_metadata，不含猜测值。未回传用量时本轮抛错，脱敏失败详情在同目录 deepseek_runs.jsonl，其中 tokens=null 表示未知，不参与“零 Token 成功”统计。

deepseek_runs.jsonl 的 model_response 事件记录真实 SDK 解析的 tool_calls（id/name/args）、响应模型 ID、usage；后续 tool_end 记录实际结果。用同一个 session_id 检查继承，用不同 session_id 检查隔离。完整工具结果只在事件/UI session 中，契约 result_preview 仍截断，不能只解析截断预览判断全部车次。

source=offline_sdk_stub 的材料只是协议证据，即使内部 provider 字段为 deepseek_live（标识适配器），也不能算远端成绩。真实证据还需结合部署配置、运行报告、账本与模型请求来源。Mock 与 Live 成绩分别记账，自然语言不做全部逐字匹配；比较工具、参数、实际库存/状态、引用来源和任务语义。正式方案/缺陷评价仍由 B 决定。

## 可复现条件与后续范围

每批用新的 AGENT_DB_PATH、AGENT_TRACE_DIR，先在隔离路径执行 data/seed.py；同个 Agent 实例/同个 session 保留上下文。reset/清空会话不恢复库存，严禁重置原数据或删除失败 Trace。DEEPSEEK_BUDGET_PATH 默认共享在 artifacts/runtime/deepseek-budget/requests.db，独立业务 DB 不应顺便更换费用账本。

本轮只读稳定后，再申请新增请求预算验证交通方式切换、条件继承、澄清、空结果和故障。不要把当前 Mock 的通过结果计入 DeepSeek 多轮质量。六变异仅 legacy Mock；Live/框架模式拒绝启用，不能用变异结果冒充模型自主缺陷。

"""+safety+"\n错误类别："+api_errors+"\n## A 已执行的检查\n\n"+tests
    docs["C_DeepSeek真实模型演示说明.md"] = "# C：DeepSeek 真实模型演示说明\n\n"+common+r"""
## 可以怎样介绍

模型像调度员，负责理解自然语言、选择“查余票”或“查政策”；LangChain 像流程控制台，负责调用 Python 工具并把结果送回模型；工具负责读取虚构票务数据和政策。最终文字、参数和执行记录可供测试。当前可以介绍代码和离线验证，不能说“真实 DeepSeek 演示已成功”。

报告中把数据来源分清：业务一直模拟；模型决策在 Live 下应来自 DeepSeek，在 Mock 下来自规则剧本。二者不同维度。当前新增 2 个 DeepSeek 只读工具的接入准备，旧系统 8 工具仍保留，不等于 DeepSeek 已实测全套订票。

## 部署与真实演示的两种安排

按 [B 的接入说明](B_DeepSeek真实模型测试对接说明.md) 配置环境和密钥。自动完整检查与现场演示**共用累计 5 次**，不能各运行一次绕过额度。

方案一：B 先运行完整检查，预计耗用 1+2+2 次。确认报告通过后，C 可以在网页历史回放中展示保存的真实 Trace，不再新调用模型。若需现场新问答，先取得额外预算授权。

方案二：为了在同一 5 次额度内录网页，先只运行 Hello 连通检查（1 次），然后在网页进行一次查询和一次政策咨询（通常各 2 次）。这也是实际验证，不是已完成结果。若模型多次调用或出错，应停下记录，不自动再试。

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/check_deepseek_api.py --run --connection-only
# 使用 B 手册里的 DeepSeek 环境变量，且 DEEPSEEK_MAX_MODEL_CALLS=2。
$demoRun = Get-Date -Format "yyyyMMdd-HHmmss-ffff"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\deepseek-demo-$demoRun\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\deepseek-demo-$demoRun\deepseek_live"
.\.venv-deepseek\Scripts\python.exe data/seed.py
.\.venv-deepseek\Scripts\python.exe -m streamlit run web/app.py
```

此前已经用过生成请求时，剩余不足 5，不要重新开始完整演示。预算耗尽不能删除账本、换路径或改脚本继续试。

## 建议拍摄顺序与验收条件

1. 介绍界面左侧“DeepSeek Live · 只读”、deepseek-flash 和两个工具；不要拍环境变量或 Key 输入过程。
2. 输入“查明天上海到杭州的高铁二等座”。拍处理中提示、最终回复、余票卡片、右侧 query_tickets 和参数；卡片数据必须来自本轮工具结果。
3. 展开工具原始结果与完整 JSON，显示 provider、model、Token、耗时和成功标记；stop 不能单独作为业务成功证据。
4. 输入“锁座后多久必须完成支付？”。拍 search_policy、P11 等来源；本次不执行支付。
5. 展示历史回放、源码导览；说明它们不产生新的模型调用。引用 report.json/账本实际数值，不把离线截图数字搬到 Live 报告。

当前同步接口只有通用“正在处理请求...”动画，没有模型思维展示，也没有逐阶段实时事件。动画本身不是模型调用证据。遇到 missing key、401/402、超时或预算用尽，拍脱敏错误类别，保留报告和 Trace；不要拍后台原始错误正文、认证头或内部推理。

当前 `docs/evidence/deepseek/mock_browser_final` 的截图是 Mock 回归；`offline_sdk` 是 SDK 桩，均不能作为 DeepSeek 成功图片。真实模式拍摄要等合法密钥和实际成功。最终成绩由 B 提供，C 再完成作品介绍、验收和视频。
"""
    docs["Mock与DeepSeek真实模型对照.md"] = "# Mock 与 DeepSeek 真实模型对照\n\n"+common+"\n"+status+"""
| 维度 | LangChain Mock | DeepSeek Live 接入 |
|---|---|---|
| 决策来源 | MockProvider 规则 | ChatDeepSeek 请求官方模型，当前远端未执行 |
| 调度 | 相同 create_agent / middleware | 相同 create_agent / middleware |
| 工具 | 原 8 工具可选 all | 当前强制 2 个只读工具 |
| 模拟业务 | SQLite / 15 条政策 / RAG | 完整复用，未连接真实铁路、航空或支付 |
| 模型费用 | 无远端模型 Token 费用 | 每次生成 API 请求可能计费，工具结果回传通常再请求一次 |
| 可重复性 | 规则可预期，日期/数据也会影响结果 | 输出非确定性，需依据语义/工具事实评估 |
| 变异 | 六开关保留在 legacy Mock | 不允许在 Live 启用 |
| Trace | langchain_mock / mock | deepseek_live，默认独立目录；错误/未知用量单独存失败证据 |
| 当前证据 | 11 轮 API、8 工具、CLI/Web 和浏览器回归通过 | 只有离线 SDK 协议/安全测试；真实 API 0 次 |
| 多轮能力结论 | 原 Mock 用例通过 | SDK 消息继承已验证；真实模型条件继承/交通切换/澄清尚未验证 |

以下是协议层已验证事项：DeepSeek SDK 携带 thinking.disabled；服务端格式的 tool_calls 能被识别；实际 Python 工具被执行；tool_call_id 一致、结果送回下一次 SDK 请求；Token 元数据能累计；RAG 返回 P11 来源；错误写操作被拒绝；用量缺失不冒充 0。SDK 桩的 tool_calls 是测试预设，不能证明真实大模型的决策质量。

真实模型正常结果沿用原契约；新增 provider 值不改变字段集合。Model 名称记录请求配置，实际响应模型 ID 看旁路 metadata。已有 B 接口和 V2 默认行为保留。严格要求错误永远返回契约 JSON 的判定器，需要团队先讨论未知 Token 表示，本次选择脱敏异常而不是修改 contract。

本轮没有可比的真实延迟/成功率/缺陷数量，不生成“Mock 比 DeepSeek 快多少”或“准确率提升多少”的结论。后续由 B 用隔离数据、明确模型版本和请求预算开展正式对比。
"""
    docs["DeepSeek_API安全与费用记录.md"] = "# DeepSeek API 安全与费用记录\n\n"+common+"\n## 实际费用账本\n\n"+"""| 项目 | 本轮实际记录 |
|---|---|
| 请求模型 | deepseek-flash |
| 实际返回模型 ID | 未取得，未请求 |
| 生成请求 | 0 次 |
| 余额接口请求 | 0 次 |
| 在线输入/输出 Token | 不适用/未知；没有模型响应，不填造数值 |
| 本轮调用费用 | 0；未发生成请求，不是账户总账单结论 |
| 账户余额、Key 是否有效 | 尚未验证 |
| SDK 桩 | 4 次本地 MockTransport 传输，0 次远端请求；固定用量不计真实账单 |
| 真实成功/失败/跳过 | 真实成功 0、真实请求失败 0、4 个基础项目因缺 Key 跳过 |

当前官方文档说明 deepseek-flash 对应 V4.1-Flash，支持 Tool Calls，思考默认启用，因此本项目明确关闭。计费与缓存、时段有关；当前无真实用量，不作非零费用估算。后续账本如有用量，可按执行当天官方单价估算并注明缓存/时段假设，实际费用以供应商账单为准。余额变化也可能来自其他客户端，不能直接算作本 Agent 的精确支出。[官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

## 已实施的限制

"""+safety+"""
费用账本默认 `artifacts/runtime/deepseek-budget/requests.db`，使用 SQLite 事务在请求前占名额。超时/崩溃/结果未知时不退还名额，避免重复计费。状态 reserved_outcome_unknown 表示可能已发送/到达，不能认为免费失败。余额 GET 另行计数，不属于生成请求。

上限只覆盖本项目支持的同步入口和同一 ledger；不能限制其他客户端、账户整体消费或人为删除/更换账本。没有精确的输入 Token 预估器，观察阈值不能保证严格总 Token 或人民币上限。默认输出 cap、请求体 cap、模型轮数和最多 5 次生成请求共同降低成本。不得绕过限制，超过当前授权前须再次确认预算。

本阶段无写工具，故不会发生未知结果的支付重提。将来开放写操作必须保留独立授权/归属/状态/幂等，超时先查询状态核验，不可自动重复提交。

## 隐私与错误

密钥仅在进程环境中使用，不进入 Trace、报告或 Git；不保存请求头、原始响应错误正文或完整 AIMessage。LangSmith 外部追踪默认关闭，SDK/传输调试日志受抑制。旁路只存最终回复、结构化工具事件、用量和脱敏错误。

"""+api_errors+"""
思考模式当前明确阻断：安装包离线检查显示不能把 AIMessage 里的 reasoning_content 回传到工具循环。官方说明携带 tools 时需要回传真实历史字段；因此不能用虚构或空内容补齐。当前只验证非思考载荷，启用思考需新适配和独立测试，不把内部推理展示给用户。[官方思考协议](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)

## 证据索引

- [当前无密钥检查结果](../../evidence/deepseek/missing_key_run/report.json)
- [明确标注的离线 SDK 证据](../../evidence/deepseek/offline_sdk/offline_evidence.json)
- [SDK/错误/隐私/Web 测试日志](../../evidence/deepseek/sdk_ui_unit.txt)
- [最终全部测试](../../evidence/deepseek/final_unit.txt)
- [接手数据与证据保护清单](../../evidence/deepseek/baseline.json)

官方错误类别参考：[DeepSeek 错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。LangChain 接入位置参考：[ChatDeepSeek](https://docs.langchain.com/oss/python/integrations/chat/deepseek)、[create_agent](https://docs.langchain.com/oss/python/langchain/agents)。介绍页的旧模型样例不作为本项目模型选择依据，实际配置固定为官方当前模型名。
"""
    for name,text in docs.items():
        (OUT/name).write_text(text,encoding="utf-8",newline="\n")
    log = f"""# DeepSeek 接入持续开发记录

日期：2026-10-15。分支 `{branch}`。接手 HEAD `{baseline['baseline_head']}`；原有未跟踪展示压缩包保持原样，不加入本次提交。

| 模块 | 文件与原理 | 实际验证 | Commit / 团队影响 |
|---|---|---|---|
| 安全配置/环境 | config.py、deepseek_runtime.py、requirements-deepseek*、gitignore；官方地址/唯一 Key/5 请求持久预算 | 8 项离线 runtime 测试通过，pip check 通过；Windows SQLite 连接清理失败已修正并保留失败日志 | e93a0e5746039d9d601c30e3129abee644203957；B 用独立环境，C 不展示密钥 |
| 独立连通检查 | scripts/check_deepseek_api.py、3 项脚本控制流测试；余额/短 Hello/两个工具，成功失败跳过分类 | --run 实际跳过，0 在线请求；3 个脚本桩测试通过 | 622d665526f14335b1d219c197d9f608142ce600；B 检查 JSON status，不仅看退出码 |
| 框架/会话/Trace/Web/CLI | Agent、LangChainAgent、runtime、Web/CLI、SDK 10 项自测、离线复现脚本；真实 SDK 接已有 create_agent | 新环境 88 通过；原 V3 78 通过/10 跳过；原 V2 35 通过/53 跳过；10 入口检查、11 轮 8 工具 Mock、5 轮 Mock 浏览器通过 | {sha}；正常契约不变，错误/未知 Token 独立异常；B 正式规则未改 |
| 交接与核对 | 本生成脚本、5 份交接报告、当前结果摘要、机器核对脚本 | 依据保存日志/元数据生成，不发送 API | 后续文档提交，最终 SHA 在最终回复/ git log 提供 |

早期问题记录：1. SQLite 的 with connection 不关闭连接，Windows 临时 DB 清理失败，改为显式 closing；2. 原 V2 未装 httpx，新测试应 skip 而不是 import error；3. 10 月 13 日 DB/Trace 哈希在接手前已有变化，保留用户当前数据，新增 --baseline-manifest 检查本次 356 文件；4. 源码插入安全检查导致行号改变，A 浏览器代码导览检查改为动态行号，不更改 B 判定。

证据索引见 docs/evidence/deepseek/handoff_summary.json。源码提交对应上述文件和实际命令；后续仅文档与核对补充。没有真实 API 成功/失败结果；有无 Key 检查及明确跳过，不把 MockTransport 与真实 API 混计。尚未完成：真实只读闭环、在线多轮与安全、其余 6 工具开放、思考协议、正式 B 评价和 C 验收。
"""
    (ROOT/"docs/deepseek_development_log.md").write_text(log,encoding="utf-8",newline="\n")
    print(json.dumps({"reports":list(docs),"source_commit":sha,"online_requests":0,"tests":results},ensure_ascii=False))


if __name__=="__main__":
    main()
