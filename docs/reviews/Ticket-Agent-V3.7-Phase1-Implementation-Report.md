# Ticket Agent V3.7 阶段1实施报告

日期：2026-11-01（Asia/Shanghai）。阶段范围：用户端文案与技术信息分层；不实施阶段2–7。

## 1. 目标、起始状态与结论

目标：普通用户以出行咨询、演示订单和示例政策为主；技术诊断在开发者端查看；测试控制台独立保留。保留演示数据、非真实出票/扣款、失败及费用边界。

开始前完整重读PROJECT_STATUS和阶段0报告。现场分支为feat/ticket-agent-v36-stabilization，HEAD为139cdbe2fca8c7249847f245cffef1ed0545dd36；只有既有未跟踪PROJECT_STATUS.md及阶段0审查报告，没有其他修改。两份文档哈希与阶段0最终核验一致，未切换分支、恢复或清理文件。

验收结论：**阶段1实现与隔离离线验收完成；真实浏览器视觉验收未完成**。最终完整pytest为1098 passed / 11 failed / 1 skipped，另199子测试通过。与同环境修改前比较，新增6项通过、2个通过子项，失败和skip的完整ID集合完全相同，没有新增回归；不宣布全仓全绿。

## 2. 修改文件与原因

| 文件 | 修改原因及范围 |
|---|---|
| web/app.py | 用户/开发者工作空间导航显示名；模型选择收进高级折叠区；简化侧栏、页面标题及页脚。原选项值、默认选择表达式、session_state、路由和控件key保留 |
| web/conversation.py | 简化欢迎/来源/费用/加载/错误/确认说明；普通用户只显示进度、政策原文和可核对参数；原始诊断引导至开发者端；保留执行与授权调用 |
| web/presentation.py | 车次卡显示演示来源；订单卡标注演示订单及非真实支付；政策卡说明项目示例来源；不改返回数据或订单状态 |
| web/demo.py | 快速体验文案；去除主流程里的数据库/Trace/工具函数名；保留原演示阶段、Agent消息和模拟支付按钮 |
| web/developer_workspace.py | 明确只读诊断职责；同一选中运行下展示完整政策、追问、错误记录；原始事件、审计及LangSmith面板保留 |
| web/user_copy.py（新增） | 展示层中文参数、事件提示、阶段文案和错误说明；不更改原始事件/参数/模型回复或执行判断 |
| tests/test_phase1_user_copy.py（新增） | 六项离线交互/边界验收，含两项费用说明子测试；不修改旧测试、不新增skip/xfail |
| PROJECT_STATUS.md | 记录阶段1实际进展、测试/证据、未解决问题及后续待确认范围 |
| 本报告 | 保存前后对比、失败历史、契约落实及阶段边界 |

新建运行产物只在artifacts/runtime/v37-phase1-20261101/；原始回归、B快照、阶段0报告及历史Trace不覆盖。

## 3. 用户可见文字及信息分层

