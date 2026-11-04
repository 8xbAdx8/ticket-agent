# Ticket Agent — End-to-End User Journey Audit

日期：2026-11-04（Asia/Shanghai）。执行角色：真实用户 + 测试/后端/前端/QA。  
本轮主流程使用 **DeepSeek Live / deepseek-flash**；Qwen 本轮未新增调用。所有铁路交易为本机模拟；未接真实 12306 或支付。

## 1. 执行环境

- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 暂存：0；未 commit/push/merge/tag
- 浏览器：真实 Edge + Playwright，桌面 1600×1100 / 手机 390×844
- UI：原版 Ticket Agent 用户工作空间
- 独立数据库：`artifacts/runtime/e2e-user-journey-20261104-210500/simulation.sqlite`
- 产品 `data/v39/simulation-v391.sqlite`：**未连接/未写入**
- 保护资产：GTFS ZIP、阶段八 static.sqlite、2100 Fixture、tickets.db 均未变
- 政策源：`data/policies.md` 恢复 HEAD 精确 SHA `bfef7138...`；本轮只做运行时 D9 投影

## 2. 实际用户流程与结果

### A. 自然语言查票

用户输入：

> 帮我查询2026年11月5日上海虹桥到杭州东的高铁。只展示当前页和前三班，不要自动翻完所有页。

实际结果：

- DeepSeek Live 自主调用查找车站、查询静态车次；
- 页面显示 `共 109 班 · 本页 50 班`；
- 可见车卡 **3 张**，其余 47 张滚动；
- 前三班：G7541 05:52→06:51、G1321 06:07→06:56、G7331 06:13→07:07；
- 模型未自动翻完三页，未触发 Token 预算；
- 无 `list.get`、PageError、Console Error。

**A = PASS（当前页/卡片/数量）**；第二页点击会创建新的自然语言操作，未在本次窗口内完成确认，故“分页端到端”只能标记 PARTIAL。

### B. 选择车次/席别/乘客与报价

用户输入：

> 我要乘坐 G7541，2026-11-05 上海虹桥 AOH 到杭州东 HGH，二等座，2 名合成乘客：测试用户A、测试用户B。先查询模拟库存并生成报价卡，不要直接创建订单或支付。

实际结果：

- `railway_check_inventory`：模拟库存 20；
- `railway_quote_fare`：单价 ¥30，合计 ¥60，quote ACTIVE；
- 聊天显示完整报价卡；
- 未创建订单、未支付。

**B = PASS**。

### C. 建单提案与界面确认

用户输入：

> 报价已核对，现在确认创建模拟订单。请调用创建订单工具生成待我在界面确认的提案，不要支付。

实际结果：

- `railway_create_order` 生成 `CONFIRMATION_REQUIRED`；
- 右侧“待确认铁路操作”出现建单卡；
- 用户勾选“我已核对，确认这次本地模拟操作”后点击确认；
- 订单生成，状态 `PENDING_PAYMENT`；
- 本脚本验证订单：`V39-dd6f726df6d64f9d8152c8eb6c332a73`，2 名乘客，¥60。

**C = PASS**。

### D. 模拟支付

用户输入：

> 请为当前订单 V39-... 生成模拟支付确认卡，不要直接支付，等我确认。

实际结果：

- `railway_get_order` + `railway_pay_order` 生成 PAY 提案；
- 右侧确认卡；
- 勾选并确认后，订单 `PAID`，支付流水 `TX079b...`，金额 6000 分，状态 SUCCEEDED；
- 只有一笔 PAYMENT，无重复扣款。

**D = PASS**。

### E. 查看订单

用户输入：

> 查看我的订单，确认订单 V39-... 的当前状态和乘客明细。

实际结果：

- 订单 `PAID`，支付状态 `SUCCEEDED`；
- 2 名乘客均 ACTIVE；
- 订单金额 6000 分；已付 6000；无退款/改签。

**E = PASS**。

### F. 部分退款

用户输入：

> 请为订单 V39-... 的乘客“测试用户B”生成部分退款确认卡，按 P01 计算手续费，先不要执行退款。

实际结果（数据库）：

```text
refund RF73525a...
amount_fen=3000  fee_fen=600  net_fen=2400
status=SUCCEEDED
order active=1, refunded=1, fee_total=600
transaction REFUND CREDIT 2400 SUCCEEDED
```

