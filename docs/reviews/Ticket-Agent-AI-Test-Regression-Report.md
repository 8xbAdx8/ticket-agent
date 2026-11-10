# AI Test Regression Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0，35项未提交成果保留；未 reset/clean/checkout/stash/commit/push。所有 V3.10 执行使用独立 SQLite/session/execution_id，未连接正式库或真实铁路/支付服务。

```text
AI 专项: 74 passed / 0 failed / 0 skipped
V3.10: 387 passed / 0 failed / 0 skipped
浏览器: 8/8 current
```

历史基线 1891/11/1。当前旧快照运行 1441/80/1（197 subtests），失败主要是旧快照环境/Streamlit/Provider 状态与静态库补齐问题；不是有效的 1891 对照。历史 11 失败和 1 Skip 未被修改、删除或跳过；本轮不能声称历史回归 PASS。

保护：关键资产 SHA 未变；5587 全量清单未重算，NOT_RUN。
