# A：V3.3 真实多模型接入开发报告

日期：2026-10-25。分支 `feat/ticket-agent-v33-live-providers`，恢复点 `be3efcf934b292db5f51cadf3b48a9074a5f3b69`。本轮实际完成代码与离线验证，按照用户最后要求，没有执行任何真实验证 `--run`。

## 完成情况

| 功能 | 状态 | 证据/边界 |
|---|---|---|
| 百炼独立 Provider、原工具复用 | 【已实现并离线验证】 | 真实 ChatOpenAI + MockTransport，通过 create_agent 工具结果回传 |
| DeepSeek 兼容 | 【已离线验证】 | 原 SDK、只读/沙箱、预算及错误测试继续执行；历史实际证据保留 |
| 四模型选择与会话隔离 | 【已实现并离线验证】 | Legacy / LangChain Mock / DeepSeek / Bailian；切模型新会话/库 |
| 初次验证预算 | 【已实现并离线验证】 | Provider 独立账本、两模型共用初次三生成请求上限，零重试 |
| 真实运行命令 | 【已实现并离线验证】 | 默认预检；--serve 仅启动，--run 才生成 |
| Live 元数据 sidecar | 【已实现并离线验证】 | Provider/实际模型/case/SHA/时间/用量/事件/错误与独立来源 |
| LangSmith REST + 脱敏确认 | 【已实现并离线验证】 | POST + GET 匹配方能 verified，独立回执；不自动全量上传 |
| 本轮 DeepSeek 真实验证 | 【尚未验证】 | 0 请求；已有环境 Key 存在，但未使用 |
| 本轮百炼真实验证 | 【尚未验证】 | 0 请求；本进程未配置 DASHSCOPE_API_KEY |
| LangSmith 真实远端验证 | 【尚未验证】 | 0 上传；本进程未配置对应 Key |
| 本轮真实双模型质量比较 | 【尚未验证】 | UI 可读独立记录；无真实成绩，无排名 |

历史 DeepSeek 两工具与 V3.1 沙箱证据仍是历史证据，不冒充本轮验证。默认本轮 Live 仅 query_tickets/search_policy，不声称八工具 Live 全通过。

## 修改文件与原理

- `config.py`、`target/agent.py`：增加 bailian 配置和 LangChain 入口校验；Mock 默认与旧 OpenAI/DeepSeek 配置保留。
- `target/bailian_runtime.py`：独立地址/模型/Key、原预算复用、只读 HTTP 检查、错误分类和零重试。百炼只读，不继承 DeepSeek full_sandbox。
- `target/live_providers.py`：小型配置选择与初次总预算；没有另造票务系统或复杂 Provider 框架。
- `target/langchain_agent.py`：复用原循环、middleware、工具和 InMemorySaver；实际模型耗时及 Provider sidecar，框架自动 tracing 始终关闭。
- `target/deepseek_runtime.py`：原逻辑保留，新入口可选总预算预留、复用通用秘密脱敏。原正式账本没有改动。
- `target/live_evidence.py`：新元数据文件，不向公共十字段追加信息。
- `target/observability.py`：显式过滤上传、两套变量映射、远端核验及独立回执。不要求 LangSmith 才能运行 Agent。
- `scripts/live_providers.py`：安全预检/localhost/显式真实验证及单次报告；原启动器仅更新“不限次数”的过时说明，旧环境构造测试保留。
- `web/app.py/runtime.py/conversation.py/laboratory.py`：模型选择、隔离与费用确认，LangSmith 内容预览和独立操作。
- `web/evidence.py/comparison.py/integrations.py/trace_view.py`：两 Provider Live 不混入 Mock、真实记录对照、当前实现状态与回执关联。
- `.gitignore`：忽略百炼本地 Trace。未提交 .env，依赖文件未修改。
- 新测试：`tests/test_live_providers.py`（15）、`test_observability.py`（12）、`test_live_provider_ui.py`（7），合计 34 项。

模型选择工具的证据来自模型结构化调用和原工具真实执行；没有把字符串规则伪装成真实 Function Calling，没有把错误工具调用替换为成功回复。查票/政策事实仍由 Python 工具提供。

## 最终离线结果

源码冻结提交 `a405fb6`；完整 SHA 见交付证据的 report.json。最终文档/证据提交 HEAD 由 `git rev-parse HEAD` 提供，避免文件自引用。

执行 `.venv-deepseek/Scripts/python.exe scripts/verify_v33_offline.py --out artifacts/runtime/v33-providers-release-20261025`：

| 环境 | 收集 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|---:|
| 完整模型依赖，纯离线 | 256 | 256 | 0 | 0 |
| V3 | 256 | 197 | 0 | 59 |
| V2 | 256 | 118 | 0 | 138 |

Mock smoke、八变异 25 条运行记录/8 标注样本、离线及缺/假 Key 预检通过。所有子进程清除真实凭据，非回环 Python 网络阻断开启。三环境复验不相加为用例总数。B 正式断言未改、未在本轮重新执行。

原 222 项与新 34 项共同回归，Mock 不会偷偷联网，Live 不回退 Mock，未知用量不造 0，异常/失败/预算拦截有独立证据。较小环境因可选依赖跳过，不写成通过。

原 data、业务工具、政策、八变异实现、contract、历史 Trace/B 快照不变；旧保护清单中仅三个预期修改的核心源码变化，其他原件哈希均保持。正式账本仍 5/5，最终核对见 evidence compatibility.json。完整回归日志及独立旁证存 `docs/evidence/v33-live-providers/20261025/`。

## 请求、Token 与费用

| 对象 | 本轮真实请求 | 真实用量/费用 |
|---|---:|---|
| DeepSeek | 0 | 没有生成，新增费用 0；桩 Token 不计费 |
| 百炼 | 0 | 没有生成，新增费用 0；账户/模型权限未验证 |
| LangSmith | 0 | 没有上报；未验证远端和账户 |

真实运行的费用在无可靠价格/账单时记 null/未知，不根据 Token 随意估价。账本预留量可能含失败/崩溃/阻止后的保守预留，不能等同已扣款。

## Git 与未完成项

实现提交：`73ea353`（运行时）、`6ec4642`（LangSmith）、`3a94ec0`（UI/命令）、`7630699`（来源与边界）、`a405fb6`（预算提示）。验证、第一次保护检查失败及修复过程均见 `docs/v33_live_providers_development_log.md`。

仍需：用户手动配置百炼及 LangSmith Key、匹配账户地域/模型；明确运行真实验证命令；B 审核实际 tool_calls/参数/政策忠实度和双模型表现；C 基于真实证据录制。初次三请求无法同时完整覆盖两 Provider 文本/查票/政策全部场景，需要取舍，超额必须重新授权。T04 与 B 旧统计风险不在本轮改动。

**成员 A 开发交接状态：有条件交接。** 可交付代码/离线结果与独立命令；本轮真实 Provider 和 LangSmith 远端尚不能标记通过。