| 位置 | 修改前 | 修改后 |
|---|---|---|
| 主导航 | Agent 用户端 / Agent 开发者端 / 测试控制台 | 用户工作空间 / 开发者工作空间 / 测试控制台；内部仍为出行助手/开发者工作台/测试工作台 |
| 欢迎说明 | 工具调用、Trace、缺失字段等技术描述 | 查车票、问政策、查看订单；演示数据和示例政策，不提供真实出票 |
| 模型选项 | 直接占据侧栏主区域 | 收在“模型设置（高级）”；Legacy Mock/LangChain Mock/DeepSeek Live/Qwen选项值及选择逻辑不变 |
| 车次卡 | 虚构票务 | 演示数据 · 不真实出票；未知价格/余票仍保持未提供 |
| 订单卡 | 模拟订单、支付/退款状态 | 演示订单；仅模拟订单和支付状态，不真实出票、扣款或退款；原状态值不变 |
| 政策 | run_id、检索模式/版本/分数、进入模型上下文、事件编号和完整JSON | 用户保留编号、标题、原文、示例来源及“找到条款不等于回答已验证”；详细记录在开发者端 |
| 失败政策折叠标题 | 原技术状态标题 | 明确“政策检索失败”或“查询未确认成功”，不能用普通参考政策标题掩盖失败 |
| 确认卡 | 原始JSON参数、模拟数据库说明 | 中文车次/日期/席别/乘客等真实参数值；保留非真实交易说明。原确认/取消按钮及执行逻辑不变 |
| 运行区域 | 原始Trace、工具名/耗时、生命周期及JSON | 五阶段业务进度、历史选择和“在开发者端查看此运行”；运行ID保留为DOM关联元数据，不作可见主文案 |
| 追问 | 生成来源、回退代码、run_id、JSON | 后续问题及点击行为说明；在线发送、辅助追问和点击新消息的费用含义明确 |
| 在线费用 | 发送会产生API费用 | 主问题收费；回答后整理追问可能额外一次模型服务；点击追问作为新消息计费，仅属于当前会话服务；不改授权实现 |
| 错误 | 内部错误类别、HTTP/配置变量等诊断 | 超时结果可能未知、服务不可用、余额或权限问题等可操作提示；未知错误不回显内部细节，不包装为成功 |
| 快速演示 | 60秒、离线规则模型/模拟数据库、工具序列 | 四步快速体验，独立演示会话，无模型费用，不真实出票/扣款；显示保存的对话 |

保留少量明确标识的高级/开发者折叠说明（如服务不可用时不自动回落Mock、改签处理详情），不把它们作为普通主流程内容。演示支付、演示改签等必要安全措辞没有机械删除。原始模型回复不做事后字符串替换，避免改写真实回复证据。

## 4. 五项产品契约及阶段外边界

| 契约 | 落实情况 |
|---|---|
| 客户语言与演示边界 | 页面、车次、订单、政策、支付附近均保留来源与限制，不声称12306实时、真实锁座/出票/扣款 |
| Live授权按Provider/会话隔离 | 仅补费用含义；_live_request_allowed、allow_live返回方式和发送授权调用不变。没有恢复checkbox、增加默认授权或移除下层确认；历史授权契约问题仍保留 |
| 显式模型配置优先 | 已记录为确认的产品契约；本阶段按要求不改choices/qwen_ready/initial/selection及模型构建，当前优先级差异仍待后续明确任务解决 |
| 改签后退票 | P01/P02/P03及业务代码不变，界面继续明确改签后不支持退票，不按文案任务修改政策 |
| 两主空间与独立测试控制台 | 仅更改显示文案；原三个内部路由及测试入口、七维度统计、正式数据读取继续保留 |

未修改target/、config.py、data/、web/runtime.py、web/evidence.py、web/langsmith_panel.py、web/design.css、web/scroll_bridge.py。未添加二维码、支付回调、四面板、数据源抽象、Override配置或Grid/Flex布局。

## 5. 控件、会话和旧断言影响

AST核查五个已有修改源码：58个显式key表达式完全一致（app 5、conversation 37、demo 8、developer_workspace 8）。未新增或改名session_state变量；导航只用format_func更改显示名，底层取值和页面判定不变。

发送按钮、user_message、provider_selection、workspace_mode、user_run_<sid>、确认/取消按钮等关键标识保留。体验入口由“开始60秒演示”改为“开始快速体验”，仍用demo_start；政策折叠标题和部分说明没有持久业务含义，但原折叠展开状态可能在界面更新时重置。

旧断言与新展示的处理：

