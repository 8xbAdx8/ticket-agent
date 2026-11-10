# DeepSeek Generation Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0，35项未提交成果保留；未 reset/clean/checkout/stash/commit/push。所有 V3.10 执行使用独立 SQLite/session/execution_id，未连接正式库或真实铁路/支付服务。

DeepSeek 使用现有 Provider `deepseek-flash`、真实 API、无自动重试。最终 5 条质量 PASS，全部经过用户逐批实际批准并在 V310Adapter 执行 PASS：

| case_id | 目标 | 工具 |
|---|---|---|
| AI-GEN-4ae2a85b44994a35 | 上海虹桥站搜索 | search_stations |
| AI-GEN-30ffe9d683f44748 | 二等座余票 | query_trips/check_inventory |
| AI-GEN-14a86bdeddd042db | AOH→HGH 分页 | query_trips |
| AI-GEN-0e9919962d014e9e | 杭州东站搜索 | search_stations |
| AI-GEN-b905ea5104f74da7 | limit=4 查询 | query_trips |

另有早期 DeepSeek 候选因参数或 checks 错误被质量/执行拒绝，保留证据；未修改原始响应。

已知 Token 与未知预留见 Budget 报告；费用 UNKNOWN。
