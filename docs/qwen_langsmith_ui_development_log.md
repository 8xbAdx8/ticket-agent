# Qwen / LangSmith 界面修复开发记录

日期：2026-10-27。基线 `f9b7d4b51cd0af4a324adf21836b488b890a4fd9`；新分支 `codex/fix-qwen-langsmith-ui`。

## 实现与自测

- 功能：修复切页后当前会话从 Qwen 退回 DeepSeek、LangSmith 无记录时没有前置提示，以及深色控件交互态对比度。
- 修改文件：`web/conversation.py`、`web/design.css`；新增 `tests/test_qwen_langsmith_ui.py`。
- 核心原理：把当前会话选择存到不会被控件生命周期清理的状态键；原下拉框键继续兼容。切回页面时恢复当前会话，不按新默认模型改写历史会话。费用确认随会话隔离。导出仅使用当前 Provider 的已有运行记录。
- 修改前：新增导航回归实际失败，证明当前会话ID退回原DeepSeek。证据 `artifacts/runtime/qwen-langsmith-ui-20261027/before-fix.xml` 保留。
- 修改后命令：`python -m pytest tests/test_qwen_langsmith_ui.py tests/test_langsmith_readback_entries.py tests/test_live_provider_ui.py tests/test_v33_app.py -q`；实际40 passed，其中新增7项。
- SDK专项：实际ChatOpenAI/LangChain执行，只用假Key与MockTransport；模拟模型2次请求、实际Python工具1次、LangSmith模拟POST/GET各1次。真实外网请求均0。
- 提交：`558a5cddea2dce4ed3437499f76aa8a7b5de52ff`。
- B/C影响：当前模型、会话与费用提示保持一致；空运行不能导出，但现在明确说明原因。模型来源不一致时停止导出。B原断言与Agent契约不改。
- 未完成：没有新增真实Qwen调用或LangSmith上传，不把离线核验标为真实远端验证。

## 浏览器与完整回归

旧8554服务仍缓存原Python模块，已只重启通过父子进程链核对的本任务服务。新服务中实测Qwen→集成中心→出行助手，会话与徽标仍为Qwen；输入、展开面板在深浅主题可读。没有点击付费发送或上传，截图与DOM检查在新证据目录。浏览器恢复深色主题。

完整命令：

```powershell
.\.venv-v35\Scripts\python.exe scripts/verify_v352_offline.py --out artifacts/runtime/qwen-langsmith-ui-20261027/final-offline
```

实际595 passed、94 subtests passed、0 failed、0 skipped。旧环境兼容、Mock冒烟、原八变异及RAG八变异均通过。原文件1638项额外快照、完整回归3933项原文件和62项既有V3.5.2证据均无变化。原预算、索引、历史Trace、B文件与用户未跟踪ZIP保留。

使用说明：`docs/handoff/v352/千问LangSmith界面修复说明.md`。最终文档提交不改变已测试实现，Git最后提交可用 `git log -1 --format=%H` 核对。
