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

## 完整回归发现与修复

- 验收入口提交68e17ad。执行python scripts/verify_v341_offline.py --out artifacts/runtime/v341-final-20261025：专项72通过、62组断言全对，但完整353项中原test_v32_audit的hallucinated_train子场景失败，smoke因此失败；V3/V2均无失败，历史文件不变、真实请求0。原失败目录保留。
- 原变异场景模型回复“查到G9999有余票”，工具可见结果由M7故意注入G9999，独立数据库审计应继续检出伪造来源；新检测器不能为此单独豁免变异。实际问题是把“有余票”当成不可识别的精确数量。
- 修复seats_left支持明确的正库存谓词（>0），不捏造具体张数；权威库存仍必须是整数，0库存会明确失败。“余票充足”等不精确表达保持indeterminate。没有修改变异或原断言。A自建symbolic_stock预期据此改为只检正库存，新增0库存反例及含糊库存反例，不修改B用例。
- 修改target/reply_consistency.py及A用例；专项74通过0跳过，原test_v32_audit定向回归日志original-audit-fixed.txt。随后新目录重新运行全量回归，不将旧failed报告改成passed。

## 模块三：最终回归与团队交付

- 修复提交9bd3c29049bb6de920e80283e3a9a4e361155470后执行python scripts/verify_v341_offline.py --out artifacts/runtime/v341-release-20261025：专项74/74，64组字段预期全部通过；完整355/355，V3为290通过65跳过，V2为204通过151跳过，均0失败。原281项不改，Mock smoke、八变异25/8与原9项审计定向通过。
- 本轮真实模型请求0、LangSmith0、拦截到的外网尝试0；校验初始3590历史文件哈希全部不变（完整入口保护3589，另一个文件是用户ZIP），正式5/5和V3.4共享4/4不变。
- 新发布docs/evidence/v341/包含每用例完整输入/权威/输出/预期/实际/断言、两历史原文重放与来源SHA、通过及失败日志；不改docs/evidence/v34/。新增四份正式报告和独立待授权计划，计划建议先百炼2请求，未创建新在线执行入口/额度，不当作已运行。
- A专项开发的库存预期修改有明确语义改进和0库存反例；B正式断言未改。当前状态有条件交接，尚缺修复后Live及B独立质量评价。最后仅做安全/证据一致性/Git交付，不增加模型请求。
- 本地安全检查1352文件，对3个已配置秘密仅内存精确匹配，命中0；无秘密/原始推理字段/用户路径进入新交付材料。3590个历史文件哈希不变，原断言/业务/变异/预算代码不变；security_review.json留证。B手册只读示例实际执行，输出四条原时刻错误。随后索引新证据并核对Git暂存字节，用户原ZIP排除，准备仅推送独立开发分支。
- 交付提交938ca2a后检查原回复Markdown双空格和原失败日志行末空白：保留原样，只在新证据及原文对照文档限定Git空白检查属性，避免自动trim篡改引用；新增元数据提交，不改写旧提交。113个新证据文件Git暂存SHA256逐项一致。
