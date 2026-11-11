# V3.11-R1 Final Acceptance：最终验收报告

日期：2026-11-11（Asia/Shanghai）。`HEAD 2bba4caa379b111aadcefd0369e79cf6259e33e7`，未 commit/push。

## 1. 最终状态表

| 验收项目 | 最终结果 |
|---|---|
| DeepSeek 主生命周期 | **PASS** |
| DeepSeek 独立取消 | **PASS** |
| Qwen 主生命周期 | **PASS** |
| Qwen 独立取消 | **PASS**（旧 R1 剩余额度 8 次，新会话/新 SQLite；补充批次本身的取消链失败，见下） |
| Browser E2E | **PASS（确定性 UI 执行）**；Live-model 浏览器执行 **NOT_RUN**（consent/agent-session） |
| Oracle | **PASS**：补充 6/6 + 旧 R1 11/11；存在取消订单 ACTIVE item 语义缺口 |
| 完整回归 | **2176 passed / 11 failed / 1 skipped**（含 199 subtests） |
| 5587 保护核验 | **5587 检查；2 差异**：1 个已批准预算测试例外 + 1 个 API 账本追加 |
| 独立审查 | **CONDITIONAL_PASS**（独立只读子 Agent；非外部人工验收） |
| 预算 | 补充 60/60；旧 R1 94/96（DeepSeek 48/48，Qwen 46/48） |
| Git | 未 commit/push/merge/tag |
| **Overall** | **PARTIAL** |

## 2. 双模型真实 Live

### DeepSeek

主链订单 `V39-993caf1eddf74daebe251243c4326f39`：

```text
QUERY_QUOTE
CREATE_PROPOSAL → CREATE_ORDER
PAY_PROPOSAL → PAY
PARTIAL_REFUND_PROPOSAL → PARTIAL_REFUND
CHANGE_TRIPS → CHANGE_QUOTE → CHANGE_PROPOSAL → CHANGE
FULL_REFUND_PROPOSAL → FINAL_REFUND
final CANCELLED
paid=6000, refunded=5800, fee=200, net=200, active=0
```

独立取消订单 `V39-2bcec6d95ae84dccb2218762acdd573f`：

```text
PASS, CANCELLED, hold RELEASED, paid=0
```

### Qwen

主链订单 `V39-cfe7f4e75dd94442806dee7db2202e1f`：

```text
QUERY_QUOTE
CREATE_PROPOSAL → CREATE_ORDER
PAY_PROPOSAL → PAY
PARTIAL_REFUND_PROPOSAL → PARTIAL_REFUND
CHANGE_TRIPS → CHANGE_QUOTE → CHANGE_PROPOSAL → CHANGE
FULL_REFUND_PROPOSAL → FINAL_REFUND
final CANCELLED
paid=6000, refunded=5800, fee=200, net=200, active=0
```

独立取消订单 `V39-3ac403d716fb4e81bae4b85c9da03356`：

```text
PASS, CANCELLED, hold RELEASED, paid=0
```

**重要限定：** 该 Qwen 独立取消使用了旧 R1 剩余额度 8 次，不是 60/30 补充批次。补充批次中的 Qwen 取消 `1abcb00c...` 在 60/60 处被 `acceptance_http_budget_exhausted` 截断，未建单、未取消，原始 FAIL 保留。不能把两者混为同一批次成绩。

## 3. 预算

```text
补充批次:      60/60
  DeepSeek:    30/30
  Qwen:        30/30
旧 R1:         94/96
  DeepSeek:    48/48
  Qwen:        46/48
费用:          UNKNOWN
```

旧 R1 的 94 条请求记录和补充批次 60 条记录分别核对，没有 orphan/duplicate；未知请求未自动重试。

历史 `batch.policy.max_http_requests=50` 是旧基础字段，R1 有效限制由 `R1Batch.max_http` 与 `r1_limits`（96 或 60）共同执行。

## 4. Oracle

- 补充 6 个 SQLite：**6/6 invariants PASS**。
- 旧 R1 11 个 SQLite：**11/11 invariants PASS**。
- 独立审查复核：每套完整链 49/49、每个取消 27/27、空失败库 11/11，零失败。

