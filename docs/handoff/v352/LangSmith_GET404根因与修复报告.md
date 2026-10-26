# LangSmith 导出后 GET 404：根因与修复报告

完成日期：2026-10-27，Asia/Shanghai。基线 `07240af12b2a0eed3a0d9b64cfec01b6e7f18262`；分支 `codex/fix-langsmith-readback`。

## 结论

原记录已经存在，无需重新上传。对 `c7200cf1-ecea-4f8e-bd3b-bd9d4e30c37d` 的两次只读复核均为 HTTP 200。修复版校验器确认 **Run ID、输入、输出、全部上传元数据及载荷 SHA256** 一致，返回 `remote_status=verified`、`remote_verified=true`。

确认的程序缺陷是：把“POST 已接受、GET 暂时未读到”直接归类为最终失败，没有提供保留原 ID 的只读复核入口。官方协议说明 POST 将 Run 放入入库队列；本案的“立即 404、稍后同 ID 返回匹配记录”与异步入库可见性延迟一致。但没有服务端入库日志，不能确定准确延迟、初次 404 的服务端细节，或把所有 404 都归因于延迟。

本轮 **Run GET 共 2 次、新 POST 0 次、模型生成 0 次、Embedding 0 次**。另只读下载官方公开 OpenAPI 文档一次，与 Trace API 操作分开统计。旧账本不变，不产生模型 Token；LangSmith 自身存储/读取费用未查询，未知。

## 原始证据与复核

| 项目 | 实际内容 |
|---|---|
| 本地 Trace ID | `350a018f0c3846da95e685d8ab6eda86` |
| 远端 Run ID | `c7200cf1-ecea-4f8e-bd3b-bd9d4e30c37d` |
| LangSmith 项目 | `ticket-agent-v33-review` |
| Endpoint | `https://api.smith.langchain.com` |
| 原 POST / GET | 202 / 404，原 `remote_status=failed` |
| 原本地保存状态 | Trace 与 sidecar 均已保存 |
| 载荷哈希 | `d835e0322d0bd1ca33652a3159ca720b2895f984dcc8d6197d28732dec319d68` |
| 2026-10-26 23:53:28 起的诊断 GET | HTTP 200，约 3654 ms；ID、输入、输出、载荷哈希匹配 |
| 2026-10-27 00:08:48 起的修复版 GET | HTTP 200，约 5563 ms；全部上传元数据也匹配 |
| 服务端关联 ID | 两次响应均未提供本工具白名单中的关联头；保存本地 verification_id/attempt_id，不编造服务端 ID |

原回执为 `artifacts/runtime/v33/user/web-710e38159bc3/traces/langsmith_exports.jsonl`，未修改。旁证在相同目录的 `provider_runs.jsonl`、`deepseek_runs.jsonl`，公共 Trace 在 `traces.jsonl`。新增只读核验结果保存为独立的 `langsmith_readbacks.jsonl`；不覆盖原失败回执。

可移交的真实证据：

- [原回执副本](../../evidence/langsmith-readback-20261027/original-receipt.json)。
- [首次只读诊断](../../evidence/langsmith-readback-20261027/diagnostic-get.json)。
- [修复版严格核验回执](../../evidence/langsmith-readback-20261027/verified-readback.json)。
- [冻结的脱敏载荷](../../evidence/langsmith-readback-20261027/filtered-payload.json)。
- [路径、哈希及请求计数清单](../../evidence/langsmith-readback-20261027/manifest.json)。

原程序没有保留初次 POST 响应 JSON、404 响应正文和服务端关联 ID；这些历史缺失不能补造。新程序保存状态码、响应 JSON 类型及有限字段名、响应体哈希、耗时和允许的关联 ID，不记录原始认证头或敏感响应正文。

## 官方协议核查

