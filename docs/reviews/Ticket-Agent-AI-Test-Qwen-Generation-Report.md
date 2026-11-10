# Qwen Generation Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0，35项未提交成果保留；未 reset/clean/checkout/stash/commit/push。所有 V3.10 执行使用独立 SQLite/session/execution_id，未连接正式库或真实铁路/支付服务。

Qwen 使用现有 `qwen3.8-flash`，真实 API；一次 524 和一次 schema 形状问题均保留证据，未自动重试。最终 5 条质量 PASS、用户批准、V310Adapter 执行 PASS：

| case_id | 目标 | 工具 |
|---|---|---|
| AI-GEN-4b7d2ad324d842ac | 余票库存 | query_trips/check_inventory |
| AI-GEN-c8366411195c4fb2 | 车次分页 | query_trips |
| AI-GEN-4e2c3d5b415e47e2 | 车站搜索 | search_stations |
| AI-GEN-53078b35e865453a | 上海虹桥搜索 | search_stations |
| AI-GEN-eac8dfeb150e4d73 | 杭州东搜索 | search_stations |

Qwen 原始响应中的 `{role,content}` turns 仅做 transport 形状规范化，原始响应对应 `qwen-v310-pathfix-raw.json` 保留。
