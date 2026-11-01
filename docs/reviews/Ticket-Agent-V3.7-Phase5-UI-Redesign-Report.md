# Ticket Agent V3.7 — 阶段五用户端 UI 重做报告

交付时间：2026-11-01T14:58:06+08:00（Asia/Shanghai）。先完成A归档/推送，再实施B阶段五。

**结论：阶段五实现和隔离离线验收完成，等待用户验收。完整1251 passed / 11 failed / 1 skipped / 199 subtests；新增9项通过，原11失败/唯一Skip逐ID保持，新增失败0。四规格Edge测量38/38、交互32/32、业务72/72，共142/142，72张实际截图。全仓仍有11项历史失败，不宣称全绿。**

## 1. 阶段一至四归档与Push

归档Commit `c889b082dd4bd07e3514038a69362b71dd21915c`，39个文件，`feat(ticket-agent): complete V3.7 phases 1-4`；远端origin/feat/ticket-agent-v36-stabilization经ls-remote核验为相同SHA。远端初始与139cdbe一致；正常Push，不force/rebase/改历史。阶段五代码未混入该Commit，当前阶段五不自动Commit/Push。
完整提交/排除清单与敏感信息检查见Ticket-Agent-V3.7-Pre-Phase5-Git-Archive-Report.md；runtime、账本追加、DB/会话/Trace、缓存/浏览器/截图日志按既有忽略规则保留本地，不删除。归档时工作区一度干净。首次本机代理不可用，仅单次Git命令临时http.proxy=绕过，未改持久配置。

## 2. 目标、参考与范围

image3.png未提供，用户明确答复“队长没给我”；按任务内结构图和客观验收实施，未声称复刻缺失截图。目标为真实桌面双栏、整页不滚动、聊天/右栏分别滚动、聊天外输入框、移动单栏展开相关信息、深浅主题和既有业务完整。仅UI/桥接/呈现，未开发阶段六Override或阶段七数据源。

## 3. eval-audit：实施前实际发现

读取项目原版eval-audit，用本地源码、阶段四原始截图/Trace/JUnit、阶段1.2尺寸资料审查，并在实施前输出发现；不调用远端观测API。详见skill-audit.json。

- 布局存在三套高度来源：Python430/560、CSS clamp、JS inline height/min-height/flex-basis；右栏处于文档流，确认卡在聊天滚动区之外。
- 阶段四72+24测试验证业务/入口/横向宽度，不能证明输入框稳定或页面/聊天局部滚动。
- 原发送nonce、确认、会话恢复和DB复核真实存在，移动控件可能造成会话状态竞态或重复发送；不能以UI成功文案代替实际Trace/DB。
- 迭代实测发现：欢迎页默认跳底、顶栏回调在控件创建后写会话key、缺失旧不可用提示、iframe回调随卸载失效、移动标题与展开按钮重叠、透明工具栏拦截新会话点击。均修正并保留失败证据。

## 4. write-code-eval：规则和使用边界

读取原版write-code-eval，将失败模式转为输入→预期→失败条件→证据。输入为真实浏览器尺寸/轮次/滚轮/键盘/表单，预期为像素、scrollTop、Trace次数和SQL状态；不是截图主观打分。完整规则见code-eval-spec.json；两个Skill使用记录/原SHA在skills-usage.json，未改原文件。
未采纳LLM Judge、远端Trace拉取、评分口径改造、新依赖和新标签平台：布局、次数、权限与库存可直接客观验证，且不属于本阶段。Skill没有浏览器运行器/API，本次使用已有Edge/Playwright、pytest/AppTest/SQL实现其方法。

## 5. 布局方案与父容器尺寸

新增web/user_layout.py与user_layout.css，选择器仅作用于含user_workspace的用户页，开发者/测试页继续原布局。Streamlit1.65本地API和实际DOM已核对：st.container支持height="stretch"、horizontal及原生容器；实际stLayoutWrapper父层也必须设置min-height:0和可收缩高度。
外层按100dvh/动态视觉视口约束；自有顶栏为auto行，主体为minmax(0,1fr)。主体CSS Grid为minmax(0,2.1fr)+minmax(300px,1fr)。左栏Flex column，历史wrapper flex:1 1 0/min-height:0，历史overflow-y:auto；输入框wrapper flex:0 0 auto，位于历史容器之外，未使用sticky/fixed假装固定。右栏独立overflow-y:auto，overscroll-behavior防止滚轮串到页面。
已删除Python chat_height=560/430和旧CSS clamp；bridge不再写聊天height/min-height/flex-basis。正常视口高度由CSS管理，JS只在visualViewport小于布局视口时提供键盘等场景的补充高度，并保留原显式滚动token/锚点/读者位置。全页overflow约束以真实父容器尺寸和可访问的局部滚动为前提，不是单独加overflow:hidden。