依据 [官方 REST 追踪说明](https://docs.langchain.com/langsmith/trace-with-api)、[实时 OpenAPI](https://api.smith.langchain.com/openapi.json) 和本机 `langsmith==0.14.8` 的 `Client.create_run/read_run` 源码：

1. `POST /runs` 的规范路径为 `/api/v1/runs`；OpenAPI 明确描述为把单条 Run 放入入库队列。202 是接受请求，不保证紧接着的读取已可见。
2. Run ID 来自创建请求的 `id`。原代码已经生成 UUID 并使用同一个 UUID 读取，这一部分没有错误。202 响应不保证提供新的 Run ID；不能把响应中的其他 ID 当作运行 ID。新代码保留客户端 ID，若返回显式但不同的 `id`，记录协议不匹配，不擅自改用它。
3. 本案 `GET /runs/{run_id}` 已实际成功；本机旧版读取方法也使用该短路径。规范 v1 路径 `/api/v1/runs/{run_id}` 的 `session_id/start_time` 是可选参数。本案未额外指定工作空间头，现有 Key 权限下读取成功，不需要猜测项目参数或换地域。
4. 官方说明，多工作空间 Key 需要明确工作空间配置。项目名用于创建时的 `session_name`；工作空间与项目不能混为一个 ID。新回执保存工作空间配置的哈希，后续复核发现变化时停止，不悄悄换工作空间重读。
5. [V2 读取协议](https://docs.langchain.com/langsmith/smithdb-sdk-migration-runs) 要求 `project_id`，且默认只返回 ID，完整核验必须显式选择输入、输出、元数据等字段。当前没有迁移到 V2，也没有自动尝试其他端点；v1 后续迁移应另行验证。
6. 官方异步入库协议允许本项目作有限读取等待，但未承诺本案的可见性 SLA，也没有规定必须采用本项目的等待间隔。最多 3 次 GET、间隔 1 秒和 2 秒，是本次工程策略；不能据此推算服务端入库耗时。

核查摘要和原始 OpenAPI 摘录哈希见 [protocol-audit.json](../../evidence/langsmith-readback-20261027/protocol-audit.json)。

## 实现与失败判定

`target/observability.py` 保留原有白名单导出与本地 Trace，增加以下有限逻辑：

| 结果 | 新行为 |
|---|---|
| POST 202 → GET 200，内容匹配 | verified |
| POST 202 → GET 404 | 仅对相同 ID 最多读取 3 次；只有后续匹配 200 才 verified |
| 持续 404 | pending_verification；仍可能是未入库、权限/工作空间或记录不可见，不能证明上传成功或永久不存在 |
| GET 401 / 403 | failed，authentication_failed / permission_denied，停止读取 |
| GET 429 / 5xx | pending_verification，准确记录限流/服务错误；不自动重试这些错误 |
| GET 超时或连接错误 | 待验证，记录脱敏错误，不自动重试 |
| GET 200 但错误 ID、输入/输出或元数据不匹配 | failed，remote_readback_mismatch |
| GET 无效 JSON/响应结构 | failed，invalid_readback_response，不输出原始正文 |
| POST 超时 | upload_outcome_unknown，保留客户端 ID，禁止自动重复 POST，后续只读核验 |

只有官方明确的 202 异步确认后的 404 触发有限延迟轮询。201 测试夹具的 404 保持原有停止行为，原测试断言不改。每次 `verify_existing()` 默认仍只有 **1 次 GET**；网页用户显式确认后才允许最多 3 次。所有 POST 均无自动重试。

新导出在本地保存不可覆盖的脱敏载荷快照 `langsmith_payloads/<run-id>.json`，后续读取使用原快照，防止系统提示或字段投影变化导致错误比对。响应只允许增加服务端额外元数据，所有本项目上传的元数据字段必须匹配。

网页中的已接受 ID 或上传结果未知记录，只显示“重新核验现有远端记录（仅GET）”。运行时也阻止同一轮再次上传，按钮连点不能绕过。新回执写入 `langsmith_readbacks.jsonl`，原导出回执保留。Trace 页面可分别查看原上报与后续只读核验。

## 如何使用

网页代码更新后重启服务；本次此前由开发工具启动的 8554 服务已完成重启，未改其他服务。打开 LangSmith 面板，已有远端 ID 时勾选只读核验同意，使用 **仅 GET** 按钮，不需要重新发送模型消息。

服务重启后原浏览器会话内存不保证恢复，但磁盘证据保留；可直接用以下命令核对本次历史 ID。首先仅预检，**不会联网**：

```powershell
.\.venv-v35\Scripts\python.exe scripts/check_langsmith_export.py `
  --receipt docs/evidence/langsmith-readback-20261027/original-receipt.json `
  --payload docs/evidence/langsmith-readback-20261027/filtered-payload.json `
  --run-id c7200cf1-ecea-4f8e-bd3b-bd9d4e30c37d
```

实际预检结果：`ready_not_run`、HTTP 0。需要再次读取时，由使用者显式增加 `--run --max-get-requests 1 --out artifacts/runtime/langsmith-user-check-20261027-01`；输出目录必须不存在，不能覆盖证据。此入口只有 GET 代码路径，没有 POST，也不调用任何模型。持有其他账号/工作空间 Key 的成员可能无法读取此历史 ID，应如实保留权限或不可读结果。

## 实际测试

| 范围 | 结果 |
|---|---|
| 新增专项 | 38 passed、0 failed、0 skipped；原始夹具、预期及参数在两个新增测试文件中 |
| 最终完整 pytest | 588 passed、0 failed、0 skipped，另 94 subtests passed |
| 旧 DeepSeek 环境 | 收集 588，跳过 24，无失败 |
| 旧 LangChain 环境 | 收集 588，跳过 100，无失败 |
| 旧 V2 环境 | 收集 588，跳过 234，无失败；缺失新依赖的项目如实跳过 |
| Mock 冒烟 | 10 条命令，32 条 Mock Trace，通过 |
| 原八变异与 RAG 八变异 | 既有矩阵通过；RAG 8 项实验通过 |
| 原文件保护 | 本任务 1600 个原文件快照无变化；完整回归 3933 个原文件及 62 个 V3.5.2 证据无变化 |
| 模型、Embedding 网络请求 | 0；离线子进程清空真实凭据并拦截非回环网络，阻断尝试 0 |

原有 B 正式测试原件、断言和成绩未修改，不用 A 自测数量替代 B 的正式评分。`Agent.chat()` 十字段、工具五字段、本地 Trace、Mock 和变异业务实现均保持原有接口。

完整离线命令为 `scripts/verify_v352_offline.py --out artifacts/runtime/langsmith-readback-20261026/final-offline-r2`。摘要、JUnit、38 项测试逐项状态在 [证据目录](../../evidence/langsmith-readback-20261027/offline-summary.json)。第一次完整回归期间修改网页入口，导致旧环境缓存了旧模块并报 ImportError；该失败如实保留。固定提交后完整重跑通过，没有修改旧测试来消除失败。

## Git 与仍需确认的事项

- `d83e97827818235091d640c8b5a3df5179860c51`：异步入库读取、错误分类、严格内容匹配及 27 项新测试。
- `7c8fbcc10966892064881f799c30001684f729b7`：网页/CLI 只读核验、防重复 POST 及入口测试。
- `198bd3156e9dddddc10369a9790e888a3a622949`：Streamlit 重载时保留旧会话数据、补当前复核方法；最终源码与测试基线。
- 随后的交付文档提交不改变上述执行代码；最终 SHA 以 `git log -1 --format=%H` 为准。

本轮没有用新 POST 在真实网络中主动制造一次“202→短暂404→200”；该时序由确定性 Mock HTTP 覆盖。真实验证仅复核原运行 ID，已成功。未来延迟超过有限等待窗口仍会进入待验证，不自动加次数或重传。V2/SmithDB 协议迁移、多地域和多工作空间在线验证仍未执行。成员 B 应独立复核这些边界，成员 C 应将真实只读回读与 Mock 时序测试分开展示。
