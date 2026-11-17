# Trace 与质量判定一致性

## 历史“妈妈”事件

原始审计 ID `cbe8c088462046d99e49f322136c47d1`：`artifacts/runtime/v33/user/web-aa088c032007/traces/audit_runs.jsonl` 第 3 行及同目录 provider 旁证第 3 行。模型确有澄清原文、无工具调用；旧回答校验将用户原话误识别为业务事实并抛 `reply_data_indeterminate`，所以 Agent 并未正常返回完整契约结果。界面占位“请求未完成”不是模型回复；历史旁证的 stop 也不是业务成功证明。旧失败原因缺失的问题已有修复，原件不变。本轮以 `tests/test_trace_quality_consistency.py` 的历史回放作离线回归。

## 查票 indeterminate

原始 Trace `6ed4d02f56244449ba992e803c86f200`：`artifacts/runtime/v33/user/web-f9d4cb6b05d6/traces/audit_runs.jsonl` 第 1 行及 provider 旁证。真实执行 query_tickets；三车次和 25 个字段匹配，但回复中“如果您需要改查其他席别或返程车次，可以告诉我”被旧规则误当数据声明。原件未改；已有规则修复后的离线重放不能冒充新的 Live 结果。完整核查见 `docs/handoff/v352/Trace回复与质量一致性修复报告.md`。

## 当前边界

公开 Agent 返回、模型原文、工具结果、网页展示、质量判定是不同层：失败时不能把 UI 占位当作模型回答。明确失败有原因，证据不足标 indeterminate；M8 不适用场景不计入通过。Legacy 为兼容契约，异常仍可能有 `finish_reason=stop`，必须查 sidecar 的 `legacy_provider_error` 和失败原因。缺少数据库证据不再默认 PASS；对政策改写等自然语言结论仍须人工判断。

本轮源码测试提交 `08560abd8d111c70da1dd63e58659c113cd02b15`；交接文档所在提交以 `git rev-parse HEAD` 为准。离线回归：679 项通过，103 个子测试通过；JUnit 失败 0、错误 0、跳过 0。真实模型、Embedding、LangSmith 请求均为 0。原始文件核对 18369 项，变更 0 项。详细结果见 `docs/evidence/test_lab_audit/offline-report.json` 和 `protected-receipt.json`。
