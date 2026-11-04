# V3.9.3 浏览器与可读性报告

本机Edge/Playwright，4规格：桌面1600×1100、手机390×844，各浅/深主题。最终 `artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/ui-sealed/results.json`：52通过/0失败/0跳过，16真实截图，PageError0、Console8、网络失败8、阻断8；均为fonts.gstatic.com图标资源，原记录不隐藏。

代码和字号：原三栏/独立滚动/固定输入保留，正文浏览器计算16px、1.7行高；最初旧14px规则覆盖已通过更限定的选择器修正。右栏铁路查询三入口与静态真实候选、20条分页/第二页、聊天卡片/共享Agent卡、输入框与无整页横向溢出均实际验证。窄屏表格内部滚动，不宣称所有列同时可见。

修改前：`artifacts/runtime/v392-delivery-20261103-234500/evidence/desktop-light-original.png`等历史原件。修改后：`artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/ui-sealed/desktop-light-chat.png`、`desktop-dark-chat.png`、`mobile-light-chat.png`、`mobile-dark-chat.png`；另有original/query/pagination截图。画面所示演示日期为2026-11-04，查询39条；11月6日40条是另组真实模型测试，不混用。

两Provider原UI真实查询另见 `artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/live-ui/qwen-ui.png`、`live-ui-deepseek/deepseek-ui.png`。Qwen四HTTP、DeepSeek四HTTP（均含追问），有实际工具和数据库核对。双Key切换自动化多次失败未调用模型，不计作通过；保留live_ui_deepseek_r2/r3/r4及诊断。DeepSeek单Provider验证不是双Key切换成功。

早期ui-results/r2有手机展开区定位失败，r3/final/sealed保留过程；不覆盖失败。最终只针对列出的检查项通过，未完整覆盖数据库不可用、长文本/多行输入组合、原UI完整三人交易流程和实体手机。UI查询库0订单/报价/提案/交易，不能称交易UI验收完成。

开发者空间/测试台导航保留；原技术功能未删除，但本轮不调用LangSmith真实上传。自建临时服务已停止，用户服务未停止；离线socket外联拦截，真实模型测试独立目录。
