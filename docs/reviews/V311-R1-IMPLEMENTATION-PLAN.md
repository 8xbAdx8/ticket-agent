# V3.11-R1 实施计划（阶段一产出）

日期：2026-11-10（Asia/Shanghai）。本文件是**只读审计后的实施方案和预算申请**，不是已实施代码、不是 Live 结果、不是用户验收。

现场：`HEAD 2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，`staged=0`，61 项未提交/未跟踪成果保留。本阶段未修改生产代码、未运行真实模型、未消耗 API Token。

## 1. 实施目标

复用现有 V3.11 组件：

- `target/scenario_live_agent.py`：原 `Conversation`/Agent 编排、可信 `test_user` 确认、独立 SQLite。
- `target/scenario_business_oracle.py`：只读 SQL、独立 P01、库存/资金/状态断言。
- `target/scenario_live_budget.py`：现有持久批次和 V311 guard。
- `target/scenario_faults.py`：可信故障注入。
- 原 11 工具 Registry、原 Agent、原 Service、原 proposal/confirm/幂等。
- V3.11 的 Trace、Run Events、数据库快照和测试控制台。

不重写 Agent、不新增确认工具、不让模型持有确认 secret、不复制 Service。

## 2. 多轮生命周期设计

### 2.1 原则

一轮 `Conversation.send` 只完成一个**可验证业务边界**，不得把查询、建单、支付、退款、改签、取消全部塞进一条用户消息。

每个业务轮明确：

```text
turn_intent
  -> 允许工具集合
  -> 最大模型调用数
  -> 最大工具调用数
  -> 明确完成条件
  -> 写操作前后 checkpoint
  -> 独立 Oracle 断言
```

不修改 `langchain_agent.py:89-92` 的单轮 Token 前置保护；不在本阶段提高 `turn_token_budget`、`max_output_tokens`、HTTP 上限或关闭审计。

### 2.2 业务阶段

```text
PREPARE
  -> QUERY / QUOTE
  -> CREATE_PROPOSAL
  -> ORDER_CREATED（可信确认后）
  -> PAY_PROPOSAL
  -> PAYMENT_CONFIRMED
  -> REFUND_PROPOSAL / REFUND_COMPLETED
  -> CHANGE_QUERY / CHANGE_PROPOSAL / CHANGE_COMPLETED
  -> CANCEL_PROPOSAL / CANCELLED
  -> VERIFIED / STOPPED_UNKNOWN
```

每个阶段是一个独立 `turn` 或一个独立可信确认步骤；`CREATE_ORDER`、`PAY`、`REFUND`、`CHANGE`、`CANCEL` 一次只允许一个 pending proposal。

### 2.3 建议的轮次拆分

#### A 购票

```text
A1 查询车站/车次/余票 → 选择真实 trip
A2 报价 + 乘客信息 + 生成 CREATE_ORDER 提案（不确认）
A3 test_user 确认建单 → 独立 Oracle 检查订单/hold
A4 查询订单 → 结束
```

#### B 支付

```text
B1 查询当前订单 → 生成 PAY 提案
B2 test_user 确认支付 → 检查 PAYMENT、PAID、hold CONSUMED
B3 重复支付请求 → 幂等/无第二笔扣款
```

#### C 全额退款

```text
C1 查询订单/ACTIVE 乘客 → 获取 P01 预览 → 生成 FULL REFUND 提案
C2 test_user 确认 → 检查 refund_request/items/REFUND、订单状态
C3 重复退款请求 → 幂等/无第二次成功
```

#### D 部分退款

```text
D1 选择一个 ACTIVE item → 生成 ITEMS REFUND 提案
D2 test_user 确认 → 检查乘客、净额、手续费、累计已退
D3 再请求剩余/超余额退款 → 拒绝或只允许剩余，不允许超退
```

#### E 改签

```text
E1 查询原订单 → 查询目标车次/余票/目标报价
E2 生成 CHANGE 提案（显示原/新、差价、hold 影响）
E3 test_user 确认 → 检查 CHANGE、原 order_id、旧/新 hold、差价
E4 拒绝/失败分支 → 原订单状态和库存不得错误变化
```

改签沿用原 `order_id`，不要求生成第二张订单；这是现有 Service 的真实语义。

#### F 取消

```text
F1 查询订单 → 检查是否待支付/已支付
F2 生成 CANCEL 提案 → 展示库存/退款影响
F3 test_user 确认 → 检查 CANCELLED、hold 释放、必要退款
F4 重复取消 → 幂等且无新增副作用
```

### 2.4 每轮持久字段

新增的 R1 测试编排层（不是生产 Agent）保存 `v311-r1-checkpoint/1`：

```json
{
  "schema": "v311-r1-checkpoint/1",
  "run_id": "...",
  "conversation_id": "web-...",
  "parent_trace_id": "...",
  "trace_id": "...",
  "provider": "deepseek|bailian",
  "model": "...",
  "scenario": "A|B|C|D|E|F",
  "phase": "ORDER_CREATED",
  "order_id": "V39-...",
  "proposal_ids": ["..."],
  "completed_ops": ["QUERY", "CREATE_ORDER"],
  "pending": null,
  "idempotency_keys": ["..."],
  "db_path": "artifacts/runtime/.../simulation.sqlite",
  "db_sha256": "...",
  "before_sha256": "...",
  "after_sha256": "...",
  "http_requests": 0,
  "token_usage": {"prompt": 0, "completion": 0},
  "last_reply_sha256": "...",
  "checkpoint_time": "2026-11-10T..."
}
```

checkpoint 只保存测试编排状态和数据库摘要，不保存 API Key、确认 secret、模型内部 reasoning 或可重放 token。pending proposal 必须通过数据库重新读取和 `decision_preview` 重新绑定，不能恢复旧的确认 secret。

## 3. 安全恢复设计

### 3.1 未知结果

```text
模型/工具超时或异常
 -> 不自动重试写操作
 -> 读取 checkpoint + SQLite
 -> 若已有成功交易/订单：标记 COMMITTED，绝不再次执行
 -> 若确定没有副作用：可生成新提案，使用新 request_id
 -> 若无法判断：STOPPED_UNKNOWN，保留证据，等待人工
