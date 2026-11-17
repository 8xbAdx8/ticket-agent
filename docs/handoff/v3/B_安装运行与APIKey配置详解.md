# 成员 B：从零安装、运行与 DeepSeek API Key 配置详解

本说明用于包含只读话术/失败留证修复的 V3 冻结候选。业务修复提交 e216fdf，冻结交接提交 82d769b；本包准确版本以根目录 PACKAGE_MANIFEST.json 的 source_commit 为准。旧 bff292cd ZIP 不包含这些修复。

## 1. 先弄清当前范围

| 事情 | 现在是否可以做 | 需要 Key 吗 |
|---|---|---|
| 安装 Python 和依赖 | 可以，pip 访问软件包仓库，不是模型请求 | 不需要 |
| Mock CLI/Web、8 工具演示 | 可以，明确标 Mock | 不需要 |
| A 的 102 项自测和 SDK 协议桩 | 可以，离线执行 | 不需要 |
| 读取已保存的两条真实 Live 场景 | 可以，是历史回放 | 不需要 |
| 输入 API Key、检查本机是否设置 | 可以，只检查本机配置 | 需要自己获授权的 Key |
| 新 Live 消息、Hello、余额查询、--run 连通性测试 | **当前不允许，等待团队解除冻结及批准预算** | 需要 Key 和预算授权 |

**5 次生成请求已用完，剩余 0。换电脑没有账本，不代表获得新额度。不要删除账本、换路径、换 Key 或提高上限绕过。** 教你配置 Key 不等于授权调用；配置存在不能证明 Key 有效、余额足够或本轮执行成功。

Live 只有 query_tickets 和 search_policy；其余六工具未开放。Mock 可以用 8 工具，但成绩与 Live 分开。包内没有 B 原来的完整 judge/、100 条正式用例和判定器，tests/ 是 A 的自测，cases/demo.json 是示例。

## 2. 解压并找到项目根目录

把整个 ZIP 解压到自己的目录，如 D:\ticket-agent-v3-B。不要在压缩包里双击源码。在能看到 README.md、target、scripts 和锁文件的那一层打开 PowerShell：

```powershell
cd D:\ticket-agent-v3-B
Test-Path .\target\agent.py
Test-Path .\requirements-deepseek-lock.txt
Get-Content -Raw -Encoding UTF8 .\PACKAGE_MANIFEST.json | ConvertFrom-Json | Select-Object source_commit,branch
```

两个 Test-Path 应为 True。目录只是示例，不需要 A 电脑的路径。包不含 .git；看 manifest 判断版本，需要提交历史时再克隆 GitHub 对应分支。

收到 ZIP 旁的 SHA256 文本后，检查下载是否损坏：

```powershell
Get-FileHash -Algorithm SHA256 "D:\下载目录\你收到的交接包.zip"
```

结果应与 .sha256.txt 一致；manifest 还列出各文件哈希。A 会对本次 ZIP 解压、校验并自测。

## 3. 安装 Python 3.12 和依赖

A 的实际环境为 Python 3.12.14；其他 Windows 版本的全新安装未逐一验证。

```powershell
py -0p
py -3.12 --version
py -3.12 -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt
.\.venv-deepseek\Scripts\python.exe -m pip check
```

没有 py 时先安装可信的 Python 3.12 发行版并重开终端，也可用实际解释器路径替代 py -3.12。不要复制他人的虚拟环境，里面常有绝对路径。

直接调用虚拟环境解释器，无需 Activate.ps1，无需改 PowerShell 执行策略。pip check 应显示 No broken requirements found。安装会访问软件包仓库，不请求 DeepSeek；失败时不要直接把所有包升级到最新版。

主要版本以 requirements-deepseek-lock.txt 为准：LangChain 1.4.5、langchain-core 1.6.10、langchain-deepseek 1.1.1、LangGraph 1.2.15、OpenAI SDK 3.29.0、httpx 0.28.1、Streamlit 1.65.0。

