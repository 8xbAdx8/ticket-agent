# Ticket Agent V3.7 阶段六：Baseline 与 Developer Override 执行隔离

更新时间：2026-11-01T19:32:16.659908+08:00。结论：**COMPLETE（离线工程验收；保护例外已批准）**；等待用户验收，停止于阶段六。完整回归仍有原11失败，不能称项目全绿；103条正式断言未重新执行，真实模型风格与外部API未验证。1892清单中1890文件字节不变；target/tools.py与web/evidence.py两项限定源码差异已获用户明确批准。公开工具Schema与DIMENSIONS的AST哈希不变，原清单和原哈希完整保留；不将其描述为1892文件字节零差异。

## 1. 阶段六目标

在保留阶段五未提交工作的基础上，使会话实验配置真正进入下一轮Agent，冻结正式配置、限制执行权限，并隔离实验报告。未进入阶段七、未接12306、未Commit/Push/Merge。

## 2. 实施前审查发现

现场分支`feat/ticket-agent-v36-stabilization`、HEAD `c889b082dd4bd07e3514038a69362b71dd21915c`；起始Git状态见`artifacts/runtime/v37-phase6-baseline-override-20261101/before-approved.json`，完整保留阶段五源码/报告/72截图。发现旧Agent只在空对象时构造、Legacy工具Schema不足以代表权限、LC最终Prompt有替换及附加、历史报告无新配置身份、待确认操作须绑定配置。按本地实际源码先审计再实现；最小计划为存储→解析→执行器→隔离评估→编辑器→离线/浏览器证据。

开工唯一历史差异是百炼账本追加8249字节。用户明确批准保留追加、采用当前账本保护基线；原250920字节前缀完整。批准后的259169字节SHA为`fa5fceb48f57a756d23715d5c53f80d883a36d6e12dee937a1a45548ddbdc3e3`，本阶段未再修改。不能以此次批准代表真实API授权。

## 3. Baseline设计

`target/baseline_profile.json`冻结八工具、五项confirm权限、固定seed/政策/103目录哈希及2026-10-20时钟。正式解析不构造/读取Override Store；正式网关固定Mock、独立DB/Trace、身份与RAG，拦截网络并在finally恢复全局/环境/缓存。Baseline Prompt固定日期及模拟身份，不继承用户环境；LC/Legacy由显式正式引擎策略区分，页面只读。SYSTEM_PROMPT原值不改。

## 4. Developer Override设计

`artifacts/runtime/developer-overrides/<sid>.json`指向严格schema1配置，`<sid>/revisions/00000001.json`等保留历史。会话归属/路径限制、字段白名单、合法工具/Provider/model、有限温度、deny/confirm与RAG校验；未知字段拒绝。文件锁+线程锁+CAS；临时文件fsync、排他历史link、原子指针replace。指针失败时旧指针有效，孤立revision保留、下次跳号，不覆盖。SHA用于完整性核验，不把本地可写文件当作账户认证系统。

## 5. EffectiveConfig解析与实际变更文件

每轮开始解析不可变dataclass及tuple，配置hash变更才重建Agent。运行中不重新读Store；同引擎历史带入新执行器；恢复Baseline生成新revision，回到该会话最初配置，不使用上次Override模型。工具集取Baseline、开发者选择、运行模式安全范围交集。新模型不会修改其他会话或全局默认配置。

