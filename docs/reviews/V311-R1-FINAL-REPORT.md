# V3.11-R1 最终实施与 Live 验收报告

日期：2026-11-11（Asia/Shanghai）。`HEAD 2bba4caa379b111aadcefd0369e79cf6259e33e7`，未 commit/push。

## 1. 最终结论

```text
DeepSeek:
  Pilot PASS
  完整购票/支付/部分退款/改签/最终退款 PASS
  最终订单 CANCELLED
  取消链 PASS
  HTTP 30/30

Qwen:
  Pilot PASS
  完整购票/支付/部分退款/改签/最终退款 PASS
  最终订单 CANCELLED
  取消链 FAIL（30/30 HTTP 用尽，未确认取消）
  HTTP 30/30

补充批次: 60/60
旧 R1 批次: 86/96，保留未动
```

两个模型都通过原 Agent/Registry/Service 完成了真实的多轮主生命周期；Qwen 的独立取消链未完成，因此整体仍为 **PARTIAL**，不能标记 COMPLETE。

## 2. Live 业务结果

### DeepSeek

订单 `V39-993caf1eddf74daebe251243c4326f39`：

```text
QUERY_QUOTE
CREATE_PROPOSAL → CREATE_ORDER
PAY_PROPOSAL → PAY
PARTIAL_REFUND_PROPOSAL → PARTIAL_REFUND
CHANGE_TRIPS → CHANGE_QUOTE → CHANGE_PROPOSAL → CHANGE
FULL_REFUND_PROPOSAL → FINAL_REFUND
final: CANCELLED
paid_total_fen=6000
refunded_total_fen=5800
fee_total_fen=200
net_paid_fen=200
active_item_count=0
```

取消链订单 `V39-2bcec6d95ae84dccb2218762acdd573f`：

```text
PASS
CANCELLED
active_item_count=1
paid_total_fen=0
```

### Qwen

订单 `V39-cfe7f4e75dd94442806dee7db2202e1f`：

```text
QUERY_QUOTE
CREATE_PROPOSAL → CREATE_ORDER
PAY_PROPOSAL → PAY
PARTIAL_REFUND_PROPOSAL → PARTIAL_REFUND
CHANGE_TRIPS → CHANGE_QUOTE → CHANGE_PROPOSAL → CHANGE
FULL_REFUND_PROPOSAL → FINAL_REFUND
final: CANCELLED
paid_total_fen=6000
refunded_total_fen=5800
fee_total_fen=200
net_paid_fen=200
active_item_count=0
```

Qwen 独立取消链（使用旧 R1 剩余额度，新建独立 SQLite）：

```text
PASS
order V39-3ac403d716fb4e81bae4b85c9da03356
CANCELLED, active_item_count=1, paid_total_fen=0
```

旧 R1 的 Qwen 剩余额度由 38/48 变为 46/48；未恢复旧进程 secret，未重放旧 proposal。

## 3. Oracle

补充批次 6 个隔离数据库：

```text
6/6 invariants PASS
```

旧 R1 10 个数据库：

```text
10/10 invariants PASS
```

检查包含订单、支付、退款、手续费、库存、hold、transaction、idempotency、proposal、audit_events、P01、资金守恒。

## 4. 回归与保护

```text
R1 专项:              6/0/0
V3.11 专项:           76/0/0
合并 V3.11+R1:        82/0/0
当前完整回归:         2176/11/1
历史失败/Skip 逐ID:   相同，无新增
浏览器当前布局:       8/8
5587 保护:            5587 匹配，0 差异
```

完整回归仍是 11 个历史失败、1 个 Skip；没有删除/跳过/降低断言。浏览器只是当前布局/入口，不是完整审核→执行→Trace E2E。

## 5. 未完成

- Qwen 独立取消链（本轮已 PASS）；
- 用户拒绝、重复支付/退款、超时/数据库失败的全矩阵；
- 浏览器审核→批准→执行→Trace 完整 E2E；
- 独立只读审查。

因此：

```text
DEEPSEEK_FULL_A-F: PASS（含独立取消）
QWEN_FULL_A-F:     PASS（主链 + 独立取消）
BROWSER_E2E:       NOT_RUN / PARTIAL
INDEPENDENT:       NOT_RUN
V311_R1_OVERALL:   PARTIAL（浏览器完整 E2E/独立审查未完成）
```

## 6. 预算

补充批次：

```text
HTTP: 60/60
DeepSeek: 30/30
Qwen: 30/30
已知 Token: 509759
未知预留: 0
费用: UNKNOWN
```

旧 R1：

```text
86/96，DeepSeek 48/48，Qwen 38/48，保留未动
```

没有新增预算、没有自动重试、没有把离线结果混入 Live。

## 7. 结论

主票务生命周期现在由 DeepSeek 和 Qwen 分别真实完成，并由独立 Oracle 验证；DeepSeek 还完成了独立取消。Qwen 的唯一缺口是补充批次最后一条 CANCEL 在 30/30 处被预算截断。

项目整体仍是 **PARTIAL**，不能因为主链 PASS 就声称完整 A–K 验收通过。继续 Qwen 取消链和浏览器/独立审查需要新的明确授权。
