# Ticket Agent V3.11-R2 QA-09 与真实业务验收

2026-11-12，Asia/Shanghai。**整体 PARTIAL，独立审查 CONDITIONAL PASS。**

两家 Provider 各有一条真实候选通过 QA-09 并进入原工作台。DeepSeek 驱动真实查询、报价和建单提案，由 `test_user` 经用户授权代操作确认一笔模拟建单。Qwen 驱动查询、经停、库存及报价。两条运行均达到每轮 8 HTTP 上限。模拟支付、部分退款、改签和最终退款或取消在本批为 NOT_RUN。

## QA-09 与 DSL

| 原始运行 | 结果 | 原始缺陷或准入证据 |
| --- | --- | --- |
| 上轮 DeepSeek | REJECTED | 原始 `chat` 缺少 `message`，未提供有效 `checks` |
| 上轮 Qwen | REJECTED | 缺少顶层 `turns`，`chat` 缺少 `checks` |
| R2 DeepSeek 初次 | REJECTED | 已补对话结构，缺少 `dimension`、`source_turn_ids`、`covered_nodes` |
| R2 DeepSeek 修订 | PASS | 先离线核对必填字段及合法示例，再发一次新 Pilot。实际模型原文通过 |
| R2 Qwen | PASS | DeepSeek 通过后发起，实际模型原文通过 |

改动前通用 Prompt、Provider 实际请求与解析器对必填字段的表达不一致。改动后先校验模型原文，再调用现有 V3.10 语义门和静态审核。批准绑定原文、审核计划、证据及批准文件 SHA。每家保留自己的完整合法示例与反例。拒绝响应、解析结果和原始请求均在独立证据目录。

- 顶层响应是 `{"scenarios":[…]}`。模型提供 `title`、`objective`、`difficulty`、`risk_level`、`execution_adapter=v310`、`turns` 和 `integration_steps`。C 端还必需 `dimension`、`source_turn_ids`、`covered_nodes`。来源轮次引用当前脱敏快照；`turns` 是独立的 1–40 项非空字符串数组，每项最长 10,000 字符。
- 每个步骤有 `kind` 和非空 `checks`。每条检查恰有 `path`、`op`、`value`，操作符为 `eq`、`ne`、`ge`、`len`、`contains`、`not_contains`。检查路径从本步骤实际 `result`、`state`、`metrics`、`db` 或先前已绑定的输出取值。非法字段或越界索引在静态或运行时校验拒绝。
- `chat` 的 `message` 是最长 10,000 字符的非空字符串。`tool` 需要真实注册表工具名及 `args` 对象，按 Registry Schema 和参数约束校验。`confirm` 需要提案引用、显式布尔 `approved` 和 `actor=test_user`，这描述测试步骤；真实 R2 交易仍由工作台可信确认。`advance` 需要整数 `seconds`，范围 1–2,592,000。`history` 和 `flag` 需要顶层布尔 `enabled`。`foreign_confirm` 需要 `proposal`，`foreign_order` 需要 `order`。`qr` 使用现有执行器结果及断言。可选 `as` 绑定该步骤的实际结果，后续 `$alias.path` 只能引用已定义变量。
- 用例 ID、运行 ID、请求 ID、哈希、审核状态、实际结果和判定由系统记录。原始模型输出没有补写。两份通过候选的 `turns` 和 `integration_steps` 与审批计划逐字段一致。

## Live、批准和数据库

| 项目 | DeepSeek 运行 | Qwen 运行 |
| --- | --- | --- |
| 工作台运行 ID | `23f818150c784ab6b9d7c6ce31ce999f` | `909e7feb5a70477980e0e6eb2750f8c1` |
| 真实候选 | 修订 Pilot 1 条 PASS，另保留 1 条 REJECTED | 1 条 PASS |
| 批准 | `test_user`，用户授权代点，SHA 绑定 | `test_user`，用户授权代点，SHA 绑定 |
| 原 Agent | 区间查询、经停、库存、报价、建单提案 | 区间查询、经停、库存、报价 |
| 真实工具后果 | 模拟建单 1 笔，Oracle 验证提交 | 报价 1 笔，0 订单、0 Hold、0 交易 |
| SQLite | `PENDING_PAYMENT / UNPAID`，2 合成乘客、1 ACTIVE Hold（2 人）、6000 分票面金额、0 交易、3 条库存事件 | 外键与业务不变量通过，已验证范围为查询及报价 |
| 确定性断言 | 已执行步骤 PASS | 已执行步骤 PASS |
| 跨 Provider Judge | Qwen `indeterminate`，缺同一操作的 Agent/UI 状态证据 | DeepSeek `passed`，范围为只读工具与报价 |
| 四层一致性 | Business 和 Runtime 均为 `PENDING_PAYMENT`。Agent 与结构化 UI 事件缺失，整体 UNKNOWN | 0 写订单操作，NOT_RUN |
| 七维度覆盖 | 工具调用维度覆盖工具选择、参数构造，2/42 | 工具调用维度覆盖工具选择、参数构造，2/42 |

DeepSeek 订单为 `V39-51da111abcf840bcb8465e3508faf039`，Hold 为 `H66bf4e9f06e44ab19b4ba837ff4ef278`。订单、乘客、Hold、库存事件和幂等记录从实际隔离 SQLite 只读核对。已完成的付款金额为 0 分；支付、退款及改签的资金守恒在本轮没有真实业务样本。

