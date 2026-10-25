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

## 2026-10-25 LangSmith 显式导出

- 运行时提交 `73ea353`。新增 `target/observability.py`，使用官方 REST `/runs` 创建完成记录并 GET 原 ID 回读；已安装 SDK 支持自动批处理，故本项目为明确统计/零重试选择直接 httpx，不启用框架全量 callback。
- 两道开关：环境显式启用 + 每次导出 consent。上传前展示范围，仅本轮只读消息/结果及元数据；过滤未知字段、秘密值、认证头、手机号/邮箱/身份证格式及 reasoning_content，不传完整会话、订单或旁证全文。任意姓名等自由文本无法保证自动识别，仍须人工检查。
- 远端回执与公共 Agent/本地审计分离，POST 接受不等于已验证，只有 GET 内容/ID/摘要匹配才 verified；失败不改变原模型结果。不发送后台请求或自动重试。
- 命令 `.venv-deepseek/Scripts/python.exe -m unittest discover -s tests -p test_observability.py -v`，11/11 通过，证据 `artifacts/runtime/v33-providers-observability-first.txt`。全部使用 MockTransport，真实 LangSmith 上报 0，不标远端验证成功。
- B/C 影响：可选新导出接口，不变更十字段或正式判定；用户未显式配置/确认时仍完整本地运行。

## 2026-10-25 命令入口与前端接线

- LangSmith 模块提交 `6ec4642`。新增 `scripts/live_providers.py`：默认只预检，`--serve` 只启动 localhost，必须显式 `--run` 才生成。初次两个 Provider 合计最多 3 次；一次工具闭环通常占 2 次。没有执行任何 `--run`。
- `web/app.py`、`web/runtime.py`、`web/conversation.py`、`web/laboratory.py`：四模型选择，新 Provider 新建会话/库；新 Live UI 使用独立账本和共用初次三次上限；测试 case ID 入独立旁证。已有启动脚本不修改。
- `web/integrations.py` 和 `web/comparison.py`：显示百炼已实现/真实未验证；LangSmith 的未配置、关闭、已配置未验证和实际回执分别呈现；可查看当前两 Provider 的独立原始记录，未生成成绩排名。
- LangSmith 导出前显示过滤后的实际内容和范围，独立按钮才上传，local/remote 状态分别保存；协议使用 REST POST + GET，无后台批量/重试。导入/换页/切模型不联网。
- 原 V3.3 34 项自测重新通过（`artifacts/runtime/v33-providers-ui-first.txt`）；新增 `tests/test_live_provider_ui.py` 的 6 项模型选择/缺 Key/隔离/重绘/CLI 预检测试通过（`artifacts/runtime/v33-providers-new-ui-first.txt`）。命令均 `python -m unittest discover -s tests -p 对应文件 -v`；API 0、LangSmith 上报 0。
- 同步收紧百炼官方域名范围（不允许任意用户 OSS 域名）、分类 400 余额/模型错误；Qwen 请求显式关闭思考模式，其他模型的协议支持仍须真实验证。记录真实请求起始时间，并允许失败时导出已保存的本地 sidecar，仍不改公共契约。

## 2026-10-25 联调边界修复

- 前端/命令模块提交 `3a94ec0`。发现旧离线批次只排除 DeepSeek，新增百炼后会混入；改 `web/evidence.py` 排除全部 `_live`，新增断言验证两个真实 Provider 均不计入离线成绩。
- `web/trace_view.py` 增加按唯一 Trace ID 关联当前 Provider 元数据及 LangSmith 回执，不改变旧 JSON。百炼 400 的 Arrearage/模型/Key 代码进一步分类，拒绝非模型用户域名。
- `target/deepseek_runtime.safe_text` 复用既有通用凭据脱敏，涵盖新增 Provider/LangSmith 与已加载配置中的凭据，正常业务参数不改。
- 新增测试后，命令 `python -m unittest discover -s tests -p test_live_provider*.py -v` 22/22；`python -m unittest discover -s tests -p test_observability.py -v` 12/12。日志 `artifacts/runtime/v33-providers-integration-final.txt`、`v33-providers-observability-final.txt`。合计新增 34 项 A 自测，不是 B 正式成绩。
