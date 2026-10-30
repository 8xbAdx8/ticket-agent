# Ticket Agent --- DeepSeek Harness 交接任务书

> 更新日期：2026-10-30。接手时先读本节，再按用户的新指令工作。
> 本文是工程交接，不自动授权新的 UI 重构、真实 API 验收、Git 提交或推送。末尾旧版 UI 任务书仅供追溯，不是当前待执行任务。

## 1. 先明确你接手的是什么

你接手的是已存在的 Ticket Agent 工作区，不是新项目。项目集成了模拟票务 Agent、Streamlit 用户端、开发者端和测试控制台。

- 项目目录：`D:\codexproject\ticket-agent`。
- 本次核对分支：`feat/ticket-agent-v36-stabilization`。
- 本次核对 HEAD：`04b9a42a47e8ca81ce77cca352655708a1e1ea63`。
- **工作区存在大量未提交修改及未跟踪文件。HEAD 不是当前全部功能的快照。只克隆这个 SHA 无法得到本次追问实现。**
- 成员 A 负责 Agent 开发和本模块自测；成员 B 负责正式测试与评价；成员 C 负责验收、报告和视频。不要把 A 自测写成 B 正式成绩。

无法访问目录时，说明需要挂载或提供完整工作区；不能假装已经运行或修改代码。

当前项目状态以 `README.md` 顶部为入口。本文重点交接最近完成的智能追问与连续对话修复，不代替对全项目各功能的验收。

**交接时发现的后续修改，必须先处理版本边界：**

- 编写期间一次采样中，`target/followups.py` 的 SHA-256 为 `21d7be94f359f281ac423cf141e68594d48b457fc3e4579be047b4e49bcc98d4`。稍后复查文件又发生变化，说明工作区仍有并行修改；这个哈希只代表该次采样，不是冻结后的当前版本。接手时重新计算。
- 最近连续性测试汇总 `result.json` 记录的该文件 SHA-256 为 `a4c0f47dec21bbc7e5fd17d97b8ffee1136a8879dcb666c8a400e3e0a354d1c8`；不是 CRLF/LF 转换造成的差异。
- 当前代码还新增了 `executed_query()`、`read_all()`、`emit_event()` 以及更细的追问生命周期事件和 `followup_id`。`executed_query()` 的注释指向“把历史工具结果回传事件误认成本轮实际查票，导致后续证据回退失效”的问题；这是代码中的修复说明，本次没有独立运行验证。
- 该次采样中，`web/runtime.py`、`web/conversation.py`、`tests/test_followups_continuous.py` 与最近连续性测试记录的哈希一致。没有覆盖上述后续代码，也没有确认其修改来源或整体完成状态；不据此保证之后的工作区继续不变。
- **因此，下文通过数是已有受测快照的成绩，不是当前追问模块最新字节的验收结论。** 接手后先核对该文件的后续变更并运行专项，不能因为 `prompt_version` 仍是 `/2` 就认为代码完全相同。
- **该版本边界已在本轮复验后闭合：当前哈希、根因与真实十轮结果见第 10 节。**

## 2. 已有模块与事实边界

| 模块 | 接手入口 | 说明 |
|---|---|---|
| 对外 Agent | `target/agent.py`、`docs/contract.md` | 保持团队公共接口 |
| 模型执行 | `target/langchain_agent.py`、`target/deepseek_runtime.py`、`target/bailian_runtime.py` | Legacy/LangChain Mock、DeepSeek/Qwen 的现有实现，不另建 Provider |
| 模拟工具 | `target/tools.py` | 八个工具复用现有 Schema、分发、确认与业务校验 |
| 用户端 | `web/conversation.py`、`web/runtime.py` | 聊天、会话、工具结果、追问、操作确认 |
| 开发者端 | `web/developer_workspace.py`、`web/run_view.py` | 配置、事件与运行证据展示 |
| RAG 与证据 | `web/policy_interaction.py`、`target/rag_service.py`、`target/run_events.py` | 检索状态、文档证据、独立运行事件 |
| 离线测试 | `scripts/v37_tests.py`、`scripts/regression_center.py` | 前者支持专项，后者创建隔离副本执行完整回归 |

八个工具为：`query_tickets`、`monitor_seat`、`lock_seat`、`create_order`、`pay_order`、`cancel_order`、`query_order`、`search_policy`。工具实际可用性以当前运行配置和后端校验为准。