## 4. 第一件事：不配置 Key，跑离线自测

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/handoff_offline_selftest.py
```

该入口适用于解压包，不依赖 A 原机的数据库、真实账本或三套虚拟环境。它为子进程清除模型凭据、限制 Python 只能访问回环网络、使用新临时 DB/Trace，并运行现有 unittest。DeepSeek 用例内部使用 httpx.MockTransport，不消耗真实 API。

锁定环境预计输出 status=passed、tests=102、skipped=0、blocked_network_attempts=0、new_deepseek_api_requests=0。log 指向 artifacts/runtime/B-offline-*/unit.txt，同目录有 result.json。跳过不为 0 时先核对依赖，不能计为通过。

scripts/run_deepseek_review_offline.py 是 A 原机的三环境审查入口，依赖未打包的原文件和账本，不适用于 B 新机器。scripts/audit_deepseek_live.py 同样依赖原账本；缺失时读取已有 audit.json / budget_snapshot.json，不要造空文件补齐。

## 5. 从零跑 Mock：先隔离数据

同一个 PowerShell 里按顺序运行：

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_ENGINE="legacy"
$env:AGENT_MODEL="glm-4-flash"
$env:AGENT_LC_TOOLSET="all"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$env:DEEPSEEK_API_KEY=""
$env:AGENT_API_KEY=""
$env:LANGSMITH_TRACING="false"
$env:LANGCHAIN_TRACING_V2="false"
$runId=Get-Date -Format "yyyyMMdd-HHmmss-ffff"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\B-mock-$runId\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\B-mock-$runId\traces"
.\.venv-deepseek\Scripts\python.exe data/seed.py
.\.venv-deepseek\Scripts\python.exe cli.py once "查明天上海到杭州的高铁"
```

seed 应生成 2100 条虚构库存，查询真实执行本地 query_tickets。这里 glm-4-flash 只是沿用的模型标签，provider=mock 表示没有请求该模型。

每批测试换新 runId；不同用例隔离 session、进程和数据库。agent.reset 清记忆，不还原库存或订单。seed 默认拒绝覆盖；日期过期时换新目录重建。不要对包内证据 tickets.db 执行 seed --reset。

### CLI 多轮完整 Mock 流程

```powershell
.\.venv-deepseek\Scripts\python.exe cli.py chat
```

在交互窗口逐行输入：

```text
查明天上海到杭州的高铁
我要买一张
支付
查我的订单
帮我退掉
q
```

这是查询→模拟锁座/下单→模拟支付→订单查询→模拟退票，不是真实购票。实际调用和状态看输出。多轮必须在同一个 cli chat 中输入；多次 cli once 是不同进程，不继承上下文。

示例批量为 `cli.py batch cases/demo.json`，不是正式 100 条；最好换新 Mock 库再跑，避免受手工订单影响。

### Mock Web

保持上述 Mock 环境变量，在同一终端运行：

```powershell
.\.venv-deepseek\Scripts\python.exe -m streamlit run web/app.py
```

首次 Email 提示可以留空回车。使用终端的 Local URL，通常 localhost:8501。先确认当前模式为 Mock，再发送消息；右侧查看工具参数、ok、结果与耗时。历史页只回放文件，不恢复会话。Ctrl+C 停止服务；服务运行时不要把新命令输入它的进程。

LangChain Mock：停止服务，换新 runId 和 DB/Trace，设置 AGENT_ENGINE=langchain、AGENT_PROVIDER=mock、AGENT_LC_TOOLSET=all，再 seed 和启动。它使用真实框架调度，但模型决策仍是规则 Mock，成绩单独统计。

六变异只支持 legacy Mock。Web 左侧勾选；恢复后清空会话再测。Python 用 providers.set_mutation(name,value)，结束 providers.clear_mutations()。date_offset 取 1，其余取 True。这些不是环境变量开关，不在 LangChain/Live 启用。

## 6. API Key 是什么，如何获取

它是应用访问 DeepSeek API 的凭据，不是网页登录密码、GitHub Token 或 Codex 登录信息。由队长确认账户归属、费用和使用授权；需要时为 B 建立单独授权 Key，不能把 A 的秘密随包发送。

