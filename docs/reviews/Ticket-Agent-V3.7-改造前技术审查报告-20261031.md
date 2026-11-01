# Ticket Agent V3.7 改造前技术审查报告

审查日期：2026-10-31，Asia/Shanghai。范围：阶段0；不实施阶段1–7。

## 1. 审查结论

现有 Python / Streamlit / 双 Agent 引擎 / SQLite / RAG / 事件审计架构适合渐进改造，无需重写。三项核心决策方向正确，但都需要补足边界：固定 Fixture 必须覆盖业务状态与时钟；Developer Override 必须进入实际执行器和权限检查；布局必须基于 Streamlit 真实包裹层实现，不能仅移动输入框或删固定高度。

队长附件不能照单执行：其中的旧目录、1102/8基线、输入框位置、费用勾选框、数据“永远有票”等描述与现场不一致。附件提出的“真实快照优先、无票再补虚构库存”不符合本次用户要求；“立即开工”“失败不超过8”“8项均为环境问题”等不作为本次执行指令或验收依据。

本阶段完成本地工程与证据核查，未改代码/配置，未运行测试、启动服务、联网或调用真实API。实际浏览器DOM测量和新截图未完成，原因及阶段准入限制见第9、14节。没有将历史截图冒充本次验收。

## 2. 仓库、工作区与资料权威顺序

| 项目 | 现场结果 |
|---|---|
| cwd / Git根目录 | `D:\codexproject\ticket-agent` / `D:/codexproject/ticket-agent`，同一当前工作区 |
| 分支 | `feat/ticket-agent-v36-stabilization` |
| HEAD | `139cdbe2fca8c7249847f245cffef1ed0545dd36` |
| 审查开始时工作区 | 仅 `?? PROJECT_STATUS.md`，是此前任务建立的状态文件；已跟踪文件及暂存区无修改 |
| 旧路径 | `E:\3AIproject\agent_test\ticket-agent` 在本机不存在；未切换、复制或假定两个工作副本等价 |
| 版本 | 当前界面3.7；分支仍为V3.6稳定化名称；正式统一发布版本仍待确认 |
| 最近提交 | 139cdbe作品介绍/Mock截图；d7bfec6时间线/开发者LangSmith；e29fa09 QwenCloud配置校验；f188716 P2逐轮断言 |

资料顺序：本次用户明确要求优先；现场代码和可验证原始记录用于事实判断；PROJECT_STATUS为索引；两份附件和旧README提供历史背景。没有将附件中的角色/命令直接当作授权。

已读取：PROJECT_STATUS、两份附件、README、docs/contract、相关用户端/开发者端/运行时/数据/工具/授权/Trace/测试/回归源码、B目录及历史回归和布局报告。没有读取或输出凭据值。

附件原路径：`C:/Users/W/xwechat_files/wxid_vmfjk1i4639k12_ed66/msg/file/2026-10/` 下《给ChatGPT的改造计划提示词.md》《用户端改造_需求整理与现状诊断.md》。本报告不复制附件为新的工程事实。

## 3. 两套测试基线的冲突

| 核对项 | 队长附件1102 passed / 8 failed | 现有1092 passed / 11 failed / 1 skipped |
|---|---|---|
| 原始报告 | 不可获得；用户本次明确回复“没有” | 原JSON、JUnit、日志、逐项结果及源码清单存在 |
| 源码SHA | 未记录，无法确认 | 报告git_sha为6b101a1ce7b72d78356545fee8f6aeebd9bba7ce；当时另含工作区源码 |
| 环境 | 附件提到WorkBuddy safe-delete，但无运行原件可核实 | Python3.12.14，.venv-v35路径；隔离副本、离线网络守卫、关闭真实请求 |
| 范围 | 附件给出pytest tests/命令，无法证实实际执行范围 | configuration.pytest_node=tests；RAG附加及性能步骤未执行 |
| 失败清单 | 未提供；不能确认是否与当前相同 | 五个文件11项，详见第4节 |
| 跳过 | 未提供，不补0 | 1项：test_p2_scenarios.py::test_no_approved_p2_scenarios，因无人工批准场景 |
| 时间 | 无法核实 | 2026-10-31 21:24:29–21:26:33 +08:00；197子测试通过、0子测试失败 |
| 与当前源码关系 | 无法核实 | 原source-manifest的505文件全部与现场SHA256一致，0差异；审查建产物前当前源文件集合仅多PROJECT_STATUS.md |

