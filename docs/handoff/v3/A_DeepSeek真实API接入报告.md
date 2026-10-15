# A：DeepSeek 真实 API 接入报告

日期：2026-10-15（Asia/Shanghai）。分支 `codex/ticket-agent-deepseek-live`，已验证源码与证据提交 `d40b005ebdad2a57c8a09aa86d97911e1203f344`，接手基线 `85d457a4f34b4fad848ded4cf9c2d7334813c399`。本批文档会形成后续提交；最终 SHA 用 `git rev-parse HEAD` 获取。本轮未推送远程分支。

**真实 API 尚未验证。** 实际没有检测到可用环境密钥，生成请求 **0 次**，余额 HTTP 请求 **0 次**。连通性、密钥有效性、余额、实际返回模型 ID、真实 Function Calling 均跳过；真实 Token 为“不适用/未知”，本轮无 API 调用费用，不代表账户总账单为零。

**成员 A 开发交接状态：有条件交接。** A 的代码与离线验证可以交 B 接入回归；DeepSeek 实际效果和 C 的真实模型演示暂不能验收。A 不提供 B 正式成绩，不把 SDK 桩或 LangChain Mock 当作真实模型结果。

## 完成状态

| 标记 | 本次实际情况 |
|---|---|
| 【真实 API 已验证】 | 否；缺少密钥，未发送请求 |
| 【LangChain Mock 已验证】 | 原 8 工具、六变异、CLI/Web 回归通过 |
| 【仅代码实现】 | ChatDeepSeek 官方接入；两个只读工具具备离线 SDK 协议证据 |
| 【尚未验证】 | DeepSeek 联网、真实工具选择、多轮任务与安全表现 |
| 【存在问题】 | 当前 SDK 不回传思考字段；思考模式被明确禁用；输入 Token 与费用只能受有限约束 |

## 实现与依赖

在既有 LangChain Agent 上增加 ChatDeepSeek，并未重建业务系统。实际安装独立 `.venv-deepseek`，Python 3.12.14，pip check 通过。原环境与旧锁文件保留，新 requirements-deepseek-lock.txt 只比原 V3 锁新增 langchain-deepseek，不升级旧包。

- `langchain==1.4.5`
- `langchain-core==1.6.10`
- `langchain-deepseek==1.1.1`
- `langchain-openai==1.7.1`
- `langgraph==1.2.15`
- `openai==3.29.0`
- `httpx==0.28.1`
- `streamlit==1.65.0`

实际改动源文件（从 Git 基线差异整理）：

- `.gitignore`
- `cli.py`
- `config.py`
- `requirements-deepseek-lock.txt`
- `requirements-deepseek.txt`
- `scripts/capture_v3_live_ui.cjs`
- `scripts/check_deepseek_api.py`
- `scripts/verify_deepseek_offline.py`
- `scripts/verify_v3.py`
- `target/agent.py`
- `target/deepseek_runtime.py`
- `target/langchain_agent.py`
- `tests/test_deepseek_agent.py`
- `tests/test_deepseek_api_check.py`
- `tests/test_deepseek_runtime.py`
- `web/app.py`

## 工作流程与教学说明

DeepSeek 是决策者：接收提示词、历史消息和工具 Schema，返回服务端 tool_calls。LangChain create_agent 是调度者：把调用交给已有 StructuredTool，再将 ToolMessage（含同一调用 ID 和真实工具 JSON）送回模型。Python tools/mock_core 负责模拟库存与状态校验，RAG 仍检索原 15 条政策。模型不会直接操作数据库。

`Agent.chat → ChatDeepSeek → 官方 HTTPS API → AIMessage.tool_calls → LangChain 工具节点 → tools.dispatch → SQLite/RAG → ToolMessage → ChatDeepSeek → 最终回复`。

中间件记录实际模型响应元数据、声明的 tool_calls、工具开始/结束/参数/结果/耗时。它不从回复文字推测调用。只有发起 `/chat/completions` 的请求才进入生成请求预算；每次工具执行本身不产生模型 API Token 费用，模型读工具结果和作最终答复会再次请求 API。

## 接口与兼容性

