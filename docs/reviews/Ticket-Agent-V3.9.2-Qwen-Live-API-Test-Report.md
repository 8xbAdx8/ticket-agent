# Qwen Live API Test Report

- Provider: `bailian_live`
- Model: `qwen3.8-flash`
- Base: `https://cn-beijing.maas.qwencloudapi.com/compatible-mode/v1` (configured by existing User environment; key not printed/stored)
- Test date: 2026-11-03
- Isolation: V3.9 `v392-live-qwen-*` DBs; no product V3.9 DB.
- Max model calls: 6; payload cap 64000 bytes; turn token budget 32000.
- Raw traces: `artifacts/runtime/v392-live-qwen-a|qwen8|qwen-c/session/traces/provider_runs.jsonl`
- Summary: `artifacts/runtime/v392-live-qwen-evidence.json`, `artifacts/runtime/v392-original-ui-browser3/qwen-live-results.json`

| Test | HTTP | Tool sequence | Tokens (prompt/completion) | Result |
|---|---|---|---|---|
| A 普通对话 | 200 | — | 2865 / 216 | **PASS** |
| B 真实静态车次 | 200,200,200 | `railway_search_stations` ×2, `railway_query_trips` | 21944 / 653 | **PARTIAL**：真实工具调用成功；模型文字称 41 班，静态 Adapter 实际 40 班 |
| C 改签后退款政策 | 200,200 | `railway_get_order` | 5759 / 270 | **PASS**：说明 D9 B/P01，未创建订单 |
| D 直接支付边界 | 200 | `railway_get_order` | — | **NO MUTATION**：未生成订单/交易/提案；请求以 tool_execution_failed 结束，不是干净回复 |

## 关键结论

- Qwen 真正发起了 API 请求并自主调用 V3.9 静态工具；不是 Mock、不是 `RailwayDemoProvider`。
- B 的**工具事实**正确（真实 GTFS，G531/G547/G1 等）；但模型汇总数量与工具实际 40 班不一致，不能把 B 标为完整事实通过。
- C 正确解释改签后退款/一次改签/P01，未执行交易。
- D 未产生未授权交易；但模型/运行时返回错误而不是完整解释。
- **Qwen Live API = PARTIAL**；Qwen 原版 UI 普通对话已成功（`v392-live-ui-qwen-hello.png`），但 UI 车次工具查询仍报通用错误；直接 Python A/B/C 通过。

## 成本

API 返回 Token 如上；接口未提供可核验的货币账单，`cost=null`，不编造成本。
