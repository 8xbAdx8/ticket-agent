# Ticket Agent 产品操作与缺陷检测报告

2026-11-11 · 分支 `feat/ticket-agent-v36-stabilization` · HEAD `8a6ccf36688c9cab803d46ba0bbf652290132e19` · **PARTIAL**

## 1. 现场与实际操作

8502 开工时拒绝连接。工作区有 14 个跟踪文件修改、222 个未跟踪文件，暂存区为空。使用现有工作树源码、Python 3.12.14 和本机 Edge 157 启动隔离实例。原业务库复制后只读检查。每个业务场景使用新 SQLite，真实静态车次与经停使用阶段八 GTFS 副本，库存、价格及交易为本地模拟。

通过实际页面查询车次、查看经停、选车和报价。把真实报价 ID 作为输入，从原聊天入口发起建单，由确定性 Mock Provider 经过 Agent 和 Registry 生成 CREATE_ORDER 提案。Playwright 测试用户确认，Service 写入订单和 Hold。随后在订单卡分别发起支付、退款和改签。另验未支付取消、主题切换、刷新和历史查看。

证据根目录 `artifacts/runtime/v310-v311-qa-product-20261111/`。以下短路径相对该目录。现场、Git、原库和账本检查见 `opening.json`、`environment.json`。

## 2. AI 场景生成质量

- 实际操作目标、领域、难度、数量、模型、适配器、生成约束与在线授权。未勾选授权时，在线生成被拦截，SQLite 未新增生成记录。
- Mock 生成两条 V3.10 DSL 并刷新复查候选。拒绝重复候选，编辑另一条并核对版本，人工审核后执行并读取 Trace。手机深色页面另验 Legacy P2 生成、搜索、导出、删除未批准候选和审核留痕。
- 同一个生命周期参考计划修复前无法批准，修复后从页面批准并执行 20 步。16/16 条参考计划直接执行通过，15/16 通过当前结构审核。过期提案计划仍缺审核门要求的确认步骤业务状态断言，保留原样。
- 用 eval-audit 对照工具实际执行、人工决定与数据库状态。一个用例把字符串 `quantity` 放在合法引用旁，修复前审核 PASS、Registry 执行失败。修复后审核拒绝该候选。拒绝提案与确认交易均有独立数据库证据。
- 对 45 份历史真实模型生成记录离线回审，关联 44 条原始候选。DeepSeek 16 PASS、1 NEEDS_REVIEW、10 REJECTED。Qwen 9 PASS、8 REJECTED。原审核状态未改。

证据见 `before/scenario/`、`before/scenario-review/`、`after/scenario-review-and-execute/`、`before/reference-6/`、`after/reference-2/`、`after/management-mobile/`、`historical-ai-audit.json`。

## 3. DeepSeek / Qwen 真实测试

| 指标 | DeepSeek | Qwen |
|---|---|---|
| 本轮真实 HTTP | 0 | 0 |
| 本轮真实候选生成 | NOT_RUN | NOT_RUN |
| 本轮真实 Agent E2E | NOT_RUN | NOT_RUN |
| 新增 Token 与费用 | 0 Token，无调用费用 | 0 Token，无调用费用 |

两家配置均存在。原建单诊断批次已用 8/8，R1 补充批次已用 60/60。其他余额绑定历史批次。本轮独立批次的数值额度尚未确认，未发出新请求。历史批次共 42,281 Token，费用 UNKNOWN，两家均曾生成建单提案并完成隔离数据库核验，Qwen 最终文字受原限额拦截。历史证据保留在 [建单导航与数据库回执真实诊断](Ticket-Agent-UI-Receipt-Live-Diagnosis-20261111.md)。

## 4. 缺陷清单及修复

| ID | 等级 | 复现与影响 | 根因和修复 | 原始证据与复验 |
|---|---|---|---|---|
| QA-01 | P2 | 保存 2 条候选后页面仍显示 0。执行成功后本轮计数和 Trace 仍读旧列表。 | 页面先读取统计后写入。写入完成后重新读取列表并呈现本次回执。 | `before/scenario/`、`before/scenario-execution-3/` → `after/scenario-review-and-execute/` |
| QA-02 | P2 | 编辑提交 `[]` 时应报告格式错误，实际出现 AttributeError。 | 解析 JSON 后直接调用 `.get`。要求 JSON 对象，保留原版本。 | `before/scenario-review/` → `after/scenario/` |
| QA-03 | P2 | 拒绝重复项后预览仍显示重复警告，批准却成功。 | 预览与批准使用不同候选范围。共用审核逻辑及正式目录检查。 | 同上，另有审核事务回归 |
| QA-04 | P1 | 页面载入的 `lifecycle` 无法批准，直接执行却通过全部 20 步。 | 审核缺少有效报价和订单输出字段，也遗漏确认步骤本身强制校验的业务回执。认可实际字段和已绑定的确定性证据。 | `before/reference-6/` → `after/reference-2/` |
| QA-05 | P1 | 有合法 `trip_id` 引用时，非法 `quantity="1"` 被审核通过，执行拒绝。 | 发现任意 `$` 就跳过整个参数对象校验。仅延迟解析引用，保留字面量、必填项和条件约束。 | `matrix-before-v2/qa_invalid_mixed.json` → `matrix-after/qa_invalid_mixed.json` |
| QA-06 | P1 | 用户拒绝确认卡，数据库没有订单或 Hold，执行器仍因缺订单取消回执报 FAIL。 | `CANCELLED` 共享交易成功判定。拒绝用独立前后快照核验提案撤销与业务数据未变。 | `matrix-before-v2/qa_decline.json` → `matrix-after/qa_decline.json` |
| QA-07 | P3 | 未支付取消并释放所有库存后，历史页显示「有效乘客 3 人」。 | 把留存明细当成当前有效席位。终止订单显示原始乘客及相应状态，保留原库记录。 | `after/cancel-unpaid/` → `final/cancel-label/` |
| QA-08 | P2 | 从聊天生成提案并确认，订单已提交，回执的来源 Run 和 Call ID 为空。 | 原查找只读框架事件，遗漏 Legacy 的原始执行旁证。按同会话、同动作、实际成功返回的 proposal 绑定来源。 | `final/agent-proposal/` → `trace-final/agent-proposal/`，两引擎来源回归 |

