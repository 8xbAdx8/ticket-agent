# V3.11-R1 Regression Report

HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，未 commit/push。本轮只做离线整改，没有调用真实模型；原 R1 86 条请求、原始 FAIL、Trace、checkpoint、10 个 SQLite 和旧证据全部保留。

## 本轮

```text
R1 tests: 6 passed / 0 failed / 0 skipped
V3.11 tests: 76 passed / 0 failed / 0 skipped
Combined V3.11+R1: 82 passed / 0 failed / 0 skipped
Current authoritative full regression: 2176 passed / 11 failed / 1 skipped
Offline lifecycle targeted: 9 passed
```

原始日志：

- `artifacts/runtime/v310-v311-r1-20261110/r1-tests.log` + `r1-tests.xml`
- `artifacts/runtime/v310-v311-r1-20261110/v311-tests.log` + `v311-tests.xml`
- `artifacts/runtime/v310-v311-r1-20261110/combined-tests.log` + `combined-tests.xml`
- `artifacts/runtime/v310-v311-r1-20261110/offline-lifecycle.log` + `offline-lifecycle.xml`

## 历史

V3.11 完整回归历史为 `1971/11/1`，旧 11 个失败和 1 个 Skip 逐 ID 保留；本轮未重跑完整历史回归，不改写旧结果。

## 未完成

- 浏览器完整审核→批准→执行→Trace E2E（当前仅布局/入口）；
- 独立只读审查；
- 完整双模型 Live A–F。

因此 V3.11-R1 仍为 **PARTIAL**。
