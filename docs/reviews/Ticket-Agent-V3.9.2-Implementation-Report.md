# Ticket Agent V3.9.2 — Implementation Report

## 0. 结论

- **UI**：原版 Ticket Agent 用户工作空间已恢复；V3.9.1 独立铁路页不再是入口。
- **GTFS**：原 Agent 经 Registry 调用已有只读静态 Adapter；真实站/车次/经停可用。
- **Provider**：Qwen、DeepSeek 均已真实发起 HTTP API，并能自主调用 V3.9 工具；但 B 的模型汇总班次数与工具实际 40 班不一致，**LIVE_API_VERIFIED = PARTIAL**。
- **交易**：V3.9.1 D9/P01、退款、改签、账务、库存、幂等、T057–T076 保留；V39 测试 **164/0/0**。
- **保护冲突**：`data/v39/simulation-v391.sqlite` 在 V3.9.2 窗口内出现未解释变化（quote/proposal/audit，无订单/交易）；已停止该库写入并报告，未删除/回滚。**PRODUCT_DB_PROTECTION = BLOCKED**。
- **独立审查**：NOT_RUN；用户验收：PENDING_USER_ACCEPTANCE。

## 1. 现场

- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 暂存区：空；未 Commit/Push/Merge/Tag。
- 开工 manifest：`artifacts/runtime/v391-unified-20261103-204243/start-manifest.json`
- 原版 UI 依据：HEAD `web/app.py` + 现有 `web/conversation.py/user_layout.py/css` + Phase5 报告。

## 2. UI 恢复

`web/app.py` 已恢复 `出行助手 → web.conversation.user_page()`，不再有独立铁路页面二选一。  
`web/railway_simulation.py` 保留但不再是入口；V3.9 通过 `web/v39_bridge.py` 融入原右侧栏/原聊天。  
详见 `Ticket-Agent-V3.9.2-UI-Restoration-Report.md`。

## 3. 静态 GTFS

- DB `e32f0cd4...`；GTFS `3877dbc0...`；3169/11588/107669/187。
- 原 Agent → Registry → `target/v39/static.py`。
- 离线聊天已验证真实 FOUND/G531 等；原聊天区显示真实工具结果表。
- 详见 `Ticket-Agent-V3.9.2-GTFS-Integration-Report.md`。

## 4. Provider

代码改动：`target/v39/registry.py`、`deepseek_runtime.py`、`bailian_runtime.py`、`live_providers.py`、`web/v39_bridge.py`、`web/runtime.py`、`web/conversation.py`。

真实 API：

| Provider | A | B | C | D |
|---|---|---|---|---|
| Qwen qwen3.8-flash | PASS | PARTIAL（41 vs 实际40） | PASS | 无未授权写入，但请求错误 |
| DeepSeek deepseek-flash | PASS | PARTIAL（38 vs 实际40） | PASS | 0 orders/transactions/proposals；请求错误 |

所有 HTTP 200；tokens 见两份报告；货币成本接口未提供，不编造。  
`LIVE_API_VERIFIED = PARTIAL`；不是完整通过。

## 5. 测试与旧回归

| 范围 | 结果 |
|---|---|
| V3.9/V3.9.1 全套 | **164 passed / 0 failed / 0 skipped** |
| T057–T076 | **20/20**；20 db-probes |
| 旧全范围 | **1640 passed / 11 failed / 1 skipped** |
| 旧失败/ skip ID | 与 sealed **完全相同** |
| B 正式 103 | BLOCKED，未执行/计分 |

证据：`artifacts/runtime/v391-d9-lifecycle-20261103-234500-v392b/`；旧回归 `artifacts/runtime/v391-d9-lifecycle-20261103-150639/old-regression-v392/`；比较 `artifacts/runtime/v392-original-ui-browser3/old-regression-comparison.json`。

## 6. 浏览器

原版 UI 四规格 **38/38、4 截图、页面错误0**：桌面/手机、浅/深；原 hero、右栏、模型入口、铁路 rail、静态查询工具表、无独立铁路页、无横向溢出。  
详见 `Ticket-Agent-V3.9.2-Browser-Visual-Regression-Report.md`。

DeepSeek Live 原版 UI 普通对话成功：`v392-live-ui-deepseek4.png`。  
Qwen 原版 UI 普通对话成功；Qwen UI 车次工具查询仍报通用错误；直接 Python A/B/C 通过，不把工具查询 UI 记为通过。

## 7. 数据库隔离

- launcher 明确设置 `RAILWAY_SIM_DB_PATH`：
  - `artifacts/runtime/v392-launcher/offline/<date>/simulation.sqlite`
  - `artifacts/runtime/v392-launcher/live/<date>/simulation.sqlite`
- session 默认 `artifacts/runtime/v392-user/<date>/simulation.sqlite`。
- Store 只新增 `v392-` 允许前缀，未放宽旧保护。
- 启动器日志打印实际 `railway_database`。
- 旧库不删除。

保护冲突见 `Ticket-Agent-V3.9.2-Database-Isolation-Report.md`：v391 DB 从 430080/`0f887d...` 变为 462848/`9ebf39...`，含 1 quote/1 proposal/11 audit，0 orders/transactions；来源未解释，已停止写入该库。

## 8. 保护与限制

保留：GTFS ZIP、static DB、2100 Fixture、旧 tickets DB、正式 103/B、V1.0–V1.2.2、历史失败批次、历史 ZIP。  
未 Commit/Push/Merge/Tag；未启用 Bridge；未调用 Harness；未接真实铁路/支付。

限制：

1. Qwen/DeepSeek B 模型班次数与工具实际 40 不一致；UI 工具表已显示真实 40/limit结果。
2. Qwen 原版 UI 普通对话通过；车次工具查询 UI 未通过；直接 API 通过。
3. 产品 v391 DB 出现未解释写入，保护审计 BLOCKED。
4. 未完成真实 UI 3 人全流程；业务由 V39 tests/SQLite probes 覆盖。
5. API 货币成本未知。
6. 单确认 Worker 限制仍在。

## 9. 状态

```text
IMPLEMENTED: YES (UI restoration, bridge, GTFS Agent, provider whitelist, DB isolation)
TESTED: YES (V39 164/0/0; original UI 38/38; old regression IDs unchanged)
LIVE_API_VERIFIED: PARTIAL (Qwen/DeepSeek A/C; B tool call but count mismatch; D no mutation/error)
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
BLOCKED: Qwen UI live; B consistency; product v391 protection conflict; formal 103/B; Bridge
```
