# V3.10 锁座生命周期报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 根因

`railway_create_order` 只创建 proposal；`Service._create` 在用户确认后自动：

```
v39_holds(status=ACTIVE, expires_at=now+900s)
v39_hold_segments
v39_orders(order_status=PENDING_PAYMENT)
```

因此不存在独立 `railway_lock_seat` 工具，也不应新增。

## 真实查询

历史会话 `web-2cbc3378642f` 的“是的，锁座”：

```
model_tool_proposed railway_lock_seat
tool_result error=当前冻结配置禁止工具 railway_lock_seat
operation BLOCKED / tool_not_completed
```

实际订单 `V39-e912...` 已有 `hold_id=Hcc...`，说明建单流程确实自动 hold；当时该历史订单现已 `EXPIRED / UNPAID`。

## 验证

`test_v310_create_order_has_no_hold_before_confirmation_and_one_after`：

- 建单 proposal 前 orders=0、holds=0；
- 确认后 PENDING_PAYMENT、恰好一个 ACTIVE hold；
- 重复确认返回同一结果，orders/holds 仍各 1。

Live DeepSeek 新订单：

```
V39-305b23d846aa4f35962582d4e5a0c2d7
hold H42884112c9884d0498b1fb282cc9a31a
最终 PAID，hold 已 CONSUMED
```

锁座生命周期 = PASS（自动 hold、幂等、过期由 Service 管理）；单独锁座工具不存在是正确设计。