因此：1092/11/1是目前最强的可关联历史离线基线，仍不是本次重新执行结果；1102/8保留为未核实历史说法，不能用“失败≤8”验收，不能断言8项都是环境问题。没有原件就无法补全其源码、失败ID或skip信息，重跑当前代码也不能恢复那次历史事实。

证据：`artifacts/runtime/commit-current-20261031-212140/regression-report.json`；内部目录 `regression/20261031-212341-821bacb9/` 的source-manifest.json、results.json、junit.xml、pytest.log。

报告原源码指纹：`7991993de4b896e08e3c6cd29ee094e27117105ae515f224e74b08524e1c6491`；测试集指纹：`fdfc27d0cd78c32889042e4f39cc23838cf5711d4fb54a743ebdf52a168be0c5`。本次逐文件比对不等于重现运行环境或重新运行测试。

另有selected-report：158通过、0失败、1跳过、62子测试通过；使用排除六个前端文件的选择性源码，不能替代最终完整回归。不能将它与1092相加。

本次不重跑完整测试：源文件已能对应现存完整报告，本阶段没有实现修改；重跑无法解决1102/8缺失的历史归属。已审查测试副作用：build_db、临时目录清理、SQLite状态写入、Trace/JSONL追加、AppTest会话写盘等，直接在原工作区运行并非纯只读。

后续若获准复验，优先现有regression_center的prepare机制：冻结P0 v2夹具+当前源码覆盖到独立副本、独立DB/Trace/用量目录、清除进程凭据、禁本地secrets、外部socket阻断、全新产物目录。须事先核实其保护范围、旧包解压路径和网络守卫；不直接使用会在原项目执行pytest的v37_tests作为完整隔离替代。

## 4. 当前11项失败：证据和处理方向

以下是静态根因定位与契约冲突分类，不是已实施修复或重测结论。

| # | 测试方法（省略公共test_前缀） | 原失败与现场链路 | 后续处理 |
|---|---|---|---|
| 1 | deepseek_direct_send：configured_online_default_is_deepseek_and_render_never_calls_agent | 预期DeepSeek，实际Qwen；app.py存在百炼配置时优先Qwen | 明确显式Provider与自动探测的优先级；独立保留“渲染不调用模型”判据 |
| 2 | deepseek_direct_send：direct_send_permission_is_session_and_provider_specific | _live_request_allowed仅检查live和compose sid，测试预期Qwen或lab不直接授权 | 明确mode/provider/sid作用域和费用确认，不靠旧checkbox残值；下层写确认不能放宽 |
| 3 | deepseek_direct_send：qwen_still_requires_its_original_checkbox | KeyError user_allow_live，当前composer已无该checkbox | 当前任务及附件要求费用确认，但当前实现是费用caption+主动发送；先定产品契约，再修实现或经明确范围迁移A端UI判据 |
| 4 | followups_continuous：qwen_ten_clicks_survive_timeout_and_saved_replay | 在访问user_allow_live时提前失败，未走完10轮场景 | 修入口前提后重验超时回退、连续性和只读回放；不能据此称追问算法已坏或已通过 |
| 5 | followups_mvp：qwen_ui_consent_automatically_includes_followups_offline | 同样提前找不到user_allow_live | 确认主请求授权是否包含辅助追问及费用告知，再测生成次数和回退 |
| 6 | qwen_langsmith_ui：empty_qwen_run_has_a_clear_reason_and_disabled_export | 用户页未出现原LangSmith提示；相关面板已移开发者端 | 新位置验证“无记录不导出”，不把缺提示自动认定为安全守卫失败 |
| 7 | qwen_langsmith_ui：explicit_history_selection_is_preserved_and_model_is_explained | 测试初始变量deep实际受Qwen默认值影响；最终DeepSeek提示断言失败 | 分开测试默认配置与历史会话显示；保持来源说明和真实会话绑定 |
| 8 | qwen_langsmith_ui：live_fee_consent_does_not_follow_a_different_provider | StopIteration，查找确认checkbox失败 | 定义费用同意的Provider/会话隔离；不得只删此安全场景 |
| 9 | qwen_langsmith_ui：qwen_panel_rejects_another_provider_record_without_export | 用户页不再显示原面板来源错误 | 在开发者页和export_last下层分别验证跨Provider拒绝及无远端POST |
| 10 | qwen_langsmith_ui：qwen_stays_active_after_opening_integration_center | sid/provider断言已走过，失败在旧确认checkbox文案 | 保留切页不串会话的功能断言，另按明确契约验证授权控件 |
| 11 | unlimited_live_ui：bailian_user | 在主动点击发送后，离线SDK载荷为2而预期0；并非初次渲染时产生2次请求 | 新发送逻辑与旧费用前提冲突；用MockTransport分开断言渲染/授权/发送/追问次数，不据此宣称发生真实API调用 |

