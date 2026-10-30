# 连续智能追问 + Trace 事件链修复报告（2026-10-30）

## 1. 两轮后追问消失的真正根因

不是候选用完，也不是模型不稳定，而是**候选生成把“本轮是否真查过票”判错了**。

`target/followups.py::candidates` 原来的判断是：

```python
if not any(e.get('tool') == 'query_tickets' for e in events):
    ... 回退到上一轮查票证据
```

但从第二轮起，只要模型请求里回放了上一轮的查票结果，事件链就会写入
`tool_result_in_model_request`（`tool=query_tickets`）。这个**回显事件**让
`any(...)` 为真 → 代码认为“本轮已查票” → 不再回退到真实证据 → 本轮候选为 0 →
`selected=[]` → 追问消失。

离线复现（不花钱）：第一轮查票后有 35 条候选；第二轮回答未调用工具时
`options=0 / facts_tickets=0`，第三轮直接 `stopped`。修复后同样场景
`options` 稳定在 30–35，连续 10 轮不断。

**次要缺陷**：`candidates` 把**当前轮**的 `query_result_train_authority` 断言套在
**上一轮**的证据上，当前回答一旦提到车次而没有本轮工具佐证，历史证据会被整批丢弃。
已改为只对当前 run 的事件生效（历史 run 的审计在 `_record_followups` 里已单独过滤）。

**为什么旧十轮测试没发现**：SDK 替身每一轮都对用户消息回一个 `query_tickets`
工具调用，`any(...)` 恒为真且每轮都有真实 `tool_result`，恰好绕开了回显事件这条路。
真实 API 下第二轮之后通常不再调用工具，于是立刻踩中。

## 2. 修改文件

| 文件 | 改动 |
|---|---|
| `target/followups.py` | ① 用 `executed_query()` 只认真正执行过的 `tool_result`（排除回显事件，空结果仍算已执行）；② 断言作用域收敛到当前 run；③ 新增按记录生成的问题（每班次 4 条：出发/到达/余票/票价），让候选随数据增长而不是靠堆模板；④ 新增 `read_all()`（已展示问题去重）与 `emit_event()`（UI 侧事件写链）；⑤ 生命周期事件 `followup_generation_started/completed/failed`、`followup_fallback_used`，并保留旧事件名兼容既有测试；⑥ 快照新增 `followup_id` |
| `web/runtime.py` | `shown_followups()`：把已展示过的建议并入 `asked`，保证每轮都是**新**问题；`_record_followups` 传入 |
| `web/conversation.py` | `_followup_lifecycle()` 写 `followup_displayed/selected/submitted`；点击追问时把 `followup_id`、生成方式带到下一轮并写入 `next_run_id`；「运行详情与 Trace」新增**智能追问生命周期（独立事件链）**面板，与业务五阶段并列、不混入工具列表 |

## 3. 真实 DeepSeek API 请求次数

| 项 | 数值 |
|---|---|
| 主 Agent 模型调用 | 11（第 1 轮含 1 次 `query_tickets` 工具往返，其余 9 轮各 1 次） |
| 追问生成调用 | 10（每轮 1 次） |
| **合计** | **21 / 30 预算** |
| 重试 | 0（`max_retries=0`，每轮追问最多 1 次） |

证据目录：`artifacts/runtime/followups-real-20261030-123513/`
（`acceptance.json`、`followups.jsonl`、`followup_events.jsonl`）

## 4. 连续十轮逐轮结果（真实会话，同一 sid `web-988217734b63`）

| 轮 | 工具 | 建议数 | 新建议 | 生成方式 | 耗时 | Token(p/c) | 累计请求 |
|---:|---|---:|---:|---|---:|---|---:|
| 1 | query_tickets | 3 | 3 | model | 1237 ms | 1044/85 | 3 |
| 2 | — | 3 | 3 | model | 1403 ms | 991/96 | 5 |
| 3 | — | 3 | 3 | model | 1467 ms | 1059/98 | 7 |
| 4 | — | 3 | 3 | model | 1427 ms | 1127/118 | 9 |
| 5 | — | 3 | 3 | model | 1446 ms | 1213/114 | 11 |
| 6 | — | 3 | 3 | model | 1259 ms | 1342/128 | 13 |
| 7 | — | 3 | 3 | model | 1346 ms | 1526/143 | 15 |
| 8 | — | 3 | 3 | model | 1226 ms | 1598/145 | 17 |
| 9 | — | 3 | 3 | model | 1359 ms | 1690/141 | 19 |
| 10 | — | 3 | 3 | model | 1596 ms | 1801/143 | 21 |

