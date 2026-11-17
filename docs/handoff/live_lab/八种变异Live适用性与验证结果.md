# 八种变异 Live 适用性

本轮两个只读模型各实际执行 `date_offset`、`repeat_call`、`route_error`、`no_citation`、`hallucinated_train`。注入、检出、模型识别、模型恢复、业务正确分别列出；未知不等于成功。故意注入缺陷时 fail 可以是正确拦截。

|模型|变异|Trace|注入|平台检出|模型自主识别|模型恢复|业务正确|
|---|---|---|---|---|---|---|---|
|bailian|mutation-date_offset|399c13607fb84498aff235639da82925|是|是|未知|未知|否|
|bailian|mutation-hallucinated_train|d80c1addbcf14dd0b9d767d3d7f5f745|是|是|未知|未知|否|
|bailian|mutation-no_citation|cb26fb7f997f405fbe149f921ee29f09|是|是|未知|未知|否|
|bailian|mutation-repeat_call|57a26aafb002430bb890b63f5ace2f1d|是|是|未知|未知|未知|
|bailian|mutation-route_error|21dbd79ea2a34b25941761a54e37c6ff|是|是|未知|未知|否|
|deepseek|mutation-date_offset|e95c5ededfec4483b0aae809d9831f1e|是|是|未知|未知|否|
|deepseek|mutation-hallucinated_train|cc6d42f58b414c3ab22988e7f49bc0ac|是|是|未知|未知|否|
|deepseek|mutation-no-citation-after|82aea39f0fec434196ba8580f1788bed|是|是|未知|未知|否|
|deepseek|mutation-no_citation|dab4d8286cba4d8e88aae7e707aaa81b|是|是|未知|未知|否|
|deepseek|mutation-repeat_call|bcb5ba5391dd445a82398b7082e066d8|是|是|未知|未知|是|
|deepseek|mutation-route_error|4f80cbb0636f44ee87ab2c7e84bf1df8|是|是|未知|未知|否|

`skip_lock` 和 `infinite_loop` 依赖写业务/监控工具，在正常 Live 只读工具集不适用；`concurrent_duplicate_order` 只在独立 SQLite 影子库执行，不对正常 Live 暴露写工具。相关隔离离线证据见 `docs/evidence/test_lab_audit/matrix.json`，不能将其冒充本轮 Live。

DeepSeek no_citation 原先因缺 doc_id 抛 client_error；修复后真实复验变为 `unavailable_policy_citation`，仍是预期拦截，不宣称完整业务成功。证据见 `backend` 目录按场景 Trace ID 检索。

本轮源码回归 SHA `e5688aae59ee9a8716527aae5e4591a4da41a6c3`；报告提交 SHA 请用 `git rev-parse HEAD` 查看。主环境 699 项通过、109 个子测试通过；失败 0、错误 0、跳过 0。旧环境跳过情况：deepseek_unit 跳过 24；v3_unit 跳过 139；v2_unit 跳过 277；mock_smoke 跳过 0。本轮原文件快照 20059 项，变更 0 项。