总体处理：先固定契约，保留原失败原件，逐项修复/复验；不得使用xfail、跳过或只看总失败数掩盖新增回归。103正式用例断言不动；A端UI测试若需随新契约迁移，必须列清旧/新前提及理由，不将所有失败批量认作过时。

## 5. 103条正式用例、七维度与保护办法

现场case_catalog为103条：功能准确性15、工具调用25、RAG15、多轮12、安全18、边界12、性能6。

B manifest的7份文件全部通过其保存SHA256核对。直接读取原记录得到：Legacy101执行/101通过/0失败，另X17/X18引擎不适用；LangChain100执行/100通过/0失败，另X15/X16/T19不适用。它们是2026-10-20、代码0af2712276258fee02573da33688a836738814c6的B独立Mock快照，没有在当前代码重新执行。201是执行次数，不是201条不同用例；不适用不是pytest skip。

相关断言已经检查：must_call、must_not_call、args/args_last、调用顺序、must_call_ok、reply_contains/禁止片段、引用、stop、工具结果来源、耗时、异常。F06/F10/M03/M08等依赖购付退及多轮状态；X06固定本人联系人；日期使用相对日期宏；E03/E11要求+30天/过去日期无结果且不出现G73，X10禁止编造G9999。未发现要求真实查询必须返回某个G7301/G101成功车次的目录断言，但不能据此忽略底层种子车次、路线及原测试夹具依赖。

七维度由web/evidence.py的DIMENSIONS定义；summary的通过率分母是passed+failed，skipped/not_applicable/not_verified/indeterminate/missing分别记录；competition_view复用这些适配函数。变异矩阵另有grain及seven_dimensions=False，不应混入正式通过率。formal_results要求batch SHA/provider/mode，现有格式没有完整Developer配置身份，需另设计自定义结果而不能冒用B正式结果。

保护方案：

1. 保留B目录及全部正式expect/断言字节，阶段前后核对manifest和哈希；不重写历史结果。
2. 建立版本化Baseline Profile，固定Prompt模板、工具集、权限基线、引擎、Fixture版本、业务时钟锚点、政策路径/哈希、RAG模式和变异默认值；当前Baseline须记录新SHA，不冒充B旧SHA。
3. 正式执行入口强制Baseline，不能读取Developer Override；通过函数调用身份/专用进程落实，不能仅用页面隐藏开关或“pytest时设置环境变量”。
4. Fixture覆盖inventory、用户、初始订单/锁座状态、价格、库存、热点售罄、政策和相对时钟。每案例独立数据库；缺Fixture报错；测试全程禁外网，无快照/实时/虚构补票回退。
5. 正式Baseline、Developer自定义评估、真实数据/真实模型验证使用不同batch/source/profile身份、报告与目录；历史七维度界面和DIMENSIONS不改。

注意：case_catalog是原用例的无损目录和expect证据，不等于完整独立B执行器源码。本仓库A pytest/验证器不能自动获得“B正式重跑”身份；后续需确认实际B执行入口及外部断言包，缺失时明确阻塞而不重造评分器。

## 6. 数据源决策的兼容性审查

当前链路：Agent → tools.dispatch参数校验/事件 → HTTP Mock或_call_local → mock_core.query_tickets → SQLite inventory。锁座、订单、退票、改签都依赖同一inventory行；_conn在缺DB时会build_db，访问时还会回收过期锁座。因此“查询”也可能写数据库，不能当作原库只读浏览接口。

data/seed.py使用固定随机种子20261012、以config.today()起7天、30高铁+5机票线路生成2100行；热点近期二等座刻意置0，商务/公务可能0。附件“永远有票”不成立。随机数固定不等于绝对日期/业务状态可复现，现有build_db也不是已经版本化的严格Fixture。

