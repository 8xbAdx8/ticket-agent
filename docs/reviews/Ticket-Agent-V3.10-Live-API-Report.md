# V3.10 Live API 报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 本轮真实调用

近期本机会话统计：

```
HTTP        15
prompt      89,864
completion   2,819
total       92,683
DeepSeek     12 HTTP（完整 DeepSeek 购票/支付）
Qwen          3 HTTP（查询对照）
费用         UNKNOWN
```

DeepSeek 会话 `web-c5f67523775c`：7 HTTP，43,804+1,132 Token，完成查询→报价→建单→确认→PENDING→PAY→QR→PAID。

Qwen 会话 `web-10e7eb321874`：3 HTTP，17,730+715 Token，查询 109 班、卡片、追问正常，未做支付。

## 结果

- DeepSeek purchase/QR/PAID：PASS
- Qwen query：PASS（未做 purchase）
- 双 Provider 全场景：PARTIAL
- HTTP 200 未被当作业务成功，均核验 SQLite。