官方 [API 开放平台](https://www.deepseek.com/platform/)提供“获取 API Key”，指向[密钥管理页](https://platform.deepseek.com/api_keys)。登录本人/团队授权账户，在 API Keys/密钥管理中按当前平台界面创建并保存。账户余额与权限由持有人确认。可查[官方文档](https://api-docs.deepseek.com/zh-cn/)。入口于 2026-10-16 核对；登录后的账户状态未代查。

不要把 Key 发到群里、粘进源码、截图、报告、Trace 或 Git。不要给 A 发送完整 Key。本项目只读 DEEPSEEK_API_KEY；AGENT_API_KEY 属于旧 OpenAI 兼容 Provider，不能代替它。不要修改 Codex 自身模型或认证配置。

## 7. 安全配置 Key：可以输入，暂不运行 Live

先停止旧 CLI/Web，在项目目录新开 PowerShell。下面仅将隐藏输入放入当前终端进程，不写 Git、不联网：

```powershell
$keyInput=Read-Host "输入你获授权的DeepSeek API Key（隐藏输入）" -AsSecureString
$keyPtr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($keyInput)
try {
    $env:DEEPSEEK_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPtr)
    Remove-Variable keyInput,keyPtr -ErrorAction SilentlyContinue
}
```

不要把完整 Key 写在一条明文赋值命令里并截图，避免进入历史。环境变量最终以明文交给 Python 子进程，是 SDK 工作所需，不代表加密存储。

设置 Live 参数本身不会请求模型：

```powershell
$env:AGENT_PROVIDER="deepseek"
$env:AGENT_ENGINE="langchain"
$env:AGENT_MODEL="deepseek-flash"
$env:AGENT_BASE_URL="https://api.deepseek.com"
$env:AGENT_LC_TOOLSET="read_only"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:DEEPSEEK_THINKING="disabled"
$env:LANGSMITH_TRACING="false"
$env:LANGCHAIN_TRACING_V2="false"
$env:AGENT_API_KEY=""
```

只检查变量是否存在，不打印值、不联网、不创建或重置账本：

```powershell
@'
import os, json
print(json.dumps({"key_present": bool(os.getenv("DEEPSEEK_API_KEY", "").strip())}))
'@ | .\.venv-deepseek\Scripts\python.exe -
```

应看到 key_present=true。False 通常是新开终端没有继承、拼错变量名或输入为空。True 不证明密钥有效、余额足够或网络可达；本轮不验证真实 Key，也不查余额。

本节只配置，不启动 Live CLI/Web。继续测 Mock 时，重新执行第5节的全部 Mock 环境设置，别留下 AGENT_PROVIDER=deepseek 后直接点发送。

**代码不会自动加载 .env。** 只建 .env 写入 Key 不会生效，本教程使用环境变量即可。不需要 setx 写全局配置；当前终端关闭后，另一个新终端不会自动继承这些临时值。已有 Web 不会读到后来修改的环境，需从这个终端重新启动，但当前禁止启动 Live 发送。

结束时先 Ctrl+C 停止带 Key 的子进程，再清除变量并关闭终端：

```powershell
Remove-Item Env:\DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
```

清除父终端变量不能清掉已运行的子进程环境，必须先停止它们。不要用完整环境变量列表、echo Key 或 Debug 日志来检查。

## 8. 为什么现在不能点 Live 发送

预算 5/5 已耗尽。配置 Key、换电脑、重新解压、换 session 都不会产生授权。本包不含真实账本，也不替 B 创建新可用额度；不能自设预算路径、提高上限或删账本。

下一阶段先由团队确认：是否解除冻结、批准多少生成请求、谁管理额度、共享哪个真实账本、B/C 如何分配。然后 A 提供相应批准配置。当前教程不提供绕过冻结的启动器。

获准后入口仍是 CLI once/chat、Streamlit 发送和 Agent().chat。一条消息可能产生多次模型请求，不是“一条用例=一次费用”。check_deepseek_api.py --run 还会做余额、Hello、两个工具场景，不能随手当免费预检重跑。不要反复点击发送碰运气或并发压力测试。

届时业务 DB/Trace 可以隔离，费用账本须使用团队指定共享位置；不能拿 SDK 桩账本替代真实账本。只允许 query_tickets/search_policy，不得改 all 开其余六工具。

现在可以读 docs/evidence/deepseek/api-20261016-001224-2c3484/report.json 及 traces 中两个 JSONL。那是修复前已保存的真实场景，新 Prompt/守卫尚未在线回归，不能混为一谈。

## 9. Python 接口、Trace 与正式 100 条用例

入口仍为 `from target.agent import Agent; agent=Agent(); result=agent.chat(session_id,message)`。环境在导入 config/Agent 前设置；多轮复用同一个 agent/session，不同进程内存不共享。

正常返回 10 顶层字段、calls 5 字段，以 docs/contract.md 为准。tool_sequence 是实际调用顺序；stop 是循环结束，不代表业务成功。result_preview 会截断，完整结果看 deepseek_runs.jsonl 的 tool_end，不要从最终回复猜调用。

Live 失败抛 DeepSeekError，包括 API 错误、未知 Token、预算耗尽、工具失败和能力越界。B 要捕获，不能假定每次都有返回字典。失败旁证有 error/category、tool_attempts、tool_sequence、model_final 原始最终文字、observed_tokens 已确认部分；完整 tokens=null。CLI 失败退出 2，诊断对象不是正常契约；错误后当前内存会话清空，磁盘历史保留。

详见 [B 冻结对接](B_V3只读冻结测试交接_20261016.md)和[原 100 条复用](B_DeepSeek正式测试交接_20261016.md)。使用 B 自己的 judge/cases/assertions；不覆盖 A 的 tests，不修改原标准答案换分。复核五个 xfail/xpass，不能把95 passed+5 xfailed写成100 passed。

关闭额外真实 LLM 裁判后再跑正式 Mock；legacy Mock、LangChain Mock、Live 分组统计。支付成功等不适用只读 Live 的用例记 N/A，不能算 PASS。正式 Live 回归需另行批准预算。

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| 找不到 py/python | 安装或定位 Python3.12，新开终端；不要用商店占位符 |
| 找不到虚拟环境解释器 | 检查项目根目录和 venv 是否创建成功 |
| 缺 langchain_deepseek 等模块 | 用同一解释器装锁文件，再 pip check |
| Activate.ps1 被拦 | 无需激活，直接调用虚拟环境 python.exe |
| seed 提示库存在 | 换新 runId；不要覆盖原证据，reset 不还原数据库 |
| 中文乱码 | 运行前设 PYTHONIOENCODING=utf-8；文件按 UTF-8 读 |
| Streamlit 要 Email | 留空回车，那里不是 API Key 输入框 |
| 网页打不开 | 确认服务仍运行，使用终端 Local URL；端口占用可改 server.port |
| missing_DEEPSEEK_API_KEY | 在同一终端按第7节输入；.env不自动生效 |
| 401/authentication_failed | 经批准在线后检查 Key 权限；不要提交认证头 |
| 402/insufficient_balance | 由持有人核对计费，别反复重试 |
| request_budget_exhausted | 停止，找 A/队长协调，不删账本 |
| timeout/429/500/503 | 保存脱敏证据和已占预算，不自动重试或加压 |
| read_only_capability_violation | 看原 model_final；越界输出已拒绝，不是业务成功 |
| tool_execution_failed | 查看 ok=false、tool_end；不能用最终成功话术盖过失败 |
| token_usage_unknown | 总用量未知，不能填0或用observed_tokens冒充总数 |

交回 A/C 时记录包版本、依赖、模式、用例/session、输入、Trace/旁证、判定理由和脱敏截图。历史真实运行5生成+1余额GET，输入4796/输出563，总5359，实际费用未知；本次打包不新增模型请求。正式成绩由B提供，C再制作报告。
