# AI Test Budget Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0，35项未提交成果保留；未 reset/clean/checkout/stash/commit/push。所有 V3.10 执行使用独立 SQLite/session/execution_id，未连接正式库或真实铁路/支付服务。

本轮取消项目内部累计 Token 硬上限，保留审计：

```text
HTTP rows: 31
DeepSeek: 17 rows, 11 response_received, 6 unknown
Qwen:     14 rows, 8 response_received, 1 http_error, 6 unknown
Known tokens: 140,281
Unknown reserved: 403,918
Fee: UNKNOWN
Policy: ticket-acceptance-budget/3, max_total_tokens=None
```

未知记录未清零、未删除；旧 10 条未知和新增未知均保留预留。HTTP 50 次、输出 4096、Provider 配额仍生效；没有项目级 Token 拒绝。费用无法从现有响应核实，保持 UNKNOWN。