`Agent().chat(session_id, message)` 保留，正常返回仍是原 10 顶层字段，calls 仍是原 5 字段；provider 新值为 `deepseek_live`，model 是请求配置，服务端实际模型 ID 在旁路事件 `model_response.response_model`。没有改 docs/contract.md，也未改原八工具、数据库业务、RAG、Trace 类或成员 B 的正式规则。

Token 用量未知或请求失败时，DeepSeek 路径抛出脱敏 DeepSeekError，并在 deepseek_runs.jsonl 保存失败；不创建含假 0 用量的普通成功 Trace。原契约未定义错误返回形状，因此不擅自添加字段/nullable Token。CLI 的错误 JSON 是诊断信息，不是 Agent 成功契约。B 若要求所有失败也返回完整契约，需先由团队确认未知 Token 的兼容表示。

默认 DeepSeek Trace 单独存入 traces/deepseek_live；建议每次显式指定隔离目录。已有会话隔离/重置、Web 卡片、历史 JSONL 回放、CLI 保留。DeepSeek 不支持 legacy 引擎，不允许把 MockProvider 注入成真实模式；六变异仍只供 legacy Mock 使用。

## 已执行验证

- `.venv-deepseek`：88/88 项 A 自测通过，0 跳过，见 [final_unit.txt](../../evidence/deepseek/final_unit.txt)。
- 原 `.venv-v3`：78 项通过、10 项明确跳过，见 [日志](../../evidence/deepseek/final_v3_compatibility.txt)。
- 原 `.venv`：35 项通过、53 项明确跳过，见 [日志](../../evidence/deepseek/final_v2_compatibility.txt)。跳过由缺少 httpx/LangChain/DeepSeek SDK 决定，不算通过。
- `scripts/smoke.py --output-dir docs/evidence/deepseek/mock_smoke`：10 项入口/服务检查通过，32 条 legacy Mock Trace；包含六种故意缺陷注入，见 [证据](../../evidence/deepseek/mock_smoke/verification.json)。
- `scripts/verify_v3.py --toolset all --baseline-manifest docs/evidence/deepseek/baseline.json --output-dir docs/evidence/deepseek/mock_framework_fixed`：11 轮 LangChain Mock API、8 工具及 CLI/Web 通过，见 [证据](../../evidence/deepseek/mock_framework_fixed/verification.json)。
- `scripts/capture_v3_live_ui.py --browser <本机浏览器> --out docs/evidence/deepseek/mock_browser_final`：5 轮实际 Mock 浏览器操作、JSON 下载/回放/代码/清空通过；这是 Mock 页面证据，不是 DeepSeek 页面成功截图。
- `scripts/check_deepseek_api.py --run --out docs/evidence/deepseek/missing_key_run`：实际结果为跳过，见 [report.json](../../evidence/deepseek/missing_key_run/report.json)。
- `scripts/verify_deepseek_offline.py --out docs/evidence/deepseek/offline_sdk`：4 次 MockTransport 桩请求，执行查询与政策两个闭环，远端请求 0；见 [明确标注的离线证据](../../evidence/deepseek/offline_sdk/offline_evidence.json)。

## 风险和未完成

缺密钥导致在线四组场景均未验证；SDK 桩不能证明真实模型选择工具、处理缺失条件或拒绝攻击的能力。原 B 的 95/100 基线没有更新，本次不生成覆盖率、成功率或正式成绩。6 个其余工具尚未向 DeepSeek 开放，需只读 Live 验证通过后另行评估，不能仅改 all 绕过保护。

当前 ChatDeepSeek 1.1.1 的离线载荷检查不回传 reasoning_content。非思考模式显式禁用该协议；不提供 enabled 演示。后续须采用支持真实字段保留/回传的版本或审查过的适配器，并单独验证，不补造空思考内容。

原 V2 保护快照中的 DB/Trace 与接手时数据已不同；本次使用接手时新清单，356 文件哈希保持。没有恢复/覆盖用户数据。早期 Windows SQLite 连接未关闭、旧环境依赖导入和历史基线失败证据均保留，最终结果见 final_* 与 mock_framework_fixed。

未修改 Codex 自身配置、认证或全局模型，没有推送主分支/强推/移动旧标签。源代码、离线验证具备交接条件，真实模型验收暂不具备。