模型 API 可以是真实服务，但票务、锁座、订单、支付均为模拟，不连接真实 12306、航司或支付系统。RAG 千题工程是另一条工作线；README 记录的 430 条已核对、570 条待复核，不能写成千题全部通过。

## 3. 最近实际完成的智能追问

### 用户使用方式

选择 DeepSeek Live 或 Qwen Live，勾选原有真实请求确认框，再点击发送。回答后自动显示“你可能还想了解”。**没有独立的追问开关，也没有额外调用次数提示文案。**

点击建议沿用当前会话，提交为普通用户消息，仍走原有费用确认、工具权限和模拟操作确认流程。不能把点击追问接成直接执行工具。

### 当前实现方式

1. `Conversation.send()` 完成主对话，得到公共 Trace 与审计记录。
2. `_record_followups()` 复用当前 Agent 的模型与设置，调用 `target/followups.py`。
3. 从真实工具结果、政策证据构建候选，过滤已问过的问题。班次比较使用已有车次、席别、日期、出发/到达、票价与余票字段。
4. 最多将 6 个候选交给同一 Provider 的模型，以 JSON 选择 2～3 条；只接受候选内的问题，拒绝无依据的新内容。
5. 每轮追问最多增加 1 次模型请求，零重试。继续经过现有 HTTP 守卫与用量统计；不为追问调用工具、Embedding 或 LangSmith。
6. 无授权、模型异常、超时、格式错误、空结果、Token 预算不足等情况使用确定性规则回退。Mock 始终离线。
7. 每条回答追加保存自己的追问。刷新、历史查看只读已保存记录，不重新生成。

这是“证据候选构建＋模型选择”的 MVP，**不是任意自由生成的通用推荐器**。没有足够证据时可以不给建议，不能为了满足数量编造问题。生成不足两条时不凑数；历史推荐经过已问过滤后即使只剩一条，页面仍显示这一条。

### 连续追问原问题及修复

| 原因 | 已实施修复 |
|---|---|
| 初版只有少量全局模板，第一轮之后容易用尽 | 增加依据实际班次字段的逐对比较问题，继续过滤已问的问题 |
| 下一轮模型不重新查工具时，没有当前轮新证据可供推荐 | 显式传入同会话成功运行的历史 run_id，复用原始证据快照，保留源事件与源 run_id |
| 页面从旧回答开始去重，旧推荐遮住最新推荐 | 最新回答优先拥有重叠推荐，旧回答不能先占用最新的问题 |
| 两条建议点掉一条后，剩余一条被整组隐藏 | 保留剩余有效问题的展示，不修改已保存快照 |

历史快照不能被说成当前库存；本轮查询返回空结果时，不能拿旧库存填补；不同会话的证据不能复用。失败或检测到车次来源异常的历史运行不能自动成为推荐依据。

## 4. 需要保护的关键代码

| 文件 | 关键入口 | 修改时注意 |
|---|---|---|
| `target/followups.py` | `candidates()`、`generate_and_save()`、`read_record()` | 提示词版本当前为 `ticket-followups-mvp/2`；保留来源约束、单次调用与保存去重 |
| `web/runtime.py` | `Conversation.send()`、`_record_followups()`、`followups_for()` | 推荐挂在成功对话后；终止事件仍为 `agent_returned`；不能让辅助失败覆盖主回答 |
| `web/conversation.py` | `execute()`、`_followup_suggestions()`、`_consume_followup()`、`_conversation()` | 保留当前会话校验、点击去重、最新回答优先、原有确认流程 |
| `web/policy_interaction.py` | `policy_view()`、`followup_questions()` | 继续复用实际政策证据及规则回退，不从最终文字猜测来源 |
| `web/design.py` | 追问事件标签 | 开发者端使用已有运行事件，不能伪造模型思考过程 |
| `tests/test_followups_mvp.py` | 初版生成、回退、保存、点击与协议专项 | 两家 SDK 走离线 HTTP 替身，不是真实在线成绩 |
| `tests/test_followups_continuous.py` | 十轮点击、超时恢复、历史重开、前文证据隔离 | 最近新增连续性专项 |

本轮连续性修复实际修改了 `target/followups.py`、`web/runtime.py`、`web/conversation.py`，新增 `tests/test_followups_continuous.py`，更新 `README.md`。不要覆盖这些尚未提交的工作。

