# 测试实验室 Bug 审计报告

## 基线和范围

基线 `c484dfe4dacd32e043d62052012ef7684abfa14d`，独立分支 `fix/ticket-agent-test-lab-audit`。检查了 `web/laboratory.py`、`web/runtime.py`、`web/trace_view.py`、`target/diagnostics.py`、`target/concurrency_probe.py`、Provider、Trace、RAG、契约及已有回归。未修改 B 正式测试、原 Trace、历史账本或原始索引。

## 已修复问题

|级别|触发及原因|修复和证据|源码提交|
|---|---|---|---|
|P1|Legacy 的 repeat_call 漏检，route_error 和 no_citation 出现虚假通过：旧质量规则没有独立检查工具事件与事实来源|按实际工具调用和原始回答判定；修复前失败见 `detectors-before.txt`，修复后见矩阵与审计旁证|`bdfae55`|
|P1|Legacy 模型异常仍给出 stop、旁证漏记错误，UI 可能把异常当成功|保持十字段 stop 兼容旧契约，旁证增加 `legacy_provider_error` 和失败原因，UI 检查旁证|`bdfae55`|
|P1|权威数据库不可用时查询结果仍被判 PASS|数据不可得标记 indeterminate 并说明原因；见 `before-fixes.txt`|`4bb5a24`|
|P2|过期锁/线程失败实验强行运行不适用的 M8 注入，导致页面异常|保留正常对照并明确标记不适用；见 `before-fixes.txt`|`4bb5a24`|
|P2|快速双击测试按钮或并发按钮导致重复实验|每次渲染使用新的提交标识，旧动作失效；见 `duplicate-before.txt`、`concurrency-double-before.txt` 和浏览器报告|`b3f7fd5`、`08560ab`|
|P2|刷新后无法通过界面读取先前实验；Mock case ID 丢失|新增受限的会话 ID 本地回放；保存 Mock 测试用例 ID；见 `replay-before.txt`、`case-id-before.txt`|`b3f7fd5`、`bdfae55`|
|P3|离线或缺少 Live 配置时按钮不可用但缺少原因|显示脱敏的中文配置原因，见 `key-prompt-before.txt`|`bdfae55`|

未发现有证据证明本轮存在 P0；以上是本轮复现的缺陷，不能保证项目没有其他缺陷。检测器对政策路由只处理明确表达，对改写或隐含语义仍需人工核验。单会话快速重复点击已验证，跨进程、跨标签的全局恰好一次提交未证明。刷新后的回放只恢复已保存证据，不重建 Agent 多轮上下文。

## 模式与安全

Legacy / LangChain Mock 已实际执行。DeepSeek / Qwen 的模式选择、授权、只读白名单、旧账本不拦截等经离线替身与已有回归检查，**本轮没有 Live 请求**。真实 API 依旧需主动确认，保留只读白名单、超时、步数限制、脱敏和无静默回退；项目本地不限制日常请求次数，不代表服务商免费。

结论：**CONDITIONAL**，可交 B 开展离线独立测试；Live 实际表现、跨用户长时并发及语义检测范围须 B 按授权单独验证。

本轮源码测试提交 `08560abd8d111c70da1dd63e58659c113cd02b15`；交接文档所在提交以 `git rev-parse HEAD` 为准。离线回归：679 项通过，103 个子测试通过；JUnit 失败 0、错误 0、跳过 0。真实模型、Embedding、LangSmith 请求均为 0。原始文件核对 18369 项，变更 0 项。详细结果见 `docs/evidence/test_lab_audit/offline-report.json` 和 `protected-receipt.json`。

兼容环境另外分别运行了旧 DeepSeek、V3、V2 环境，报告的跳过数依次为 24、139、275（由各环境依赖能力决定）；这与当前主环境 0 跳过分开统计。完整详情见 `docs/evidence/test_lab_audit/offline-report.json` 中 compatibility。
