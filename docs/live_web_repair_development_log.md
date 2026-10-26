# 日常 Live 与 LangSmith 页面修复记录

日期：2026-10-26。基线：`5e13a0b85cf9b42fd262b923046e2972f47e2758`。新分支：`codex/fix-live-web-and-langsmith`。

用户明确授权日常手动对话不限制累计请求次数；本轮未代发自动付费请求。以下记录依实际源码、Git 与离线输出整理，不改变 B 的正式成绩。

## 模块一：普通网页与验收账本解耦

- 提交：`fd71460`。
- 文件：`target/live_providers.py`、两个 Runtime、`web/runtime.py`、`web/conversation.py`、`web/integrations.py`、`target/observability.py`、两启动脚本、`tests/test_manual_live_web.py`。
- 原因：DeepSeek 旧账本格式被统一预算层拒绝；Qwen 页面使用了已满的 V3.5 账本。启动器关闭 SDK 自动上传又被 UI 误当成关闭手动导出。
- 原理：仅普通用户新会话选择 interactive 配置，两个 Provider 分开累计记账，累计上限为 0（无限）；工具仍用已有两工具白名单。验收 profile 和旧账不变。LangSmith 手动导出设置独立保存，SDK 自动回调始终关闭。
- 实际验证：针对性首轮 33 passed；兼容修正后完整第二轮 545 passed、89 subtests passed，0 failed、0 skipped。命令与原始日志：`artifacts/runtime/live-web-repair-20261026/offline-r2/`。
- 开发发现：完整第一轮 543 passed / 1 failed，原因是把旧程序显式创建的测试会话也禁用了；缩小禁用条件至历史验收会话，未改变原测试断言。初轮证据保留在 `offline/`，公开摘要保留在交付证据目录。
- B/C 影响：新日常网页不再占用正式限额；实验室与正式脚本的限额继续保留。页面移除过期横幅，并显示实际失败类别。LangSmith 需预览与同意才上传。
- 未完成：本轮未自动请求千问，也未请求 LangSmith 远端核验。

## 模块二：后续询问被误作票务事实

- 提交：`22a1c75cffb96400a148ba83f73bbdfc00a7a690`。
- 文件：`target/reply_consistency.py`、`tests/test_ticket_follow_up.py`、两份独立证据 JSON。
- 实际现象：用户在修复后的 localhost 手动发送查票，DeepSeek 两次 HTTP 200、query_tickets 实际成功，25 个业务字段和 3 个身份匹配；仅礼貌后续询问触发 indeterminate。
- 原理：有限识别没有具体车次/数字/可用性断言的后续信息请求。带身份、数值或数据声明继续原有核验；错误时间的反例仍 failed。原始模型输出及历史旁证不改写。
- 实际验证：专项 79 passed、2 subtests passed；最终 `scripts/verify_v352_offline.py --out artifacts/runtime/live-web-repair-20261026/final-offline` 为 550 passed、91 subtests passed，0 failed、0 skipped。旧环境兼容、Mock 冒烟、原变异与 RAG 变异均通过。
- 原记录：`docs/evidence/live-web-repair-20261026/user-manual-deepseek-query.json`；新离线判定：同目录 `offline-replay.json`。未进行修复后的真实重发。
- B/C 影响：后续追问不应误当车次事实；B 仍独立评估自然语言准确性，C 不得把离线复算称为新 Live 验证。
- 未完成：泛化语义判断仍有限，复杂隐含事实仍可能 indeterminate，需要 B 复核。

## 交付文档与安全核对

运行方式见 `docs/handoff/v352/在线页面修复与日常使用说明.md`；启动总说明同步更新。最终代码测试 HEAD 为 `22a1c75`，其后文档提交记录可通过 `git log --oneline -3` 查到。

原 Chroma/历史证据/旧账本保留；本任务额外 1542 个原文件快照无变化，完整回归 3933 个原文件及 62 个 V3.5.2 证据文件无变化。新增提交文件与派生日志检查实际配置的三个秘密值，未发现明文匹配。项目本地导出开关仅存布尔值，被 Git 忽略；未暂存用户已有的 `docs/showcase/v3展示.zip`。

此次开发自动生成、Embedding、LangSmith 请求数均 0。观察到用户手动 DeepSeek 请求 2 次、Token 总计 2215，费用未知，独立日常账本记录；不计为本轮自动化回归。旧正式 DeepSeek 5/5、V3.5 Qwen 4/4、V3.5.2 共享生成 4/4 和 Embedding 5/5 均保留。
