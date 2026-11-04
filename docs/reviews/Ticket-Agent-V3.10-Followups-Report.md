# V3.10 追问报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 根因

`web/conversation._followup_suggestions` 在 `view.status=='failed'` 或没有保存的 followup 时直接返回；长会话/失败轮次可能没有可点击追问。

## 修复

新增 `_fallback_questions`，按以下状态返回 2–3 个确定性追问：

- 有 PENDING order：查看订单详情、继续模拟支付、退款/改签规则；
- 有 PAID/CHANGED order：订单明细、部分退款、改签方案；
- 失败操作：重试、查看订单、政策；
- 铁路轮次：完整经停、比较下一班、其他席别；
- 普通轮次：规划铁路、示例政策、我的订单。

saved followup 仍优先；过滤后为空才用 fallback；失败 Agent 轮次也显示；不使用固定五轮/十轮上限。

## 测试

`test_every_turn_has_deterministic_followup_fallback` 覆盖普通、失败、20 次重复调用；`test_user_policy_chat` 既有“检索失败不展示追问”语义保留。

限制：未做真实 20 轮 UI 点击回放；fallback 的结构性覆盖已通过。