| 文件（相对项目根目录） | 修改原因 |
|---|---|
| `PROJECT_STATUS.md` | 增量维护当前阶段及本次证据，保留历史记录。 |
| `docs/reviews/Ticket-Agent-V3.7-Phase6-Baseline-Override-Report.md` | 阶段六完整交付报告。 |
| `target/agent.py` | 接入冻结配置、真实Prompt/Schema、公共入口范围和旧提案版本检查。 |
| `target/bailian_runtime.py` | 合法temperature传入原SDK构造，不改变默认选择/重试/费用。 |
| `target/baseline_profile.json` | 冻结正式工具/权限、模型注册种子、fixture/政策身份及正式时钟。 |
| `target/deepseek_runtime.py` | 合法temperature传入原SDK构造，不改变默认选择/重试/费用。 |
| `target/dev_overrides.py` | 严格会话存储、锁/CAS/原子指针/不可变revision和SHA。 |
| `target/execution_config.py` | 不可变EffectiveConfig、共同安全边界和配置sidecar。 |
| `target/langchain_agent.py` | 精确Prompt、模型构造参数、双层工具拒绝及当前提案确认；直连模型一致性校验。 |
| `target/profile_evaluation.py` | 离线正式配置入口及独立自定义报告，保留原B断言回调。 |
| `target/prompt_config.py` | 抽出既有精确Prompt组合，固定Baseline日期/模拟身份。 |
| `target/run_events.py` | 每run配置旁证与实际model_start Prompt；自定义save_trace=False仍保留配置身份。 |
| `target/tools.py` | 既有dispatch执行前统一拒绝，八工具公开Schema不改。 |
| `tests/test_dev_overrides.py` | 存储、校验、Baseline隔离、不可变和原子故障客观测试。 |
| `tests/test_override_execution.py` | 实际双引擎、SDK/Trace、权限/费用、恢复/页面/评估与UI集成测试。 |
| `web/conversation.py` | 迁移用户底层RAG设置、费用状态提醒、待确认提案配置绑定。 |
| `web/developer.py` | 真实历史规则/用例关联，批准0与T04未复验事实展示。 |
| `web/developer_config.py` | 会话编辑/保存/恢复/只读Baseline/独立离线评估。 |
| `web/developer_workspace.py` | 嵌入配置编辑器和只读历史快照，原LangSmith功能保留。 |
| `web/evidence.py` | 排除Developer实验旁证，DIMENSIONS不改。 |
| `web/formal_results.py` | 正式导入联合真实配置身份，拒绝伪造owner/自定义/非Baseline新运行。 |
| `web/order_actions.py` | 页面退改操作适用工具策略，确认前复核预览配置。 |
| `web/payment.py` | 已配置会话的页面确认key加配置身份，避免旧勾选跨revision复用。 |
| `web/runtime.py` | 下一轮重建、原始配置恢复、Provider费用重核、RAG实际值与页面权限映射。 |
| `web/user_features.py` | 既有页面入口费用授权与订单预览绑定，业务服务不变。 |

阶段五`web/app.py`、`web/design.css`、`web/scroll_bridge.py`、`web/user_layout.py/css`和`tests/test_phase5_layout.py`继续保留且相对开工字节不变；仅conversation/user_features在原布局上做阶段六增量。所有既有测试文件字节不改，控件key仅已配置支付确认新增配置身份，防旧确认沿用；未重命名原session_state业务变量。

## 6. Prompt真实生效证据

`target/prompt_config.py`精确保留原Legacy日期、LC只读替换/日期/安全规则组合；suffix追加不能给予工具权限。冻结后由真实model_start输入复算SHA，独立sidecar记录`submitted_to_model_adapter`；初始快照区分`frozen_not_submitted`，不把预览冒称已发送。两引擎专项直接捕获实际输入。sidecar中的Prompt文本仍适用原有隐私脱敏，含模拟手机号时其展示文本不能直接复算原始输入SHA；本次隔离浏览器以已知固定演示身份还原该一处占位再核验，实际adapter输入另由专项测试捕获校验，不能把脱敏文本SHA与原始输入SHA混用。四规格实际用户run关联与SHA核验见`*-config-evidence.json`、`browser-run-linkage.json`及verification。

## 7. 工具白名单拦截证据

Legacy最终Schema过滤，同时`tools.dispatch`在后端调用前拒绝；LC注册/中间件/适配器共同限制，直接LC入口也冻结配置。敌意模型即使提议被禁工具，拒绝事件仍关联run/call，不修改DB/库存，不伪造成功。专项比较完整SQLite dump，浏览器取消query_tickets后再发送并核对库存哈希，恢复后真实query_tickets成功。

## 8. 写操作权限验证