## 6. 滚动桥接与竞态修复

保留bottom/run请求和原nonce；sessionStorage key追加会话scope，避免不同会话串滚动位置；无历史的欢迎页从顶部开始。resize/visualViewport和滚动监听每次挂载先移除旧函数再绑定当前iframe函数，避免旧iframe卸载后回调不再触发；当前iframe轮询随组件销毁，不累加后台轮询。
迭代中的旧回调问题在六轮真实发送后将390×844改为390×650复现，输入框仍停留旧y；修正后四规格反复rerun、移动缩放和回切均实测通过。保留原始失败JSON，未手工设置被测scrollTop/伪造DOM。仅实际鼠标滚轮/键盘/控件操作，evaluate用于只读测量。

## 7. 顶栏、欢迎、确认卡及信息层级

顶栏提供新会话和历史会话；切换改用Streamlit on_click，在控件实例化前更新已有会话key，复用原激活/Conversation服务，不改模型选择。侧栏原导航/模型选择仍保留；移动端为自有标题给展开按钮留空，并禁止透明Streamlit顶栏覆盖自有控件的点击，保留侧栏展开按钮可点击。
欢迎区保留能力/演示来源与四快捷卡，桌面四列、手机两列；旧快速体验仍为欢迎卡片内显式入口，不在每轮对话重复。聊天流已移除“更多模拟工具”和“高级设置”；按车次退票、行李、改签归入右栏。
操作确认显示“请确认本次操作”、原始业务参数的中文描述和明确演示边界，动作参数仅在“查看技术细节”折叠code内展示；不以原始JSON作为主卡。保留原确认/取消按钮文案兼容旧断言、写操作授权/Trace/幂等。pending聊天预确认尚无工具提案时只显示原请求，不伪造工具参数。
默认单行输入及Enter提交契约不变；显式“多行输入”切换使用原生text_area，Enter换行、Ctrl+Enter/发送提交。key仍为user_message，原nonce/clear_on_submit/确认链路保持。真实浏览器验证草稿经面板rerun保留、发送一次只产生一次Agent运行。
现有模型设置继续位于全局侧栏；政策向量选项移至右栏“政策查询费用选项”，保留原key和独立联网授权，未恢复已移除Qwen费用checkbox。技术诊断仍在开发者端，未实现实时配置Override。

## 8. 右栏与业务复用

右栏按本次行程摘要、本人订单只读摘要、既有工具结果推荐车次、常用六入口、政策速查排列；无真实查询结果时明确空态，不编造车次。我的订单摘要使用原order_read_model，不当作Agent查询成功；正式查询仍经Agent.chat→query_order。阶段四状态不一致警告/禁写/诊断、支付二维码、P02、退改preview/confirm原服务保持。
手机<768px主体单栏；聊天与输入框优先，相关信息在其下方由原生toggle展开为40dvh局部滚动栏，既不挤出输入框也不要求滚动整页。动态视口与safe-area-inset-bottom已处理；本次为Edge真实390×844新上下文及650px缩放，未宣称实体手机软键盘实机验收。

## 9. 修改文件

| 文件 | 原因 |
|---|---|
| web/user_layout.py（新增） | 顶栏/会话入口、只读摘要和右栏编排，无业务写入。 |
| web/user_layout.css（新增） | 用户端视口Grid/Flex、父wrapper高度、手机展开、主题变量和遮挡修正。 |
| web/conversation.py | 重组聊天/确认/输入/右栏；多行输入与技术细节；原发送、费用、确认业务语义保持。 |
| web/scroll_bridge.py | 删除聊天高度写入；动态视口/会话scope/监听重绑和欢迎滚动。 |
| web/design.css | 移除冲突旧聊天clamp一行，其他工作区风格保持。 |
| web/user_features.py | 四快捷按钮增加布局容器；其他面板实现和key不改。 |
| web/app.py | 用户页演示边界在局部区域保留，避免页尾再占整页高度；其他工作区footer保留。 |
| tests/test_phase5_layout.py（新增） | 9项初始无调用、发送去重、多行、会话/表单、确认及scope检查。 |
| PROJECT_STATUS.md及阶段五/归档报告 | 长期状态与交付证据，归档报告是Push后生成，未混入先前Commit。 |