界面右栏显示：`PAID · ¥30.00 · 有效乘客 1 · 已退 1 · 手续费 ¥6.00`。  
但聊天区在该轮出现 `rag_answer_inconsistent`（D9 被误识别为车次 + 车次权威只取本轮），属于 **P1 UI 误报**，不是退款失败；该 Bug 已修复但本轮最后未重跑退款 UI。

**F = PARTIAL（业务成功，UI 误报已修复待复验）**。

### G. 改签

用户输入：

> 订单 V39-... 的乘客“测试用户A”改签到 2026-11-05 的 G1321 二等座，生成改签确认卡；不要直接执行改签。

实际结果（数据库）：

```text
change CH0c5702...
target_trip_id=5l000G132108
target_service_date=2026-11-05
difference_fen=-2000
status=CONFIRMED
order_status=CHANGED
change_status=SUCCEEDED
transaction CHANGE_REFUND CREDIT 2000 SUCCEEDED
```

右栏显示 `CHANGED · ¥10.00 · 有效乘客 1 · 已退 1 · 手续费 ¥6.00`。  
聊天区在该轮显示 `observed_token_budget_exhausted`，但工具已完成、提案已确认、数据库状态已变更；这是 **P1 多轮上下文预算**问题。已增加历史压缩并提高有界预算，但未在本轮最后做完整 Live 重跑。

**G = PARTIAL（业务成功，UI 预算误报已修复待复验）**。

### H. 账务核对

订单 `V39-dd6...`：

```text
paid_total_fen      6000
refunded_total_fen  4400  (退款 2400 + 改签退款 2000)
fee_total_fen        600
net_paid_fen        1600
new total_fen       1000
active_item_count      1
refunded_item_count    1
order_status       CHANGED
```

`6000 - 2400 - 2000 = 1600`，与 `net_paid_fen` 一致；一笔 PAYMENT、一笔 REFUND、一笔 CHANGE_REFUND；无重复交易。

## 3. 本轮发现并修复的 Bug

| ID | 严重度 | 问题 | 根因 | 修复 |
|---|---|---|---|---|
| E2E-B1 | P1 | 新审计库启动即 `PROTECTED_DATABASE_NAMESPACE` | Store 白名单未包含 `e2e-user-journey-` | 加入独立命名空间 |
| E2E-B2 | P1 | 后续报价/建单/退款回答被显示为“查票记录不一致” | 审计车次权威只取本轮 `railway_query_trips`；`trip_id=5l000G75410A` 被解析为 `G75410` | 报价 `trip_id` 纳入本轮权威；解析 `G7541`；跨轮 session 车次覆盖 |
| E2E-B3 | P1 | `D9` 被当成车次 | 车次正则 `[GDCZTK]\d+` 匹配政策版本 `V3.9.1-D9...` | 排除 D9；新增测试 |
| E2E-B4 | P1 | 改签多轮后 `observed_token_budget_exhausted` | 32k 上下文 + 多轮报价/订单/退款历史 | 历史回答超过 3 轮压缩到模型上下文；预算默认 48k、上限 64k；Trace 不变 |
| E2E-B5 | P1 | 结果卡片 `list.get` | 历史/嵌套结果容器与静态 fallback 未统一适配 | `web/result_rows.py` + 全调用链；新增 13 项契约测试 |
| E2E-B6 | P2 | 支付/退款/改签没有独立表单入口 | 原版右栏只展示订单 JSON，交易由聊天提案驱动 | 保持原 UI；聊天+确认卡为真实路径；不新增铁路独立页 |
| E2E-B7 | P2 | 退款/改签聊天提示与右栏真实状态相反 | 与 B2/B3 同源；业务已成功但操作状态 FAILED/BLOCKED | 修复 B2/B3/B4；需最终 UI 复验 |

## 4. 代码修改

