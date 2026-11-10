# V3.11-R1 架构审计

日期：2026-11-10（Asia/Shanghai）。阶段：**只读架构审计**；本阶段未修改生产代码、未运行测试、未调用 DeepSeek/Qwen API、未消耗 Token、未提交/推送。整体仍 **PARTIAL**。

## 1. 现场与保护

```text
仓库: D:\codexproject\ticket-agent
分支: feat/ticket-agent-v36-stabilization
HEAD: 2bba4caa379b111aadcefd0369e79cf6259e33e7
staged: 0
工作区: 61 项未提交/未跟踪成果，保留不覆盖
```

- V3.11 封存证据：`artifacts/runtime/v310-v311-20261110-implementation/`。
- V3.11 当前报告：`docs/reviews/V311-IMPLEMENTATION-REPORT.md`、`V311-LIVE-AGENT-REPORT.md`、`V311-COVERAGE-REPORT.md`、`V311-FAULT-INJECTION-REPORT.md`、`V311-REGRESSION-REPORT.md`、`V311-INDEPENDENT-REVIEW.md`。
- 本阶段只读；未 reset/clean/checkout/stash，未覆盖历史报告、数据库、Trace、账本或 Manifest。
- 正式 103 仍 BLOCKED；不得将本审计中的任何静态结论写成 Live PASS。

## 2. 实际调用链

```text
scripts/run_v311_remaining.py::execute
  -> target.scenario_live_agent.AgentRun
  -> web.runtime.Conversation.send
  -> target.agent.Agent.chat
  -> target.langchain_agent.LangChainAgent.chat
  -> create_agent / LangGraph graph.invoke
  -> target.langchain_agent.ContractMiddleware.wrap_model_call
  -> DeepSeek/Qwen HTTP + Token/HTTP 账本
  -> 原 11 个 railway tools / target.v39.registry.dispatch
  -> target.v39.service.Service
  -> 隔离 SQLite + proposal/idempotency/audit
  -> AgentRun.turn -> target.scenario_business_oracle.snapshot/invariants
  -> run-*.json / audit JSONL / LiveBatch 账本
```

关键源码位置：

- `target/scenario_live_agent.py:41` `AgentRun.__init__`：创建原 `Conversation`，`mode='live_agent'`（transport 为 None）或 `sdk_stub_agent`。
- `target/scenario_live_agent.py:72` `environment`：固定 `RAILWAY_SIM_DB_PATH`、`TICKET_TEST_MODE=1`、`TICKET_DATA_MODE=fixture`，阻断工具外网；模型端点单独由 guarded `httpx.Client.send` 限制。输出上限 `DEEPSEEK_MAX_OUTPUT_TOKENS=2048`、`DASHSCOPE_MAX_OUTPUT_TOKENS=2048`。
- `target/scenario_live_agent.py:108` `turn`：每次调用 `self.session.send(message, request_id, ...)`；捕获当轮 audit、events、tool_end、request 用量。
- `target/scenario_live_agent.py:142` `_record`：保存 before/after、`invariants`、调用方冻结的 `task_checks` 和 `reply_claims`。
- `target/scenario_live_agent.py:174` `confirm`：只接受 `actor='test_user'` 和预览中精确的 proposal/payload；通过 `Conversation.confirm_railway_proposal`。
- `target/langchain_agent.py:62` `ContractMiddleware.wrap_model_call`：在模型调用前检查 Token；`91` 行为根因所在。
- `target/langchain_agent.py:151-152`：每次模型响应后把 `usage` 累加进 `ctx.trace.tokens`。
- `target/scenario_live_budget.py`：`LiveBatch` 继承 `/3` Batch，额外 `v311_admission` guard、24/50 HTTP、每 Provider 12/25；不是 Token 硬限。
- `target/scenario_business_oracle.py`：只读 SQL、独立 P01/资金/库存检查；不导入业务 Service。

## 3. 为什么完整改签/取消/连续退款被截断

### 3.1 直接触发点

`target/langchain_agent.py:89-92`：

```python
if ctx.deepseek_settings:
    if (sum(ctx.trace.tokens.values())
        + ctx.deepseek_settings.max_output_tokens
        > ctx.deepseek_settings.turn_token_budget):
        raise DeepSeekError("observed_token_budget_exhausted")
```

