# Ticket Agent V3.9.2 — Phase 0 审计与恢复依据

- 日期：2026-11-03（Asia/Shanghai）
- 仓库：`D:\codexproject\ticket-agent`
- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 暂存区：空；工作区有既有修改/未跟踪成果；未执行 reset/checkout/覆盖。
- 本文件仅记录审计，不代表任何 Phase 1–6 修复已完成。

## 1. 原版 UI 来源

**可靠来源：**

1. `git show HEAD:web/app.py`：原版入口，`出行助手` 直接调用 `web.conversation.user_page()`，没有铁路页面二选一。
2. `web/conversation.py::user_page`：原版聊天主区、输入框、确认卡、历史回放。
3. `web/user_layout.py`：原版顶部栏、右侧 `rail`、移动端信息开关。
4. `web/user_layout.css`、`web/design.css`、`web/presentation.py`：原版视觉与组件。
5. `docs/reviews/Ticket-Agent-V3.7-Phase5-UI-Redesign-Report.md` 与
   `artifacts/runtime/v37-phase5-ui-redesign-20261101/`：阶段五四规格截图/测量证据。

**当前偏差：**

- 当前未提交 `web/app.py` 在 `page == 出行助手` 时优先调用 `web/railway_simulation.page()`。
- `web/railway_simulation.py` 是独立的铁路工作区（主区/右栏/场景/铁路会话），不是原版四面板。
- 这是 V3.9.1 本轮新增的未提交改动，不是 Git HEAD 的原版行为。
- **恢复方式**：只恢复 `web/app.py` 的 `出行助手` 路由到 `web.conversation.user_page()`；不重置/覆盖其他文件。
- `web/railway_simulation.py` 保留但不再是用户工作空间入口；不删除 V3.9 业务服务。

## 2. 原版 UI 结构（需保留）

- 左侧：模型设置、工作空间导航（用户/开发者/测试）、主题、历史会话。
- 主区：欢迎/能力卡、四快捷入口、聊天消息、政策证据、确认卡、聊天输入框。
- 右栏：本次行程摘要、我的订单、推荐车次、用户功能、政策速查、退款面板、运行详情。
- 移动端：单栏 + “相关信息/常用功能”开关；无横向页面溢出。
- 必须保留原 CSS、组件 key、聊天交互和右侧既有功能。

## 3. Agent / V3.9 现状

- `target/agent.py` 与 `target/langchain_agent.py` 都已在 definitions/adapt_tool 层接入 `target.v39.registry`，但：
  - `target/v39/registry.denial` 对 `ctx.provider != 'mock'` 返回 `V39_LIVE_NOT_AUTHORIZED`。
  - `target/v39/registry.definitions` 需要 `CURRENT` 上下文和 `SERVICE` ContextVar；原版 user_page/Conversation 没有设置这些。
  - 原版 `Conversation._send` 不创建/绑定 V3.9 Context/Service。
  - `effective_config.tool_whitelist` 只来自旧工具 `TOOLS`；V3.9 工具不会进入 LangChain 工具集。
- `target/langchain_agent.py` 的 `adapt_tool` 已能解析 `tools.TOOLS + railway.TOOLS`；但构造时 V3.9 工具只在 `railway.definitions` 可用时加入。
- 结论：**必须新增 V3.9 session bridge**，在原始 `Conversation._send` 内绑定 Context/Service/EffectiveConfig；不是重写 Agent。
- V3.9.1 业务服务（D9、退款、改签、账务、库存、提案、确认、幂等）完整保留，不做替换。

## 4. Provider / 真实 API 现状