## 5. 数据保存和公共契约

会话运行目录由 `Conversation` 创建，不要硬编码某个旧会话路径。查看该对象的 `sid`、`root`、`trace_dir` 定位：

- `traces.jsonl`：公共对话 Trace。
- `run_events.jsonl`：实际执行事件，追问事件使用原对话同一个 run_id。
- `followups.jsonl`：每轮独立的追问快照。

追问快照包含 `session_id`、`run_id`、`provider`、`model`、`prompt_version`、`input_hash`、`public_trace_sha256`、`suggestions`、`generation_source`、`fallback_reason`、`grounding`、`source_event_ids`、`source_run_ids`、辅助请求数、Token 与耗时等。未知用量保持未知。

回放同时匹配会话、run_id 与公共 Trace 哈希，读取原版本保存的问题；不能用今天的模型重新生成旧记录。

必须保留：

```python
from target.agent import Agent
agent = Agent()
result = agent.chat(session_id, message)
```

返回十字段：`session_id`、`provider`、`model`、`user_msg`、`steps`、`tool_sequence`、`reply`、`finish_reason`、`tokens`、`total_latency_ms`。

`steps[].calls[]` 五字段：`tool`、`args`、`ok`、`latency_ms`、`result_preview`。**追问不加进这两个公共结构，而保存在独立文件中。直接调用 Agent.chat 不等于经过用户端追问服务。**

`finish_reason=stop` 只表示循环结束，不等于业务成功。辅助追问用量与主对话用量分别保存，不能悄悄改写主 Trace 的 Token 或延迟。

## 6. 已经执行的验证：分清版本和来源

以下均为现存历史日志，不是编写交接书时重新执行的测试；当前追问模块存在第1节所述后续修改。

| 范围 | 实际结果 | 证据目录 |
|---|---|---|
| 最新连续性专项 | 3 项、23 子项通过；0 失败 | `artifacts/runtime/followups-continuous-20261030-121139/special-r1/` |
| 最新相关离线回归 | 51 项通过；0 失败、0 跳过 | 同父目录 `related-r1/` |
| 最后载荷脱敏调整后复验 | 1 项、10 子项通过 | 同父目录 `payload-final/` |
| DeepSeek 十轮点击 | 10 轮各有2～3条推荐，模型选择均成功 | 同父目录 `rounds-r1/deepseek.json` |
| Qwen 十轮点击 | 10 轮各有2～3条推荐；第5轮模拟超时，规则回退后继续 | 同父目录 `rounds-r1/bailian.json` |
| 前一版 MVP 完整回归 | 956 项、124 子项通过；0 失败、0 跳过 | `artifacts/runtime/regression-center/20261030-115605-6c331731/` |

十轮测试使用真实 SDK 和现有模拟工具，但 HTTP 层是 `httpx.MockTransport`：每个 Provider 共30次**模拟** HTTP 请求，20次主对话加10次追问；不能写成30次真实 API。

最近两轮追问开发的真实模型、Embedding、LangSmith 请求均为 **0**。前一版的956项不能当作连续性修复后的完整回归；最新修复后只执行了表中专项及相关回归，没有重新跑完整 pytest。

汇总与源码哈希：`artifacts/runtime/followups-continuous-20261030-121139/result.json`。该文件中的哈希对应当时工作区；README 后续更新交接说明可能变化，不代表运行代码已重新验证。

## 7. 接手后如何启动和复测

先确认实际 Git 状态和本轮涉及的少数文件，不需要再做全仓盘点：

```powershell
cd D:\codexproject\ticket-agent
git branch --show-current
git rev-parse HEAD
git status --short
git diff --check
```

运行用户端：双击根目录 `启动_离线模式.cmd` 或 `启动_在线模式.cmd`。在线需要用户本地配置，缺配置不能假装已联网或静默回退 Mock。已有环境为 `.venv-v35`；换机器还需要按依赖说明安装环境。

