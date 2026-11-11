# V3.11-R1 Offline Lifecycle Report

HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，未 commit/push。本轮只做离线整改，没有调用真实模型；原 R1 86 条请求、原始 FAIL、Trace、checkpoint、10 个 SQLite 和旧证据全部保留。

## 离线 A–F

使用现有 SDK Stub（原 Agent 图/Registry/Service，不调用真实模型），专项 9 个测试通过：

```text
tests/test_ai_scenario_v311.py::test_agent_three_passenger_refund_change_remaining_to_cancelled
tests/test_ai_scenario_v311.py::test_agent_cancel_and_clock_expire_preserve_orders
tests/test_ai_scenario_v311.py::test_failed_payment...
tests/test_ai_scenario_v311.py::test_duplicate_request...
...
9 passed
```

其中完整链覆盖：

```text
create → pay → partial refund → change (same order_id) → partial refund
→ full refund → CANCELLED
```

并覆盖未支付取消、Hold 过期、拒绝、重复请求/只读恢复、失败交易。最终 Oracle invariants 全部通过。

## 改签语义

改签沿用原 `order_id`，旧 hold 关闭、新 hold/目标 quote/差价写入；没有错误断言“必须生成第二张订单”。

## 限制

SDK Stub 不是 Live；不能计入真实模型成绩。DeepSeek 原 Live `CHANGE_TRIPS` 工具规划失败仍保留，不因离线测试通过而删除。
