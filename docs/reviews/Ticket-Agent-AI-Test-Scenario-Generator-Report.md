# Ticket Agent AI 测试场景生成交付报告

2026-11-09，最终状态 PARTIAL。当前分支 feat/ticket-agent-v36-stabilization，HEAD c1620cb4e9e8df094494fc77ef3f0d07ef9928c3。

## 现场与范围

开工记录见 artifacts/runtime/ai-scenario-20261109/opening.json。开工已有12个跟踪文件修改及乘客提案、模拟时钟等未跟踪成果。暂存为空。代码进程盘点只能识别本机执行器，不能证明所有Codex会话均空闲；本轮只在新模块及web/app.py导航追加入口，开工已有源码SHA复核仅web/app.py发生本轮预期变化。原有修改保留。没有提交或推送。

## 实现与架构

测试控制台新增同级入口“AI 测试场景生成”。复用原主题、侧边栏、表单、折叠面板及JSON组件，页面纵向流式排版，正文左对齐，无全局CSS改动。十个领域选择、难度、数量1至5、模型、目标和高级约束。Mock明确展示固定流程样例。DeepSeek/Qwen生成调用复用p2_generator.call、现有Provider、密钥配置和持久预算V2，每次显式点击、单次1请求、4096输出Token、零自动重试。费用未知保存UNKNOWN。在线需勾选本次费用授权。

候选结构在target/scenario_generator.py中版本化为ticket-ai-scenario/1，兼容既有P2数据。包含case_id/title/category/difficulty/objective/preconditions/conversation/expected_behavior_details/expected_tool_calls/expected_state_changes/assertions/risk_level/source_references/generation_model/prompt_version/created_at/review_status、原P2 turns/expect/turn_expects及normalized_hash。工具参数类型、枚举、未知字段、引用和可执行断言复用P2校验并补充严格门控。规范化内容Hash忽略标题与空白变化，另用SequenceMatcher与字符二元组Jaccard查相似。审批时与B正式catalog及其他候选比较。相似度只用于提示，不能当业务正确性评分。

证据包读取旧八工具Schema、V3.9十一工具注册表、SYSTEM_PROMPT及本次基线effective prompt、政策文档、D9政策与生命周期实现、现有103用例catalog、历史乘客提案缺陷报告、源文件SHA。不会读取API Key。没有railway_lock_seat。生成内容默认PENDING，PASS只代表确定性结构检查通过。预期不明确、前置数据未适配、铁路工具、数据库状态、调用顺序等尚无可用执行适配时标NEEDS_REVIEW并阻止批准。

SQLite独立存放artifacts/runtime/ai-scenarios/candidates.sqlite。cases保存当前修订；history追加修改/审核/删除轨迹；generations记录生成状态、原始响应、来源快照、用量及失败；runs独立记录每次执行、修订号和原执行器原始回执。批准冻结内容；修改需匹配revision，批量审核同一事务；删除仅未批准候选，保留审计墓碑；已执行记录保留。支持搜索、状态及执行结果筛选、排序、JSON导出、编辑、单条/批量审批/拒绝/归档。

已批准用例调用原p2_executor.run_case，原Legacy Mock沙箱、SQLite、逐轮断言、工具真实执行事件及run_events/Trace均复用，保存case/revision/run_id/evidence_ref。生成失败与Agent测试失败分别存在generations/runs。正式103、P2原候选/approved、RAG1000、七维度和历史成绩均未改动。

## 文件清单

- target/scenario_generator.py，新增证据包、候选校验、独立存储、生成与P2执行适配。
- web/scenario_generator.py，新增测试控制台页面及审核交互。
- web/app.py，仅新增一个导航值和一个分发分支。
- tests/test_ai_scenario_generator.py，新增17项确定性测试。
- PROJECT_STATUS.md，本轮状态增量。
- 本报告。

## 审计与Skill

实际读取frontend-design、eval-audit、write-code-eval。前端沿用蓝白/深色主题，生成、审核、执行按工作流组织。eval-audit发现旧执行器只支持Legacy Mock、旧八工具，不具备数据库状态/调用顺序/性能耗时断言；采用能力门控，没有把自然语言期望当执行断言。write-code-eval用已知失败模式构造正反例，验证虚构工具、错参、空断言、待定预期、重复、修订冲突、未批准执行、批准后删除、工具事件及Trace路径、预算持久化与Provider切换还原。未采纳另建LLM Judge、Embedding去重或改写P2/正式基线的做法，现有确定性检查足以覆盖已支持范围，额外模型评分缺少标注校准。

