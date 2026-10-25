# V3.4.1 开发记录（2026-10-25）

## 基线与原始复现

- 实际基线分支feat/ticket-agent-v34-api-audit，HEAD e7831d3dce401653e8da8fc3911b574415015ba6；工作区仅用户原有docs/showcase/v3展示.zip未跟踪。新建codex/ticket-agent-v341-answer-integrity，不覆盖旧分支或标签。
- 读取A_V3.4报告、两Provider原始结果/Trace、API汇总与当前检测器。隔离工作目录artifacts/runtime/v341-work保存3590个原始文件哈希，包含历史证据、数据库、旧账、契约与用户ZIP。
- 用旧检测器实际复现百炼4处错误（G7303/G7301的depart与arrive互换），原始Trace 7f83f6a0165a46fd8791e74ff7f84558。DeepSeek同场景正确。只读原件，不改回复、Trace和预算。

## 模块一：字段检测与共用安全降级

- 修改target/reply_consistency.py：按完整业务身份筛选候选，不覆盖同车次的不同日期/席别；比较九字段；明确错误、无法判定、仅已检字段一致分开；保存字段/行号/原文/权威来源。旧事件缺executed可读，失败/明确未执行/只有预览不作权威。
- 修改target/langchain_agent.py：两个Live Provider使用同一逻辑；failed抛reply_tool_mismatch，indeterminate抛reply_data_indeterminate。仍保留原model_final事件顺序和文字。公共十字段/五字段不改；Mock路径不变。
- 修改web/conversation.py与cli.py：明确中文安全提示，CLI百炼也用脱敏失败输出；不把错误原文替换为成功回答。未开放额外工具、未修改SDK/预算/请求逻辑。
- 新增tests/test_v341_reply_consistency.py和tests/fixtures/v341_reply_cases.json：62组完整输入/工具权威/模型输出/独立预期，另有4项属性与6项真实SDK+MockTransport集成测试，共72项。每个Provider覆盖正常/错配/无法判定，只有本地桩HTTP，不是真实API。
- 实际命令：python -m unittest discover -s tests -p test_v341_reply_consistency.py -v。首轮58通过；扩展到67项时1失败（DeepSeek正确原文“均有余票”的范围被过度判为无身份字段）；为明确的全量库存断言增加单查询范围核验后67通过，补充边界后72通过0失败0跳过。日志分别保留specialist-first/second/third/final.txt，不改预期换通过。
- 实际运行原test_v34_api_audit.py 25通过；旧checked_fields时间计数兼容，train_no身份另计。手工复现曾发现“查询到的班次”被误识别为城市路线，已修复并由DeepSeek原文用例覆盖；主动声称的引号不能冒充用户引用豁免，单独覆盖。
- 本模块模型请求0，LangSmith请求0，原4/4和正式5/5不变。B须独立评估语言规则误报/漏检及安全停止行为，C不得把历史重放当修复后Live。

## 模块二：可复现证据导出与完整离线门禁

- 模块一提交8bd3822。新增scripts/verify_v341_offline.py：只接受新runtime子目录，剥离真实Key、禁用本地秘密发现，复用原网络守卫和verify_v33_offline.py完整回归。
- 每组专项用例导出输入、权威事件、模型输出、预期、实际字段结论、断言结果；历史DeepSeek/百炼分别导出原始来源SHA/Trace/工具/回复/Token/延迟与新检测器的离线重放，明确不是修复后Live。
- 读取保护范围原件并核对哈希，不重写原预算或Trace；每个输出目录全新，失败输出保留，不复用旧证据目录。
