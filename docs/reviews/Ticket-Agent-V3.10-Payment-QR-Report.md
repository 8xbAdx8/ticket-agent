# V3.10 支付二维码报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 根因

`target/payment_qr.py` 已有 `render_qr`，但唯一调用点是旧 `web/payment.py`（旧 `tickets.db` + `demo_payment`）。V3.10 `business_panels/_orders` 只生成 PAY proposal，没有 QR；`v39_bridge` 只显示 pending 文本。因此 V3.9 支付链无二维码。

## 修复

新增 `web/v39_payment.py`：

- 只接受 `action=PAY`、`state=PENDING`、未过期、订单 `PENDING_PAYMENT/UNPAID`、金额一致；
- 用 `Decimal(total_fen)/100` 精确转元；
- `render_qr(order_id, amount, str(amount))`，payload 只含 order_id/amount/currency/demo；
- 刷新从 SQLite 的 pending proposal + order 重新生成，不存图片；
- 只读历史显示 QR 但明确禁止确认；活跃页面在 `v39_bridge` pending 卡中显示 QR；
- 支付确认仍走 `business_actions.confirm` / `Service.confirm`，不调用真实支付。

## 实测

Live DeepSeek：

```
订单 V39-305b23...
PAY proposal P3fbae3030ae8478aaae641063479b641
QR 显示：订单 V39-305... ¥30.00 CNY 本地模拟
确认后 PAID
交易 TX0ce8551e006d4b109c5a1206e429a9ee PAYMENT 3000 SUCCEEDED
```

截图：`live-qr2.png`、`live-paid2.png`。

## 限制

- 本轮未在 QR 显示后主动刷新页面再确认（刷新恢复逻辑由 AppTest 和 read-only 投影验证，Live 刷新未完成）；
- 支付方式选择只用于展示，不持久化为业务字段；
- 不提供真实扫码回调。
