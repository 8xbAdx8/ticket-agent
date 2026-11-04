# V3.10 上下文管理报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 现状

完整 Trace 保留；模型上下文由 `target/v39/model_result` 投影。大页/历史数据不应无限进入每轮。现有测试包含 50/50/9 分页、跨轮选择、Token 预算与截断恢复。

## 本轮

- 保持 Trace 完整；
- 不提高预算上限（`DEEPSEEK_TURN_TOKEN_BUDGET=48000` 仅用于本轮验收，有界且低于 V2 400k 总预算）；
- 付款/交易上下文继续使用业务快照，不依赖旧模型回复；
- 没有为二维码或 Prompt 添加原始大表。

## 验证

V3.10 全套 344/0/0，包含分页和上下文测试；未新增 109 班 Live 查询（本轮 Live 查询返回当前页 20/50，未自动翻完）。

限制：本轮没有重复跑 50/50/9 的完整模型上下文；既有离线分页测试保持通过。
