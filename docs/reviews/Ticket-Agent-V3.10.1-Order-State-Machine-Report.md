# Ticket Agent V3.10.1 — 订单流程卡死与业务状态一致性修复报告

日期：2026-11-04（Asia/Shanghai）。执行：DeepSeek 实施工程师。主流程使用真实 DeepSeek Live，原版用户工作空间，独立 SQLite。不是独立审查。

## 1. 真实运行追踪

发现会话：`web-ace9f11c127a`

用户操作：

```text
查询2026-11-05 上海虹桥 → 杭州东
我要买G7541的票，我叫三三
```

实际工具轨迹：

```text
railway_check_inventory  trip_id=5l000G75410A  quantity=1  → available=19
railway_quote_fare       trip_id=5l000G75410A  passenger=1 → quote Q49cb... total=3000
railway_create_order     quote_id=Q49cb... passengers=[person#...] contact=...
                         → P87a275811b3148b5a70d46d371cc0f81
                           status=CONFIRMATION_REQUIRED
```

关键事实：

- `railway_create_order` **没有**直接创建订单；它返回建单提案。
- 随后 SQLite 中存在订单：

```text
order_id     V39-e9121949fdff48718f195b505168e8d8
proposal_id  P87a275811b3148b5a70d46d371cc0f81
order_status PENDING_PAYMENT
payment_status UNPAID
total_fen    3000
active_item_count 1
```

- 该订单是 V3.9 `service.confirm` 的数据库结果；但旧 `v39_bridge` 的确认按钮**直接调用 service.confirm**，没有清理 LangGraph 的 `pending_actions`，也没有写入 `user_confirmation` 事件。
- 因此界面同时存在三个互相矛盾的状态：
  1. SQLite 已有 `PENDING_PAYMENT` 订单；
  2. `session.pending_action()` 仍非空，右栏继续显示“待确认”；
  3. Agent 的工具可见结果是“建单提案”，claim guard 因此写“建单尚无成功证据”。
- 旧右栏只显示订单摘要，没有支付/取消/退款/改签按钮。

结论：

1. 订单**确实创建**（数据库为准）；
2. 聊天“无成功证据”是 **UI/claim guard 状态同步 Bug**，不是订单不存在；
3. 右栏等待确认没有可操作按钮，是因为 V3.9 确认绕过了 Agent pending 清理，并且旧桥接没有订单操作区；
4. 没有支付入口，是因为旧桥接没有调用 `railway_simulation._orders`；
5. 现有 Trace **不能证明**旧路径存在用户点击确认；数据库只能证明 `service.confirm` 已执行。因此旧路径存在审计缺口；
6. 新路径在用户确认后才创建订单；重复确认由 proposal/idempotency 保护。

## 2. 修复内容

### 2.1 可信确认与状态同步

`web/runtime.py` 新增：

```text
Conversation.confirm_railway_proposal(proposal_id, approved)
```

它执行：

1. `service.confirm` / `service.decline`；
2. 清理 LangGraph `pending_actions`、deadline、source；
3. 写入 `UI_CONFIRMED_PROPOSAL` 可信 UI 审计事件；
4. 更新当前 operation：
   - `SUCCEEDED / CANCELLED / FAILED`
   - `stage=本地模拟操作已确认`
   - 清除旧 `awaiting_confirmation` 错误；
5. 保存 replay。

`web/v39_bridge.py` 的确认/撤销改为该方法，不再直接调用 service 后留下模型暂停。

### 2.2 订单操作入口

`web/v39_bridge.py` 在订单摘要下增加“订单操作”区，复用既有 `web.railway_simulation._orders`：

- PENDING_PAYMENT：生成模拟支付确认卡、生成取消确认卡；
- PAID/CHANGED：选择乘客、退款预览、生成退票确认卡、生成改签确认卡；
- 所有写操作仍先产生 proposal，再由用户勾选确认；
- 不新增页面、不改变原有布局。

### 2.3 声明一致性

`target/v39/business_claim_guard.py`：

- 有建单提案时显示“待你在界面确认，尚未创建订单”；
- 有真实订单时显示订单号与状态；
- 只有存在 `UI_CONFIRMED_PROPOSAL` 或真实 tool/get_order 证据时，才支持“已创建订单”；
- 不能仅凭模型文字或数据库存在就推断确认。

### 2.4 其他

- `target/v39/store.py` / `scripts/run_v39_tests.py`：允许 `v3101-e2e-` 独立库；
- 新增 1 项 UI confirmation marker 测试；
- 未改 D9/P01 规则、正式103/B、GTFS/Fixture、产品 DB。

## 3. 真实 UI 复验

使用 DeepSeek Live、原版用户工作空间、独立 DB：