## 10. 自动化回归命令与结果

```powershell
.\.venv-v35\Scripts\python.exe -B -m artifacts.runtime.v37-phase5-ui-redesign-20261101.run_checks full-r4
node artifacts/runtime/v37-phase5-ui-redesign-20261101/browser_layout.js
node artifacts/runtime/v37-phase5-ui-redesign-20261101/browser_interaction.js
node artifacts/runtime/v37-phase5-ui-redesign-20261101/browser_business.js
git diff --check
```

完整回归UTC：2026-11-01T06:52:07.471995+00:00至2026-11-01T06:54:16.750244+00:00。实际独立full-r4/snapshot中pytest tests -q --tb=short，退出1；冻结P0包15文件核验，隔离temp/SQLite/Trace/Chroma，去凭据/Secrets且socket仅回环。
| 范围 | Passed | Failed | Skipped | 子测试通过 |
|---|---:|---:|---:|---:|
| 阶段四基线 | 1242 | 11 | 1 | 199 |
| 阶段五full-r4 | 1251 | 11 | 1 | 199 |
| 新增阶段五 | 9 | 0 | 0 | — |
| 原支付/退改/面板专项 | 40+59+45 | 0 | 0 | — |
所有旧测试字节和ID保留，无删除、skip/xfail或改旧断言。初次full-r1为1249/13/1，新增错误为缺失旧服务提示和顶栏回调状态竞态；修复后targeted9/0/0、full-r2/r3/r4均1251/11/1。全部原日志保留，不累计中间次数充当最终成绩。

## 11. 原11失败与唯一Skip逐ID比较

以下各ID均为阶段四Failed→阶段五Failed，新增失败0；不修或隐藏原产品契约冲突：