这是 **原单轮模型调用的前置检查**，不是 HTTP 50 次限制，也不是 `/3` 累计 Token 上限。

`ctx.trace.tokens` 在同一 `chat()` 内随每个模型响应累加：

```python
ctx.trace.tokens["prompt"] += usage.get("input_tokens", 0)
ctx.trace.tokens["completion"] += usage.get("output_tokens", 0)
```

因此同一轮 Agent 的“模型调用 → 工具 → 模型调用 → 工具 → 模型调用”越多，越接近 `turn_token_budget`；在下一次模型请求**发出前**直接返回 `observed_token_budget_exhausted`，导致本轮最终回答没有完成。工具可能已经执行、proposal 可能已经产生，但该轮 `passed=False`。

### 3.2 为什么改签路线先失败

`scripts/run_v311_remaining.py::execute` 虽然拆成多个 `turn`，但每个 `turn` 的用户消息仍要求多个操作：

- 首次 `turn` 同时：`railway_query_trips`、`railway_check_inventory`、`railway_quote_fare`、`railway_create_order`；
- 后续 `turn` 同时：`railway_quote_fare` + `railway_change_order`；
- 最终退款 `turn` 还要再次调用 `railway_refund_order`。

每个 `turn` 内的多个工具结果都会回送给模型，产生多次模型调用；复杂改签轮和后续退款轮更容易超过单轮预算。改签没有完成不是 `railway_change_order` 业务规则失败，而是**模型调用前置 Token 保护在确认前/确认后截断**。

### 3.3 为什么取消没有完整完成

V3.11 Live 证据没有完成 `railway_cancel_order` 的真实 Agent 轮次：

- `coverage-final.json` 的 live `tools` 缺少 `railway_cancel_order` 和 `railway_change_order`；
- 现有 `run_v311_remaining` 的脚本只覆盖 query/create/pay/partial refund/change/final refund，没有取消分支；
- 没有完成的取消业务，因此不能从“工具已注册”推断取消 Live PASS。

### 3.4 为什么连续退款会截断

全额/部分退款会在同一会话中增加订单快照、退款预览、确认回执和更多工具消息；后续退款轮次携带的上下文变大。Token 检查是在**每次模型调用前**执行，下一轮尚未发出就被拒绝，因此出现“前一笔已成功、后一笔未执行”的截断形态。V3.11 的 DeepSeek 场景已有 `PAID / paid_total 9000 / refunded 2850 / fee 150 / active 2`，但没有完成后续改签与最终退款；这是最明确的“业务已部分提交、生命周期未完成”证据。

## 4. 跨轮恢复与确认能力现状

### 4.1 `Conversation` / LangGraph

- `Conversation` 持有 `history`、`receipts`、`operations`、`audits` 和 `agent`；`AgentRun` 在 owner 进程内保留同一个 `session`，因此同一进程的多轮 `turn` 可以继承上下文。
- LangGraph 使用 `InMemorySaver`（`target/langchain_agent.py` 的 `self.checkpointer = InMemorySaver()`）；**不是持久化 checkpointer**。
- `web/session_store.py` 保存 `session-replay.json`，只包含历史索引、操作记录、railway state reference 和 business receipts；恢复时 `Conversation(..., read_only=True)`，明确不加载模型 checkpoint，也不恢复确认 secret。
- `AgentRun.persist()` 只保存 `run-*.json`（execution_id、session_id、rows、halted），没有 `session`、pending proposal、checkpoint 或 secret 的恢复字段；`AgentRun` 没有 `resume` 方法。

结论：**同进程多轮可继续；进程重启后的自动续跑不可用**。重启后必须先只读核对数据库，再在新提案/新会话中继续；不得恢复旧 Secret 或自动确认旧 proposal。

### 4.2 确认与幂等

- proposal 由 Service 持久化到 `v39_proposals`；`confirm` 依赖 proposal_id、session、owner、Scenario 和 payload SHA/order version。
- `AgentRun.confirm` 要求精确 `decision_preview`，`actor='test_user'`，并调用原 `Conversation.confirm_railway_proposal`；不是模型工具。
- `scenario_business_oracle.receipt_proof` 检查 `v39_idempotency` 的 `confirm:` 键、proposal 已确认、订单/交易/hold 与回执一致。
- 重复确认会命中 idempotency；失败请求不能被当成成功；但**没有把 pending proposal/确认 secret 持久化到 AgentRun 的跨进程恢复结构**。