- 运行摘要仍有完整data-run-id关联，但不再把ID显示给普通用户；保留原运行选择和跨会话隔离断言。
- 查票卡片的data-source-tool记录实际来源，用户读中文说明，旧AppTest仍可验证query_tickets来源。
- _policy_panel保留诊断组件默认能力；用户页面显式technical=False，开发者technical=True。旧独立组件测试仍能检查版本/分数/未知结论，用户主界面不显示这些字段。
- 服务不可用主提示使用客户语言；旧“不自动切换Mock”说明保留在开发者诊断折叠区，而非删除安全语义。
- 原确认按钮文字未随意改名，避免无key控件身份变化；确认卡标题和参数展示改为中文。
- 原11项失败测试完整保留，不修改103条正式断言、不改旧UI测试、不增加skip/xfail。

## 6. 隔离方式、命令和实际结果

隔离方式：复用scripts/regression_center.py的prepare和run_command；冻结P0 v2证据/缓存解压到本次新副本，再覆盖当前源码；关本地secrets和自动追踪、移除真实凭据、socket只允许loopback；DB/Trace/用量在副本中。没有在原正式目录执行pytest。为避免系统pytest-of-W无权限，后续批次显式设置独立TEMP/TMP及PYTEST_ADDOPTS=--basetemp=<批次>/temp/pytest，不清理系统目录。

执行命令模板（解释器为项目.venv-v35 Python3.12.14；cwd为对应snapshot/ticket-agent）：

    python -B scripts/v37_tests.py --out <副本>/artifacts/runtime/phase1-results-r2
    python -B scripts/v37_tests.py --case tests/test_phase1_user_copy.py --out <副本>/artifacts/runtime/phase1-focused
    python -B scripts/v37_tests.py --out <副本>/artifacts/runtime/phase1-full

完整进程参数、开始/结束时间、退出码、JUnit、pytest.log、逐项结果均在各副本产物中。脚本中的real_api_requests=0不能单独当作网络证明；应与隔离环境、socket守卫及用量来源一起理解。

| 批次 | Passed | Failed | Skipped | 子测试 | 说明 |
|---|---:|---:|---:|---|---|
| 修改前baseline首跑 | 1056 | 47 | 1 | 197通过 | 含原11失败及36项pytest临时目录setup权限错误，原记录保留 |
| 修改前baseline临时目录隔离r2 | 1092 | 11 | 1 | 197通过 | 与阶段0可关联历史基线一致；不是将旧1102/8的归因坐实 |
| candidate-r1阶段1专项 | 5 | 1 | 0 | 2通过 | 确认卡乘客列表被st.write渲染为JSON；已改为中文列表文字，参数原件不变 |
| candidate-r2完整 | 1093 | 16 | 1 | 199通过 | 新增5项展示/兼容失败；未删测试，逐项修正，原件保留 |
| candidate-r3最终完整 | 1098 | 11 | 1 | 199通过、0失败 | 2026-11-01 00:27:16–00:29:22 +08:00；失败/skip集合与baseline-r2完全一致 |

candidate-r2新增5项：LiveProviderUITests缺服务说明；ExecutionTraceTests完整运行ID；ScrollLayoutUITests跨会话ID；PolicyChatIntegrationTests失败政策标题/诊断字段；V33AppTests查票来源。修正包括失败标题必须可见、完整关联元数据、原诊断组件能力及折叠服务说明，没有更改旧断言。

新增六项验收覆盖：切页不初始化Agent/不串会话；查询及政策来源与用户无原始JSON；开发者读取原记录不重发或改写Trace；确认卡准确展示参数且渲染不执行；两Provider主问题/额外追问费用说明且不改原授权形式；失败不变成功、卡片演示边界。

最终同批相关结果：阶段1新增6项通过；LangSmith面板11项通过；LangSmith读取核验27项通过；多轮授权12项通过。这些已经包含在1098项内，不另相加。唯一skip仍为无人类批准P2场景的test_no_approved_p2_scenarios，不是本阶段新增skip。

## 7. 保护与证据索引

独立根目录：`artifacts/runtime/v37-phase1-20261101/`。

