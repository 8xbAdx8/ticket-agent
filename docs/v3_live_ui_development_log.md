# V3 真实前端开发记录

日期：2026-10-13。分支：`codex/ticket-agent-v3-live-ui`，从已保存设计材料的 `5b606203a06f8b600f90978a6a35f76b55db9355` 建立。

## 模块：把设计稿接入实际 Agent

- 用途：原静态 HTML 设计不能发送新请求；现在 `web/app.py` 实际执行 `Agent.chat()` 并展示业务事实。
- 修改文件：`web/app.py`；新增 `web/theme.css`、`web/presentation.py`、`tests/test_web_live_ui.py`、`scripts/capture_v3_live_ui.py`、`scripts/capture_v3_live_ui.cjs`；新证据位于 `docs/evidence/v3_live_ui/`。
- 原理：仅从本轮已有 tool 消息 / LangChain tool_end 事件读取完整 JSON，与公共 Trace 顺序匹配；不再查一次工具，不增加公共字段。对 HTML 文本进行转义。
- 实际验证命令和最终结果：V3 `unittest discover` 67 项通过；原环境 Web 13 项中 9 通过、4 框架测试明确跳过；legacy smoke 10 项入口/服务检查通过；LangChain all 工具 11 轮 API 及 CLI/Web 验证通过；实际浏览器 5 轮业务通过且没有因下载/回放/清空增加 Trace。
- 开发发现：手机截图需等待侧栏动画结束；Streamlit 1.65 的下拉框显示值属于 input value，不能用纯文本定位；跨轮使用固定控件标识可能缓存旧工具标签，改为 session/轮次标识并增加断言。请求异常时隐藏旧结果，初始化异常时保留回放功能。
- 尚未完成：细粒度实时阶段、流式回复、公网部署、真实模型联网实测、B 正式评分、C 人工验收。
- 源码与运行证据 commit：`b1036aa4e536fcf21d2601672ae7af372ccc6854`。
- 对 B 的影响：入口、契约、工具/Trace 语义不变；新增 A 前端自测，不更改正式判定规则。页面控件布局调整，若 B 有额外浏览器定位脚本需确认。
- 对 C 的影响：可直接拍摄绿色工作空间的实际 Mock 功能；入口为 Streamlit，而历史 `index.html` 仍只回放。使用最新 `delivery_browser` 截图，避免把早期诊断图当最终图。

本记录与 [真实前端使用说明](handoff/v3/V3真实前端使用说明.md) 同步保存。后续文档/核对提交属于同分支文档补充；`git log -2 --oneline` 可查看对应记录。最终提交 SHA 在最终回复提供，不在自身 commit 中循环引用。
