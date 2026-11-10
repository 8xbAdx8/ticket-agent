# V3.11-R1 实施结果（第二轮：pilot、扩展链、Qwen 取消）

日期：2026-11-10（Asia/Shanghai）。`HEAD 2bba4caa...`，未 commit/push。整体 **PARTIAL**。

## 结果

```text
PILOT DeepSeek/Qwen: PASS（查询→报价→建单→确认）
DeepSeek:             PARTIAL
Qwen:                 PARTIAL（已包含取消 PASS）
R1 Oracle:            PASS（10 个隔离 DB invariants）
R1 专项测试:          3/0/0
V3.11 回归测试:       76/0/0
浏览器:               NOT_RUN
历史完整回归:         NOT_RUN
5587 保护:             NOT_RUN
独立审查:             NOT_RUN
```

## 已执行

- 新建 R1 批次 `artifacts/runtime/v310-v311-r1-20261110/`，总 96、每 Provider 48、pilot 24。
- Pilot：DeepSeek/Qwen 均完成查询、库存、2 人报价、建单提案、可信确认；订单 `PENDING_PAYMENT`、`total_fen=6000`、2 passengers。
- DeepSeek 扩展：
  - `QUERY_QUOTE`、`CREATE_ORDER`、`PAY`、`PARTIAL_REFUND` PASS；
  - 最终 `PAID`、`refunded=2850`、`fee=150`、`active=1`；
  - `CHANGE_TRIPS` 未调用要求的 `railway_query_trips`，任务断言 FAIL；
  - CANCEL 未取得提案。
- Qwen 扩展：
  - `QUERY_QUOTE`、`CREATE_ORDER`、`PAY` PASS；
  - 后续支付提案轮的回复被 `reply_claims` **误报**为已支付成功；原始 FAIL 保留；
  - 已修复未来时态误报（“点击确认后才会执行支付”不再算已支付声明）；
  - Qwen 取消链 **PASS**，最终 `CANCELLED`。
- 所有 10 个隔离 DB 的 Oracle invariants PASS，包含资金、库存、退款、P01、hold/订单关系。
- R1 代码新增 `state_preface`：每轮注入当前 SQLite 订单/乘客/pending 状态；改签轮拆成 `CHANGE_TRIPS` + `CHANGE_QUOTE`。
- R1 专项测试 3/0/0；V3.11 测试 76/0/0。

## 预算

```text
R1 HTTP: 86 / 96
DeepSeek: 48 / 48（耗尽）
Qwen:     38 / 48
已知 Token: 636,141
未知预留:   672,900
费用:       UNKNOWN
旧 V311:  39/50，剩余 11 未使用
```

没有提高单轮 Token 保护、没有自动重试、没有重置旧账本。

## 失败与限制

- DeepSeek 改签前模型没有调用 `railway_query_trips`；这是模型工具规划失败，不是 Service 改签失败。
- DeepSeek 取消未取得 CANCEL proposal；Qwen 取消 PASS。
- Qwen 支付提案轮是测试 Oracle 未来时态误报，修复后原始 FAIL 不删除、不重写；未重新执行该轮。
- DeepSeek 已耗尽 48 次批准额度，不能继续补跑；R1 只剩 Qwen 10 次。
- 完整 A–F 双模型、拒绝/幂等/故障矩阵、浏览器、历史回归、5587 全量保护、独立审查均未完成。

## 结论

```text
PILOT: PASS（两者建单）
DEEPSEEK FULL LIFECYCLE: PARTIAL（create/pay/partial refund；change/cancel missing）
QWEN FULL LIFECYCLE: PARTIAL（create/pay/cancel；后续退款/改签未完成）
ORACLE: PASS（10 DB invariants）
V311_R1_OVERALL: PARTIAL
```

未满足任务书完整 A–K，不能标记 COMPLETE。
