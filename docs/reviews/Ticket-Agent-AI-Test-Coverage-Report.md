# AI Test Coverage Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0，35项未提交成果保留；未 reset/clean/checkout/stash/commit/push。所有 V3.10 执行使用独立 SQLite/session/execution_id，未连接正式库或真实铁路/支付服务。

分母明确：

| 维度 | 实际/分母 | 说明 |
|---|---:|---|
| 工具 | 3/11 | search_stations/query_trips/check_inventory |
| 业务流程 | 1/5 | 只读查询 |
| 订单状态 | 0/6 | 无写流程 |
| 合法转换 | 0/10 | 无 |
| 安全/权限 | 0/7 | 无 |
| 异常/恢复 | 0/4 | 无 |
| 多轮 | 0/1 | 无 |
| 回复一致性 | 0/1 | 无 |
| Trace 完整 | 13/13 steps | 最终 10 条 execution 的 run steps |
| AI 候选执行率 | 10/10 | 已批准 10，执行 10 |
| 故障检出 | 0/0 | 未注入故障到最终 AI 执行 |

不得把 10 条只读通过写成十类业务覆盖；建单/支付/退款/改签/取消仍未覆盖。
