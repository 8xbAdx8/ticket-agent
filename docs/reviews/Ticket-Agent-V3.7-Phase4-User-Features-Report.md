# Ticket Agent V3.7 — 阶段四：四大功能面板与统一订单中心交付报告

交付核验时间：2026-11-01T14:09:24+08:00。仅阶段四；未提交/推送/合并，未进入阶段五。

**结论：阶段四实现及隔离离线验收完成，等待用户验收。最终1242 passed / 11 failed / 1 skipped / 199 subtests；新增45项通过，新增失败0，原11失败与唯一Skip逐ID一致。Edge四规格业务72/72、横向溢出/导航24/24；40张实际截图。全仓仍有11项历史失败，不宣称全绿。**

## 1. 开工基线与保护

分支`feat/ticket-agent-v36-stabilization`，HEAD `139cdbe2fca8c7249847f245cffef1ed0545dd36`。接手工作区已有阶段1/1.2/2/3代码、依赖和文档未提交修改，完整保留；开工Git及2285文件哈希在before.json、diff-before.txt。读取PROJECT_STATUS、前序报告/verification、退改/支付/Agent/工具/政策/七维度实现。
开工发现`artifacts/runtime/api-usage/bailian/dbc4325ea7a9515b7a04/requests.jsonl`较阶段三追加6890字节，原244030字节为完整前缀。用户明确答复“是，保留追加内容，以当前账本为基线继续”。原始差异和哈希在preflight-ledger-difference.json；本阶段未发起Live请求、未改账本。不能将原3708/4056清单表述为无差异：其唯一差异是获准保留的追加；获准后的4056基线零差异。
保护检查发现前曾提前创建读取层草稿，已在当时明确告知；未继续业务执行，得到用户基线确认后继续。未重置、清理或回滚用户文件。

## 2. eval-audit使用及实施前发现

按原版Skill方法审查证据和失败模式，先向用户输出发现再实施。没有虚构Skill运行器或网络API。详见skill-audit.json。

| 优先级/领域 | 发现 | 采纳处理 |
|---|---|---|
| P0/订单数据源 | Agent结果、demo-payment-receipts和page-order-state分别用于工具历史与刷新，不能合并当作当前交易状态。 | target/order_read_model.py统一当前库只读投影；历史Trace原样保留，中心比对不一致即禁操作。 |
| P0/界面成功与业务完成 | 只看文案不能验证支付、库存释放、退款、改签是否完成。 | 复用阶段二/三服务，SQL回查订单/库存/明细/source=page，preview与reload做前后比较。 |
| P0/Agent证据链 | 快捷提示不能代替独立面板；直接查库存会丢失正式Agent工具证据。 | 查票和订单使用Conversation.send→Agent.chat→原工具；无成功工具记录拒绝展示成功。 |
| P1/身份与重复动作 | UI隐藏按钮不足以防止越权和重复确认。 | 只读投影限制CURRENT_USER_PHONE，复用业务二次校验，保留阶段三并发/回滚/幂等测试。 |
| P1/政策可追溯 | 模型摘要或硬编码政策容易丢失原始来源。 | 复用documents/keyword，真实doc_id/chunk_id/source/content，选中政策带入后续Agent问题。 |
| P1/费率边界 | 页面另写费率可能在48/24小时和小数金额处漂移。 | 提取共享Decimal计算，原quote调用同一函数，固定时钟及正反例测试。 |
| P1/空态与异常 | 空列表、未成功工具、过期锁和工具/库状态差异必须区别。 | 保留明确空态，过期只读推断，不一致诊断JSONL且禁用操作。 |

## 3. write-code-eval使用与确定性规则

原版方法用于pytest/AppTest、SQL前后状态及实际Agent Trace/Edge检查，分别记录输入/预期/失败条件/证据。Skill文件均保持原哈希。未采纳LLM Judge、远端Trace拉取、新依赖和正式评分改造：这些规则可客观验证，不需要语义评委或联网。详见code-eval-spec.json、skills-usage.json。

