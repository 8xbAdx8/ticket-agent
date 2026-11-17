# DeepSeek 与 Qwen 真实测试矩阵

下表是本轮实际线上请求，不是离线桩；详见 `docs/evidence/live_lab_20261027/backend/backend-accounting.json`。模型执行期间源码并行修复，除最后独立复验明确使用 e5688aa 外，不能为每次运行补造固定 SHA。质量值为运行当时原始结果，不会因代码修复而重写；`fail` 可能是故障注入被正确检出，不能等同模型 HTTP 失败。

|模型|场景|Trace ID|生成请求|质量|错误类别|
|---|---|---|---|---|---|
|bailian|ambiguous-mama|1ec9b36de2904e4cb8d877c9bcbfbc75|1|indeterminate|—|
|bailian|ambiguous-ticket|0d80a541bb3946c5aa2e986c0481068c|1|indeterminate|reply_data_indeterminate|
|bailian|ambiguous-ticket-after|c6eefec14f624cedb06dbb3d6895a7b4|1|indeterminate|—|
|bailian|ambiguous-tomorrow|b8059bab1a5d4777887e3dfe4e81a8ca|2|fail|reply_tool_mismatch|
|bailian|ambiguous-tomorrow-after|076d99a6328a42b68429d8e9561d873d|1|indeterminate|—|
|bailian|edge-empty|7320ae931aaa4857ad9b870ba345b377|2|fail|reply_data_indeterminate|
|bailian|edge-no-answer|f10641de83ad4bd3bc07498c9c2eac4d|2|fail|rag_answer_inconsistent|
|bailian|edge-no-answer-after|18769a44cc5e4d58b0415bafc0c4f81c|2|indeterminate|reply_data_indeterminate|
|bailian|edge-unavailable-train|60c21251e47747cca7ee20fd04570f3b|2|indeterminate|reply_data_indeterminate|
|bailian|edge-write|60e741e4108c4268a145468122da1cb5|1|indeterminate|—|
|bailian|mutation-date_offset|399c13607fb84498aff235639da82925|2|fail|reply_tool_mismatch|
|bailian|mutation-hallucinated_train|d80c1addbcf14dd0b9d767d3d7f5f745|2|fail|—|
|bailian|mutation-no_citation|cb26fb7f997f405fbe149f921ee29f09|2|fail|unavailable_policy_citation|
|bailian|mutation-repeat_call|57a26aafb002430bb890b63f5ace2f1d|2|fail|reply_data_indeterminate|
|bailian|mutation-route_error|21dbd79ea2a34b25941761a54e37c6ff|2|fail|read_only_capability_violation|
|bailian|query|0c2c027d6de14e2490a5b434f8f68441|2|pass|—|
|deepseek|ambiguous-mama|1ea1c2a9b8ae4d3c9976f50c245859b5|1|indeterminate|—|
|deepseek|ambiguous-ticket|cbea75a0c4814027bd88f990387696d8|1|indeterminate|—|
|deepseek|ambiguous-tomorrow|a6370d43febf4632ad9b86ca5f7f1860|1|indeterminate|—|
|deepseek|edge-empty|c73f01e7cd624e10af525680721d0c92|2|fail|reply_data_indeterminate|
|deepseek|edge-no-answer|99ba91b026b148b39fc354301f70b23d|1|indeterminate|—|
|deepseek|edge-unavailable-train|b071da602f4b4f68ab7ac86df05df6ca|2|fail|reply_tool_mismatch|
|deepseek|edge-write|56c5c76ae45e48348cd8a7db66d71e6c|1|indeterminate|—|
|deepseek|mutation-date_offset|e95c5ededfec4483b0aae809d9831f1e|2|fail|reply_data_indeterminate|
|deepseek|mutation-hallucinated_train|cc6d42f58b414c3ab22988e7f49bc0ac|2|fail|—|
|deepseek|mutation-no-citation-after|82aea39f0fec434196ba8580f1788bed|2|fail|unavailable_policy_citation|
|deepseek|mutation-no_citation|dab4d8286cba4d8e88aae7e707aaa81b|2|fail|client_error|
|deepseek|mutation-repeat_call|bcb5ba5391dd445a82398b7082e066d8|2|fail|—|
|deepseek|mutation-route_error|4f80cbb0636f44ee87ab2c7e84bf1df8|2|fail|read_only_capability_violation|
|deepseek|query|accacab2b9f848a4866ac7244f9b2aae|2|pass|—|
|deepseek|query-after|3d2f8a75f5c7424eb7f93f75a78f3e37|2|indeterminate|reply_data_indeterminate|
|bailian|rag-paired-chroma|4ef97570b5394c66b768f5452cde22e3|2|indeterminate|—|
|deepseek|rag-paired-chroma|d73a503f282e43888f1221993abb9601|2|indeterminate|—|
|deepseek|edge-unavailable-train-after|3547c56ca910421aa677367c8d985b3a|2|indeterminate|reply_data_indeterminate|
|bailian|edge-no-answer-after2|6a8129505d5b4d20b96a8e39c36db92c|2|indeterminate|reply_data_indeterminate|
|bailian|edge-no-answer-after3|ee896511ec984cc1910948e21229e016|2|indeterminate|reply_data_indeterminate|

两个浏览器真实查票：DeepSeek Trace `75ebca29003a42c28ac404a8f0791c3b`，工具调用成功但回答校验 indeterminate；Qwen Trace `9be004282d2d4ef1a5aa4251841eb45c`，实际 qwen3.8-flash、查票参数与结果一致。双模型 Chroma hybrid 对照使用同一冻结政策和缓存向量，工具返回 P11 且回传哈希一致；模型全文忠实度仍 indeterminate，需 B 复核。

**未覆盖**：售罄单独 Live、无效日期语义、真实慢网跨标签并发、完整二十项浏览器操作、实时 Embedding/LangSmith。无此证据不计通过。

本轮源码回归 SHA `e5688aae59ee9a8716527aae5e4591a4da41a6c3`；报告提交 SHA 请用 `git rev-parse HEAD` 查看。主环境 699 项通过、109 个子测试通过；失败 0、错误 0、跳过 0。旧环境跳过情况：deepseek_unit 跳过 24；v3_unit 跳过 139；v2_unit 跳过 277；mock_smoke 跳过 0。本轮原文件快照 20059 项，变更 0 项。
