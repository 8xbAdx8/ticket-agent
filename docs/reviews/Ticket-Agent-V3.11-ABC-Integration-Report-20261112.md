# Ticket Agent V3.11 A/B/C 整合验收

整体状态 `PARTIAL`。五板块已接入主应用。DeepSeek 与 Qwen 均发出真实生成请求，两家候选均被质量门拒绝。该结果触发了 Pilot 停止条件。

## 整合内容

| 范围 | 变更及原因 | 证据边界 |
|---|---|---|
| B 端证据 | `web/evidence.py` 提供同会话唯一事件读取，`target/scenario_workbench_evidence.py` 保存原始事件归属及状态观察引用。结果下钻复用 `web/trace_view.py::show_record` | 保留原历史入口、正式成绩和 B 端快照 |
| A 端状态 | `web/order_state_evidence.py`、`web/runtime.py`、`web/business_state.py` 在 Agent 实际返回明确状态和订单状态组件实际调用后记录事件。`target/consistency_audit.py` 按 session、run、operation、order、proposal 和时点核对 | 提及状态、代码示例、跨单或跨会话记录不能用于判定。四层缺证保持未知。本轮离线反例通过，真实订单浏览器链路仍缺 |
| C 端工作台 | `web/app.py`、`web/consistency_audit_view.py` 接入五个板块，保留原导航。`target/scenario_workbench.py` 添加逐条审核、哈希校验、独占批准凭据和恢复。`target/scenario_workbench_summary.py` 按实际检查汇总，保留历史 42 单元定义 | 离线样本可用，真实候选未通过，Live 结果板块无已执行用例 |
| 真实执行接入 | `target/scenario_abc_live.py`、`target/scenario_live_agent.py`、`target/scenario_business_oracle.py`、`target/v39/store.py` 复用现有 Agent、Provider、Registry 和隔离数据库读取 | Pilot 执行器限定为一次只读查询。模拟建单、用户确认、支付、退款、改签的 Live 联验未执行 |
| 独立预算 | `target/scenario_abc_budget.py`、`scripts/run_v311_abc_pilot.py` 独立持久化授权、请求归属、原始响应和拒绝结果 | SQLite 事务内限制总 40、单家 20、单轮 8、累计 300,000 Token，生成输出 ≤4096，Agent/Judge ≤2048，重试 0。继承账本配置仅记录原有机制 |
| 缺陷及测试 | `target/scenario_v310.py` 修复 M1 必须传整数 `1` 的配置。`tests/test_v311_abc_integration.py` 验证预算拒绝、候选审批、来源哈希、同轮路由和四层误关联 | 原用例和旧断言保留 |

## Live Pilot

批次 `V311-ABC-INTEGRATION-LIVE-20261112`。用户输入为合成的上海虹桥到杭州东车次查询。启动脚本使用实际离线合成会话建立可追溯的输入来源。第一次启动在该来源预检失败，账本请求为 0。修改合成输入使站点编码正确进入真实查询后才发出下表请求。

| Provider | 实际 HTTP | Prompt | Completion | 合计 Token | 费用 | QA-09 |
|---|---:|---:|---:|---:|---|---|
| DeepSeek `deepseek-flash` | 1 | 4,571 | 276 | 4,847 | UNKNOWN | 拒绝。`chat` 缺 `message`，`checks` 为空 |
| Qwen `qwen3.8-flash` | 1 | 4,467 | 268 | 4,735 | UNKNOWN | 拒绝。缺 `turns`，`chat` 缺 `checks` |
| 合计 | 2 | 9,038 | 544 | 9,582 | UNKNOWN | 0 条可审核候选 |

两次均返回 HTTP 200，零自动重试。保存了真实 usage、请求 ID、来源 run ID、脱敏后的响应和质量门错误。两家均未进入人工批准、Live Agent、Judge 或 Live SQLite Oracle。后续提示已补齐可执行 JSON 示例，未重发请求。Pilot 时 Workbench 的通用 Prompt SHA 早于 Pilot 附加约束，实际发给 Provider 的完整 Prompt 保存在批次的 `prompts/`，与模型回执通过 run ID 和请求 ID 关联。后续代码先构造实际 Prompt，再计算 Workbench SHA。

## 浏览器、覆盖与 Oracle

Edge Playwright 通过桌面 `1600×1050` 和手机 `390×844` 的浅色、深色及切换检查。两种尺寸均验证五板块共享 `18ccbed37bf249c2bbf10a29fdc9aff6`、读取来源 Trace、刷新恢复、跨会话拒绝、下载和两家 Live Pilot 的失败门禁。最终每种尺寸均为 0 Console Error、0 PageError。Streamlit 服务端日志另有 `WinError 10054` 连接重置记录。最初测试保留了错误的自动化定位日志，另一次运行发现原页签图标依赖外部资源，已替换为本地图标并复测。

此浏览器用例明确标记为离线。生成和 Judge 使用确定性测试替身，实际离线 Agent 执行了铁路查询。该用例只覆盖工具选择和参数构造 **2/42**。其余 40 个单元保持未覆盖。独立只读 SQLite 复核订单、交易和占座均为 0，外键检查无异常。浏览器没有执行真实模型场景审批或交易。

原始结果为 `browser/release-result.json`，截图为 `screenshots/release-*.png`，请求和控制台记录分别在 `network/` 与 `console/`。下载包含四份材料和包内 SHA。校验结果为 `browser/export-verification.json`。

## 证据与回归

- 最终离线专项 80 通过、0 失败、0 跳过，另有 46 个子测试通过。包括 A/B/C 证据、预算、审核、真实工具离线调用和现有业务回归。
- 完整回归 403 通过、4 失败、0 跳过。与上一轮 C 端 407 个 ID 的判定逐项一致。四个回环 RPC 历史失败保留。团队 404/3 的失败原件仍未取得。
- M1–M7 的原工具/SDK 替身路径验证了真实注入事件和故障检出。M2 的安全停止与无订单已有断言。M8 验证隔离并发重复和原库不变。它们均属离线证据，各故障的 Live 恢复仍未验证。
- 开工时 C 端交付 SHA-256 31/31 匹配。保护对比以 `opening.json` 的现存资产清单为准，`protection-final.json` 记录授权源码差异。正式 103、B 历史、原始数据及旧预算账本保留。
- 独立审查 `CONDITIONAL PASS`。初审发现 UI 关联字段遗漏和代码示例误判，均已修复并纳入测试。完整交易链、真实 Judge 与 Oracle 仍缺实证。

原始证据在 `artifacts/runtime/v311-abc-integration-20261112/`。本轮 Git 分支 `feat/ticket-agent-v36-stabilization`，HEAD `68f6a5c80ab6fadde3815d0e6e1a0371392d81c9`，暂存区为空。工作区包含开工前的修改及本轮增量。