## 实际验证与证据

统一证据目录 artifacts/runtime/ai-scenario-20261109/。

- 最终专项命令 python -B -m pytest tests/test_ai_scenario_generator.py tests/v39/test_acceptance_budget_v2.py -q -p no:cacheprovider --basetemp=<本轮独立目录>。结果24 passed / 0 failed / 0 skipped，其中新模块17项、原预算7项。原始日志unit-sealed.log，JUnit unit-sealed.xml。首轮预算专项因默认pytest临时目录ACL失败保留在unit-r2.log，改用项目隔离basetemp后通过，没有改旧断言。
- 完整隔离回归命令及源码副本见 regression_r3.py、regression-r3-command.json、full-01/snapshot/ticket-agent/runner_r3.py。结果1842 passed / 11 failed / 1 skipped，199子测试通过，159.33秒。包含新模块当时14项、V3.9 387项和旧1441通过项。之后补充的3项及最终小范围门控/元数据及预算丢失拒绝重建修复通过上述24项专项，整套回归没有再次执行。results-r3/保存逐ID、原始日志、JUnit。baseline-comparison.json证明原11失败和唯一Skip ID零增减。
- 首两轮完整回归日志保留。第一轮42失败/40错误，缺RAILWAY_SIM_DB_PATH且tmp_path在UI允许范围外；第二轮52失败/175错误，临时目录位于V3.9不接受的命名空间。第三轮只修验证环境，使用独立v310-*及v391-d9-lifecycle-*目录后恢复历史失败集合。未改保护逻辑、旧测试断言或Skip。
- Edge+Playwright验证1600×900、1366×768、800×900、390×844，各浅/深主题。35检查/0失败，8张规格截图，另1张审核选择截图，PageError0。Console32/NetworkFailure32均为主动拦截fonts.gstatic.com图标，不声称Console为0。browser-05/results.json和PNG保存真实证据。首轮输入框未blur导致按钮仍禁用、另一轮服务未就绪、以及刷新回默认工作空间的驱动误判，原日志保留。修正测试驱动后完成候选生成、人工批准、原P2执行、刷新再导航恢复、各尺寸横向溢出检查。
- protection.json覆盖5586个开工保护文件，SHA零变化，包括原测试、数据/RAG、原Trace/账本和静态SQLite。source-review.json记录已有源码仅web/app.py预期改变。最终Git状态和diff检查另存本目录。
- 模型真实请求0，真实模型Token未知，真实费用UNKNOWN。Mock流程Token0/费用0。预算验收使用替身请求，单测构造20输入/10输出Token，仅为离线测试数据。真实模型生成/Live验证NOT_RUN，没有自动启用模型、铁路、支付或Bridge。

## 验收矩阵

| 项目 | 状态 |
|---|---|
| 导航集成 | PASS |
| UI响应式 | PASS，8规格 |
| AI场景生成 | PARTIAL，已接两Provider，Mock验证，真实请求NOT_RUN |
| Schema校验 | PASS，当前已支持字段 |
| 重复检测 | PASS，Hash/相似检测/正式catalog |
| 人工审核 | PASS，本地操作者记录 |
| 数据持久化/隔离 | PASS |
| 原执行器接入 | PARTIAL，仅Legacy Mock及P2断言 |
| Trace关联 | PASS |
| 新功能单测 | PASS |
| 原有回归 | 基线一致，整套仍11 FAIL/1 SKIP |
| 浏览器 | PASS，35检查 |
| 保护核验 | PASS，5586文件 |

## 未完成与风险

最终PARTIAL。真实模型生成质量、Token及费用尚未验证。铁路工具、真实SQLite业务状态变化、工具顺序、延迟/吞吐及LangChain/Live被测Agent尚未接入本模块执行适配，相关候选不能批准执行。原103执行器仍BLOCKED。当前生成使用基线effective prompt，不支持选择会话Developer Override。审核人是本地审计标识，沿用本机单操作者部署，没有新增独立身份认证。生成预算账本丢失时依据已有生成历史拒绝重建新批次，并保留FAILED原因及预算错误类别。进程中断可能留下RUNNING条目，需人工核验，不自动重放交易或模型请求。

当前Mock样例用于验证工程流，重复请求会产生相似候选并由审批门控阻止，不能作为高质量AI生成的证明。时间/SQL状态断言不受支持时宁可待审核，不能把检测到的格式正确当成业务成功。外部独立审查NOT_RUN，用户验收PENDING。可以开始对已支持的离线路径做独立代码审查，完整验收需补齐上述适配及受控真实模型验证。