只支持deny/confirm，confirm不代表用户已确认。原身份、订单归属、幂等、状态/政策规则保持；自定义LC每次真实写提案需要确认。页面支付/退改也映射原工具能力，预览与配置绑定；旧revision批准拒绝，可取消重生成。未新增自动批准能力，未修改退票/改签/支付业务服务。

## 9. Legacy与LangChain一致性

两者共用EffectiveConfig、scope和dispatch拒绝，实际敌意模型分别验证白名单及deny。默认未配置会话沿用原兼容路径，旁证明确为`legacy_runtime`、`runtime-unpinned`，不能冒充新正式Baseline。既有正式测试可信内部入口仍保留原授权行为，开发者自定义路径额外确认不可省略。

## 10. Provider与Temperature证据

合法Provider/model来自既有注册配置及冻结种子，不能输入URL/任意模型。切换Provider先停止发送、重核当前Provider/会话/revision费用授权；未恢复Qwen独立checkbox。原主请求/额外追问费用含义保留。temperature取保守交集0—1，NaN/布尔/越界拒绝；Mock显示N/A。两SDK构造捕获+两条HTTP MockTransport实际请求JSON验证model、temperature=.25及最终Prompt，直连LC模型不一致提前拒绝。全部为离线替身，真实风格效果未验证。

政策检索方式及Embedding授权移至开发者端，下一轮实际RAG使用冻结值；授权开关默认关闭，保存不发请求。Mock实验不伪造温度采样或真实Embedding结果。

## 11. 配置revision及SHA

两新增测试文件共60项通过，含revision递增、跨会话/路径拒绝、非法JSON/篡改、CAS及指针失败恢复。四规格真实保存revision1、恢复revision2，旧版本文件保留；最终Prompt与配置SHA分别记录，不混用。测试及浏览器最终源码清单与当前py/css/配置一致，文档随后更新另有SHA。

## 12. Trace sidecar

公共Agent十字段、工具五字段保持，未给公共Trace添加配置字段。私有运行对象保存实际工具子集，sidecar位于每会话Trace目录的`config-events/`及全局`artifacts/runtime/config-events/`，记录session/run/batch、source/mode/baseline/revision、最终Prompt/hash、实际工具/权限、Provider/model/temperature、Fixture/政策。失败及自定义save_trace=False仍有配置身份。历史无快照时明确缺失，不回填伪造；只读展示不执行。

## 13. Baseline/Override隔离

正式入口`target.profile_evaluation.run_batch('baseline')`使用独立离线网关，不读取Store，不访问网络；自定义`developer_custom`只允许离线Mock，独立目录/Trace/schema，标签`Developer Experiment · Non-Baseline`。正式导入联合mode/source/baseline/revision/batch/fixture及实际run旁证判断，不仅依赖owner；实验不进入正式七维度聚合。Phase6前无sidecar历史保持原兼容导入，不把旧记录补标为新Baseline；新legacy_runtime拒绝作为正式成绩。

## 14. 正式103条保护

103原case_catalog、expect、B所有快照/manifest与所有旧测试SHA不变。四规格正式按钮只核验103输入/expect与配置身份，每批103行均`not_verified`；本仓库缺少B原始独立断言执行器，不重写其规则。网关预留原执行器回调，取得原件后才能授权重新计分。这里没有“103条通过”的新结论，也没有更新B正式成绩。

## 15. Skills审查记录

完整读取并使用原版`eval-audit`与`write-code-eval`的方法，原文件SHA保持。使用本地源码、报告、Trace、DB及实际测试，无远端MCP/LLM Judge/新依赖。