## 5. SQLite Oracle

16 条参考计划和 4 条补充计划执行通过，另保留两条故意错误的负对照。验证重复支付、重复退款、重复取消、已支付取消、Hold/提案过期、他人订单、功能撤销和只读会话。另注入回读失败、Hold 写入异常、提案过期和确认凭据丢失，4/4 通过。

当前构建中，自动定位在人工滚动前就已到达正确 proposal。旧 `DATABASE_RECEIPT_NOT_VERIFIED` 原证据为确认凭据丢失，未创建订单、Hold 或成功确认账本行。本轮故意断开提交后回读时，独立 Oracle 确认订单实际已写入，应用显示 UNKNOWN。恢复回读核验原回执，全程只执行一次确认。Hold 写入异常则整体回滚。

| 浏览器步骤 | 订单状态 | 有效乘客 | 净支付（分） | 累计手续费（分） |
|---|---|---:|---:|---:|
| 建单 | PENDING_PAYMENT | 3 | 0 | 0 |
| 支付 | PAID | 3 | 9000 | 0 |
| 退一人 | PAID | 2 | 6150 | 150 |
| 改签剩余两人 | CHANGED | 2 | 2150 | 150 |
| 退完剩余两人 | CANCELLED | 0 | 250 | 250 |

原支付 9000，首次净退款 2850，改签退差 4000，末次净退款 1900。三个成功退款明细对应不同乘客，最终库存占用为 0。独立计算 P01、资金守恒、库存事件和外键均通过。未支付取消只释放 Hold，交易笔数保持 0。证据见 `trace-final/refund-change/`、`receipt-faults/`、`matrix-after/`。

## 6. Playwright 浏览器验收

Edge 桌面 1600×1050、手机 390×844，覆盖浅色、深色及主题切换。离线 Agent 建单、提案自动定位、确认前门控、支付、退款和改签已实际操作。相同 proposal 经 rerun 保留。刷新只读恢复有效提案和已提交订单状态，旧确认权限不恢复。支付后可查看对应历史运行与开发者证据。

截图、Console、PageError、网络和失败截图分别保存在 `trace-final/agent-proposal/`、`trace-final/refund-change/`、`after/pending-mobile/`、`after/management-mobile/`。首次退款驱动未实际提交，重跑用鼠标选择可见乘客并通过 SQLite 核验，原失败尝试保留。在线模型浏览器链路待独立预算。

## 7. 修改清单

- `web/scenario_generator.py`、`target/scenario_generator.py` 和 `target/scenario_v310.py` 处理页面状态、候选审核和 Oracle。
- `target/v39/read_model.py`、`target/v39/planner.py`、`web/business_panels.py`、`web/railway_simulation.py` 统一终止订单乘客展示。
- `web/business_actions.py` 关联来源执行证据。
- `tests/test_scenario_product_qa.py` 新增 12 项缺陷回归。
- `PROJECT_STATUS.md` 与本报告记录结论。证据、原始日志和可复现脚本在本轮目录。

## 8. 回归与保护

隔离全量 2023 passed / 11 failed / 1 skipped，另 199 个子测试通过。11 个失败与 1 个跳过逐 ID 和原有效基线一致。这次全量含订单状态文案修复，早于最后的提案来源关联。最终代码相关专项 580 passed / 0 failed / 0 skipped，覆盖 V3.9、场景生成、V3.10/V3.11、R1 和动效。首次全量因临时库目录前缀触发路径保护，保留原日志并修正运行配置后重跑。未放宽路径保护或测试断言。

命令、JUnit 与日志见 `pytest-full-final/`、`pytest-targeted/`。现场与结束 SHA 比对见 `protection-end.json`，Git 差异见 `git-task.diff`。未提交或推送。

## 9. 尚未解决

本轮独立真实模型预算待确认。当前构建的真实候选与真实 Agent 端到端尚未重测。正式 103 独立评分仍为 BLOCKED，历史 11 失败和 1 Skip 保留。过期提案部分回执仍保留通用错误码，具体原因记录在 `failure_reason=PROPOSAL_EXPIRED`。

```yaml
PRODUCT_OPERATION: PASS
AI_SCENARIO_GENERATION: PARTIAL
LIVE_AGENT_TEST: PARTIAL
DATABASE_ORACLE: PASS
BROWSER_E2E: PARTIAL
BUGS_FOUND: 8
BUGS_FIXED: 8
REGRESSION: PASS
OVERALL: PARTIAL
```

回归 PASS 指与历史有效基线相比无新增失败，浏览器 PARTIAL 包含尚未运行的真实模型链路。