目前没有target/train_source.py、TICKET_TEST_MODE正式分流或真实12306快照路径实现。

推荐落地约束：

- 测试模式始终加载固定Fixture；不要先查真实快照。模式选择要fail-closed，不能因DB缺失或未知模式自动build_db。
- 用户模式只读真实快照，显示来源、抓取时间、覆盖日期、适用车次/席别及过期/不可用状态；缺覆盖或失效明确提示。只有明确启用并获授权才可实时查询，失败不伪造库存。
- 保持tools公开Schema和现有字段兼容；来源元数据优先用工具实际结果的兼容扩展和独立事件承载，不改公共Trace十字段。
- 查询来源与库存/锁座写入必须一致。真实余票只用于展示，不是本地锁座成功的真实售票依据。真实查询结果若映射到演示订单，应使用独立演示状态、明确数据源关联及“未真实出票”含义，不能把本地扣库存说成12306锁座。
- 铁路数据源不能覆盖机票用例；机票无真实源时明确不可用，Fixture仍覆盖正式机票场景。
- “近10天”需明确未来可查询日期窗口还是过去留存；快照不能穿越查询当时的可售日期。余票数、票价缺失/未知各自保留未知，不能把“有”推算成具体库存。

仅将mock_core.query_tickets替换为train_source.query_tickets不足以完成本决策；这是阶段7的主要架构障碍。当前不研究或访问外部接口，也不认定附件提供的12306地址/抓取策略已验证。

## 7. Baseline / Developer Override的实现审查

已有基础：Agent构造器可接system_prompt、tool_names、model；LangChain使用create_agent；Conversation.send统一封装运行/保存；scoped用CALL_LOCK串行临时替换全局config/env并finally恢复；run_events和审计sidecar已有run_id/session_id/provider/model。

实际缺口：

- 开发者页当前只读：提示词/Schema/权限/规则关联展示，没有保存生效的编辑器。工作台提供独立调试和三栏证据，不是可写配置台。
- Conversation._send只在self.agent is None时构建Agent；保存JSON不会更新已构建graph/模型。_values只覆盖现有Provider/model/RAG等字段，未传Developer Prompt/白名单/权限/temperature。
- Legacy路径没有与LangChain同等的显式tool_names执行白名单应用；仅限制提供给模型的Schema不足以阻止实际dispatch，必须校验执行边界。
- LangChain只读模式会把传入Prompt替换为READ_ONLY_PROMPT，之后还追加日期/业务/安全说明；模板SHA不能冒充最终发送Prompt的SHA。
- 模型构造未接Developer temperature；不能把UI滑块当作生效配置。Mock应明确“不适用/不影响规则输出”，不能靠Mock回答风格验证真实模型temperature。
- InMemorySaver保存模型会话；session_store仅存少量settings和run引用，恢复明确read_only，不恢复模型checkpoint或旧操作授权，也不含override。
- 已有事件包含实际system_prompt内容，但未统一记录所要求的prompt_sha256/tool_whitelist/write_policy/temperature/config_source配置快照。

推荐设计（尚未实现）：保存经校验的不可变配置版本与revision/hash；下一轮开始冻结EffectiveConfig，在CALL_LOCK内创建/更新执行器，执行中保存只作用于后续轮。明确旧模型上下文的保留/迁移策略，禁止重放已执行写操作；有待确认提案时不得静默换权限/工具配置，应保持提案版本或取消后重新提出。

权限只能在系统安全上限内收紧：有效权限=Baseline允许范围∩Provider/模式安全范围∩Developer白名单/策略∩当前身份/当轮授权/操作确认。附件“自动执行”不能成为跳过身份及用户确认的路径；本阶段不批准该选项。

每run新增sidecar/config事件：session_id、run_id、最终生效prompt_sha256（含动态追加内容）、模板版本/哈希、实际tool_whitelist、write_policy、实际model、temperature（含不适用）、config_source、config_revision、Baseline/Fixture/政策身份。保留公共十字段/工具五字段，通过run_id关联，不向旧Trace补写新字段。

