# V3.11-R1 Evidence Reconciliation

HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，未 commit/push。本轮只做离线整改，没有调用真实模型；原 R1 86 条请求、原始 FAIL、Trace、checkpoint、10 个 SQLite 和旧证据全部保留。

## 原始证据

- `artifacts/runtime/v310-v311-r1-20261110/r1-budget.sqlite`：86 请求；
- `pilot-summary.json`、`lifecycle-summary.json`、`R1-STATUS.json`；
- 原始 FAIL、Trace、checkpoint、10 个 `cases/*/simulation.sqlite`；
- 旧 `V311-R1-partial-review.zip` 和 Manifest 不覆盖。

## 核对

- Oracle 重新只读核对 10 个 DB：**10/10 invariants PASS**；
- 原始失败（DeepSeek `CHANGE_TRIPS`、Qwen 支付提案误报、取消未完成）保留；
- Qwen 取消 PASS；
- R1 测试 6/0/0；
- V3.11 专项 76/0/0；
- 合并 V3.11+R1 82/0/0；
- 当前权威完整回归 2176/11/1，失败/Skip 与基线逐 ID 相同；
- 浏览器布局 8/8（非完整 E2E）；
- 5587 项重算 5587 匹配、0 差异；R1 新文件未纳入旧基线；
- 独立审查仍未执行。

## 结论

证据可以追溯；没有把 partial 结果写成 COMPLETE。
