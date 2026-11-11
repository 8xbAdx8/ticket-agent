# V3.11-R1 Budget Reconciliation

HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，未 commit/push。本轮只做离线整改，没有调用真实模型；原 R1 86 条请求、原始 FAIL、Trace、checkpoint、10 个 SQLite 和旧证据全部保留。

## 双层限制

```text
batch.policy.max_http_requests = 50   # 旧 /3 基础策略，历史字段
R1Batch.max_http = 96                 # 本批次有效准入
r1_limits.http_limit = 96             # 独立 R1 guard
r1_limits.provider_limit = 48
r1_limits.phase = pilot -> released
```

`R1Batch` 通过 `Batch(..., max_http=96)` 覆盖基础准入；`v311_r1_admission` trigger 再次检查 96/48/pilot。两个层不允许超过 96；`batch.policy` 的 50 是历史显示值，不是本批次有效上限，导出时必须同时看 `r1_limits`。

## 实际

```text
R1 HTTP 86/96
DeepSeek 48/48
Qwen 38/48
剩余 10（仅 Qwen）
旧 V311 39/50，剩余 11 未使用
```

## 边界测试

`test_r1_effective_limits_are_96_total_and_48_each_after_release`：

- 释放 pilot 后写入 96 条请求成功；
- 第 97 条被 `acceptance_http_budget_exhausted` / `R1_HTTP_LIMIT` 拒绝；
- 直接 SQL 第 97 条也被 R1 trigger 拒绝；
- pilot 初始 24/12 限制由 `test_r1_batch_pilot_then_release_is_persistent` 覆盖。

## 未知/导出

- 未知请求保留 `UNKNOWN` 预留，不自动重试；
- 预算 SQLite 与业务 SQLite 分离；finalize/导出失败不回滚预算行；
- 旧 V3.11 账本只读保留，不重置。
