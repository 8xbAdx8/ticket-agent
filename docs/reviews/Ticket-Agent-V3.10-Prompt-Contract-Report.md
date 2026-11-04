# V3.10 Prompt 契约报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 根因

`target/agent.py` 第 4 条仍写“下单前必须先 lock_seat”；V3.9 只有 `railway_create_order`，没有 `railway_lock_seat`。模型把旧规则和 `railway_` 前缀组合，实际产生：

```
model_tool_proposed railway_lock_seat
config_permission_denied
当前冻结配置禁止工具 railway_lock_seat
```

这不是注册工具被冻结，而是**模型幻觉工具名**。

## 修复

- `web/v39_bridge.prepare` 对 V3.9 effective prompt 替换第 4 条，并明确“无独立锁座、建单确认后自动 hold”。
- `target/execution_config.tool_denial` 对 `railway_lock_seat` 返回可操作说明，而不是“冻结”：
  “当前版本没有独立锁座操作。请先完成报价并创建建单提案，用户确认后系统会自动创建限时座位占用。”
- 没有注册 `railway_lock_seat`，没有扩大白名单，没有删除 Legacy 八工具。

## 契约测试

`tests/v39/test_v310_contract.py`：

- 11 个真实工具、无 `railway_lock_seat`；
- 未知锁座提示不含“冻结”、包含建单/自动；
- V3.10 prompt 包含自动 hold 说明；
- DeepSeek/Qwen 共用同一 Registry 与 effective prompt（代码路径）。

结果：344/0/0 全套通过。