| 发现 | 风险 | 实际问题 | 处理 |
|---|---|---|---|
| F01 | high | 旧Conversation仅agent is None时构建，保存JSON不保证下一轮生效。 | 每轮冻结EffectiveConfig；hash变更才重建；同引擎保留历史；在途不变。 |
| F02 | critical | 仅隐藏工具Schema不能证明执行边界安全；页面业务也可能绕开Agent工具。 | 共享工具拒绝边界，页面映射原工具能力；比较DB完整状态与拒绝事件，不仅返回文案。 |
| F03 | high | 模板Prompt与日期/只读替换/安全附加后的实际Prompt不同；环境身份可能影响Baseline预览。 | 统一精确组合，冻结日期/模拟身份；捕获实际模型输入复算SHA，旧Trace不补造。 |
| F04 | critical | owner单字段不足以隔离自定义实验与正式成绩。 | 独立报告schema/目录及真实run sidecar来源联合判断；新legacy_runtime不冒充Baseline。 |
| F05 | critical | 待确认操作若未绑定revision，配置切换可能沿用旧批准。 | 冻结提案配置；变更后拒批，仅允许取消再生成；费用/页面勾选与配置身份绑定。 |
| F06 | high | 指针落盘失败不能破坏旧配置；并发需要CAS而非仅线程锁。 | 文件锁+CAS+不可变版本+原子指针；保留孤立revision而非覆盖删除。 |
| F07 | high | 未取得B原始独立断言执行器，不能以配置核验替代103条正式重新计分。 | 原始输入/expect哈希不变；预留原始executor回调；明确不运行/不替代原成绩。 |
| F08 | medium | 原11个失败继续存在；T04历史漏检与批准用例0不能淡化。 | 逐ID比较；保持历史证据，展示未重新验证；另行产品契约修复任务处理。 |

未采纳远端观测连接（禁止真实API且已有本地证据）、LLM Judge/新标注评分（客观约束用代码，不能改正式七维度）。F07不能核定的原断言执行器继续保留限制，F08旧失败继续独立处理。详见`skill-audit.json`、`code-eval-spec.json`、`skills-usage.json`，未虚构Skill运行API。

## 16. 新增测试

仅新增`tests/test_dev_overrides.py`、`tests/test_override_execution.py`，60项客观检查在完整回归中全通过；未删除/修改旧断言、未新增skip/xfail。每项输入/预期/失败条件见code-eval-spec，测试映射：

| 规则 | 内容 | 实际测试函数 |
|---|---|---|
| C01 | 最终Prompt SHA | `test_final_prompt_matches_actual_model_and_sidecar` |
| C02 | revision与不可变历史 | `test_revision_atomic_pointer_history_and_sha` |
| C03 | 白名单dispatch | `test_actual_dispatch_blocked_in_both_engine_adapters` |
| C04 | 敌意模型提议 | `test_hostile_model_proposal_blocked_at_execution_boundary` |
| C05 | deny/confirm非授权 | `test_write_policy_does_not_authorize_by_itself` |
| C06 | 工具与参数上限 | `test_invalid_settings_never_save` |
| C07 | 费用授权隔离 | `test_provider_switch_never_inherits_fee_consent` |
| C08 | 下一轮生效 | `test_frozen_run_does_not_follow_store_edits` |
| C09 | Baseline无Override读取 | `test_baseline_never_reads_override_and_config_frozen` |
| C10 | 正式103身份 | `test_formal_103_identity_without_regrading` |
| C11 | 自定义结果归属 | `test_formal_import_rejects_custom_even_with_owner_spoof` |
| C12 | 恢复与旧提案 | `test_pending_langchain_proposal_keeps_revision_and_requires_cancel` |
| C13 | 真实构建参数 | `test_sdk_mock_transport_captures_exact_temperature_and_prompt` |
| C14 | RAG与页面安全 | `test_selected_rag_mode_reaches_actual_retrieval` |

## 17. 完整回归

命令（PowerShell，项目根目录）：

```powershell
$env:PYTHONPATH=(Get-Location).Path
.venv-v35/Scripts/python.exe artifacts/runtime/v37-phase6-baseline-override-20261101/run_checks.py full-r10
```

helper复用原regression_center.prepare，在独立snapshot、DB/Trace/temp运行`.venv-v35/Scripts/python.exe -m pytest tests -q --tb=short --junitxml=...`，15冻结P0输入核验；删除进程环境中的业务凭据、外部socket guard，原正式目录不写。最终源清单`full-r10/source-manifest.json`；时间/命令/退出码见summary。