- 已存在 Qwen（Bailian/OpenAI 兼容）与 DeepSeek Provider、模型设置、User 级 API Key。
- `target/deepseek_runtime.py::allowed_tools` 在 `full_sandbox` 只返回旧 `TOOL_NAMES`，不含 V3.9 11 工具。
- `target/bailian_runtime.py` 使用同一 `allowed_tools`，同样不含 V3.9。
- `target/deepseek_runtime.py`/`bailian_runtime.py` 的 HTTP guard 会拒绝未列入 permitted 的工具。
- `target/langchain_agent.py` 会检查 `set(names) <= allowed_tools(settings)`；不扩展则真实模型无法获得 V3.9 工具。
- User 级配置检查（不打印密钥）：DeepSeek `True`、Qwen `True`；进程环境当前未加载 Key，CMD/PowerShell 启动器会从 User 环境刷新。
- Qwen base URL：`https://cn-beijing.maas.qwencloudapi.com/compatible-mode/v1`；model `qwen3.8-flash`。
- 结论：
  - 需扩展 `allowed_tools(full_sandbox)` 到旧 8 + V3.9 11。
  - 需让 V3.9 Context 的 `provider` 允许真实 Provider，同时保留 Baseline/权限检查。
  - 禁止静默回退 Mock；API 失败显示错误。
  - API Key 不写文件/日志/截图。

## 5. 静态 GTFS 现状

- Adapter：`target/v39/static.py`。
- DB：`artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite`；SHA `e32f0cd4...`。
- GTFS ZIP：SHA `3877dbc0...`。
- 3169 站、11588 有效车次、107669 经停、187 隔离。
- 不得复制/重建；所有入口保持 `Agent → Registry → Static Adapter → GTFS SQLite`。

## 6. 数据库与启动器现状

- `web/railway_simulation.py` 默认路径 `data/v39/simulation-v391.sqlite`。
- `scripts/launch_app.py` 当前只设置旧 `AGENT_DB_PATH`/`TRACE_DIR`，**没有设置** `RAILWAY_SIM_DB_PATH`。
- CMD 只设置 `RAILWAY_SIMULATION_ENABLED=1`，不设置 V3.9 DB 路径。
- `target/v39/store.py::safe_path` 仅允许 `data/v39` 或 `artifacts/runtime/v39-implementation-*` / `v391-d9-lifecycle-*`；新增独立 `v392-*` 运行目录需最小白名单扩展。
- 风险：在线/离线 CMD 会共用 `data/v39/simulation-v391.sqlite`，并可能因 worker lease 互相阻塞；不能覆盖 `simulation.sqlite`、`simulation-v391.sqlite` 或 GTFS DB。
- Phase 4 要求：launcher 明确设置独立 `RAILWAY_SIM_DB_PATH`，启动日志打印实际路径，初始化前后核对 SHA；不删除旧库。

## 7. 保护资产现状

- HEAD/分支未变；暂存区空。
- 既有 49 项工作区变化/未跟踪成果保留；不得 reset/checkout。
- 4056/5538 API 账本已有 3735 字节追加，当前 274579 bytes / `87cfd3ed...`；来源未归属，保留。
- 正式 103/B、Bridge、V1.0–V1.2.2、历史失败批次保持。
- 已有 V3.9.1 统一页面不作为回滚依据；只恢复 UI 路由。

## 8. Phase 1–6 实施计划（下一步）

1. Phase 1：恢复 `web/app.py` 到原版 `user_page` 路由；保留 V3.9.1 页面文件但不作为入口；跑原版 UI 四规格。
2. Phase 2：新增 V3.9 session bridge，在原 `Conversation._send` 内绑定 Context/Service/EffectiveConfig；让旧 Agent 调用 11 个工具。
3. Phase 3：扩展 Provider allowed_tools 与 Context provider 检查；Qwen/DeepSeek 各自真实 API 最小测试；失败明确 BLOCKED。
4. Phase 4：launcher 独立 `RAILWAY_SIM_DB_PATH` + Store 白名单最小扩展；保留旧库。
5. Phase 5：原版 UI 四规格、双模型、双引擎、T057–T076、旧回归、两 CMD。
6. Phase 6：报告、manifest、独立审查 ZIP；不调用 Bridge/Harness。

## 9. 审计结论

- 原版 UI 可从 HEAD 可靠恢复，不需要重做设计。
- V3.9.1 业务能力可保留，不需要回退 D9/账务/库存。
- 真实 API 与 V3.9 工具的主要断点是 **allowed_tools + Context/Service + effective config**，不是重写 Provider。
- 数据库路径必须由启动器隔离，不能使用产品默认库。
- 在完成上述最小接线前，不得宣称 V3.9.2 LIVE_API_VERIFIED 或原版 UI 已恢复。