初次浏览器确认已经提交，随后界面的订单投影缺少 Hold 状态，导致回执未显示。补齐订单、Hold 与交易投影后，用相同执行 ID 只读恢复，浏览器显示了同一个 `PENDING_PAYMENT` 订单，未重复建单。首次 Qwen Judge 的 65,516 字节请求在本地发送前被 64,000 字节上限拦截。保留首次记录，将重复工具正文压缩后生成 23,315 字节评判包，并使用该运行最后一条 HTTP 发出独立 Judge 请求。原始完整 Trace 单独保留，精简包保留检查、工具参数、来源和 Oracle 引用。复评结果仍为无法判定。

## 真实请求预算

| Provider | R2 HTTP | Prompt Token | Completion Token | 合计 Token | 实际费用 |
| --- | ---: | ---: | ---: | ---: | --- |
| DeepSeek | 9 | 63,439 | 2,560 | 65,999 | UNKNOWN |
| Qwen | 8 | 51,823 | 1,847 | 53,670 | UNKNOWN |
| 合计 | 17 | 115,262 | 4,407 | 119,669 | UNKNOWN |

共用批次累计 19/40 HTTP，DeepSeek 10/20、Qwen 9/20，129,251/300,000 Token。通过的两个工作台运行各 8/8，首次被拒运行 1/8。旧账本两条原始记录逐字段一致。实际 HTTP 证据保留完整请求消息、载荷 SHA-256、Provider、模型、请求 ID、运行与执行身份、原始响应及使用量。自动重试 0，真实铁路、支付、Embedding 和 LangSmith 请求 0。

## 浏览器、回归与并行变更

- Edge + Playwright 在桌面验证真实候选入审、两次授权代点批准、原 Agent 操作、DeepSeek 确认建单及只读恢复。两条封存运行都显示来源 Trace、执行 Trace、Judge 和 SQLite 关联证据，五面板使用同一运行 ID，刷新恢复通过。封存检查每条 0 PageError、0 失败网络请求、2 条图表 Console 警告。完整业务浏览器 E2E 为 PARTIAL。
- R2 定稿快照专项 159 passed、46 subtests passed。受影响 V3.9 业务套件 403 passed / 4 failed / 0 skipped，与前一批 407 个测试 ID 和结果完全一致。四个旧失败为确认 RPC 并发、T011、T031、T072。团队 404/3 原始失败 ID 仍未取得。整仓完整测试未重新执行。
- 用户告知 DeepSeek 并行改动后，现场确认工作台改为五入口，旧测试总览入口撤下。R2 审批门禁及业务执行核心与定稿快照一致。合并现场同一专项为 154 passed、32 子测试通过、19 条失败（5 条常规失败、14 条子测试失败），均来自旧 `tests/test_competition_view.py` 的 6 个 JUnit 父用例。五入口的单独报告及原日志保留，导航合同与旧测试仍需对齐。用合并现场代码重新启动 Edge，两个已封存运行的五面板、来源和执行 Trace、Judge 及刷新恢复再次通过，各有 2 条图表 Console 警告、0 PageError、0 失败网络请求。
- 可复现命令和隔离输入见 `artifacts/runtime/v311-r2-qa09-live-20261112/{targeted-review-fixes,full-review-fixes,targeted-shared-worktree}/setup.json`。R2 浏览器记录和截图位于同一目录下的 `browser/`。

## 代码与保护

| 模块 | 文件 |
| --- | --- |
| 生成契约 | `target/scenario_generation_contract.py`、`target/scenario_generator.py`、`target/scenario_v310.py` |
| 原始请求、预算及复现 | `target/scenario_abc_budget.py`、`target/scenario_abc_live.py`、`target/scenario_r2_live.py`、`scripts/run_v311_r2_pilot.py`、`scripts/run_v311_r2_judge_recovery.py` |
| 审批、执行与隔离 | `target/scenario_workbench.py`、`target/scenario_live_agent.py`、`target/scenario_r2_business.py`、`target/scenario_business_oracle.py`、`target/v39/store.py` |
| 业务工作台和展示 | `web/scenario_r2_desk.py`、`web/consistency_audit_view.py` |
| 测试和原始响应夹具 | `tests/test_v311_r2_qa09.py`、`tests/fixtures/v311_r2_qa09/` |

独立审查发现批准 SHA 需要在原 Agent 创建之前核验，以及 Judge 需要在订单观察缺失时降级。两项已离线修复并通过独立复核。两条实际运行的批准和数据库结果未受这两项缺口影响。

分支 `feat/ticket-agent-v36-stabilization`，HEAD `68f6a5c80ab6fadde3815d0e6e1a0371392d81c9`。暂存区空，工作区保留此前及 DeepSeek 的并行修改。开工 2,763 个路径复核，无未解释的内容变化。上一批 91 项 SHA 对照有 10 个工作区源码差异及 1 个授权共享账本追加，其余 80 项一致；旧账本两行、旧 JSON 报告和旧原始响应保持完整。现场前后状态及每项 SHA 见 `opening.json`、`protection-final.json`、`sha256.txt`。原始正式 103、历史结果和正式数据库未参与本轮重算。正式 103 继续 BLOCKED。

## 剩余验收

本轮尚缺原 Agent 驱动的模拟支付、退款、改签闭环，以及同一订单的 Agent/UI 结构化状态证据。候选本身只验区间查询工具参数。新的全生命周期验收需要一份明确覆盖交易的候选、同一订单的四层事件，以及单独明确的运行与预算安排。当前两个已批准运行各自达到 HTTP 上限。保留原始失败、已创建的演示订单和所有交易证据。
