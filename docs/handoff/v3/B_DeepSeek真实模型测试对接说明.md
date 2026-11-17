# 只读质量修复后的最新说明（2026-10-16）

源码修复提交 `e216fdf57ec8f34b84134ba2b30b05e5d6ff5985`。请先看 [当前冻结交接](B_V3只读冻结测试交接_20261016.md)。两工具已有历史Live证据，其余六工具未开放；本轮102项A离线自测通过，新增API请求0，额度仍5/5。新提示词尚未联网回归；旧ZIP bff292cd是修复前版本。

下方保留前次审查/演示背景，其中“待修复话术”“过时标签”已由本轮离线修复，旧缺Key结论仅属于历史。

---

# 最新对接：2026-10-16 正式测试交接

真实两个只读场景已有证据；5次生成额度已用尽，当前禁止任何新增API请求。请以 [B 正式测试交接](B_DeepSeek正式测试交接_20261016.md) 为当前说明：保留原100条Mock与判定，Live只读筛选另记，不混合成绩。当前仓库没有完整judge/100用例源码，本次未执行B正式回归。

正常Agent.chat契约未变；Token未知/请求错误仍是脱敏异常路径，交B确认。原始SQLite与历史Trace未变。

---

## 历史存档：2026-10-15 接入说明原文

以下在线命令/密钥步骤仅为当时接入说明，当前冻结期间不得执行；“真实未验证/0次请求”是历史状态。

# B：DeepSeek 真实模型测试对接说明

日期：2026-10-15（Asia/Shanghai）。分支 `codex/ticket-agent-deepseek-live`，已验证源码与证据提交 `d40b005ebdad2a57c8a09aa86d97911e1203f344`，接手基线 `85d457a4f34b4fad848ded4cf9c2d7334813c399`。本批文档会形成后续提交；最终 SHA 用 `git rev-parse HEAD` 获取。本轮未推送远程分支。

**真实 API 尚未验证。** 实际没有检测到可用环境密钥，生成请求 **0 次**，余额 HTTP 请求 **0 次**。连通性、密钥有效性、余额、实际返回模型 ID、真实 Function Calling 均跳过；真实 Token 为“不适用/未知”，本轮无 API 调用费用，不代表账户总账单为零。

**成员 A 开发交接状态：有条件交接。** A 的代码与离线验证可以交 B 接入回归；DeepSeek 实际效果和 C 的真实模型演示暂不能验收。A 不提供 B 正式成绩，不把 SDK 桩或 LangChain Mock 当作真实模型结果。

## 安装与选择模式

首次安装可复用已有 Python，保持原环境：

```powershell
.\.venv-v3\Scripts\python.exe -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt
.\.venv-deepseek\Scripts\python.exe -m pip check
```

本机本次已经安装，不要在运行服务时重复创建环境。Mock：AGENT_PROVIDER=mock，AGENT_ENGINE=langchain，AGENT_LC_TOOLSET=all，清除遗留 AGENT_MODEL/BASE_URL 或明确换回对应 Mock 配置；legacy Mock 变异用 AGENT_ENGINE=legacy。DeepSeek Live 配置如下。

```powershell
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

| 限制 | 当前实现 |
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

错误类别：400 invalid_format；401 authentication_failed；402 insufficient_balance；422 invalid_parameters；429 rate_limited；500 server_error；503 service_unavailable；连接错误 network_connection；超时 timeout。还单独报告 missing_DEEPSEEK_API_KEY、request_budget_exhausted、token_usage_unknown、dependency_missing 等本地错误。只存类别和状态码，不存响应错误正文、Authorization、原始异常堆栈或内部推理。

## A 已执行的检查

- `.venv-deepseek`：88/88 项 A 自测通过，0 跳过，见 [final_unit.txt](../../evidence/deepseek/final_unit.txt)。
- 原 `.venv-v3`：78 项通过、10 项明确跳过，见 [日志](../../evidence/deepseek/final_v3_compatibility.txt)。
- 原 `.venv`：35 项通过、53 项明确跳过，见 [日志](../../evidence/deepseek/final_v2_compatibility.txt)。跳过由缺少 httpx/LangChain/DeepSeek SDK 决定，不算通过。
- `scripts/smoke.py --output-dir docs/evidence/deepseek/mock_smoke`：10 项入口/服务检查通过，32 条 legacy Mock Trace；包含六种故意缺陷注入，见 [证据](../../evidence/deepseek/mock_smoke/verification.json)。
- `scripts/verify_v3.py --toolset all --baseline-manifest docs/evidence/deepseek/baseline.json --output-dir docs/evidence/deepseek/mock_framework_fixed`：11 轮 LangChain Mock API、8 工具及 CLI/Web 通过，见 [证据](../../evidence/deepseek/mock_framework_fixed/verification.json)。
- `scripts/capture_v3_live_ui.py --browser <本机浏览器> --out docs/evidence/deepseek/mock_browser_final`：5 轮实际 Mock 浏览器操作、JSON 下载/回放/代码/清空通过；这是 Mock 页面证据，不是 DeepSeek 页面成功截图。
- `scripts/check_deepseek_api.py --run --out docs/evidence/deepseek/missing_key_run`：实际结果为跳过，见 [report.json](../../evidence/deepseek/missing_key_run/report.json)。
- `scripts/verify_deepseek_offline.py --out docs/evidence/deepseek/offline_sdk`：4 次 MockTransport 桩请求，执行查询与政策两个闭环，远端请求 0；见 [明确标注的离线证据](../../evidence/deepseek/offline_sdk/offline_evidence.json)。