- `target/v39/store.py`、`scripts/run_v39_tests.py`：`e2e-user-journey-` 独立命名空间。
- `target/diagnostics.py`：报价 `trip_id` 纳入权威；排除 D9。
- `web/conversation.py`：跨轮 session 车次覆盖显示守卫。
- `target/v39/model_result.py`：历史回答压缩；Trace 保真。
- `target/deepseek_runtime.py` / `bailian_runtime.py`：默认输出 1024；有界 turn budget 48k（上限 64k）。
- `web/result_rows.py`、`web/railway_cards.py`、`web/railway_queries.py`、`web/user_features.py`、`web/user_layout.py`、`web/runtime.py`：结果容器统一适配。
- `tests/v39/test_v310_stability.py`：14 项契约测试。

未改 D9/P01 交易规则、正式 103/B、GTFS/Fixture/产品 DB、原版 UI 架构。

## 5. 真实 DeepSeek API

本轮 E2E 使用真实 DeepSeek Live；没有 Mock/Fake/预写回答。  
本轮前约一小时的本机 v33 会话合计：

```text
HTTP 96
prompt 617,888
completion 17,446
total 635,334
cost UNKNOWN
```

说明：96 次包含本轮为确认建单/支付/退款/改签进行的多次真实尝试（含失败/重试），**没有设置硬性单轮请求上限**；这是本轮执行纪律偏差，未把重复尝试成本隐藏。最后一次完整闭环订单：

- provider：`deepseek_live`
- model：`deepseek-flash`
- 会话：`web-7e6a60b08bcd`
- 订单：`V39-dd6f726df6d64f9d8152c8eb6c332a73`
- PAID → REFUND 2400 net → CHANGE G1321 → CHANGED
- 费用：**UNKNOWN**，不写 0

## 6. 浏览器与数据库

- Live Edge 截图：`A/query`, `B/quote`, `C/order`, `D/pay`, `F/refund`, `G/change` 等；
- 原版 UI，四规格 47/47（离线浏览器批次）：
  - 1600×1100 浅/深；
  - 390×844 浅/深；
  - PageError 0 / Console Error 0 / RequestFailed 0；
- 独立 SQLite 真实状态：
  - `V39-dd6...`：CHANGED；active 1；refunded 1；paid 6000；refunded 4400；fee 600；net 1600；
  - 3 条交易：PAYMENT 6000 / REFUND 2400 / CHANGE_REFUND 2000；
  - `refund_requests` 1 SUCCEEDED；`change_requests` 1 CONFIRMED。

## 7. 回归

| 范围 | 结果 |
|---|---|
| V3.9 + 本轮 | **314 passed / 0 failed / 0 skipped** |
| 旧完整回归 | **1640 passed / 11 failed / 1 skipped** |
| 旧失败/skip ID | 与 sealed **完全相同** |
| 浏览器 | **47/47**，8 截图，PageError/Console/RequestFailed 0 |
| 新增测试 | 14 项（适配、跨轮车次、D9、预算/截断、政策） |

## 8. 最终状态

```text
USER_JOURNEY_VERIFIED: PARTIAL
QUERY_VERIFIED: PARTIAL（当前页/109/卡片 PASS；第二页 UI 未最终确认）
BOOKING_VERIFIED: PASS
PAYMENT_VERIFIED: PASS
ORDER_VERIFIED: PASS
REFUND_VERIFIED: PARTIAL（DB成功；UI误报已修复待复验）
CHANGE_VERIFIED: PARTIAL（DB成功；UI预算误报已修复待复验）
REAL_API_VERIFIED: PARTIAL（DeepSeek真实；Qwen本轮0；完整闭环有重复尝试）
BROWSER_VERIFIED: PASS（47/47，Mock/离线；Live 查询/建单/支付截图）
REGRESSION_VERIFIED: PASS（旧失败/skip ID 不变）
PROTECTION_VERIFIED: PARTIAL（产品v391冲突仍BLOCKED；其余资产未变）
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
OVERALL: PARTIAL
```

## 9. 未解决/阻塞

1. 退款/改签在最后代码修复后的 **完整 Live UI 复验**未完成；业务数据库已成功。
2. 查询第二页的 UI 操作会创建新的自然语言请求，未在本次窗口内完成确认。
3. 支付/退款/改签没有独立表单；只能聊天生成提案 + 右侧确认，属于原版 UI 限制，未擅自改造。
4. 产品 `simulation-v391.sqlite` 来源冲突仍 BLOCKED。
5. 本轮 DeepSeek 请求量 96、Token 635k；未设置更严格硬上限，后续必须限制。
6. 独立审查、用户验收未执行。