### 4.3 工具结果传递

`ContractMiddleware` 将 ToolMessage 结果加入下一次模型请求，并发出 `tool_result_in_model_request`；`AgentRun.turn` 捕获 `tool_end` 的 `executed=True`、`ok`、`args`。传递链路本身可用；问题是多工具/多轮累积和恢复边界，不是“工具结果没有回传”。

## 5. 独立业务 Oracle

`target/scenario_business_oracle.py` 的独立性：

- `snapshot` 以 `mode=ro` + `PRAGMA query_only=ON` 打开测试 SQLite；路径必须位于 `artifacts/runtime/v310-v311-*` 或 `v310-ai-executions`。
- `invariants` 直接从 `v39_orders/order_items/holds/hold_segments/transactions/transaction_allocations/refund_requests/refund_items/change_requests/inventory_segments/inventory_events/proposals/idempotency/order_snapshots/item_price_snapshots/audit_events/quotes` 读取。
- P01 是独立 Python/Decimal 计算（`p01`），不是调用生产退款计算；退款出发时间从冻结 GTFS 独立读取。
- `receipt_proof`、`decline_proof`、`reply_claims` 独立检查确认回执、拒绝无副作用、有限正向业务声明。
- `AgentRun._record` 每次保存 before/after、invariants、task checks、trace 和业务回执。

Oracle 仍有两个边界：

1. `AgentRun` 的 `before` 来自同一测试 SQLite；它不能证明测试库与正式库完全无连接，只能依赖路径/只读/隔离工厂证据。
2. `invariants` 覆盖核心业务表，但不覆盖所有 UI/CSS/Trace 语义；回复一致性是有限规则，不是通用自然语言 Judge。

## 6. 真实业务状态机（按现有代码）

来源：`target/v39/service.py`、`target/v39/lifecycle.py`、`target/v39/policy.py`。

### 订单状态

`PENDING_PAYMENT`、`PAID`、`PAYMENT_FAILED`、`EXPIRED`、`CHANGED`、`CANCELLED`。

### 已声明合法转换

`NONE→PENDING_PAYMENT`、`PENDING_PAYMENT→PAID/PAYMENT_FAILED/EXPIRED/CANCELLED`、`PAID→PAID/CHANGED/CANCELLED`、`CHANGED→CHANGED/CANCELLED`。

### 关键语义

- `CREATE_ORDER` 确认后才创建订单、乘客明细、ACTIVE hold；`PENDING_PAYMENT`。
- `PAY` 成功写 `PAYMENT` 交易、hold `CONSUMED`；失败保留失败交易并释放占用。
- 退款仅 ACTIVE 乘客；每名乘客最多一次成功退款；退款按冻结价格和 P01；失败不能释放库存或累计成功金额。
- **改签沿用原 `order_id`**：产生 `change_requests`、新 quote/hold、旧 hold 关闭、订单转 `CHANGED`；不能断言“必须生成第二张订单”。
- 取消：待支付订单释放 hold；已支付/已改签取消按现有退款路径；不得把 cancel/refund/change 混成一个操作。
- 订单容量/资金/库存须由 Oracle 对账；不能仅看 Agent 回复。

## 7. 覆盖与当前基线

V3.11 Live（`coverage-final.json`）：

```text
工具 9/11，缺 railway_cancel_order、railway_change_order
流程 4/5，缺 change/cancel
状态 2/6（PAID、PENDING_PAYMENT）
转换 3/10
Trace 11/11 非重放轮次
```

SDK Stub 不能替代 Live：`11/11、5/5、6/6、10/10` 是替身图/确定性执行成绩，不是真实模型成绩。

## 8. 设计缺陷与风险