恢复须区分只读回放与显式新执行：回放读取当时快照；继续执行重新加载当前已批准配置并重新授权，不把历史确认恢复成可执行权限。自定义评估报告独立于正式Baseline，不能仅用owner=A代替配置来源分类。

## 8. 用户端现状与目标差距

| 目标 | 现场现状 | 改造边界 |
|---|---|---|
| 客户文案 | 模拟/沙箱/历史质量提示散落在conversation/presentation/demo/app | 可简化主流程语言，但真实数据尚未接入，不能写“车次价格来自12306实时数据”；保留简洁数据来源、示例政策和非真实支付说明 |
| 四独立面板 | QUICK_PROMPTS填充提问，尚非完整查询/政策/订单/计算交互 | 统一走会话执行与审计；查询订单仍执行身份检查；纯计算器可不调用模型 |
| 支付二维码 | 已有pay_order模拟状态变更，无二维码模块 | 本地二维码仅编码数据不会自动通知后台；扫码不等于付款。应设计演示确认按钮或受控本地回调，保留鉴权/单次确认/幂等，标注不会真实扣款 |
| 退票选择 | cancel_order按order_id，已有本人订单校验 | UI先按车次筛本人订单、多候选选定order_id再确认；不改公开工具Schema，也不允许车次号直接退掉多笔订单 |
| 改签 | 有target.reschedule的preview/confirm，用户需手填订单/目标，直接走业务函数 | 优先订单选择/差价预览/友好确认；补运行事件和权限关联，不冒充模型工具调用 |
| 改签后退票 | P01/P02/P03及mock_core明确禁止 | 附件建议允许退票与当前政策冲突，不能当普通Bug修复；Baseline保留，产品规则变更须独立版本及明确确认，不能改原政策/成绩 |
| 行李费用 | 已有target.baggage纯函数和用户端折叠表单 | 复用计算器，移到功能区域；保持P06示例语义 |
| 双栏 | 有记录后显示聊天+运行轨迹右栏；首屏单栏 | 右栏需改客户信息与功能；技术Trace移开发者端，保留必要业务状态 |
| 配置/权限 | 用户页有RAG和Embedding开关，开发者页只读 | 移配置时仍保留明确费用许可和下一轮生效证据，不能移动后默认开放联网 |
| 最终两个空间 | 当前三个：用户/开发者/测试 | 建议保留测试控制台为独立评价入口，附属开发者或顶级导航待确认；不能为“两空间”删除正式评价能力 |

政策、费用与身份语义不能只靠文案改名。源码“改签后不退”的事实不支持直接写“按真实铁路规则可退”；本次不联网研究或宣称真实规则。

## 9. Streamlit版本、DOM实现及浏览器条件

- 本机 `.venv-v35` 实际解释器3.12.14；site-packages元数据及本地实现为Streamlit1.65.0，存在container(height等布局参数)实现。
- 当前conversation.py:636–648仍使用560/430；但_column_body里顺序是历史滚动container结束→确认卡→_composer，**输入框已在历史滚动容器之外**。附件“输入框在容器内”不准确。
- design.css:99–102对stLayoutWrapper及st-key-user_chat_scroll设置overflow和clamp上限；scroll_bridge.py按innerHeight/顶部/输入框测高，但仍有240最小高度和560上限，并直接调整carrier的height/min-height/flex-basis。它是局部高度修补，尚非完整视口Grid布局。
- 当前摘要条使用sticky；窄屏CSS将含user_rail的horizontal block纵排。高级设置、演示、更多工具等仍能撑高外层，因此不能仅从局部滚动认定整页永不滚动。
- 历史《对话滚动架构报告》记录过实际CDP尺寸测量、截图和922项回归，是历史证据；其自身描述和附件存在差异，不能代替当前页面现场测量。
- 本机Edge可执行文件存在：`C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`。常用8501/8502/8503/9222端口未观察到监听。浏览器工具清单提供IAB，未提供可直接控制的Edge DOM连接。
- 项目脚本上下文resolve playwright-core得到MODULE_NOT_FOUND；node_repl尝试导入playwright/playwright-core未成功，其中具体报错为ESM default export错误，**不据此认定整台机器绝无Playwright包**。未安装依赖或尝试联网修复。
- 因本阶段无UI改动、无运行中的隔离实例，未启动应用、测量实时DOM或生成截图。不能宣称本次满足四规格UI验收。后续UI阶段验收前必须补齐本地Playwright+Edge可运行链及隔离Mock实例；此项不以静态审查替代。

