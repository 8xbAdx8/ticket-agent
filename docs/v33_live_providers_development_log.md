# V3.3 多模型与可选观测开发记录

## 2026-10-25 检查与恢复点

- 实际开工分支 `codex/ticket-agent-v33-ui-dashboard`，HEAD `be3efcf934b292db5f51cadf3b48a9074a5f3b69`；仅原未跟踪 `docs/showcase/v3展示.zip`，保留原状。
- 创建用户指定分支 `feat/ticket-agent-v33-live-providers`。V1/V2 标签、原正式 5/5 账本和 B 原始层不改。
- 已核对 `Agent.chat` 十字段、calls 五字段，现有 create_agent / InMemorySaver、独立旁证、八变异和启动器。原 222 项验证证据在 `docs/evidence/v33/20261025/`，不覆盖。
- 首次执行 `scripts/verify_v33_offline.py --out artifacts/runtime/v33-providers-baseline-20261025` 时源码修改与验证重叠：所有子命令通过，但保护检查发现本轮有意修改的两个源码文件，整体报告 failed。该报告保留，不作为干净基线；最终必须在源码冻结后重新验证。
- 官方资料仅只读查阅，不属于模型请求。百炼地域/套餐地址和 Tool Calling 能力按官方文档核对，要求显式配置模型和地址，不假定账户权限。

## 2026-10-25 百炼运行时与统一 Live 旁证

- 新增 `target/bailian_runtime.py`：复用已安装 ChatOpenAI、原工具与 LangChain 循环；独立 HTTPS 地址校验、只读白名单、零重试、独立预算。配置只读 DASHSCOPE 环境变量。
- 新增 `target/live_providers.py`：简单配置选择与新验证入口共用初次三请求上限，两个 Provider 各有独立账本；不改原 DeepSeek 正式账本。
- 新增 `target/live_evidence.py`：Git SHA、case ID、实际模型、真实事件/用量/模型耗时/本地保存状态的独立 sidecar，不增加公共十字段。
- 修改 `config.py`、`target/agent.py`、`target/langchain_agent.py` 接入 bailian，保留 Mock 和 DeepSeek 路径；`target/deepseek_runtime.py` 仅加新入口可选的总预算预留与百炼秘密脱敏。`.gitignore` 增加百炼 Trace 目录。
- 新增 `tests/test_live_providers.py`，命令 `.venv-deepseek/Scripts/python.exe -m unittest discover -s tests -p test_live_providers.py -v`，实际 14/14 通过。证据暂存 `artifacts/runtime/v33-providers-core-first.txt`。真实 SDK + MockTransport，不是真实 API 验证。
- 本阶段真实模型请求 0；本轮在线条件与后续命令仍待完成。B/C 需要分别验收当前百炼与历史 DeepSeek，不共享成绩。实现提交 SHA 见后续交付表和 git log。
