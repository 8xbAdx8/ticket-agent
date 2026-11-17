# 真实 API 请求与 Token 用量

统计使用每次 usage 日志的 request_started 与对应 response，按 request ID 去重；浏览器 4 次计入，不将 start/finish 两条日志算成两次。

- bailian: 35 次，输入 32124 Token，输出 4427 Token，未知用量字段 0，HTTP 状态 {'200': 35}。
- deepseek: 31 次，输入 28632 Token，输出 3740 Token，未知用量字段 0，HTTP 状态 {'200': 31}。

合计 66 次真实模型生成请求；Embedding 0、LangSmith 0。HTTP 200 仅是 HTTP 状态，不能证明模型任务或质量通过。Token 来自服务端返回，不含推算。实际费用**未知**：没有可靠账单或逐请求计费依据，不以 0 元冒充。各个调用路径、时间、请求 ID、Trace ID 和原始响应记录见 `docs/evidence/live_lab_20261027/backend` 及 `browser-usage`；`usage-summary.json` 是独立聚合。

本轮源码回归 SHA `e5688aae59ee9a8716527aae5e4591a4da41a6c3`；报告提交 SHA 请用 `git rev-parse HEAD` 查看。主环境 699 项通过、109 个子测试通过；失败 0、错误 0、跳过 0。旧环境跳过情况：deepseek_unit 跳过 24；v3_unit 跳过 139；v2_unit 跳过 277；mock_smoke 跳过 0。本轮原文件快照 20059 项，变更 0 项。
