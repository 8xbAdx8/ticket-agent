# V3.6 Git 与离线回归

- 起始分支 `codex/live-eight-tools-20261028`，起始 HEAD `63b0988db6bb01cef29938a9ec2b5e7c6c61d6a1`；原有 19 个已跟踪修改、17 个未跟踪文件（包含用户 ZIP）。
- 项目外备份 `ticket-agent-v36-backup-20261028-001`：36 个原始变更/未跟踪项已复制并逐项 SHA-256 验证。备份包含用户 ZIP，不加入 Git。
- 无 reset/clean，原始历史、标签和测试证据未改写。忽略文件扫描遇到一个临时目录无权限，未宣称完整清点；运行数据留在原处。
- 扫描当前改动及本进程三个配置密钥的精确值未命中；用有限模式检索 Git 历史没有匹配，但不能保证所有历史秘密均已识别。
- 依赖相关改动合并为恢复基线 `f7f72cd`；确认 `c1bf721`、RAG 订单绑定 `d340360`、审计展示及关联 `b01b6e7`、跨轮锁座审计 `e1360f6`。
- 最终源码提交 `e1360f6`：`.venv-v35/Scripts/python.exe -m pytest tests -q --junitxml=artifacts/runtime/v36-stabilization/offline-final.xml`，768 passed，117 subtests passed，0 failed。使用 `PYTHONUTF8=1`、`TICKET_DISABLE_LOCAL_SECRETS=1` 和关闭 LangSmith。
- 测试含 Streamlit AppTest 与启动健康检查；没有声称完整真实浏览器 E2E。独立审计的正式成绩仍由 B 产生。
- Chroma 基线6个文件，回归前后逐文件 SHA-256 字节一致；未执行本轮逻辑向量全量比对。未全面核对所有历史数据库和账本的变更，不能声称全量一致。
