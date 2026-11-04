# V3.10 Agent 架构审计


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 架构链

UI（原版用户工作空间）
→ `web/runtime.Conversation`
→ `web/v39_bridge.prepare` / `web/business_state`
→ `target/langchain_agent` + V3.9 Registry
→ `target/v39/service` + SQLite
→ `target/v39/read_model` / `web/business_panels` / `web/v39_bridge`

## Prompt 链

- Legacy `SYSTEM_PROMPT` 仍有旧 `lock_seat` 规则，仅用于旧八工具。
- V3.10 `prepare()` 用 `str.replace` 将第 4 条替换为“无独立锁座、create_order 确认后自动 hold”，再拼接 V3.9 动态铁路说明。
- DeepSeek/Qwen 使用同一 `effective.prompt` 和同一 Registry；Provider 仅决定 transport。

## 工具/权限链

`target/v39/registry.py` 真实注册 11 个 `railway_*`；没有 `railway_lock_seat`。`ACTIONS` 只映射 create/get/pay/cancel/refund/change。`railway_create_order` 只返回 proposal；用户界面确认后 `web/business_actions.confirm` 调 Service。

## 订单/交易链

`railway_quote_fare` → `railway_create_order` proposal → 用户确认 → `Service._create` 自动写 `v39_holds(ACTIVE, 900s)` + `PENDING_PAYMENT` → PAY proposal → `Service.confirm` → `v39_transactions(PAYMENT, SUCCEEDED)` + `PAID`。

## UI 读取链

`web/business_state.current` 只读已提交 SQLite，`business_panels` 负责订单/操作，`v39_bridge` 负责 pending + 新二维码；旧 `web/payment.py` 仅服务旧 `tickets.db`，不再作为 V3.10 支付依据。

## 发现

- 旧 Prompt 的 `lock_seat` 规则会误导 V3.10 模型。
- 旧支付 QR 未接入 V3.9。
- 追问在失败/长会话可能无 saved followup。
- 完整报告见各专项；状态为 PARTIAL，不是 COMPLETE。