```

### 3.2 进程中断

- 同进程：保留 `Conversation`/`AgentRun`，按 checkpoint 继续。
- 新进程：只读恢复 `session-replay.json` + SQLite，不恢复 `InMemorySaver`、旧确认 secret 或旧 pending action。
- 过期 proposal：不能确认；重新查询订单后生成新 proposal。
- 数据库状态与 checkpoint 不一致：停止，不覆盖数据库。

### 3.3 幂等

- `request_id` 每轮唯一；重复提交同一 request_id 只返回已有 receipt。
- 写操作以 Service 的 proposal/idempotency 为准。
- 重复确认、重复支付、重复退款必须验证无新增成功交易/无重复扣款。
- 不自动重放任何 `transactional=1` 请求。

## 4. 独立 Oracle 与断言

使用 `scenario_business_oracle`，不调用 Agent 自己的成功回复作为唯一证据。

每个 checkpoint 后执行：

- 订单：数量/状态/owner/乘客/金额/原新关系。
- 库存：`inventory_segments` 的 held/sold、`inventory_events` 借贷、容量、hold segments 精确区间。
- 支付：成功 `PAYMENT` 数量、金额、方向、order paid_total、debit 守恒。
- 退款：`refund_requests`/`refund_items`/`REFUND`、乘客身份、净额、手续费、累计退款、不可超退。
- 改签：原订单 ID、`change_requests`、旧/新 hold、目标 quote、差价、change_count≤1。
- 取消：CANCELLED、hold 释放、退款路径、重复取消无新增。
- Trace：同一 execution_id/run_id 的事件、proposal、tool、SQLite 状态关联；文件存在不算 Trace 完整。
- 回复：仅对明确正向业务声明做有限检查；不能把无声明当成功。

必测矩阵：

| 能力 | 正常 | 用户拒绝 | 幂等/重复 | 失败/超时 | 越权/隔离 |
|---|---|---|---|---|---|
| 查询 | A | 拒绝继续 | 重放 | 工具失败 | 跨用户 |
| 建单 | A | 拒绝确认 | 重复确认 | DB 失败 | 只读/owner |
| 支付 | B | 拒绝支付 | 重复支付 | 支付失败 | 跨 owner |
| 全额退款 | C | 拒绝退款 | 重复退款 | 退款失败 | 越权 |
| 部分退款 | D | 拒绝部分 | 超余额 | 部分失败 | 错乘客 |
| 改签 | E | 拒绝改签 | 二次改签 | 目标无票/失败 | 非本人 |
| 取消 | F | 拒绝取消 | 重复取消 | 库存释放失败 | 只读 |

## 5. 双模型矩阵

DeepSeek 和 Qwen 分别执行，不合并成功：

| 场景 | DeepSeek | Qwen |
|---|---|---|
| 查询/报价 | 1 run | 1 run |
| 建单 + hold | 1 | 1 |
| 支付 | 1 | 1 |
| 全额退款 | 1 | 1 |
| 部分退款 | 1 | 1 |
| 改签 | 1 | 1 |
| 取消 | 1 | 1 |
| 用户拒绝（5 类） | 5 | 5 |
| 幂等（支付/退款/确认） | 3 | 3 |
| 失败/超时/恢复 | 4 | 4 |
| 跨用户/只读 | 2 | 2 |

先跑 **pilot**：每个 Provider 只跑 A（查询→建单提案→确认→订单/hold）。pilot 通过独立审查后才跑 B-F；不把 pilot 成功当作完整生命周期成功。

## 6. 离线模拟方案（先于 Live）

1. **SDK Stub Agent**：沿用现有 `sdk_stub_agent`，不消耗真实 API；使用原 Agent 图/工具/Service。
2. 每个 checkpoint 做 Oracle 前后断言。
3. 离线跑完整 A-F、拒绝、幂等、故障、恢复。
4. 只有离线/Stub 的流程、数据库、Trace、UI 全部通过，才允许申请真实 API。
5. Stub 结果明确标注 `sdk_stub_agent`，不进入 Live 覆盖。

离线隔离：

- 新 `v310-v311-r1-*` 或现有允许的 `v310-` 路径；
- 独立 SQLite、session、execution_id、clock；
- 不连接 `simulation-v391.sqlite`、正式 DB、GTFS 写接口、真实铁路/支付/RAG 外网；
- 静态 GTFS 只读，SHA 固定；
- 每个场景前后备份数据库，Oracle 只读打开。

## 7. 预算申请

### 7.1 旧批次（只读保留，不挪用）

V3.11 旧批次已经 39/50 HTTP、320985 Token，剩余 11 HTTP；任务书明确未授权，**不作为本轮额度**。不重置、不删除、不改旧账本。

### 7.2 新 V3.11-R1 批次建议

建议新建独立批次：

| 项目 | 建议 |
|---|---:|
| 总 HTTP | **96** |
| 每 Provider HTTP | **48** |
| pilot HTTP | 24（每 Provider 12） |
| pilot 后剩余 | 72 |
| 单次输出上限 | 2048（沿用现有；不为验收提高） |
| 单轮 Token 保护 | 保持现有 `turn_token_budget`，不删除、不提高 |
| 最大业务轮次/场景 | 8 |
| 最大模型调用/轮 | 3 |
| 最大工具调用/轮 | 3 |
| 生命周期累计 Token | 只记录、告警，不设项目内部硬上限 |
| 费用 | UNKNOWN，不能用未知单价伪造金额 |

预计规模：

- 6 场景 × 2 Provider × 约 3-4 轮 = 约 36-48 个业务轮；
- 每轮可能 1-2 个模型请求 = 约 60-96 HTTP；
- 另加拒绝/幂等/故障/恢复，建议 96 上限，实际按 checkpoint 停止，不自动补跑。

**Token 估算**：平均输入约 6k-9k、输出约 0.3k-1k，96 请求约 60万-96万 Token 量级，仅容量规划，不是硬限制或费用承诺；实际以账本为准。

### 7.3 请求用户授权

本阶段不调用 API。请用户明确批准：

1. 新建 V3.11-R1 批次；
2. 总 HTTP 96、每 Provider 48；
3. 先 pilot 24，pilot 审查后再释放 72；
4. 允许在**合成用户/合成乘客/独立 SQLite/模拟支付退款**范围内写入；
5. 确认费用 UNKNOWN，不要求本轮把单价假定为真实账单。

如果没有批准，Live 全部 NOT_RUN，只执行离线/Stub 和审计。

## 8. 实施顺序与门禁

```text
P1 冻结当前现场/保护清单
P2 新建 R1 隔离批次和 checkpoint 模型（只测试侧）
P3 重构 AgentRun 为“每轮一业务边界”的 LifecycleRunner
P4 建立独立 Oracle checkpoint 断言
P5 SDK Stub 跑 A-F、拒绝、幂等、失败/恢复
P6 浏览器审核→执行→详情→Trace 交互
P7 用户批准 pilot；只跑 A 两 Provider
P8 pilot 独立审查；不合格停止
P9 释放剩余预算，跑 B-F 与异常矩阵
P10 完整回归、保护 SHA、Trace/DB/ZIP、独立审查
```

每个阶段停止条件：

- Token 保护再次触发：停止该轮，保存 checkpoint，不自动重试；不得提高上限或删保护。
- 业务状态与 checkpoint 不一致：STOPPED_UNKNOWN。
- Oracle 失败：保留失败，不修改断言。
- 预算不足：停止，报告剩余额度，不新建/重置账本。
- 任何真实费用不可核实：UNKNOWN。

## 9. 验收标准

只有以下全部满足才能 COMPLETE：

- DeepSeek 和 Qwen 各自完成 A-F（不是合并计数）；
- 每轮上下文/业务状态恢复；
- 确认/拒绝无副作用；
- 写操作幂等；
- 订单/库存/资金独立 Oracle 全通过；
- 失败/超时/中断安全恢复；
- Trace 与 execution/DB 一致；
- 数据库隔离证明；
- 历史回归逐 ID 无新增失败；
- 浏览器实际审核/执行/详情链路；
- 5587 保护逐项结果；
- 独立只读审查通过。

任何一项缺失：V3.11-R1 **PARTIAL**；未执行项 **NOT_RUN**，不确定项 **UNKNOWN**。

## 10. 当前状态

```text
ARCHITECTURE_AUDIT: PASS（本文件）
IMPLEMENTATION_PLAN: PASS（本文件）
IMPLEMENTED: NOT_RUN
OFFLINE_TESTED: NOT_RUN
LIVE_AGENT_VERIFIED: NOT_RUN
ORACLE_VERIFIED: NOT_RUN
BROWSER_VERIFIED: NOT_RUN
REGRESSION: NOT_RUN
PROTECTION_RECHECK: NOT_RUN
INDEPENDENTLY_REVIEWED: NOT_RUN
USER_ACCEPTED: PENDING
V311_R1_OVERALL: PARTIAL（等待预算/范围批准）
```

本阶段停止。未调用任何真实 API、未启动测试、未修改生产代码；等待用户审批第 7.3 节的 R1 预算和隔离写范围。
