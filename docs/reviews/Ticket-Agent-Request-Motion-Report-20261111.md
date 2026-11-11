# Ticket Agent 等待状态与动态交互交付报告

日期：2026-11-11（Asia/Shanghai）。HEAD `8a6ccf36688c9cab803d46ba0bbf652290132e19`；分支 feat/ticket-agent-v36-stabilization。仅用户工作空间展示层增量，未提交/推送。项目原V3.11-R1 PARTIAL状态不因本轮UI验证改变。

## 实现与真实状态来源

复用原Conversation → interaction.operations / _chat_future → run_events → run_view。没有新增业务状态机、API、模型调用、数据库迁移、工具或Trace字段。

- 模型等待：只有收到model_start且尚无model_end时显示“AI 正在思考”和三个顺序起伏圆点。未知内部阶段只显示“正在处理请求”。
- 模型生成：仅预留真实model_delta/model_token事件映射；当前原引擎没有向页面提供逐Token流，实际使用等待指示与完整回复，不模拟打字。
- 工具：只有真实tool_start才显示工具名及调用中；tool_result/railway_tool_result切换成功、失败或拦截。同call_id关联，多个并行调用不互相覆盖；模型仅提议工具不代表执行。铁路链若没有start事件，只有返回后才展示结果，不猜测执行中。
- 步骤：沿用原run_view.phase_states；活动步骤蓝色轻脉冲，成功绿色✓，失败红色!，阻塞⊘，待确认静态◉，待执行/未知灰色。历史和已完成步骤不循环播放。
- 回复/结束：最新回复轻微淡入；本轮成功结束图标一次轻缩放，失败不套成功动画；仍保留开发者详情入口及业务回执。
- 输入：沿用现有busy/防重与控件key，按钮显示“处理中”并禁用，输入草稿可继续编辑。完成/失败后恢复“发送”。没有更改多轮对话或确认权限。
- 动效：CSS只使用轻微opacity/transform；复用原右侧0.35秒fragment同时更新聊天等待占位，不增加另一套持续轮询。没有第三方动画依赖/全局页面重构；减少动态效果下关闭三点、步骤及结束/回复动画，保留静态文字和状态符号。

## 文件变更

| 文件 | 原因 |
|---|---|
| web/request_motion.py（新增） | 纯展示状态与工具事件映射、转义HTML、历史静态回退 |
| web/request_motion.css（新增） | 用户空间局部动画、主题变量与prefers-reduced-motion |
| web/conversation.py | 接入原刷新循环、实时等待/工具回执、按钮标签及回复/结束展示 |
| web/user_copy.py | 步骤状态图标与活动动画入口，原用语转换保持展示职责 |
| web/user_layout.py | 载入局部CSS，不改布局 |
| tests/test_request_motion.py（新增） | 16项纯展示确定性检查 |
| PROJECT_STATUS.md | 本轮状态及真实证据增量 |
| 本报告 | 记录交付、局限及证据 |

控件key、session_state变量、Agent/Provider/工具Schema/交易D9/P01/SQLite服务/正式103均未更改。开工已有R1源码与报告修改原样保留。

## 测试结果

- 新展示单测：16 passed / 0 failed / 0 skipped。
- 最终相关前端回归r5：115 passed / 0 failed / 0 skipped，另6个子测试通过。包括新单测、原阶段1文案/费用与控件、阶段5布局、P1执行事件、政策交互、用户政策聊天、v39聊天防重/历史恢复。
- 使用现有regression_center.prepare的隔离副本、冻结Fixture及外网阻断。没有在旧业务DB运行测试。命令见frontend-command-r5.json。
- 第一批因遗漏RAILWAY_SIM_DB_PATH出现6 failed/19 errors；r2修正环境后115通过。后续r3的隔离目录命名触发既有PROTECTED_DATABASE_NAMESPACE，15失败；没有改保护器或旧断言，采用允许的v391-d9-lifecycle-*目录后r4/r5均115通过。失败日志保留，不覆盖旧证据。
- 本轮没有重新运行完整项目回归，不把此前1971/11/1或R1报告套作本轮全量结果。原历史失败/Skip断言未修改。

## Edge + Playwright

最终browser-r3：**126 passed / 0 failed**。1600×1100、1366×768、800×900、390×844，均浅/深主题。27张真实截图。原Conversation/Agent/工具执行，模型使用明确SDK替身，超时和工具异常是隔离注入，不是Live验证。

覆盖模型等待、三点顺序动画、动态效果减少设置、忙碌发送禁用但草稿可编辑、多轮查询、真实工具开始/成功/失败、模型超时、用户确认等待、结束后动画移除、按钮文字不裁切、历史刷新只读且不重启请求、移动无横向溢出。

PageError=0；Console错误24、网络失败24，均为浏览器主动阻断的既有fonts.gstatic.com外链图标。新动效没有外链资源。旧browser首批在隔离fixture刷新路径未映射时失败，原件保留；修正测试fixture的只读恢复路径后r2为118/0。目视发现按钮文字可能省略，改为“处理中”并局部缩减按钮左右padding，最终r3新增完整文字检查126/0。

## 保护与安全

开工5590项保护资产：5589项一致。原百炼账本追加8397字节，原507867字节SHA前缀完整，用户在本对话明确确认来自自身/其他会话并保留；当前516264字节及SHA见ledger-retention-approved.json。未截断/重写账本。所有业务源文件、原测试、原数据库及冻结数据无本轮新增差异。新测试文件单列，不混入旧基线。

本轮真实模型/铁路/支付/Embedding/LangSmith请求均0，不消耗真实Token。SDK用量是合成测试记录，不作为真实API用量。测试服务器已停止，只操作本轮隔离端口，不影响原用户服务。

## 局限与结论

UI范围 IMPLEMENTED / FRONTEND_TESTED / BROWSER_VERIFIED（SDK）；真实模型验证NOT_RUN，用户ACCEPTED待定。没有Token级真实流式输出或铁路工具start事件的地方保持粗粒度反馈；没有放宽原业务/请求权限。没有做CPU/FPS专项基准，轻量性依据CSS实现及复用既有轮询，不宣称性能零影响。

项目整体仍PARTIAL，不自动提交推送或进入其他阶段。

## 证据索引

`artifacts/runtime/ui-wait-motion-20261111/verification.json`，SHA256 `b8a1f75cbc9590bf812a399d8947e5f0321ddb15f04da261df68370ba4639914`

`artifacts/runtime/ui-wait-motion-20261111/frontend-command-r5.json`，SHA256 `c78e868bb616d86c1b2071487a5c418bfbaa7162e9e35a99b1d2b850af1d048c`

`artifacts/runtime/ui-wait-motion-20261111/frontend-regression-r5.xml`，SHA256 `7ea2fe1856c147ec8b68c0c9ad2a325197d217ef0a042bf7b96dd7ae3d4a67fe`

`artifacts/runtime/ui-wait-motion-20261111/browser-r3/results.json`，SHA256 `e7ef1311b02fe6eb1f6c8da653b47913f71b3a14c42412961ea3d30445af70a7`

`artifacts/runtime/ui-wait-motion-20261111/ledger-retention-approved.json`，SHA256 `a406393d55b8b8a4adfdd9ecd6be379b09d3c76944a8a6ddfb776436c53ad76b`

截图：`artifacts/runtime/ui-wait-motion-20261111/browser-r3/`，包含各规格waiting/tool/complete及timeout/confirmation/tool-failure。