布局建议：在用户工作区真实Streamlit包裹层上建立可用视口高度Grid；聊天列Flex column且min-height:0；history flex:1/min-height:0/overflow-y:auto；confirmation/composer位于history之外，flex:0 0 auto；外层overflow:hidden。右栏独立可滚/折叠，不能挤走输入区。应移除与新布局冲突的固定height、clamp及bridge写height逻辑，同时保留位置记忆/新消息提示。

390×844采用单栏，对话优先，功能进入独立可展开区；使用动态视口和safe-area处理软键盘，展开功能时仍有可到达的滚动区域，不以整页overflow:hidden把功能裁掉。禁止把sticky当唯一方案，也不能假定Python的container/columns就等于目标DOM。

未来必须用1600×1100、390×844的浅/深四种组合测：外层与history的scrollHeight/clientHeight、composer边界、滚动前后位置、长对话、待确认卡、错误、工具结果、功能展开、sidebar折叠及rerun。截图只是证据之一，需同时保留DOM尺寸与行为数据；桌面缩放不能冒充移动键盘验证。

## 10. 分阶段实际开发顺序及准入

严格保持用户规定的0→1→2→3→4→5→6→7，不擅自换阶段或跨阶段实现。

| 阶段 | 目标与必要前置 | 核心验收 |
|---|---|---|
| 0 | 本报告、源码/正式数据保护清单、基线冲突与产品契约清单 | 已有证据如实归属；1102/8及实时DOM缺口保持未知；等待用户确认 |
| 1 | 客户语言及技术信息分层；先约定费用确认/来源标注/两空间导航边界 | 不声称未接入的真实余票；不修改正式expect/业务Prompt/政策；针对控件断言影响逐项记录 |
| 2 | 演示二维码与支付状态展示 | 扫码/点击/确认的真实行为明确；无真实扣款、无未授权写入；重复确认幂等 |
| 3 | 订单选择式退票/改签、预览及确认 | 先查本人订单，不以车次绕过order_id/身份；P01规则冲突先确认，Baseline不变 |
| 4 | 四独立面板、行李及改签入口 | 复用既有会话/业务/审计；纯计算与模型调用分开；旧八工具Schema不变 |
| 5 | Grid/Flex视口布局，功能与聊天分离 | Playwright+Edge四规格、长对话与状态组合、实际DOM和截图验收 |
| 6 | Baseline与Developer Override执行隔离 | 下一轮生效的配置快照；白名单执行拦截；权限只能收紧；自定义报告不混正式 |
| 7 | Fixture/真实快照数据源及后续授权实时查询 | 先完成Baseline+Fixture离线可复现，再评估真实数据；无缓存明确不可用，无偷偷回落或默认联网 |

每阶段结束更新PROJECT_STATUS并交付目标、文件/原因、实现、命令/实际结果、差异、Trace/截图、风险和授权需求，然后停止等待确认。不能用“失败总数没增加”放过失败用例换人、新skip或被删用例。

## 11. 本阶段交付、证据与修改范围

1. 目标：改造前技术审查与基线建立；实际实现新功能：无。
2. 修改文件：新增本报告；增量更新PROJECT_STATUS；新增独立审查产物 `artifacts/runtime/v37-phase0-20261031-review/`。不修改源码、配置、测试、正式数据或旧证据。
3. 文件原因：本报告保存完整方案评估；状态文件保存当前阶段、基线对应关系、缺口和下一步；独立JSON保存可核查哈希和目录/用例统计。
4. 本次测试命令：无。只执行Git/文本读取、标准库JSON/AST分析及SHA256比较；未导入web.app/Agent/config执行应用。没有pytest通过数可报告。
5. 本次Passed/Failed/Skipped：未执行，不填造0通过；沿用可关联历史1092/11/1，197子测试通过。
6. 与原基线：无源码/测试实现变化；首次将完整505文件逐一对应，补核B快照通过/不适用数与唯一skip原因。
7. 本次Trace：无Agent执行，无新增Trace；模型/Embedding/LangSmith请求均0。
8. UI修改/截图：无；实时DOM及四规格新截图未验证。
9. 独立产物：audit.json、protected-before.json及交付核验verification.json；原源码清单和B manifest不覆盖。
10. 保护范围：B目录、docs/evidence、data/rag1000、tests、target/p2_*、target/tools.py及web/evidence.py，共1892文件建立哈希清单；不扩大为全部历史SQLite/Chroma/Trace的完整性证明。
11. 未Commit/Push/Merge，未reset/clean/stash；保留已有未跟踪PROJECT_STATUS。
12. 是否需要额外授权：本阶段不需要真实API或外网；后续阶段实施、Playwright依赖环境补齐、真实模型或12306接入按各阶段范围确认，不在本次执行。