| 规则 | 输入 | 预期 | 失败条件 | 证据 |
|---|---|---|---|---|
| 查票提交一次 | 城市/日期/高铁机票五种席别，点击一次再rerun | query调用1次；仅成功真实工具结果作为车次；rerun不再发送 | 重复调用、绕过Agent或接受没有工具的假成功 | test_ticket_submit_once_and_empty_result_without_refresh_resend; test_ticket_agent_real_trace_and_selection_does_not_write; test_panels_query_uses_actual_agent_and_preserves_trace |
| 无效表单 | 同城、过去日期、交通方式与席别不兼容 | 警告，不发送Agent | 无校验仍发送请求 | test_invalid_ticket_form_never_sends_agent |
| 订单归属/状态 | 本人3订单及FOREIGN，五种原状态、过期lock | 仅本人，准确状态/按钮，读取不写库 | 越权展示、错误动作权限、读取写状态 | test_owned_projection_permissions_and_readonly; test_expiry_projection_does_not_write_database |
| 支付改签退款 | 真实中心点击支付/预览改签/确认/退票，再reload | DB状态、差价/库存明细一致；preview只读；page_operations来源page；刷新不写 | UI成功但DB未变、历史Trace伪造、重复记录 | test_center_and_chat_reuse_controls_without_duplicate_keys; browser-verification.json; 四规格db-final.json; 原阶段三59项 |
| 订单不一致 | 支付后Agent旧pending和当前paid | 显示差异、保留JSONL，危险动作禁用，需重新查询 | 静默使用旧结果或允许写操作 | test_changed_projection_and_inconsistency; browser mismatch_blocks_operations; 隔离会话order-consistency.jsonl |
| 政策来源 | 五类及关键词/无结果/清空/选政策 | 真实文档编号、内容和source；上下文保留来源 | 凭空来源、空筛选伪结果、偷偷Embedding | test_policy_uses_existing_sources; test_policy_categories_use_real_document_content; test_policy_filter_clear_and_context_has_source |
| 费率及无副作用 | 固定49/48/47/24/23小时；已发车、pending、已改签、NaN、缺票价、小数123.45 | 5/10/10/10/20%；P12退款0；P02拒绝；6.17手续费，不连接DB | 边界或Decimal错误、产生DB写入 | test_shared_calculator_boundaries; test_calculator_restrictions; test_invalid_price; test_calculator_decimal_precision_and_no_database_access |
| 面板切换 | 六入口/关闭/切换后票价123.45 | 没有Agent自动调用、状态保存、没有重复控件key | 切换触发写/模型、丢表单或重复key | test_independent_panel_render_and_switch_without_agent; test_form_and_results_survive_panel_switch; browser-verification.json |
| 行李和退改原规则 | 原成人/儿童/重量尺寸，以及并发/回滚/P02 | 原规则测试保持；不另写计算和改签服务 | 原测试退化、复制业务、重复改签或已改签可退 | tests/test_baggage_calculator.py; tests/test_reschedule_order_selection.py; tests/test_refund_by_train.py; 四规格浏览器 |

## 4. 统一订单读取架构

新target/order_read_model.py以SQLite URI mode=ro读取现有会话tickets.db；不建第二个订单库。限制CURRENT_USER_PHONE，投影orders、demo_payments、refunds、reschedules、inventory和锁过期时间。保留raw status，过期锁只推导effective_status不写库；paid+改签记录显示已改签，取消不冒充退款。统一支付/退票/改签/凭证操作allowed/reason。
原订单amount、原支付记录amount、新票面金额和difference分开；缺少支付记录时明确未提供，不补造历史实付或把差价当已收款。现行P02、打印凭证和发车时间限制仍由原业务服务确认时复查。UI读层不充当写操作授权。
当前可操作聊天卡片与订单中心使用同一投影。历史对话原文/工具结果保留当时状态；只读恢复仍兼容前序支付/退改展示记录，不重写原Trace。订单中心在只读恢复中读取当前库并标记与历史查询差异，禁止写操作。这是当前状态与历史证据的明确分层。

## 5. 四个独立面板及常用入口

| 面板 | 实际实现 |
|---|---|
| 查余票 | 城市、日期、交通方式、席别表单；同城/过去/席别兼容校验；显式查询才调用Agent，工具结果渲染现有车次卡片；选择车次只写会话上下文，后续订票仍走原确认。 |
| 问政策 | 原documents和keyword，五类、关键词、空结果、清空/全部、真实doc_id/chunk_id/source/content；选择政策将内容/来源带入下一次实际Agent问题，不算已回答。 |
| 看订单 | 显式Agent→query_order后与当前投影逐单及ID集合核对；不同则警告、保留原结果、写order-consistency.jsonl、禁止操作；统一详情、支付/退改/关联政策。 |
| 退票费率 | 必填票价、日期时间、票种/支付情况/改签状态；共享阶段三Decimal calculate，显示政策/距发车/费率/基数/费用/退款/公式；不按里程编造价格，不连接数据库。 |
右栏六入口和首屏四快捷卡片均打开面板，不自动填固定提问。保留旧columns骨架，首屏也使用同一骨架；未改全局CSS/输入框/滚动机制。面板会话状态独立，表单切换保留，查询不因rerun重发。
行李表单迁入右栏并复用原calculate_baggage；保持原控件key和计算按钮文案，兼容旧AppTest。右栏保留可折叠表单而非在聊天流内，独立入口会展开。改签入口从本人的可改签订单下拉选择，复用阶段三change_panel/preview/confirm；没有第二套事务。

## 6. Agent链路、RAG和页面业务边界