- originals/：本次修改前相关源码及PROJECT_STATUS的字节副本。
- protected-before.json：阶段0的1892文件保护清单，本次开始前已核对一致。
- baseline/summary.json、summary-r2.json及snapshot/ticket-agent/artifacts/runtime/phase1-results*：修改前实际结果。
- candidate-r1/summary.json及phase1-focused：专项首轮及问题记录。
- candidate-r2/summary.json及phase1-full：中间完整回归及5个新增失败。
- candidate-r3/summary.json及snapshot/ticket-agent/artifacts/runtime/phase1-full/：最终完整结果，含results.json、junit.xml和pytest.log。
- 各批source-manifest.json、preparation.json：源码清单及冻结包/夹具指纹。
- scope-checks.json：控件key、关键执行函数、模型选择表达式和1892文件哈希核查。
- comparison.json：修改前后计数、完整失败/skip集合差分及相关专项结果。
- copy-inventory.json：中间轮原/新字符串清单；copy-inventory-final.json：最终清单。配合git diff阅读，不将代码常量差异全部误作可见文案。
- verification.json：最终Git、保护清单、源码对应和失败/skip集合差分。

阶段0报告不修改；103目录及B快照、七维度DIMENSIONS、全部旧测试和P2、历史证据/账本不修改。1892清单不含全部历史运行数据库，不扩展为全盘历史一致性声明。

最终核查：1892文件0变化/0缺失，B manifest七份文件全部匹配，103条目录完整；最终被测源码与当前代码清单0差异。git diff --check退出0、暂存区为空；5个已有Web源码修改，新增展示模块/测试及本报告，PROJECT_STATUS为原未跟踪文件的授权增量更新。既有阶段0报告SHA不变。核查日志中的LF/CRLF提示是Git换行规范提示，不是空白检查失败。

## 8. 未完成事项与风险

- 真实浏览器未验收：Edge存在，但项目上下文解析playwright和playwright-core均为MODULE_NOT_FOUND。本次没有联网安装、启动浏览器实例或生成截图；1600×1100/390×844浅深四规格、实际DOM、滚动与软键盘均未验证。
- 原11项Live默认模型/费用checkbox/历史面板等契约失败不在本阶段授权范围内修复；不得据本报告宣布全仓全绿。
- 原模型回复可能包含原有技术用语，本阶段未改Prompt或事后重写回复；失败诊断原件保留在原审计和开发者端。
- 简化/收起技术信息可能影响用户对诊断入口的发现；已保留每次处理对应的开发者按钮，未验证真实浏览器中的布局和可访问性。
- 当前默认模型逻辑与“显式配置优先”的目标差异仍在；本阶段不修改Provider选择，也不声称该契约已经编码完成。
- 原始高级政策联网选项仍在用户端折叠区，授权方式保持原样，不能为信息分层而默认开放真实Embedding。
- 新展示模块依赖既有展示组件，不增加Provider/业务层；新的开发者政策/追问诊断仅按选中运行读取记录，已有离线测试检查不改写Trace。

## 9. 阶段验收和停止

12项阶段要求的离线证据已建立：主流程中文与来源清晰、非真实交易边界保留、两个主空间分工与独立测试入口保留、原业务/授权/Provider逻辑未改、103正式用例/B证据和1892保护文件不改、LangSmith能力保留、相关测试实际运行、未实施阶段2–7。58个显式控件key及关键调用/模型选择表达式核查一致。完整旧失败仍11项，因此阶段完成不代表修复全部历史问题。

真实浏览器截图、DOM、可访问性和四规格视觉结论均未完成；本报告只确认实现及离线交互/回归验收，不宣称完整UI视觉验收通过。未联网、未调用真实API，未Commit/Push/Merge。HEAD仍为139cdbe2fca8c7249847f245cffef1ed0545dd36，修改留在工作区。

下一阶段只建议在用户确认后讨论阶段2演示二维码的展示及确认语义；二维码内容不等于扫码支付成功，不新增真实支付。浏览器依赖补齐与四规格验证的范围也需明确。本阶段交付后停止，不自动进入阶段2。
