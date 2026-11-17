# Live 在线测试实验室 Bug 审计

审计范围：`web/laboratory.py`、`web/runtime.py`、`web/trace_view.py`、`target/request_accounting.py`、`target/reply_consistency.py`、`target/diagnostics.py`、两个 Live transport、RAG 与历史 Trace。分支 `fix/ticket-agent-live-lab-full-audit`。原分支基线 `90affbb7e8f29734efb1990d425e71b23dfc774e`。

|级别|实际触发和根因|修复或状态|提交|
|---|---|---|---|
|P1|实际 HTTP 请求没有保存绑定工具、权限和系统提示哈希|由 transport 在 dispatch 记录名称及 schema/prompt 哈希，非 HTTP 成功证据|`8124d92`|
|P1|工具结果有三车余票但汇总句误判未知；未知业务又被显示为否|逐车核对席别和库存，未知保持未知；负例覆盖缺证据及矛盾|`d965788`|
|P1|澄清句中日期示例被误认查询事实|仅识别明确请求提供日期的示例，同句事实仍核对；Qwen 后续真实澄清可返回|`d965788`|
|P1|多车次斜杠表格被当成一个不存在车次；0（售罄）不能解析|每个车次分别比对，非法车次及余票矛盾仍失败；原样例离线重放仍有其他未知项|`68722ed`|
|P1|缺 doc_id 的检索片段导致 KeyError 被归为 client_error|不把缺失 ID 当合法来源；DeepSeek 真复验变为 unavailable_policy_citation|`24eec0d`|
|P2|无答案时未来查票建议被当成政策事实|有限规则识别建议，未知保持未知；原句离线通过，不同 Live 句式未重现|`768c681`|
|P1|“本次查询结果没有 G9999”被当成正面声称有车次|只对同轮单次成功查询的结果范围判定；真实复验不再出现该误报但仍因其他表述未知而未完成|`328f39f`|
|P1|政策 search_policy 空结果被误作车票空结果|仅关联唯一成功且 hits 为空的政策工具；新真实句式未复现原误判，但其他建议/断言仍可能拦截|`328f39f`|
|P2|有条件的未来查询建议被当票务事实|仅完整匹配且不含具体事实时忽略，其他情况保持未知；真实新输出未重现原句|`e5688aa`|

重要未解决：Qwen 曾在缺路线时自行选择北京到上海；不同自然语言汇总仍可能 `reply_data_indeterminate`；无答案时模型对班次及价格的无证据陈述被保守拦截。当前单次 HTTP 超时、零自动重试和 Agent 步数上限存在，但没有证据证明整个场景有独立硬超时或用户可中途取消；需要后续工程支持。请求完成与业务成功分别判断。

浏览器：实际 DeepSeek 与 Qwen 各一次查票；Qwen 双击只执行一轮、刷新未新增请求、未勾选确认不发请求。未逐项实测全部界面，未测跨标签慢网。没有向 LangSmith 上传。

结论 **CONDITIONAL**：可交 B 做有条件独立测试，不能宣称所有 Live 场景通过。正式验收前需处理剩余未知/模型擅自假设、场景取消与 Live 交互覆盖。

本轮源码回归 SHA `e5688aae59ee9a8716527aae5e4591a4da41a6c3`；报告提交 SHA 请用 `git rev-parse HEAD` 查看。主环境 699 项通过、109 个子测试通过；失败 0、错误 0、跳过 0。旧环境跳过情况：deepseek_unit 跳过 24；v3_unit 跳过 139；v2_unit 跳过 277；mock_smoke 跳过 0。本轮原文件快照 20059 项，变更 0 项。