查票/订单：面板→Conversation.send→Agent.chat→query_tickets/query_order；检查真实成功工具记录，不接受只有回复的假成功。选政策后的继续问答实际传入来源和内容；浏览器4次继续问答经实际search_policy，见agent-evidence.json。政策浏览直接读原文/Keyword，不新建索引、不调用Embedding。
支付/退改复用原服务与确认流程，支付补记page_operations.source=page；不生成Agent工具步骤。计算器/行李为纯函数，订单投影为只读；都不伪造Trace。不改变Agent Prompt、八Schema、十/五字段、Provider选择、授权实现、七维度、P2或A/B/Mock/Live归属。Live仅复用已有就绪/会话门槛，本阶段没有Live/Embedding/LangSmith/12306验收或费用请求。

## 7. 订单一致性与刷新

中心付款后，原Agent pending结果与DB paid会明确提示差异并禁用危险操作；再次显式查询后恢复一致卡片。改签/退票同理，不静默覆盖历史工具结果。不一致JSONL含会话/订单/六字段差异，不含手机号。支付、退改服务仍在确认时复核归属/金额/状态/库存和幂等。页面刷新只读，不重复写操作。
已改签显示新票面和差价记录，原支付金额不覆盖；P02无可执行退票按钮。费用预览与确认仍使用原quote/preview及冻结快照。投影读取失败不开放卡片写入口。

## 8. 修改文件及原因

| 文件 | 本阶段原因 |
|---|---|
| target/order_read_model.py（新增） | 本人只读订单统一投影和动作条件。 |
| web/user_features.py（新增） | 四面板、六入口、会话状态和一致性诊断，复用业务服务。 |
| target/order_refund.py | 原费率提取共享calculate；quote复用，费率/舍入/政策不改。 |
| web/conversation.py | 首屏快捷卡片/右栏面板与选中车次/政策上下文，移动原行李入口。 |
| web/payment.py | 当前卡片统一读层、中心控件namespace及支付page事件；支付交易服务不改。 |
| web/order_actions.py | 中心与聊天控件namespace隔离，重用原改签流程和投影动作条件。 |
| web/presentation.py | 显示统一display_status，旧无投影结果仍兼容。 |
| tests/test_user_features.py（新增） | 45项确定性纯函数/真实Agent/AppTest/SQL检查。 |
| PROJECT_STATUS.md / 本报告 | 增量记录当前阶段与实测证据，不改旧报告。 |
另新增本阶段独立artifacts下隔离快照/原始日志/JUnit/脚本/截图/JSON证据；历史数据库/用量/Trace未写入。原测试和前序未提交修改全部保留，依赖零变更。

## 9. 测试命令、时间与真实结果

```powershell
.\.venv-v35\Scripts\python.exe -B -m artifacts.runtime.v37-phase4-user-features-20261101.run_checks full-r10
node artifacts/runtime/v37-phase4-user-features-20261101/browser_acceptance.js
node artifacts/runtime/v37-phase4-user-features-20261101/browser_navigation.js
git diff --check
```

最终pytest时间：2026-11-01T06:03:34.241635+00:00 至 2026-11-01T06:05:44.626761+00:00。实际在独立full-r10/snapshot内执行python -m pytest tests -q --tb=short --junitxml=<独立JUnit>，退出1与11失败一致。prepare验证冻结P0包15文件，移除凭据、禁止Secrets、socket仅回环，独立temp/数据库。
| 范围 | Passed | Failed | Skipped | 子测试通过 |
|---|---:|---:|---:|---:|
| 阶段三基线 | 1197 | 11 | 1 | 199 |
| 最终full-r10 | 1242 | 11 | 1 | 199 |
| 新增Phase4 | 45 | 0 | 0 | 0 |
| 原Phase2支付 | 40 | 0 | 0 | — |
| 原Phase3退改 | 59 | 0 | 0 | — |
新增ID清单及原断言完整性见regression-comparison.json和protection-checks.json；不修改或删除旧测试，不增加skip/xfail。中间full-r2/r3曾因移动行李表单破坏旧控件产生新增失败，恢复原key/按钮后消失；targeted-r5的past_date测试假设被Streamlit min_value钳制，改为显式无效返回测试提交守卫；原失败日志完整保留，不计为最终通过。所有中间full-r*/targeted-r*为不同源码时点，不能累加或混作最终成绩。

## 10. 原11失败逐ID对照

下列每项阶段三=Failed、阶段四=Failed；不是新故障，也未宣称修复：

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

## 11. 原Skip逐ID对照

`tests/test_p2_scenarios.py::test_no_approved_p2_scenarios`：阶段三与阶段四均Skipped；无新增Skip。全部旧测试ID保留，新增失败集合为空。

## 12. 四规格Edge浏览器与截图