追问专项离线复测（输出目录必须是新目录）：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$handoffRun = Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv-v35\Scripts\python.exe scripts/v37_tests.py --case tests/test_followups_continuous.py --out "artifacts/runtime/deepseek-handoff/$handoffRun/continuous"
.\.venv-v35\Scripts\python.exe scripts/v37_tests.py --case tests/test_followups_mvp.py --out "artifacts/runtime/deepseek-handoff/$handoffRun/mvp"
```

这两个命令是离线测试，不验证真实 API。只有变更范围需要时才运行一次完整隔离回归：

```powershell
.\.venv-v35\Scripts\python.exe scripts/regression_center.py
```

完整回归依赖现有 P0 v2 包及冻结夹具，不要删除交接包或通过删除失败测试来避开依赖问题。真实模型验证需另按用户当前授权执行；配置确认、页面打开、刷新本身均不得自动发请求。

## 8. 剩余问题与下一步建议

1. **当前追问模块的后续修改尚未在本交接中复验；真实 API 连续十轮也尚未复验。** 已有离线 SDK/界面交互证明属于之前的受测快照；DeepSeek/Qwen 历史联网证据不能替代本功能的新 Live 验收。
2. 有足够模拟班次数据时已经验证十轮；不能保证任何问题、任何空证据场景都能持续提供有价值的新问题。尤其单份政策的候选仍受现有政策规则限制，不能靠改写同义句凑十轮。
3. 推荐目前由模型选择有依据的候选，精确去重和部分规则去重已实现；没有可靠的通用语义去重或自由生成质量验收。
4. 本次没有新增浏览器截图验收。Streamlit AppTest 是交互测试，不等于桌面/手机真实浏览器视觉验收。
5. 没有重新提交或打最新包。开发前 ZIP 是回滚快照，**不包含此后新增的智能追问与连续性修复**；发给另一台机器时，必须检查最新源码、未跟踪文件和必要夹具是否齐全。

建议下一步先按用户指定问题做小范围真实十轮验收，记录每轮问题、回复、推荐、生成来源、回退原因、实际请求数与 Token；失败时保留证据并定位，不自动重试、不改成假成功。未得到新任务前，不要擅自扩展 UI 或重写推荐架构。

执行顺序：先离线复核新增的实际查询判定、前文证据继承和生命周期关联，再根据用户授权决定是否 Live 复验。本次交接书编写仅修改本文档，未运行新测试，未发送模型、Embedding 或 LangSmith 请求，未提交或推送 Git。

## 9. 工作区与安全边界

- 保留全部已有未提交修改与未跟踪文件，包括前端、RAG 千题、测试和文档；不要只根据 HEAD 重建项目。
- 不执行 `git reset --hard`、`git clean`、强制覆盖、批量格式化、自动提交、推送或合并。
- 不覆盖历史 Trace、真实模型原回复、Chroma 索引、SQLite 数据库、预算历史、B 正式断言和交付物。
- 当前累计 Live 请求统计不应成为旧5/5、4/4等历史额度拦截；但单轮步数、超时、Token保护、零自动重试和用户确认仍有效。
- 密钥只使用现有受保护配置，不写进源码、文档、截图或日志，不要求用户把 Key 发到聊天。不要修改 Codex/Harness 自身认证与全局模型设置。
- 所有测试报告说明版本、范围及 Mock/Live 来源。未知、不适用、未执行和失败分开记录，不伪造 PASS。

## 10. 12:35–12:40 复验补充（优先于第 1、6、8 节的"未验证"状态）

本节由接手方在本轮修复完成后追加，只写实际执行过的证据。**文档正文第 1 节关于 `target/followups.py` 哈希不一致、后续修改未复验的警告，已由本节闭合。**

### 10.1 版本边界（写入时实测）

| 文件 | SHA-256 | 备注 |
|---|---|---|
| `target/followups.py` | `cc422f09b3a1f8cc432f17294a1b19687e999eaf69a06b590ae4811dff710333` | 12:34:36 最后写入；§1 中的 `21d7be94…`、`a4c0f47d…` 均已被取代 |
| `web/runtime.py` | `ae02c788c3578e98463ab187eda04c7aefc3b7cab20c5eb81aab93e4bee44925` | 本轮加入 `shown_followups()` |
| `web/conversation.py` | `379fadc69ff2c59da478ed53ca9211f8d89548823b2f5f92ca088192c8e7c340` | 本轮加入生命周期事件与面板 |
| `tests/test_followups_continuous.py` | `641b97598ed246e04630f4a3b3a87a49971fa889b225edcc4ad22670e24ecac2` | 与 §1 记录一致，未改动 |

下文 10.3、10.4 的测试与真实请求，均针对上表这组字节；跑完后重新计算哈希未再变化。

### 10.2 相对第 3 节新增的实现

1. `candidates()` 新增 `executed_query()`：只有 `event_type=tool_result` 且 `executed is True`、`output.trains` 为列表的事件才算"本轮查过票"。空结果仍算已查，避免用旧库存填补。
2. 当前轮 `query_result_train_authority` 断言只对当前 run 生效，不再连带丢弃上一轮证据。
3. 新增按班次生成的问题（出发/到达/余票/票价，每班 4 条），候选随检索行数增长。
4. `read_all()` + `Conversation.shown_followups()`：已展示过的建议也参与去重，每轮都是新问题。
5. 新增生命周期事件 `followup_generation_started/completed/failed`、`followup_fallback_used`，快照新增 `followup_id`；UI 侧写 `followup_displayed/selected/submitted` 并携带 `next_run_id`。
6. `web/conversation.py` 的「运行详情与 Trace」新增「智能追问生命周期（独立事件链）」，与业务五阶段并列，不并入工具列表。

### 10.3 两轮后追问消失的根因（第 3 节表格未覆盖）

模型请求回放上一轮工具结果时会写入 `tool_result_in_model_request`，其 `tool` 也是 `query_tickets`。旧判据 `any(e.get('tool') == 'query_tickets')` 把它当成"本轮已查票"，于是不再回退到上一轮的 `tool_result`，候选归零、追问消失。离线复现：第一轮 35 条候选，第二轮回答未调用工具时 `options=0`，第三轮 `stopped`。修复后同场景稳定 30–35 条。

旧十轮 SDK 替身测试没暴露该问题，是因为替身每轮都对用户消息回一次 `query_tickets`，恒有真实 `tool_result`，恰好绕开回显事件路径。

### 10.4 本轮实际验证

| 范围 | 结果 | 证据 |
|---|---|---|
| 追问专项（离线，两家 SDK 替身） | **26 passed / 23 subtests passed，0 失败** | 本地 `pytest tests/test_followups_mvp.py tests/test_followups_continuous.py` |
| **真实 DeepSeek 十轮** | 10/10 轮各 3 条、全部 `generation_source=model`、0 回退 | `artifacts/runtime/followups-real-20261030-123513/acceptance.json` |
| 真实请求数 | **21 次**（主对话 11 + 追问 10），预算 30，0 重试 | 同上 |
| 真实 Token | prompt 13,391 / completion 1,211；追问平均 1,377 ms | `followups.jsonl` 逐行 |
| 每轮新鲜度 | 每轮 `new_vs_displayed = 3`，无重复推荐 | `acceptance.json` |
| 事件链 | 80 条追问事件；`followup_id`/`previous_event_id` 齐全，链路可回溯 | `followup_events.jsonl` |
| UI 生命周期事件 | `displayed/selected/submitted` 均写入，`next_run_id` 有值（离线 UI 检查） | `artifacts/runtime/ui-lifecycle-*/ui-lifecycle.json` |

真实十轮中第 2–10 轮**没有任何工具调用**，仍连续生成追问——正是原缺陷触发路径。

### 10.5 对第 8 节"剩余问题"的修订

- 第 1 条（后续修改未复验、真实十轮未复验）：**已闭环**，见 10.4；仅 DeepSeek 复验，Qwen 仍为离线替身。
- 第 2、3、5 条不变。第 2 条的边界已实测：3 班次约 35 条候选，十轮 ×3 已接近上限；2 班次（约 20 条）时第 7–8 轮会不足两条并显式 `insufficient_evidence`，不会编造。
- 第 4 条不变：本轮仍无浏览器截图验收，UI 事件检查走的是 AppTest。

### 10.6 仍未验证（不要写成通过）

1. **8 秒超时没有按次硬计时**：线程计时器会破坏 SDK 替身的计费/事件上下文（测试一度 28 failed），已回退。现为同步调用 + provider 客户端超时，验收时以 `DEEPSEEK_TIMEOUT=8` 运行；代码中没有硬编码 8s 常量。
2. 追问生成仍同步阻塞回答约 1.2–1.6 s。
3. `followup_displayed/selected/submitted` 只在离线 UI 检查中验证，真实批次是运行时直驱，未经页面点击。
4. 真实 API 下的超时/限流回退未触发（本轮 0 回退，全部成功）。
5. 浏览器刷新后对话本身仍不持久，追问随之不可见。

---

<details>
<summary>附录：原版 UI 改造任务书（历史参考；不是本次新增执行授权）</summary>

## 角色与目标

你是 DeepSeek Harness 中的编码
Agent。请把本文作为实际执行任务，不要只输出建议。目标是在现有 Ticket
Agent 项目上改善 UI 和执行证据体验，保留现有业务、权限、测试与历史证据。

项目路径：`D:\codexproject\ticket-agent`

如果你无法访问该目录，必须明确说明并请求用户在 Harness
中打开/挂载工作区。不得假装已检查或修改本地代码。

## 开工前必做

1.  检查当前工作目录、Git 分支、HEAD、已暂存、已修改和未跟踪文件。
2.  阅读 README、当前页面入口、UI 相关源码、测试说明和已有交接文档。
3.  确认当前用户端、开发者端、测试控制台的实际实现及其数据来源。
4.  建立改动前测试基线，保存命令和日志。
5.  检查当前 DeepSeek Harness 已安装的插件/Skills。若有视觉工具或设计
    Skill，先读其说明并实际使用；若没有，给出建议，不要擅自安装大量插件。
6.  不覆盖已有未提交修改，不执行 reset、clean、删除、提交、推送或合并。

历史状态仅供参考：分支曾为 `feat/ticket-agent-v36-stabilization`，HEAD
曾为
`04b9a42a47e8ca81ce77cca352655708a1e1ea63`。这些可能过期，必须以当前工作区为准。

## 项目背景

Ticket Agent 是用于 AI 智能体测试挑战赛的模拟票务 Agent
与可靠性测试平台。历史技术栈包括 Python、Streamlit、Legacy/LangChain
Agent、DeepSeek/Qwen Live、SQLite 模拟业务、Keyword/Vector/Hybrid
RAG、Chroma、Trace、运行事件、变异测试和离线测试。

历史代码中有八个模拟工具： - `query_tickets` - `monitor_seat` -
`lock_seat` - `create_order` - `pay_order` - `cancel_order` -
`query_order` - `search_policy`

历史路径包括
`target/run_events.py`、`web/run_evidence.py`、`web/developer_workspace.py`、`scripts/v37_tests.py`、`scripts/v37_rag.py`、`scripts/v37_performance.py`。必须检查文件当前是否存在、接口是否有效，不能只凭这份列表推断当前状态。

**重要边界：** 模型 API
可以是真实的，但票务、锁座、订单和支付是模拟业务，不得暗示连接真实 12306
或真实支付。未经用户明确批准，不发送真实模型、Embedding 或 LangSmith
请求。

## 已知 UI 痛点

### 用户端

-   主内容区偏窄，桌面两侧空间利用不足。
-   首页像配置表单，不像成熟的 AI 对话产品。
-   模型费用确认、RAG 模式、Embedding 开关等高级配置过度占据首屏。
-   快捷问题、聊天消息、结构化车次结果和工具状态缺少层级。
-   工具执行与政策证据没有成为核心体验。
-   新用户不容易理解从哪里开始。

### 开发者端

-   三栏虽已存在，但三栏关联不够直观。
-   中间时间线可能无记录，而右侧独立调试可以运行，容易让人误以为是同一次运行。
-   提示词、工具
    Schema、权限、Trace、政策证据和测试结果之间缺乏清晰关联。
-   静态说明、当前真实事件和历史回放需要严格区分。

### 测试控制台

-   不应只展示通过数量和状态卡片。
-   应把测试方法、预期行为、断言、Trace、原始日志和缺陷证据关联起来。
-   RAG 检索命中、引用存在、回答正确和无答案拒答必须分别评估。
-   历史成绩不能标成当前成绩；A 自测不能冒充 B 正式测试。

## P0：先重构用户端

请直接实施，而不是只给建议。

### 目标体验

-   清晰的产品标题与一句话定位。
-   主要对话区成为视觉中心，合理利用桌面宽度并兼容窄屏。
-   欢迎状态、快捷问题和明显的输入区。
-   60 秒模拟购票演示入口。
-   高级配置默认收纳到"高级设置"，但真实 API 调用确认不可移除。
-   结构化车次结果卡片/表格，不把所有结果塞进大段文本。
-   清晰的运行阶段：查票、检索政策、等待确认、执行、完成或失败。
-   运行状态必须来自当前请求的真实事件；纯演示必须标为演示。
-   政策证据可展开查看真实文档
    ID、版本、位置和内容；缺失时标注"未记录/证据不足"。

### 模拟流程

复用现有业务与确认机制： 1. 查询车票。 2. 展示实际返回结果。 3.
用户确认锁座/下单。 4. 确认模拟支付。 5. 查询订单并展示模拟状态。

不得绕过权限、确认、幂等或现有业务校验。

## P1：开发者端真实链路

围绕同一个 `run_id` 联动三栏。

-   左栏：真实提示词、工具
    Schema、权限规则、规则与测试映射，标出来源路径/版本（仅在实际可得时）。
-   中栏：用户输入、模型请求、工具提议、参数校验、权限/确认、执行开始/结束、工具结果、RAG
    检索、最终回复和异常。
-   右栏：运行模式、输入、实际工具参数与结果、Trace、政策证据和测试关联。
-   明确区分独立调试、当前运行和历史回放。
-   不同 `run_id` 的事件不能混在一起。
-   不得伪造时间、Token、检索分数、执行结果或 Trace ID。

## P2：测试控制台

-   支持用例筛选、用例详情、预期/实际断言和日志。
-   展示变异注入及检出矩阵。
-   分开评估 RAG 检索、引用支持、无答案拒答和忠实度。
-   支持当前/历史对照及结果导出。
-   标注代码版本、时间、环境和测试范围。
-   未验证不能显示为通过。

## 视觉与实现标准

目标是成熟、可信、可读的 AI SaaS 界面，不是只换颜色。 -
统一字体、间距、圆角、边框、颜色和状态语义。 -
明确主次层级，减少重复卡片、装饰标签和无意义留白。 -
Trace、JSON、长文本采用适合阅读的详情/折叠布局。 - 先复用 Streamlit
现有组件；不要为了视觉效果立即迁移 React。 - 如果已安装 SuperDesign
Skill，先阅读其流程；若有 DSH Vision
Toolkit，实际用于截图分析、页面渲染和像素差异比较。 -
如果没有视觉工具，不能声称做过截图对比。

## 工程约束

1.  先检查再改动，保留所有原有未提交修改。
2.  不删除历史 Trace、数据库、Chroma
    索引、预算账本、正式测试原件、旧交接包或展示 ZIP。
3.  不覆盖历史报告，不弱化断言，不通过增加 skip 来制造绿色结果。
4.  不修改公共契约、业务规则或权限逻辑，除非有明确证据并说明原因。
5.  不发送真实模型、Embedding、LangSmith 请求，除非用户明确批准。
6.  不提交、推送或合并 Git，除非用户另行授权。
7.  每轮修改后运行对应测试；启动应用并检查真实渲染。
8.  测试失败要保留日志并解释原因。
9.  无法访问本地仓库时，必须请求挂载工作区，不得假装已执行。

## 验收标准

### 用户端

-   新用户能快速理解产品并开始操作。
-   桌面宽度利用合理，窄屏可用。
-   对话、快捷问题、模拟流程和结构化结果可用。
-   工具状态与实际事件一致。
-   政策证据可查，缺失时不伪造。
-   高级配置不再压过核心对话体验。

### 开发者端

-   三栏关联同一个 `run_id`。
-   能追踪工具提议、校验、权限、执行和最终回复。
-   当前运行、历史回放和独立调试明确区分。

### 测试与交付

-   用例、断言、日志、Trace 和报告可关联。
-   当前/历史、Mock/Live、A 自测/B 正式结果明确区分。
-   提供实际修改文件、启动情况、截图路径、测试通过/失败/跳过数、剩余缺口和
    Git 状态。

## 现在立即执行

1.  检查工作区、Git 状态、页面入口、测试基线和可用插件。
2.  给出精简的事实清单，指出源码位置和可复用组件。
3.  不要停在分析阶段：直接实施 P0 用户端 UI 重构。
4.  启动应用并检查截图；如有视觉工具，分析差异并至少迭代一轮。
5.  运行相关测试和完整离线回归，保存日志。
6.  如实汇报实际修改、测试、截图、风险及 Git 变化。
7.  P0 完成并验证后，再推进 P1、P2。

</details>