| 范围 | Passed | Failed | Skipped | 子测试通过 |
|---|---:|---:|---:|---:|
| 阶段五历史基线 | 1251 | 11 | 1 | 199 |
| 阶段六最终完整回归 | 1311 | 11 | 1 | 199 |
| 阶段六新增（包含于上一行） | 60 | 0 | 0 | — |

阶段二40、阶段三59、阶段四45、阶段五9全部保持通过；旧测试减少0、新失败0、原失败/Skip ID完全一致。非全绿。所有targeted/full中间运行（含LC代码拼接语法、辅助旁证重绑定、旧UI测试替身方法兼容、收尾环境隔离）及浏览器脚本/启动错误保留，最终结论仅指full-r10。一次helper遗漏PYTHONPATH在pytest启动前失败，不计测试结果；浏览器r6端口占用未运行验收，启动日志保留。收尾脚本曾错误读取公共十字段中不存在的trace_id、对脱敏Prompt直接复算SHA、把自身PowerShell命令行计作未停止服务；已改为审计旁证run_id、固定演示身份的显式还原核验及仅Python服务进程核验，原记录保留。这些属于验收脚本问题，不用来改写产品测试数量。

## 18. Edge四规格验收

使用既有Playwright1.64.1与本机Edge 156.0.4314.50，真实DOM click/fill/keyboard，不force、不改业务session_state。命令`node artifacts/runtime/v37-phase6-baseline-override-20261101/browser_acceptance.js`；隔离服务`browser-r8`端口8519，已停止。

| 规格 | 检查 | 实际Mock Agent运行 | 最新配置 |
|---|---:|---:|---|
| desktop-light | 15/15 | 3 + 1自定义评估 | revision 2 / baseline |
| desktop-dark | 15/15 | 3 + 1自定义评估 | revision 2 / baseline |
| mobile-light | 15/15 | 3 + 1自定义评估 | revision 2 / baseline |
| mobile-dark | 15/15 | 3 + 1自定义评估 | revision 2 / baseline |

合计60/60，28张真实PNG；4×(3用户run+1自定义评估)=16次Mock运行，不是收费API。实测编辑/工具/deny/model选择/温度控件、保存不发请求、下一轮阻断、恢复实际查询、只读正式配置、不重计分、自定义报告分离、手机导航与无横向溢出。实际Prompt/hash/工具与数据库回查在四份config-evidence中，失败及浏览器原始日志完整保留。

PageError=0；Console error=20、失败请求=8、拦截外部请求=8，均以原始browser-verification为准。其中8条Console为外部图标资源被拦截，另12条为`react-json-view error: src property must be a valid json object`，不能一概归为外部资源。JSON查看组件的这12条错误未单独完成根因复验（已有诊断区存在对空error调用st.json的路径），列为遗留UI诊断问题；60项实际操作检查通过不代表Console无错误。Live SDK未在浏览器发真实请求，实体手机软键盘及真实模型风格未验。

截图示例：

![桌面浅色配置](../../artifacts/runtime/v37-phase6-baseline-override-20261101/desktop-light-saved.png)

![移动深色配置](../../artifacts/runtime/v37-phase6-baseline-override-20261101/mobile-dark-saved.png)

## 19. 阶段五及历史文件保护

审批闭环（2026-11-01T19:32:16.659908+08:00，Asia/Shanghai）：用户答复“批准这两处限定差异，保留原清单并如实记录”。本次仅记录批准并复核现有SHA，未再次修改应用源码、未重跑测试；沿用最终full-r10与四规格Edge证据。原PARTIAL交付原件已保存至`approval-closeout-before/`，批准内容及两文件当前/原SHA见`protected-source-approval.json`。原始1892清单保持不动，其余1890及4056历史文件再次核验一致。