Microsoft Edge 156.0.4314.50、既有Playwright 1.64.1、Streamlit 1.65.0。最终browser-final-v3为新启动隔离进程，不依赖旧Python模块缓存；产品源码哈希与full-r10及根目录一致。
| 规格/主题 | 业务检查 | 导航/无横向溢出 | 截图 |
|---|---:|---:|---:|
| 1600×1100浅色 | 18/18 | 6/6 | 10 |
| 1600×1100深色 | 18/18 | 6/6 | 10 |
| 390×844浅色 | 18/18 | 6/6 | 10 |
| 390×844深色 | 18/18 | 6/6 | 10 |
真实交互覆盖六面板、票卡选择、政策分类/搜索/展开/上下文、订单中心支付/差价预览/确认改签/P02、第二单退票、只读刷新；SQLite回查8订单、8支付、4退款、4改签及16页面事件。改签目标库存人数扣减、差价与原实付保持检查见database-checks.json。24个额外导航检查实测document/body scrollWidth≤视口宽度。页面跳动没有性能量化，不能据此声称完成阶段五布局验收。
40张PNG及SHA256见screenshots.json；文件名以desktop-light/desktop-dark/mobile-light/mobile-dark区分，面板及center-paid/changed/refunded/readonly-reload。前序浏览器尝试及定位失败均保留在browser-attempt-r1…r6；含日期控件DOM定位、目标选项精确名称超时、旧模块缓存等记录，不冒充最终成功。

## 13. Console与网络错误分类

最终业务脚本Console资源错误12，导航补查8，共20；failedRequests/blocked逐条对应。均为主动离线拦截的fonts.gstatic.com/travel_explore/default/24px.svg，非放行联网或隐藏日志。PageError/业务验收错误0。原始数组保留在两个browser JSON，不声称Console为0。与阶段三12次为同源资源错误，次数受新增页面/查询影响。
Python侧旧Streamlit html组件弃用警告仍在app.log，非本阶段业务错误。未安装/升级依赖，服务外部socket拦截日志为空，真实模型、Embedding、LangSmith、12306、真实交易请求均0。

## 14. 保护哈希、Git与服务

1892保护文件零差异；103正式用例原内容/断言、7份B manifest文件核验通过；所有旧测试字节不变；Prompt/工具Schema/七维度和mock_core/reschedule/运行时/requirements均保持接手哈希。原3708/4056唯一差异为开工前获准账本追加，获准后的4056零差异；不能覆盖此历史差异。阶段三原报告/截图亦保留。
HEAD仍`139cdbe2fca8c7249847f245cffef1ed0545dd36`，分支不变、暂存区空；git diff --check退出0（保留原有LF→CRLF提示，不主动规范化旧文件）。最终git-status-final.txt和verification.json列出所有既有与新增未提交文件，不能将全工作区diff归属于本阶段。8517自建隔离服务的路径/PID核验和停止证据在browser-final-v3/server-stop.json；前几个自建服务也有停止记录，未停止用户其他服务。

## 15. 风险、未完成验证与下一阶段

- 原11项默认模型/费用授权/旧UI导航相关失败仍在；需独立任务按既定产品契约解决，本阶段不修或改断言。
- 当前仅演示数据、示例政策、固定模拟身份、非真实出票/扣款/退款/差价支付；没有真实Provider/Embedding/LangSmith/12306回归。
- 历史对话是当时证据，不代表当前库；中心不一致必须重新查询。历史库缺少业务记录时标记未提供，不补造。
- 两步支付成功后page审计失败会提示“记录失败、不重复支付”；此审计不是新增支付交易事务的一部分，业务支付仍由原服务保证。
- 五类政策为现有P编号分组，Keyword零答案误召回与千题Vector/Hybrid/忠实度历史风险不因此消除；不修改原RAG成绩。
- 本阶段不量化滚动跳动、不开展全面动态视口/固定输入框改造；四规格面板可操作和横向宽度核验不替代阶段五。
- 旧凭证交回流程未建模；P02禁退和一次改签保持。
下一步只建议在用户验收本报告后，再单独确认阶段五Grid/Flex/固定输入框与移动布局范围和验收；本次停止，不自动开工。

## 16. 证据索引与验收结论

统一证据根：`artifacts/runtime/v37-phase4-user-features-20261101/`。before/protection/preflight-ledger、skills三JSON、code-eval-spec、full-r10日志/JUnit/summary/source-manifest、regression-comparison、browser/navigation JSON、40截图及screenshots.json、agent-evidence、database-checks、server-stop和verification共同支持本报告。原件保留；状态文件只索引结果。
阶段四验收交付完成；全仓11项历史失败保留，未经本阶段范围验证的真实服务不宣称通过。PROJECT_STATUS已增量更新并保留前三阶段记录。完成后停止等待用户验收。