- `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_configured_online_default_is_deepseek_and_render_never_calls_agent`
- `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_direct_send_permission_is_session_and_provider_specific`
- `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_qwen_still_requires_its_original_checkbox`
- `tests/test_followups_continuous.py::ContinuousFollowupsTests::test_qwen_ten_clicks_survive_timeout_and_saved_replay`
- `tests/test_followups_mvp.py::FollowupRuntimeTests::test_qwen_ui_consent_automatically_includes_followups_offline`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_empty_qwen_run_has_a_clear_reason_and_disabled_export`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_explicit_history_selection_is_preserved_and_model_is_explained`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_live_fee_consent_does_not_follow_a_different_provider`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_qwen_panel_rejects_another_provider_record_without_export`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_qwen_stays_active_after_opening_integration_center`
- `tests/test_unlimited_live_ui.py::LivePageTests::test_bailian_user`

唯一Skip：`tests/test_p2_scenarios.py::test_no_approved_p2_scenarios`，两阶段相同。完整新旧集合及新增9ID见regression-comparison.json。

## 12. 四规格真实DOM测量

Edge 156.0.4314.50、既有Playwright1.64.1、Streamlit1.65.0；四个独立上下文首次加载，不是只缩放桌面。最终browser-r5源码与full-r4及工作区py/css/txt哈希一致。每条原始rect/scroll/client尺寸保留在layout-verification.json的measurements，包括顶栏、聊天、输入框、右栏和650px状态。

| 规格 | document/client 高×宽 | 输入框容器 y / bottom | 聊天scrollTop前→后 | 输入框y前→后 | 右栏scrollTop前→后 | page scrollTop |
|---|---|---|---|---|---|---|
| desktop-light | 1100=1100 × 1600=1600 | 963 / 1088 | 0→360 | 963→963 | 0→1065 | 0 |
| desktop-dark | 1100=1100 × 1600=1600 | 963 / 1088 | 0→360 | 963→963 | 0→1065 | 0 |
| mobile-light | 844=844 × 390=390 | 655 / 796 | 0→360 | 655→655 | 0→1745 | 0 |
| mobile-dark | 844=844 × 390=390 | 655 / 796 | 0→360 | 655→655 | 0→1745 | 0 |

布局38/38，交互32/32，复用阶段四业务72/72，总142/142。38布局含：输入框不在滚动区内、双栏/单栏、页面尺寸和scrollTop、真实滚轮改变局部scrollTop、输入框坐标稳定、右栏独立滚动、动态视口，以及elementFromPoint验证输入和新会话中心未被遮挡、移动标题不与展开按钮重叠。
交互包含单行Enter一次、多行Enter不发送/Ctrl+Enter一次、草稿经面板rerun保留、pending确认前0请求、确认后一次真实Agent调用、新会话0调用、历史会话恢复原sid不重放。业务包含六面板、政策/费率/行李、中心支付/改签/退票/P02和只读刷新，数据库8订单/8支付/4改签/4退款及16 source=page事件一致；库存和差价独立回查。
最终被验收12会话合计76次实际离线Mock Agent.chat（布局24、交互12、业务40），非真实模型API调用。原始Trace路径/哈希/工具序列见agent-evidence.json；所有页面操作仍与Agent工具Trace区分。

## 13. 截图与Console原始日志

最终72张截图：布局每规格5张（初始/聊天顶部/滚动后/输入框/右栏），交互每规格3张（多行/确认/历史恢复），业务每规格10张（六功能+支付/改签/退款/只读恢复）。实际PNG和SHA256见screenshots.json，非静态HTML或伪造截图。
Console资源错误共36条，分类计数{"layout": {"raw_console_errors": 8, "failed_requests": 8, "blocked_external": 8, "page_errors": 0}, "interaction": {"raw_console_errors": 16, "failed_requests": 16, "blocked_external": 16, "page_errors": 0}, "business": {"raw_console_errors": 12, "failed_requests": 12, "blocked_external": 12, "page_errors": 0}}。所有失败URL都为fonts.gstatic.com的travel_explore/default/24px.svg，离线主动拦截；没有隐藏Console或放行联网。PageError0、最终Playwright操作失败0；不能宣称Console0。阶段四原20条日志未修改，新增运行次数受新会话/刷新影响，不把数量差当新业务缺陷。
中间证据保留：layout-attempt-r1、browser-attempt-r3/r4、等待/选择器JSON。包含无长内容时错误期待右栏可滚动、未等待rerun/URL完成、将toggle隐藏input误当聊天输入的验收脚本错误；与真实产品竞态/遮挡分开记录。r4中间业务运行因最终顶栏修正而明确中断，原因在browser-r4/browser-interrupted.json，不算最终通过；最终r5完整重新执行。

## 14. 工程保护与Git最终状态

103正式用例和原断言、B方7份manifest文件、1892保护文件、4056获准基线全量SHA256零差异。原3708/4056与阶段三相比唯一历史差异仍是用户批准保留的账本追加，本阶段未追加/改写；保留原说明，不将授权基线偷换成原历史无差异。
未改任何target/业务服务、正式Prompt、八Schema、十/五字段、七维度、Provider选择、runtime费用授权、政策/RAG数据/P2、SQLite历史、账本或Trace。无新依赖/安装。两Skills原版保持。
HEAD仍`c889b082dd4bd07e3514038a69362b71dd21915c`，分支feat/ticket-agent-v36-stabilization；阶段五修改和Push后归档报告保留未提交，暂存区空，未再次Commit/Push/Merge。git diff --check退出0；完整清单在verification.json及git-status-final.txt。只停止自己命令路径核验的8518测试服务，各次停止记录保留；未停止用户其他服务。

## 15. 遗留风险与未验证项

- 原11项默认模型/费用授权/旧UI契约失败保留，需后续独立确认和修复，不能宣称恢复或全绿。
- 未提供原image3.png；当前是按文字结构/验收实现，视觉风格还需用户验收。
- 实体手机软键盘/刘海设备未实机验收；本次真实Edge新390px视口及650px动态视口通过，不能等同所有手机浏览器。
- Streamlit DOM选择器与同源iframe桥接依赖当前1.65结构；已保留局部fallback和实测证据，升级需复验。旧components.v1.html弃用警告仍在原始app.log，没有趁机引入新运行时。
- 数据仍演示、政策为示例、固定模拟身份，无真实12306、出票/支付/退款/补差价；真实模型/Embedding/LangSmith未调用/验收。
- 既有支付后page审计与支付事务分离、历史快照与当前库分层、凭证交回未建模、RAG历史待验证风险不因UI通过而消除。
下一步：用户验收本阶段和未提交diff；是否提交阶段五、是否进入阶段六须新的明确授权。本次停止，不自动提交、推送或进入阶段六。

## 16. 证据索引

统一根artifacts/runtime/v37-phase5-ui-redesign-20261101/：before/skills/code-eval、full-r4日志/JUnit/summary/source-manifest、regression-comparison、layout/interaction/browser JSON、geometry-summary、72PNG/screenshots SHA、agent-evidence、database-checks、server-stop、verification。Git归档独立根v37-pre-phase5-git-archive-20261101/。PROJECT_STATUS增量更新，所有历史记录保留。
