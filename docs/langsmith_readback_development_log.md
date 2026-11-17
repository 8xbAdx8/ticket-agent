# LangSmith 只读复核修复开发记录

开始：2026-10-26；完成：2026-10-27，Asia/Shanghai。分支 `codex/fix-langsmith-readback`，起点 `07240af12b2a0eed3a0d9b64cfec01b6e7f18262`。

## 1. 协议与原记录审查

确认原回执的 Run ID、项目、Endpoint、载荷 SHA256 与本地 provider sidecar 对应。原代码已经把客户端 UUID 放入 POST 的 `id`，并以相同 UUID GET，没有发现取错 ID。官方 OpenAPI 明确 POST 将单条 Run 放入入库队列；原代码对立即 GET 的 404 直接 `raise_for_status()`，归为 failed，没有有限等待和独立复核流程。

一次诊断 GET 返回 200，原 ID、输入、输出与载荷哈希匹配，不再 POST。原 POST 响应 JSON及原404正文未保存，明确缺失，不反向补造。本阶段只读证据保存于新目录 `artifacts/runtime/langsmith-readback-20261026/`。

## 2. 异步读取与严格核验

- 日期：2026-10-27。
- 提交：`d83e97827818235091d640c8b5a3df5179860c51`。
- 文件：`target/observability.py`、`tests/test_langsmith_readback.py`。
- 功能：最多一次 POST；202 后的 404 才有限轮询同 ID；持续不可读为 pending；身份、权限、限流和服务端错误分开。只有 ID、输入、输出及全部上传元数据匹配才 verified。新增不可覆盖的脱敏载荷快照与逐次请求摘要。
- 验证：`python -m pytest tests/test_langsmith_readback.py tests/test_observability.py tests/test_v34_api_audit.py -q`，64 passed、3 subtests passed；确定性 HTTP 全部拦截，无真实上传。
- 限制：读取间隔为本项目工程选择，不是服务商 SLA；没有自动重传和无限轮询。
- B/C 影响：新增 pending/upload_outcome_unknown 和更准确错误类别，只影响可选远端观测回执，不改变 Agent 业务契约。演示须区分“已接受”“可读且匹配”。

## 3. 仅 GET 入口与网页防重复

- 日期：2026-10-27。
- 提交：`7c8fbcc10966892064881f799c30001684f729b7`；兼容修复提交 `198bd3156e9dddddc10369a9790e888a3a622949`。
- 文件：`web/runtime.py`、`web/conversation.py`、`web/integrations.py`、`web/trace_view.py`、`web/app.py`、`scripts/check_langsmith_export.py`、`tests/test_langsmith_readback_entries.py`。
- 功能：已有远端 ID 时复核而不再 POST；默认命令只预检，`--run` 才 GET；CLI 默认1次、显式最多3次。新核验回执单独保存。Streamlit 重载保留已有会话字段并使用新方法。
- 验证：入口与相关网页专项 81 passed，热重载补充专项后相关 33 passed。修复版 CLI 对原 ID 实际 GET 一次，HTTP 200，严格内容检查全匹配。计入本任务两个 Run GET 之一。
- 未完成：没有创建新的真实 Run 来重现短暂404；多工作空间和v2读取未在线验证。
- B/C 影响：不能通过重复点击导出来重试读取；网页显示明确复核方式，Trace 可同时查看旧失败回执与新核验回执。

## 4. 最终回归与证据保护

在固定提交 `198bd3156e9dddddc10369a9790e888a3a622949` 上运行：

```powershell
.\.venv-v35\Scripts\python.exe scripts/verify_v352_offline.py --out artifacts/runtime/langsmith-readback-20261026/final-offline-r2
```

实际结果：588 passed、94 subtests passed、0 failed、0 skipped。旧环境分别跳过24/100/234项且无失败；Mock冒烟10条命令、32条Trace通过；原八变异矩阵与RAG八变异通过。初轮在回归过程中修改入口造成旧模块缓存错误，失败日志保留，最终固定代码重跑通过。

本任务1600个原文件快照无变化；完整回归3933个原文件及62个V3.5.2证据无变化。没有修改原始Trace、原始导出回执、模型回复、预算、Chroma、B断言、main或标签。只在原Trace目录新增后续只读核验文件，另存独立交付副本。用户已有未跟踪ZIP不暂存。

实际Run GET两次、新POST零次、生成零次、Embedding零次；公开API协议文档另读一次。未记录Key或认证头。最终说明与证据路径见 `docs/handoff/v352/LangSmith_GET404根因与修复报告.md`，文档提交不改执行代码。