已知语义缺口：

- 取消订单 `CANCELLED` 仍保留 `active_item_count=1` 和 `item_status='ACTIVE'`；
- Oracle 没有“终态订单不得有 ACTIVE item”规则，`passenger_counts` 只检查自洽；
- 这不影响 hold 释放/资金，但属于业务语义待裁定项，不能隐藏。

## 5. 回归与保护

```text
R1 专项:              6/0/0
V3.11 专项:           76/0/0
V3.11 + R1:           82/0/0
当前完整回归:         2176 / 11 / 1
```

JUnit 共 2188 tests：1977 passed + 199 subtests = 2176 passed，11 failed，1 skipped。

11 个失败/1 Skip 与历史基线逐 ID 相同，无新增、无删除、无跳过。

保护重算：**5587 检查，0 missing，2 diffs**：

1. `tests/v39/test_acceptance_budget_v2.py`：已批准的预算测试例外（5586→新哈希）；
2. `artifacts/runtime/api-usage/bailian/.../requests.jsonl`：Qwen 取消新增真实请求导致的账本追加，不是覆盖历史。

因此不能写成“5587/5587 零差异”；正确表述是 **5586 unchanged + 1 approved exception + 1 API ledger append**。

## 6. 浏览器

已完成：

- 当前代码布局/入口：8/8（4 尺寸 × 浅/深），PageError/Console/Network 0；
- 隔离候选库：候选生成、审核人、批量选择、批准通过。

完整 E2E 未完成：

- V3.10 确定性执行按钮、执行结果、执行记录与 Trace 已通过真实浏览器操作（`browser-deterministic`）；
- Live-model V3.11 执行区在浏览器中没有完成 agent session、执行与 Trace；
- 最近一次 `browser-e2e-final` 通过人工审批后，在 consent/agent-session 步骤 `TimeoutError`；
- 另一个尝试因 `TICKET_V311_BATCH_ROOT` 未配置，显示“尚未配置已授权的 V3.11 批次”；
- 因此 Browser 状态为 **确定性 E2E PASS / Live-model 浏览器执行 NOT_RUN**；不能用布局截图冒充 Live。

## 7. 独立审查

独立只读子 Agent 结论：**CONDITIONAL_PASS**。

确认：

- 60 条 supplement 与 94 条 old R1 请求 ID 逐一对齐，无 orphan/duplicate；
- DeepSeek/Qwen 主链、DeepSeek 取消、Qwen 旧批次取消真实；
- Oracle 独立于 Service，按只读 SQL/自身 P01 复核；
- 预算、finalize、checkpoint 核心路径通过；
- 当前 2176/11/1 回归可追溯。

发现并已在本报告修正/披露：

- 旧 R1 实际 94/96，Qwen 46/48；
- Qwen 取消属于旧批次，补充批次取消 FAIL；
- 最终包曾与工作树不一致，已重建；
- 保护不是 5587/0；
- 浏览器停在 consent/agent-session；
- 取消终态 ACTIVE item Oracle 缺口。

## 8. 剩余风险 / 未完成

- 浏览器完整候选审核→批准→执行→Trace E2E 未完成；
- 用户拒绝、重复支付/退款、超时/数据库失败的全矩阵未跑；
- 取消终态 ACTIVE item 语义未裁定；
- 独立审查是独立子 Agent，不是外部人工签收；
- 费用 UNKNOWN。

## 9. 最终判定

```text
DEEPSEEK_FULL_A-F: PASS
QWEN_FULL_A-F:     PASS（主链 + 旧批次独立取消；补充取消 FAIL 已披露）
BROWSER_E2E:       PASS（确定性 UI）/ Live UI NOT_RUN
INDEPENDENT:       CONDITIONAL_PASS（子 Agent）
V311_R1_OVERALL:   PARTIAL
```

核心 Live 票务生命周期已由两个模型完成并通过 Oracle；但Live-model 浏览器完整执行、取消终态语义和外部人工独立验收仍未完成，不能标记 COMPLETE。
