# V3.10 回归报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 测试

```
V3.10 full: 344 passed / 0 failed / 0 skipped
old full:   1640 passed / 11 failed / 1 skipped
```

旧失败与 skip ID 与 sealed 完全一致，无新增；新增 7 项契约测试（锁座、QR、followup、Prompt）。

## 数据库

Live order `V39-305...` PAID；hold CONSUMED；PAYMENT 3000 SUCCEEDED；外键/状态由既有 V39 测试覆盖。

## 保护

`data/v39/simulation.sqlite`、`simulation-v391.sqlite`、GTFS static、Fixture、tickets.db 未改；产品 v391 仍 BLOCKED；未 commit/push/merge/tag。

## 未完成

退款/改签 Live 未复验；浏览器完整套件未全通过；独立审查未执行。