| 级别 | 证据 | 影响 |
|---|---|---|
| P1 | `langchain_agent.py:91` 单轮 Token 前置检查 | 复合操作轮在模型下一次调用前截断；改签/连续退款未完成 |
| P1 | `run_v311_remaining.py` 每 `turn` 多工具多业务 | 生命周期边界不清晰，无法从失败点安全续跑 |
| P1 | `AgentRun` 无持久 checkpoint/resume | 进程重启不能自动恢复；确认 secret 不可恢复；不能声称可恢复 |
| P1 | Live 9/11、2/6、3/10 | 完整生命周期尚未证明 |
| P1 | 旧回归当前 1441/80/1，历史 1891/11/1 | 不能用无效快照做验收 |
| P2 | `InMemorySaver` | 同进程多轮可用，跨进程不可用 |
| P2 | Oracle 只用测试 SQLite 路径 | 隔离需路径/文件/进程证据补强 |
| P2 | V3.11 浏览器主批 64/64 但详情批超时 | 审核→确认→执行→Trace E2E 仍未全部完成 |
| P2 | 独立审查限定 CONDITIONAL PASS | 不能扩大为完整独立通过 |

未发现 P0；上述均是静态/现有证据结论。当前不改代码、不运行测试、不访问真实 API。

## 9. 对任务书问题的直接回答

1. **真实改签为什么没有完整完成？**  
   `ContractMiddleware.wrap_model_call` 在单轮模型调用前的 `turn_token_budget` 检查触发 `observed_token_budget_exhausted`；改签轮的工具/上下文累积使其在确认/后续模型调用前被截断。不是改签 Service 已证明失败。

2. **取消为什么没有完整完成？**  
   现有 V3.11 Live 脚本/证据没有真实取消轮次，`railway_cancel_order` 不在 Live 9/11；不能把工具注册当成执行覆盖。

3. **连续退款为什么截断？**  
   同一 `chat()` 内 `trace.tokens` 随多个模型响应累加；后续退款轮在模型调用前被单轮预算拒绝，已成功的部分退款保留，但不能继续宣称完整退款生命周期完成。

4. **原单轮 Token 保护在哪一层？**  
   `target/langchain_agent.py:89-92`，`ContractMiddleware.wrap_model_call` 的模型调用前置检查；不是 `LiveBatch` HTTP 50 次，也不是旧 `/3` 累计 Token。

5. **Agent 是否能跨多个模型请求继续同一业务？**  
   同一 `chat()` 内 LangGraph 多模型/工具循环可以；同一进程多 `turn` 可继承 `Conversation`；**跨进程不可自动恢复**。

6. **Conversation State 是否可靠恢复？**  
   同进程可靠；`session_store` 恢复是只读回放，`InMemorySaver` 和 `AgentRun` 没有持久 checkpoint/secret，故跨进程不能声明可靠恢复。

7. **工具结果是否正确传给下一轮？**  
   是，`ToolMessage` + `ContractMiddleware` + `tool_result_in_model_request` 有链路；问题在轮次边界与预算，不在结果丢弃。

8. **用户确认是否持久化？**  
   proposal/回执/审计在 SQLite 持久化；确认 secret 与 pending 状态在进程内，不能跨进程恢复；不得恢复旧 secret。

9. **中断后是否可能重复副作用？**  
   原 Service 有 idempotency 和 proposal/order version；`receipt_proof` 可核对。设计上仍必须“先读库、后决定”，禁止自动重试写操作；当前 AgentRun 没有自动恢复重放。

10. **订单/资金能否独立核验？**  
    可以，通过 `scenario_business_oracle` 的只读 SQL、`invariants`、P01 独立计算、`money_conservation`、库存事件；但测试库隔离身份和 UI/Trace 语义仍需补证。

## 10. 本阶段结论

```text
ROOT_CAUSE_IDENTIFIED: PASS（token 前置检查 + 复合轮次 + 无持久 checkpoint）
IMPLEMENTED: NOT_RUN（阶段一只读）
UNIT_TESTED: NOT_RUN
LIVE_AGENT_VERIFIED: NOT_RUN
ORACLE_VERIFIED: NOT_RUN
BROWSER_VERIFIED: NOT_RUN
INDEPENDENTLY_REVIEWED: NOT_RUN
V311_R1_OVERALL: PARTIAL（审计完成，实施未开始）
```

证据身份：V3.11 原有证据只读引用；本报告不修改其 SHA。
