# V3.2 持续开发记录

日期均为 2026-10-18（北京时间）。开发分支 codex/ticket-agent-v32-audit-mutations；恢复点 7e2947f0e82da63035ec6721106780e19d747e98。保留用户原有未跟踪 docs/showcase/v3展示.zip。没有读取/修改 Codex 认证配置，没有新增模型请求。

| 完成模块 | 文件及原理 | 实际验证 | 提交 | 对 B/C 的影响与问题 |
|---|---|---|---|---|
| 纯旁证与断言 | diagnostics.py、test_diagnostics.py；保守文本分类、权威快照、哈希大对象 | unittest tests.test_diagnostics：首轮 9 项通过 | 94ca27d | 新增独立文件，不改十字段；语义不确定保留未知 |
| 调用关联与 M7 | trace/agent/langchain_agent/tools/fault_injection/providers；真实派发观察、原始和可见结果分开 | test_agent + test_live_faults + diagnostics：32 项通过 | aefda78 | 新 last_audit_report；Legacy 原模型前参数不可独立还原 |
| 并发隔离 | mock_core.database_scope、concurrency_probe.py、专项测试；屏障而非随机延时 | 首轮 5 项有一失败：workers=0 被默认值覆盖；修正后并发+原 core 共 9 项通过，日志保留 | e1a9a91 | 正常事务/唯一性不改；缺陷只在临时影子库 |
| 证据语义与脱敏 | 观察不到的执行记 null；凭据脱敏；七变异证据和恢复判定测试 | 新诊断/审计/Web/并发 28 项通过；后续补历史匹配后当前专项 24 项通过（未含并发） | 54d3040 | 原契约与正式断言保持；不能自称恢复就计分 |
| Web/证据闭环 | audit_view.py、app.py、test_web.py、verify_v32_offline.py | Web 4 项通过；第一轮脚本25记录+8样本通过、真实请求0 | baeb16e | 八开关及独立并发按钮；旧数据不造诊断 |
| 完成语义与回放 | diagnostics.py、Web及测试；安全停止/无引用不算业务完成，按哈希关联 | 首轮全回归179项、pytest179+78子断言及B原101/100/55均通过后发现统计边界，定向修正24项通过 | 222947e | 不覆盖首轮证据；以 final 目录复核修正后的统计 |

开发中另外发现测试夹具把有票 G7301 当监控目标，原后端正确拒绝；修正测试准备为既有无票 G101 后通过，没有削弱业务校验。首轮 Web 清理断言使用错字段，修正为实际 resources_cleaned；不是隐藏运行失败。

最终证据脚本：`python scripts/verify_v32_offline.py --out docs/evidence/v32/20261018-final` 实际成功，25记录、8规则样本、0请求。最终回归日志、源码哈希、保护文件核对在该目录 offline/。文档与证据在后续单独 Git commit 中交付，提交列表以 git log 为准，不伪造自引用 SHA。

未完成：新增真实 DeepSeek 验证、B 独立正式新规则验收、C 人工录屏。GitHub fetch 因本机 127.0.0.1 代理连接失败；最终 push 结果另记交付状态，不能声称已上传。原 main/V1/V2/V3 标签和历史证据不动。