```text
查询 2026-11-05 上海虹桥 → 杭州东
→ 109 班，当前页 10 班，G7541
→ “我要买G7541的票，我叫三三”
→ 模型正确询问席别，没有凭空建单
→ “二等座，确认下单”
→ railway_create_order 返回提案 P3a52...
→ 用户勾选并确认
→ 订单 V39-e308... PENDING_PAYMENT
→ 右侧出现“生成模拟支付确认卡 / 生成取消确认卡”
→ 点击生成支付确认卡
→ 支付提案 P8eba...
→ 勾选并确认
→ 订单 PAID，支付流水 TXc363...
```

实际数据库：

```text
order V39-e30842324d1f4616bcee6f2dd38da978
PENDING_PAYMENT → PAID
total_fen 3000
paid_total_fen 3000
active_item_count 1
transaction TXc363be6787a04174b2642b792a8ae234
PAYMENT 3000 SUCCEEDED
```

本次处理状态：

```text
本轮处理结束
本地模拟操作已确认
```

不再出现“已拦截/等待确认”，确认后也不再保留建单 pending。

截图：

- [D2-proposal.png](artifacts/runtime/v3101-e2e-20261104-214000/D2-proposal.png)
- [F2-pay-button.png](artifacts/runtime/v3101-e2e-20261104-214000/F2-pay-button.png)
- [G2-paid.png](artifacts/runtime/v3101-e2e-20261104-214000/G2-paid.png)

## 4. Bug 清单

| ID | 严重度 | 问题 | 根因 | 状态 |
|---|---|---|---|---|
| V3101-B1 | P1 | 订单 PENDING 但聊天说建单无证据 | claim guard 只认 tool_end，未纳入 UI confirmation/DB order | FIXED，测试 |
| V3101-B2 | P1 | 确认后右侧继续等待确认 | v39_bridge 直接 service.confirm，未清 LangGraph pending | FIXED，真实 UI |
| V3101-B3 | P1 | 无支付/取消/退款/改签入口 | v39_bridge 没有订单操作区 | FIXED，真实 UI |
| V3101-B4 | P1 | 旧确认无 user_confirmation 审计 | 直接 bridge 绕过 Agent capture | FIXED：新增 UI 审计 marker |
| V3101-B5 | P2 | 缺席别时不询问 | 本次真实模型正确询问；旧截图场景为已有席别上下文 | 无新增代码；保留澄清 |
| V3101-B6 | P2 | 历史/只读会话没有操作入口 | `restore_session` 只读 | PARTIAL，需最终确认刷新语义 |
| V3101-B7 | P2 | 重复点击支付/建单 | proposal 限一、confirm 幂等 | 由既有测试覆盖 |

## 5. 测试

| 范围 | 结果 |
|---|---|
| V3.9 + 本轮 | **315 passed / 0 failed / 0 skipped**（`v39-tests-final5`） |
| 旧完整回归 | **1640 passed / 11 failed / 1 skipped**，失败/skip ID 与 sealed 相同 |
| 浏览器 | **47/47**，8 截图，PageError/Console/RequestFailed 0 |
| 新增 | UI confirmation marker、pending/order claim、订单动作可见性 |

注意：浏览器 47/47 是离线 Mock 四规格；真实 DeepSeek Live UI 截图单独保留，不能把离线结果称为 Live API 验收。

## 6. 真实 API

- Provider：DeepSeek Live / deepseek-flash
- 真实 UI 请求记录：`artifacts/runtime/v33/user/web-33b3164edeac/traces/provider_runs.jsonl`
- 早期复现会话：`web-ace9f11c127a`（Qwen 历史，仅用于根因追踪，不是本轮 DeepSeek 验收）
- 费用：**UNKNOWN**
- 未自动无限重试；每个模型响应保留 HTTP/Token/finish_reason/工具调用。
- 本轮未新增 Qwen 调用。

## 7. 最终状态

```text
IMPLEMENTED: YES
UNIT_TESTED: YES（315/0/0）
BROWSER_TESTED: YES（47/47 离线四规格；Live 截图）
LIVE_API_VERIFIED: PARTIAL（DeepSeek 查询→提案→确认→支付已真实完成；退款/改签本轮未重新 Live 点击）
PURCHASE_FLOW_VERIFIED: PASS
REFUND_FLOW_VERIFIED: PARTIAL（动作入口已存在；最终 Live 点击未复验）
CHANGE_FLOW_VERIFIED: PARTIAL（动作入口已存在；最终 Live 点击未复验）
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
OVERALL: PARTIAL
```

## 8. 未解决/风险

1. 退款/改签按钮已接入，但本轮最后没有重新点击完成一次新的 Live 退款/改签。
2. 历史/只读恢复会话仍不提供写操作；刷新后能看订单但不能直接继续支付，需明确“新建会话继续”的产品决策。
3. 产品 `simulation-v391.sqlite` 来源冲突仍 BLOCKED。
4. 正式 103/B、Bridge、独立审查未执行。
5. 旧确认路径没有历史 `user_confirmation` 事件；只能保留原 Trace 并标注审计缺口，不能回写伪造。
