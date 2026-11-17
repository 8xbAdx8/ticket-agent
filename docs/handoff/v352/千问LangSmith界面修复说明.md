# 千问与 LangSmith 界面修复说明

日期：2026-10-27。分支：`codex/fix-qwen-langsmith-ui`。基线：`f9b7d4b51cd0af4a324adf21836b488b890a4fd9`。

## 问题与实际原因

截图中左侧选择 Qwen3.8-Flash，右侧仍显示 DeepSeek。这一问题已在修改前离线复现：

1. 初始 DeepSeek 会话为历史列表第 0 项。
2. 选择千问，创建并切换到新的 Qwen 会话。
3. 前往“测试工作台→集成中心”，再返回“出行助手”。
4. Streamlit 清理未渲染的历史会话下拉框临时状态；返回时下拉框恢复默认第 0 项。新会话默认模型仍为千问，当前会话却变成 DeepSeek。

另一个困惑是：截图中的会话没有执行记录，LangSmith 面板只有上传范围说明，没有明确说明为什么不能导出。LangSmith 导出的是已有 Agent 执行记录；仅选择模型、打开面板或配置 Key，并不会产生记录。不能为了显示成功而创建虚假 Trace。

对截图中的样式问题，本次补齐了原生展开面板悬停/焦点背景、标题颜色，以及 Chromium 输入框文本填色，使它们遵循当前主题。

## 实际修改

- `web/conversation.py`：用非控件状态保存当前会话索引，恢复切页前的会话；新建/换模型时同步索引。明确选择历史会话时保留用户选择，并说明当前会话模型与新会话默认模型的区别。
- 切换到另一个会话时清除真实请求费用确认，避免把 DeepSeek 的确认误带给千问。
- 没有运行记录时，显示当前模型与前置步骤，导出按钮明确禁用。Key 缺失/关闭/配置错误分别显示，不把“未配置”写成已开启。
- 执行记录来源与当前会话 Provider 不一致时停止导出，防止跨模型记录误标。
- `web/design.css`：修复展开面板交互态、输入文本/占位符/禁用文本颜色。
- `tests/test_qwen_langsmith_ui.py`：增加 7 项离线回归，包括实际 Qwen SDK 与 LangChain 工具调用、sidecar 保存、网页预览与 LangSmith HTTP 桩导出。

没有修改模型 Provider、Agent 主循环、工具实现、接口契约、预算或变异实现。没有修改 B 的正式测试原件。原 LangSmith 202/404 有限核验与防重复 POST 机制继续保留。

## 使用顺序

1. 启动或重新启动在线脚本。此前由开发工具启动的 `http://127.0.0.1:8554/` 已重启并实际检查；其他旧启动窗口需要自行按 Ctrl+C 后重新双击 `启动_在线模式.cmd`，仅刷新网页不能保证重新加载 Python 模块。
2. 选择 **Qwen3.8-Flash Live**。右侧徽标与费用确认文字应同时显示 Qwen3.8-Flash。
3. 输入问题，勾选真实请求费用确认，点击“发送”。这一步会产生模型 API 费用，本轮修复没有代为执行。
4. 等待本轮运行记录保存后，展开 LangSmith 面板，检查脱敏预览、勾选上传同意，再点“导出本轮并验证远端”。打开面板本身不上传。
5. 已有远端 ID 时使用“重新核验现有远端记录（仅GET）”，不重复上传。失败但已保存 sidecar 的执行也可以导出诊断，不代表该业务成功。

新会话尚无记录时，按钮禁用是正常前置条件；现在页面明确解释原因。模型调用或本地保存失败时应查看错误与 Trace，不能把旧模型的记录当作当前记录。

## 实际验证

| 范围 | 结果 |
|---|---|
| 修改前导航缺陷 | 新回归用例实际失败，复现 Qwen 切回 DeepSeek；原结果保留 |
| 新增回归 | 7 passed、0 failed、0 skipped（当前完整依赖环境） |
| 专项与相关原有测试 | 40 passed |
| 完整离线回归 | 595 passed、0 failed、0 skipped，另 94 subtests passed |
| 旧 DeepSeek / V3 / V2 环境 | 分别收集595项、跳过24 / 100 / 235项，均无失败 |
| Mock 冒烟 | 10条命令、32条Trace，通过 |
| 原八变异与RAG八变异 | 既有矩阵与8项RAG实验通过 |
| 实际浏览器 | Qwen→集成中心→出行助手后仍为同一千问会话，费用文字一致；深/浅主题文字可读 |
| 本轮真实模型 / Embedding / LangSmith 请求 | 全部为0 |

Qwen 的实际 SDK 通过 `MockTransport` 接收两次模拟模型响应，自己返回 `query_tickets` 调用，再接收工具结果；真实 Python 模拟工具执行并保存本地记录。网页随后经拦截的 LangSmith POST 202 + GET 200 完成匹配核验。**这是 SDK 离线协议测试，不是本轮真实 Qwen 或 LangSmith 联网验证**，没有消耗真实预算。

浏览器检查没有点击模型“发送”或 LangSmith 上传。深色输入框实测背景 `rgb(24,30,42)`、文字与文本填色 `rgb(233,237,245)`；浅色背景白色、文字 `rgb(27,38,56)`。已恢复原来的深色主题。图片为实际页面，不是生成效果图。

证据：

- [汇总](../../evidence/qwen-langsmith-ui-20261027/summary.json)。
- [修改前失败回归](../../evidence/qwen-langsmith-ui-20261027/before-fix.xml)。
- [Qwen SDK 与导出离线证据](../../evidence/qwen-langsmith-ui-20261027/qwen-sdk-export-fixture.json)。
- [实际浏览器检查](../../evidence/qwen-langsmith-ui-20261027/browser-check.json)。
- [修复后的表单截图](../../evidence/qwen-langsmith-ui-20261027/qwen-langsmith-form.png)。
- [完整离线摘要](../../evidence/qwen-langsmith-ui-20261027/offline-summary.json)。

原文件保护：本轮1638个原文件快照无变化；完整回归3933个原文件及62个V3.5.2历史证据无变化，原Chroma索引、Trace、旧回执和正式预算不变。A自测不替代B正式质量评价。

## 提交与后续验收

实现提交：`558a5cddea2dce4ed3437499f76aa8a7b5de52ff`。完整回归在该固定提交上运行，后续文档提交不改变执行代码。最终交付SHA以 `git log -1 --format=%H` 为准。

B可独立验证两模型切页、明确历史选择、费用确认隔离、无记录提示、完成运行后的导出与只读重核验。C可使用本次真实截图和既有真实运行证据展示，不能把离线HTTP桩的 `verified=true` 当作新的远端成功。本轮没有新增真实上传复验。
