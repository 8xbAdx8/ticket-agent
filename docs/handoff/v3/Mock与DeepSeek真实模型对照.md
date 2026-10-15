# 最新对照：2026-10-16

DeepSeek已有5个真实生成请求，Hello及两个独立只读工具闭环已复核。Mock原8工具与六变异离线回归保持通过；其他6工具的DeepSeek Live、真实多轮/安全质量和B正式100条回归未验证。两类成绩不能混合，SDK桩不计Live。

实时已停止，当前API冻结；实际收费未知。详情见 [A 最新审查](A_DeepSeekLive验证审查_20261016.md) 和 [B 正式测试对接](B_DeepSeek正式测试交接_20261016.md)。

---

## 历史存档：2026-10-15 对照原文

下面“Live尚未请求”的内容只反映当时接入准备。

# Mock 与 DeepSeek 真实模型对照

日期：2026-10-15（Asia/Shanghai）。分支 `codex/ticket-agent-deepseek-live`，已验证源码与证据提交 `d40b005ebdad2a57c8a09aa86d97911e1203f344`，接手基线 `85d457a4f34b4fad848ded4cf9c2d7334813c399`。本批文档会形成后续提交；最终 SHA 用 `git rev-parse HEAD` 获取。本轮未推送远程分支。

**真实 API 尚未验证。** 实际没有检测到可用环境密钥，生成请求 **0 次**，余额 HTTP 请求 **0 次**。连通性、密钥有效性、余额、实际返回模型 ID、真实 Function Calling 均跳过；真实 Token 为“不适用/未知”，本轮无 API 调用费用，不代表账户总账单为零。

**成员 A 开发交接状态：有条件交接。** A 的代码与离线验证可以交 B 接入回归；DeepSeek 实际效果和 C 的真实模型演示暂不能验收。A 不提供 B 正式成绩，不把 SDK 桩或 LangChain Mock 当作真实模型结果。

| 标记 | 本次实际情况 |
|---|---|
| 【真实 API 已验证】 | 否；缺少密钥，未发送请求 |
| 【LangChain Mock 已验证】 | 原 8 工具、六变异、CLI/Web 回归通过 |
| 【仅代码实现】 | ChatDeepSeek 官方接入；两个只读工具具备离线 SDK 协议证据 |
| 【尚未验证】 | DeepSeek 联网、真实工具选择、多轮任务与安全表现 |
| 【存在问题】 | 当前 SDK 不回传思考字段；思考模式被明确禁用；输入 Token 与费用只能受有限约束 |

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