1892清单中1890文件字节不变；target/tools.py与web/evidence.py两项限定源码差异已获用户明确批准。公开工具Schema与DIMENSIONS的AST哈希不变，原清单和原哈希完整保留；不将其描述为1892文件字节零差异。 4056获准历史基线零差异；阶段五72图、报告、verification哈希全部不变。阶段五布局代码除授权conversation/user_features增量外不变。原Trace、API回复、SQLite、Chroma、政策、数据集、P2、历史标签不改；全部旧测试字节一致。完整清单、两处源码diff及批准账本例外见before-approved/protection-check/verification/protected-source-differences，不把实际差异抹去。

## 20. 原11失败ID对比

| 完整ID | 阶段五 | 阶段六 |
|---|---|---|
| `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_configured_online_default_is_deepseek_and_render_never_calls_agent` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_direct_send_permission_is_session_and_provider_specific` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_qwen_still_requires_its_original_checkbox` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_followups_continuous.py::ContinuousFollowupsTests::test_qwen_ten_clicks_survive_timeout_and_saved_replay` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_followups_mvp.py::FollowupRuntimeTests::test_qwen_ui_consent_automatically_includes_followups_offline` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_empty_qwen_run_has_a_clear_reason_and_disabled_export` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_explicit_history_selection_is_preserved_and_model_is_explained` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_live_fee_consent_does_not_follow_a_different_provider` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_qwen_panel_rejects_another_provider_record_without_export` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_qwen_stays_active_after_opening_integration_center` | 阶段五失败 | 阶段六仍失败 |
| `tests/test_unlimited_live_ui.py::LivePageTests::test_bailian_user` | 阶段五失败 | 阶段六仍失败 |

唯一Skip仍为`tests/test_p2_scenarios.py::test_no_approved_p2_scenarios`；没有因Phase6重写旧断言，不能把这些全部归为环境问题/测试过时。后续按显式配置优先、Provider/会话费用、追问和LangSmith展示产品契约独立修复并批准更新相关UI断言。

## 21. 未解决问题与验收边界

原11失败、历史T04漏检未重验、已批准P2用例仍0；正式103断言未重跑；真实模型风格/费用与真实Embedding、LangSmith上传/GET未重新调用验证。12条JSON查看组件Console错误保留，尚未独立根因复验。已有LangSmith上传/GET代码保留，旧测试原件保护。项目仍为固定模拟身份/示例业务，本地SHA不是数字签名/多用户认证；有磁盘写权限的操作者不在本轮账户威胁模型内，但不能靠JSON扩大八工具/deny-confirm/Provider模式上限。旧无身份报告兼容必须人工核对历史来源，不视为新Baseline。

真实模型请求0、Embedding0、LangSmith0、12306/真实支付0；SDK MockTransport响应中的usage是测试输入，不能记作实际收费Token。未知实际Token/余额不填写0或臆测。无新增依赖，未改原8次工具、轮数/超时/零自动重试、费用及业务边界。

## 22. Git最终状态与交付证据

HEAD `c889b082dd4bd07e3514038a69362b71dd21915c`，分支`feat/ticket-agent-v36-stabilization`；暂存区为空，git diff --check退出0；阶段五与阶段六变更仍未提交。完整status和逐文件源码SHA见verification。项目状态增量更新第1—12节，历史记录保留。交付入口：本报告、PROJECT_STATUS.md、`artifacts/runtime/v37-phase6-baseline-override-20261101/verification.json`；pytest/JUnit、config证据、Skills、源码、截图与服务停止记录均在独立产物目录。

## 23. 阶段七准入条件

本阶段已停止，等待用户确认阶段六验收。保护清单差异审批状态：approved；用户已批准两处限定差异，阶段六离线工程验收状态更新为COMPLETE，等待用户整体验收。阶段七须另行明确授权及12306来源/快照合法边界、联网条件、Fixture优先/缺失报错、数据来源和时间展示方案；先保护103及历史数据，不能把实时数据混入正式Mock成绩。是否提交/推送也须另行明确授权，本阶段未执行。

审批状态更新：2026-11-01T19:32:16.659908+08:00（Asia/Shanghai）；本次仅关闭保护例外审批，原11失败、103正式断言未重跑及12条JSON组件Console错误等边界不变。
