# 只读质量修复后的最新说明（2026-10-16）

源码修复提交 `e216fdf57ec8f34b84134ba2b30b05e5d6ff5985`。请先看 [当前冻结交接](A_V3只读冻结质量修复报告_20261016.md)。两工具已有历史Live证据，其余六工具未开放；本轮102项A离线自测通过，新增API请求0，额度仍5/5。新提示词尚未联网回归；旧ZIP bff292cd是修复前版本。

下方保留前次审查/演示背景，其中“待修复话术”“过时标签”已由本轮离线修复，旧缺Key结论仅属于历史。

---

# 最新安全与费用核对：2026-10-16

| 项目 | 已有真实运行 / 本次审查 |
|---|---|
| 生成请求 | 已发生5次，均HTTP200；本次新增0次 |
| 余额GET | 已发生1次；本次不重查 |
| 输入/输出/合计Token | 4796 / 563 / 5359 |
| 输入缓存命中/未命中 | 2944 / 1852 |
| 实际扣费 | 未知；没有供应商账单或可归属余额差值，不能写0元 |
| 预算 | 5/5用尽，剩余0；不得增加、删除或另建账本继续调用 |
| 当前余额/密钥有效性 | 未重新验证，只确认执行当时请求成功 |
| 安全审查 | 工作区/归档/可达Git历史未发现密钥；原数据/Trace/账本未变 |

核对来源：[原运行报告](../../evidence/deepseek/api-20261016-001224-2c3484/report.json)、[只读账本快照](../../evidence/deepseek/review-20261016/budget_snapshot.json)、[审查结果](../../evidence/deepseek/review-20261016/audit.json)、[安全扫描](../../evidence/deepseek/review-20261016/security_scan.json)。本轮没有查询收费接口或按未核对费率估算精确金额。

---

## 历史存档：2026-10-15 费用记录原文

以下“0次/0元”只对应未配置密钥的接入开发阶段，不能作为已发生5次Live请求的费用结论。

# DeepSeek API 安全与费用记录

日期：2026-10-15（Asia/Shanghai）。分支 `codex/ticket-agent-deepseek-live`，已验证源码与证据提交 `d40b005ebdad2a57c8a09aa86d97911e1203f344`，接手基线 `85d457a4f34b4fad848ded4cf9c2d7334813c399`。本批文档会形成后续提交；最终 SHA 用 `git rev-parse HEAD` 获取。本轮未推送远程分支。

**真实 API 尚未验证。** 实际没有检测到可用环境密钥，生成请求 **0 次**，余额 HTTP 请求 **0 次**。连通性、密钥有效性、余额、实际返回模型 ID、真实 Function Calling 均跳过；真实 Token 为“不适用/未知”，本轮无 API 调用费用，不代表账户总账单为零。

**成员 A 开发交接状态：有条件交接。** A 的代码与离线验证可以交 B 接入回归；DeepSeek 实际效果和 C 的真实模型演示暂不能验收。A 不提供 B 正式成绩，不把 SDK 桩或 LangChain Mock 当作真实模型结果。

## 实际费用账本

| 项目 | 本轮实际记录 |
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

费用账本默认 `artifacts/runtime/deepseek-budget/requests.db`，使用 SQLite 事务在请求前占名额。超时/崩溃/结果未知时不退还名额，避免重复计费。状态 reserved_outcome_unknown 表示可能已发送/到达，不能认为免费失败。余额 GET 另行计数，不属于生成请求。

上限只覆盖本项目支持的同步入口和同一 ledger；不能限制其他客户端、账户整体消费或人为删除/更换账本。没有精确的输入 Token 预估器，观察阈值不能保证严格总 Token 或人民币上限。默认输出 cap、请求体 cap、模型轮数和最多 5 次生成请求共同降低成本。不得绕过限制，超过当前授权前须再次确认预算。

本阶段无写工具，故不会发生未知结果的支付重提。将来开放写操作必须保留独立授权/归属/状态/幂等，超时先查询状态核验，不可自动重复提交。

## 隐私与错误

密钥仅在进程环境中使用，不进入 Trace、报告或 Git；不保存请求头、原始响应错误正文或完整 AIMessage。LangSmith 外部追踪默认关闭，SDK/传输调试日志受抑制。旁路只存最终回复、结构化工具事件、用量和脱敏错误。

400 invalid_format；401 authentication_failed；402 insufficient_balance；422 invalid_parameters；429 rate_limited；500 server_error；503 service_unavailable；连接错误 network_connection；超时 timeout。还单独报告 missing_DEEPSEEK_API_KEY、request_budget_exhausted、token_usage_unknown、dependency_missing 等本地错误。只存类别和状态码，不存响应错误正文、Authorization、原始异常堆栈或内部推理。

思考模式当前明确阻断：安装包离线检查显示不能把 AIMessage 里的 reasoning_content 回传到工具循环。官方说明携带 tools 时需要回传真实历史字段；因此不能用虚构或空内容补齐。当前只验证非思考载荷，启用思考需新适配和独立测试，不把内部推理展示给用户。[官方思考协议](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)

## 证据索引

- [当前无密钥检查结果](../../evidence/deepseek/missing_key_run/report.json)
- [明确标注的离线 SDK 证据](../../evidence/deepseek/offline_sdk/offline_evidence.json)
- [SDK/错误/隐私/Web 测试日志](../../evidence/deepseek/sdk_ui_unit.txt)
- [最终全部测试](../../evidence/deepseek/final_unit.txt)
- [接手数据与证据保护清单](../../evidence/deepseek/baseline.json)

官方错误类别参考：[DeepSeek 错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。LangChain 接入位置参考：[ChatDeepSeek](https://docs.langchain.com/oss/python/integrations/chat/deepseek)、[create_agent](https://docs.langchain.com/oss/python/langchain/agents)。介绍页的旧模型样例不作为本项目模型选择依据，实际配置固定为官方当前模型名。
