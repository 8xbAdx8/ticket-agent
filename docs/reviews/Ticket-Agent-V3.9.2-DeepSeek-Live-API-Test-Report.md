# DeepSeek Live API Test Report

- Provider: `deepseek_live`
- Model: `deepseek-flash`
- Endpoint: existing official `https://api.deepseek.com` configuration; key not printed/stored
- Test date: 2026-11-03
- Isolation: `v392-live-deepseek-*` DBs
- Max model calls: 6; payload cap 64000 bytes; turn token budget 32000.
- Raw traces: `artifacts/runtime/v392-live-deepseek-a|b|c|d/session/traces/provider_runs.jsonl`
- Summary: `artifacts/runtime/v392-live-deepseek-evidence.json`, `artifacts/runtime/v392-original-ui-browser3/deepseek-live-results.json`

| Test | HTTP | Tool sequence | Tokens (prompt/completion) | Result |
|---|---|---|---|---|
| A 普通对话 | 200 | — | 2806 / 421 | **PASS** |
| B 真实静态车次 | 200,200,200 | `railway_search_stations` ×2, `railway_query_trips` | 20239 / 694 | **PARTIAL**：真实工具调用成功；模型文字称 38 班，静态 Adapter 实际 40 班 |
| C 改签后退款政策 | 200,200 | `railway_get_order` | 5651 / 231 | **PASS**：D9 B/P01；未创建订单 |
| D 直接支付边界 | 200,200 | `railway_get_order` | — | **NO MUTATION**：0 orders/transactions/proposals/refunds；运行时 tool_execution_failed，未显示干净拒绝说明 |

## 原版 UI 附加验证

- 在原版 Ticket Agent 页面选择 `DeepSeek Live` 后发送普通对话，真实 API 返回并显示回复。
- 截图：`artifacts/runtime/v392-live-ui-deepseek4.png`
- 这次 UI 请求是 DeepSeek Live；模型/HTTP 证据来自 provider run/trace，非 Mock。

## 结论

- DeepSeek 真正驱动了原 Agent，并能调用 V3.9 静态工具；不是 Mock。
- B 的工具调用正确，但模型汇总数量与工具实际 40 班不一致。
- D 无未授权写入，但请求以错误结束，不能标安全测试完全 PASS。
- **DeepSeek Live API = PARTIAL**。
