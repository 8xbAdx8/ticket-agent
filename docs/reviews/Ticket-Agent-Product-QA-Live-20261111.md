# Ticket Agent 产品 QA 真实模型补测

2026-11-11 · `feat/ticket-agent-v36-stabilization` · HEAD `8a6ccf36688c9cab803d46ba0bbf652290132e19`

DeepSeek 和 Qwen 均通过原版聊天、真实工具调用、待确认卡自动定位、用户确认及 SQLite 建单和模拟支付。在线场景生成与落库通过，3 条生成候选均未通过最终可执行性核验，整体为 **PARTIAL**。

原离线报告 [Ticket Agent 产品操作与缺陷检测](Ticket-Agent-Product-QA-20261111.md) 和历史成绩完整保留。下面的证据路径以 `artifacts/runtime/v310-v311-qa-product-live-20261111/` 为根。

| Provider | 生成 HTTP | Agent HTTP | 总 HTTP / 上限 | Prompt Token | Completion Token | 费用 |
|---|---:|---:|---:|---:|---:|---|
| DeepSeek | 2（含修复复验） | 4 | 6/6 | 38,369 | 1,894 | UNKNOWN |
| Qwen | 1 | 5 | 6/6 | 39,823 | 1,791 | UNKNOWN |
| 合计 | 3 | 9 | 12/12 | 78,192 | 3,685 | UNKNOWN |

12 次均有真实 HTTP 200 和用量回执，总计 **81,877 Token**，剩余 0 次。所有请求与账本、原始响应逐条匹配，自动重试为 0。单次生成输出上限 4096，Agent 输出上限 2048。发送前的 SQLite 限额拦截第 7 次单家请求和第 13 次全批请求。第一轮每家各生成 1 条候选。DeepSeek 完成 Agent 验收后余 1 次，在原账本里用于已修正提示的页面复验。整个批次沿用授权的两个硬上限。见 `authorization.json`、`budget-preflight.json`、`retest-admission.json`、`budget-final.json`、`raw-http/`。

## 真实 Agent 与数据库

两家各在全新会话发送同一建单需求。输入包括 G7331、2026-11-05、上海虹桥 AOH 至杭州东 HGH、合成乘客三三和二等座。没有预建报价、订单或提案。两家实际选用 `railway_query_trips`、`railway_check_inventory`、`railway_quote_fare`、`railway_create_order`。DeepSeek 在一轮里提出库存和报价，Qwen 分两轮提出。原始工具参数与审计记录一致，返回值通过原 `ToolMessage` 进入后续真实模型请求。

| 证据 | DeepSeek | Qwen |
|---|---|---|
| 提案生成、参数匹配和自动定位 | PASS | PASS |
| 确认前无订单、Hold 和交易 | PASS | PASS |
| 用户确认后的 PENDING_PAYMENT、ACTIVE Hold 与幂等回执 | PASS | PASS |
| 单独发起页面支付并确认 | PAID，1 笔 2000 分模拟交易 | PAID，1 笔 2000 分模拟交易 |
| Trace、数据库回执、外键、库存及资金守恒 | PASS | PASS |
| 页面刷新后只读恢复，SQLite 指纹保持一致 | PASS | PASS |

建单提案来自真实模型，支付提案来自用户点击原页面入口。Playwright 记录提案首次可见坐标、确认前后、支付和历史截图，两家 PageError 均为 0。网络拦截的图标等请求与 Console 原始记录保留。SQLite Oracle 记录会话、提案、订单、Hold、幂等键、交易、来源运行及调用 ID。证据见 `live/agent-deepseek/`、`live/agent-bailian/`、`verification.json`。

## QA-09 生成提示与质量门误判

**P1，已修复。** 两家首次生成均成功持久化，质量门初判 PASS。两条候选都使用了生成提示里的错误经停路径 `result.data.0.stop_id`。实际工具 `railway_trip_stops` 返回 `data={trip,stops}`。只读复查确认这些断言取不到证据。DeepSeek 还省略了 `train_no`，把区间首条 G7541 误当成 G7331。

`target/scenario_generator.py` 修正经停路径示例和指定车次的过滤要求，并在审核时校验经停列表索引及数量断言路径。两条历史样本重新检查均为 REJECTED，原生成数据未编辑。DeepSeek 修复复验使用正确的 `data.stops` 路径并实际筛选 G7331。该候选仍生成了缺少 `enabled` 的 `flag` 步骤，还断言全程只有 2 个站。GTFS 全程实际有 9 个站，候选被现有门控拒绝。Qwen 已耗尽 6 次，针对其原样本完成离线回审。

3 条原始候选均保留 PENDING。复查只读取 GTFS 并评估可取得的结果断言，没有批准或通过正式执行入口运行候选。证据见 `live/generation-deepseek/`、`live/generation-bailian/`、`retest/generation-deepseek/`、`verification.json`。

## 回归与现场保护

新增 1 项经停形状回归。修复后隔离专项 76 passed / 0 failed / 0 skipped。前一轮 2023 / 11 / 1 全量及 580 / 0 / 0 专项保留原范围，未用新专项重算旧失败。新批次比对 8457 项受保护资产，零差异。原 SQLite、R1 账本、历史 FAIL 和 Trace 保留。Git 未暂存、提交或推送，两个隔离服务均关闭。

证据见 `prompt-fix-targeted.xml`、`prompt-fix-targeted.log`、`opening.json`、`verification.json`。

```yaml
PRODUCT_OPERATION: PASS
AI_SCENARIO_GENERATION: PARTIAL
LIVE_AGENT_TEST: PASS
DATABASE_ORACLE: PASS
BROWSER_E2E: PASS
BUGS_FOUND: 9
BUGS_FIXED: 9
REGRESSION: PASS
OVERALL: PARTIAL
```

缺陷数包含原离线 QA 的 8 项。真实模型通过范围为本批两条建单链路，退款、改签等仍引用原离线产品和 SQLite 验证。
