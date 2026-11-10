# AI Test Final Acceptance

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0；34项未跟踪/已修改工作区成果保留。未 reset/clean/checkout/stash；未 commit/push/merge/tag。

| 项目 | 结果 |
|---|---|
| DeepSeek 原生 V310 生成 | **FAIL**（HTTP 响应，候选 semantic REJECTED） |
| Qwen 原生 V310 生成 | **FAIL**（HTTP 响应，候选 semantic REJECTED） |
| DeepSeek/Qwen 语义质量 | FAIL / FAIL |
| AI 候选实际执行 | 0 |
| TEST_ONLY 执行 | 1 PASS |
| 业务断言 | TEST_ONLY 3/11 tools, 1/5 workflows |
| 缺陷检出 | 本轮真实候选 0/2 被拒绝；故障注入未作为 AI 执行 |
| AI 专项 | 74/0/0 |
| V3.10 | 387/0/0 |
| 完整回归 | 1441/80/1；非有效 1891 基线 |
| 浏览器 | 8/8 current |
| 保护 | 关键资产 PASS；5587 全量 NOT_RUN |
| Token | 已知 23,567；未知预留 369,555；剩余 6,878 |
| 费用 | UNKNOWN |
| 独立审查 | NOT_RUN |
| **OVERALL** | **PARTIAL** |