## 12. 尚未核实与剩余风险

- 1102/8原始报告不可获得，全部运行归属信息保持未知；不能与1092/11/1做逐案差分。
- 当前实际浏览器DOM/四规格截图和软键盘行为未验证；浏览器自动化运行条件未完全就绪。
- 实际B独立执行入口/完整外部断言包未确认；目录expect与历史结果已核查，不等于本次重跑正式103。
- 费用确认、Provider默认优先级、改签后退票政策、最终两空间与测试控制台关系需确定；这些直接影响后续验收。
- 实时数据的官方接口可用性、许可边界、字段完整性、覆盖日期和限流未研究或联网验证。
- Override热切换、旧模型记忆迁移、待确认操作与配置版本绑定尚无实现，需要独立测试。
- 当前累计真实API用量/费用/余额、570条RAG人工复核、千题真实Vector/Hybrid与回答质量均未因本次审查获得新验证。
- 受保护文件清单不含全部历史运行库；本次未打开这些库或执行会改状态的业务查询。并行进程若追加日志应独立留证，不能回滚。

## 13. 可供下一阶段确认的最小产品契约

建议在阶段1范围确认时同时明确：

- 客户文案可去技术术语，但在真实数据接入前保留“演示数据/示例条款/不真实出票及扣款”的简洁来源说明，不写成12306实时服务。
- 费用授权继续按Provider/会话绑定，主请求和额外追问的费用含义明确；是否恢复显式checkbox需用户定案，本次不修改。
- 默认模型建议优先显式配置，再自动探测；具体优先级作为独立交互契约，不凭旧测试或当前代码自行裁定。
- 改签后退票先保留原Baseline政策，产品新规则另行明确，不在文案阶段改业务。
- 保留测试控制台及历史七维度能力，“两个主工作空间”不等于删除测试评价入口。

## 14. 对用户七个问题的明确回答

1. **队长方案适合当前架构吗？** 总体适合渐进实施；不能直接照抄旧路径/基线/诊断和文案。须剔除测试快照优先补票、未接入却宣称12306实时、扫码自动等于支付、自动权限绕过等不成立做法。
2. **三项核心决策有实现障碍吗？** 有但无已知不可实现障碍：数据查询与SQLite业务库存一致性、可复现时钟/政策、Legacy/LangChain权限一致性、graph/模型缓存和配置热更新、真实DOM包裹层与移动键盘是主要工作量。
3. **103条正式用例如何保护？** 原目录/expect/断言及七维度哈希锁定；固定Baseline+Fixture+时钟/政策；独立DB/输出；正式入口禁止Override和外网；保留引擎不适用与历史归属，B正式执行器缺失时不能由A冒名替代。
4. **当前11失败怎么处理？** 以1092/11/1为可关联历史基线，按第4节逐案定契约、修实现或明确迁移A端UI前提，保留原记录后隔离复验；不统一归为环境或过时，不改103断言，不以失败≤8替代质量标准。
5. **代码与需求差距是什么？** 四面板/二维码/客户信息右栏尚缺；退票改签交互繁琐且政策冲突；开发者只读且无EffectiveConfig链；无严格Fixture/真实数据源；布局有局部修补但非完整Grid视口；配置身份与报告隔离需补。
6. **推荐顺序是什么？** 保持用户0→1→2→3→4→5→6→7；先完成本报告确认和必要交互契约，每阶段独立验收停下。阶段6的Baseline隔离必须先于阶段7真实数据接入完成。
7. **阶段1具备开工条件吗？** 工程结构支持有限文案改造，**尚未无条件准入**：先确认第13节文案/费用/默认模型等范围，且UI验收前补齐隔离浏览器验证条件。现在未进入阶段1；等待用户确认，不自动开发。