- 10 行快照、10 个不同 `run_id`、同一 `session_id`；每行 `model_invocations=1`、`http_requests=1`。
- 第 2–10 轮**没有调用任何工具**，追问仍连续生成——这正是原缺陷的触发路径，现已修复。
- 合计 Token：prompt 13,391 / completion 1,211；平均追问耗时 1,377 ms。
- 每轮 3 条建议与之前展示过的建议零重复（`new=3`）。

## 5. 事件链关联

真实批次 `followup_events.jsonl` 共 80 条追问事件：

```
started ×10 · model_request ×10 · http ×20 · success ×10 · completed ×10 · saved ×10 · （旧名 start ×10）
```

字段抽样（第 10 轮）：

```json
{"event_type":"followup_generation_completed","run_id":"25eb8e8d...","followup_id":"c1677d55aaa8",
 "previous_event_id":"ea3404a3...","generation_method":"model","provider":"deepseek_live",
 "model":"deepseek-flash","model_called":true,"latency_ms":1595,
 "token_usage":{"prompt":1801,"completion":143},"fallback_reason":null,
 "selected":["已查询的模拟班次 G7303 二等座 ..."],"next_run_id":null}
```

- 每条事件都有 `session_id`、`run_id`、`followup_id`、`event_id`、`previous_event_id`、`generation_method`、`provider`、`model`、`latency_ms`、`token_usage`、`fallback_reason`、`selected`、`next_run_id`。
- `chain linked: True`：所有事件都能顺着 `previous_event_id` 连成一条链。
- 未调用模型的回退事件会写 `provider=null, model=null, model_called=false, token_usage=null`，不伪造模型名与 Token。
- `followup_displayed / selected / submitted` 由 UI 层写入：离线 UI 检查结果
  `has_displayed=true, has_selected=true, has_submitted=true, submitted_next_run_id=ff368647...`，
  且 `previous_event_id` 均非空。真实批次是运行时直驱，没有经过页面渲染，所以这三类不在该批次里。

## 6. 回退次数与原因

| 环境 | 轮次 | 回退 |
|---|---:|---:|
| 真实 DeepSeek | 10 | **0** |
| 离线专项（含故意注入超时） | 10 × 2 provider | 1（bailian 第 5 轮注入 `ReadTimeout`，`fallback_reason=timeout`） |

回退路径仍为规则表 + 字面锚点，`generation_source=rule_fallback`，UI 文案显示「规则推荐」。

## 7. 专项测试

| 命令 | 结果 |
|---|---|
| `pytest tests/test_followups_mvp.py tests/test_followups_continuous.py` | **26 passed / 23 subtests passed**（含两家 SDK 替身、十轮连续、超时回退、保存回放、跨会话隔离、空结果不复用旧库存） |

未跑全仓 pytest（按要求）。

## 8. 未解决问题与边界

1. **8 秒独立超时未做成按次硬计时**。实现方式是同步调用 + provider 客户端超时
   （验收时 `DEEPSEEK_TIMEOUT=8`）。曾尝试线程计时器，但会破坏 SDK 替身的事件/计费上下文
   （专项测试一度 28 failed），已回退。当前语义：客户端 8s 超时 → 异常 → 规则回退，
   行为满足“快速失败”，但代码里没有硬编码 8s 常量。
2. **追问仍同步阻塞回答**：`_record_followups` 在 `send()` 内、`agent_returned` 之前执行，
   每轮多等约 1.2–1.6s。要彻底解决需改为渲染后惰性生成。
3. **UI 三个事件只在离线 UI 检查里验证**，真实批次未经过页面点击。
4. **候选仍有上限**：3 班次时约 35 条，10 轮 × 3 = 30 已接近上限；若每轮都点第 1 条且
   班次更少（2 班次约 20 条），第 7–8 轮会开始不足 2 条并显式 `insufficient_evidence`。
   彻底解决需要让模型在实体白名单内**自己组题**，本轮未做。
5. 未提交、未推送；`target/followups.py` 仍是未跟踪文件。

## 9. 证据分层（重要）

| 类别 | 内容 |
|---|---|
| **真实 API 验证** | 十轮连续会话、21 次真实请求、每轮 3 条且全为 `model`、真实 Token 与耗时、每轮 1 次调用 |
| **Mock / SDK 替身** | 26 项专项测试（含十轮 UI 点击、超时回退、跨会话隔离、回放） |
| **离线回放** | 修复前后的候选数对比（`diag-real-path.json`、`diag-cur.json`）、UI 生命周期事件检查 |
| **尚未验证** | 真实 API 下的超时/限流回退、真实页面刷新后的追问恢复（对话本身仍不持久）、模型自组题方案 |
