# V3.10 业务状态一致性报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 统一源

SQLite `v39_orders/v39_holds/v39_proposals/v39_transactions` 是权威；`web/business_state.current` 只读提交后的快照；Agent 回复不能替代数据库。

## 本轮修复

- `business_actions.confirm` 在可信 UI 确认后清理 LangGraph `pending_actions/deadlines/sources`，避免“订单已创建但页面仍等待确认”。
- 新增 `UI_CONFIRMED_PROPOSAL` 审计，`business_state` 以数据库回执计算 operation 状态。
- 订单 PENDING 时显示操作区；PAY pending 时显示 QR；PAID 后隐藏待支付 QR。
- `v39_payment` 不在 PAID/过期/金额不匹配时显示 QR。

## 实测数据库

```
V39-305b23d846aa4f35962582d4e5a0c2d7
PAID / SUCCEEDED
total 3000 / paid 3000
hold H428... status CONSUMED
PAYMENT TX0ce... 3000 SUCCEEDED
```

## 限制

- 退款/改签操作入口存在，但本轮没有再次执行完整的 Live 退款/改签；
- 旧历史订单 `V39-e912...` 已 `EXPIRED/UNPAID`，不能恢复为可支付；
- 只读历史页只展示状态，不恢复确认权限。
