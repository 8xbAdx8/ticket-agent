# Ticket Agent V3.10 追问系统稳定性专项报告

日期：2026-11-05（Asia/Shanghai）。范围：原版用户工作空间 + 现有 V3.10 Agent/业务架构；未改锁座、支付二维码、交易规则或全局消息发送架构。

## 1. 初始 Git 状态

```text
分支: feat/ticket-agent-v36-stabilization
HEAD: 953c8823bed988ec53579be794319d69adbf5b34
暂存: 0
工作区: Codex 已提交业务状态统一；本轮初 20 项未提交/新增
```

本轮未执行 reset/clean/checkout/commit/push/merge/tag；Codex 提交保留。

## 2. 故障复现

### A. 点击追问蓝色提示、聊天空白

代码路径：

```text
_followup_suggestions
→ st.button(on_click=_queue_followup)
→ st.session_state.user_followup_request
→ _consume_followup
→ 蓝色 info
```

修复前 `_consume_followup` 要求：

- `session.followups_for(record)` 存在且 `run_id` 匹配；
- `request.question` 在 saved suggestions 中；
- 并且用 **全历史 user_msg** 去重。

按状态生成的 deterministic fallback 没有 saved followup，因此点击必然落入：

> 这条追问已发送过或没有可关联的本轮政策证据，未重复提交。

同时候选按钮 key 只使用 `sid + run_id + index`，同一父回答/重复渲染时产生：

```text
StreamlitDuplicateElementKey: policy_followup_..._0
```

导致聊天区域渲染中断/局部空白。

### B. 五轮后追问消失

长会话中 fallback 没有 saved 记录，`_consume_followup` 无法关联；同时旧的全局去重把后续父回答下相同文本误判为“已经问过”。不是模型上下文压缩直接删除 UI，而是**提交端关联/去重错误**。

## 3. 修复

文件：`web/conversation.py`、`tests/v39/test_v310_contract.py`。

### 3.1 统一提交链路

`_queue_followup` 仍只写入 `user_followup_request`，由现有 `_consume_followup` → `execute` → `Conversation.send` → Agent 主流程处理。没有复制 Agent 调用，没有绕过 operation/persistence。

### 3.2 接受业务/政策/fallback 追问

- 按 `(session_id, parent_run_id, question)` 关联；
- 渲染时把当前父回答的 suggestions 写入 `followup_questions_<sid>_<run_id>`；
- `_consume_followup` 只要求问题属于**当前父回答**，不再要求政策证据或 saved followup；
- saved followup 存在时保留其 `followup_id`/generation_method；
- fallback 明确标记 `rule_fallback`；
- 政策证据校验仍发生在 Agent 回答/业务执行阶段，不在点击阶段拦截。

### 3.3 去重

使用：

```text
followup_sent_<sid>_<run_id>_<sha256(question)>
```

- 同一父回答同一问题：pending/sent 阻止重复；
- 不同父回答相同文本：允许；
- 提交失败/异常：移除 pending，允许安全重试；
- 不再使用全历史文本全局去重。

### 3.4 UI key

按钮 key 增加 `turn_key`（历史 turn index / 失败 request_id），不再因同一父回答重复渲染触发 `StreamlitDuplicateElementKey`；不再清空聊天。

## 4. 20 轮连续浏览器测试

环境：Edge + Playwright，原版用户工作空间，离线 Mock，独立 SQLite。

流程：查余票 → 每轮点击当前回答下的追问（包括经停、比较、最短运行时间、规划铁路），共 20 轮。

结果：

```text
20/20 轮有用户消息与 Agent 回答
每轮有“你可能还想了解”
无“这条追问已发送过”
无 StreamlitDuplicateElementKey
无 PageError
消息数量: 1 → 21
```

截图：`artifacts/runtime/v310-followup-20261105-012500/20-turns-fixed.png`

单次点击测试：

```text
点击“查看 G7541 的完整经停站”
→ 用户消息出现
→ 新经停回答出现
→ 新追问出现
→ 无蓝色提示
```

截图：`followup-click.png`。

## 5. 去重/错误测试

- 单元测试：同一父回答同一问题第二次返回 None；不同 run_id 同文本返回请求；
- 无 saved fallback 可接受；
- stale/foreign run_id 拒绝并给出明确提示，不清空聊天；
- 提交失败不永久占用 sent key；
- operation 仍由统一 `interaction.begin` 幂等保护。

浏览器 duplicate 专项没有独立截图证明“同一父回答按钮二次点击”；该分支由单元测试覆盖，整体浏览器状态标记 PARTIAL。

## 6. 业务回归

未修改 Registry、锁座/Hold、create_order、PAY、QR、business_state/panels/actions、订单 SQL 或 D9/P01。追问仍通过 `Conversation.send`，工具权限/确认机制不变。

```text
V3.10: 345 passed / 0 failed / 0 skipped
old:   1640 passed / 11 failed / 1 skipped（失败/skip ID 与 sealed 完全相同）
```

## 7. 真实 API

本次追问修复没有新增 DeepSeek/Qwen 请求；沿用现有 V3.10 证据，不增加预算，不把 Mock 称为 Live。

## 8. 数据库保护

未连接/修改 `data/v39/simulation-v391.sqlite`；GTFS、Fixture、tickets.db、正式103/B、历史账本未改。独立测试库仅 `artifacts/runtime/v310-followup-...`。

## 9. 已知问题/未完成

- 浏览器 duplicate 同父二次点击未单独截图；
- 订单/退款/改签追问的真实 Live 端到端未重新跑；
- 完整浏览器旧套件仍有一个隐藏“查车站”入口问题（非追问路径）；
- 独立审查未执行；
- 追问质量只做稳定性修复，未扩大生成质量工程。

## 10. 最终状态

```text
ROOT_CAUSE_IDENTIFIED: PASS
IMPLEMENTED: PASS
UNIT_TESTED: PASS（345/0/0）
INTEGRATION_TESTED: PASS（单次点击 + 20 轮浏览器）
20_TURN_TESTED: PASS（20/20，消息 1→21）
BROWSER_VERIFIED: PARTIAL（单次/20轮 PASS；重复父点击无独立浏览器证据）
LIVE_API_VERIFIED: PARTIAL（本次未新增 API）
BUSINESS_REGRESSION_VERIFIED: PARTIAL（回归通过；退款/改签追问 Live 未复验）
DATABASE_PROTECTION_VERIFIED: PASS
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
OVERALL: PARTIAL
```
