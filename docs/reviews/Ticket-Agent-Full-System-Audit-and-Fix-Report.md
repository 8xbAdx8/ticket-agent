# Ticket Agent — Full-System Audit and Fix Report

日期：2026-11-04（Asia/Shanghai）。执行者：DeepSeek 实施工程师，开发自测；不是独立审查。  
本轮授权：检查、测试、真实 Qwen/DeepSeek、修复、证据；未接真实铁路/支付，未 commit/push/merge/tag，未启用 Bridge。

## 1. 项目现场

- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 暂存：0
- 工作区：113 项（历史 112 + 本轮独立证据/少量源文件）
- 开工 manifest：`artifacts/runtime/full-system-audit-20261104-203200/start-manifest.json`
- 未 reset/checkout/clean；未覆盖历史证据。

### 保护基线

| 资产 | 当前 |
|---|---|
| `data/v39/simulation.sqlite` | `a429b20b...` 未变 |
| `data/v39/simulation-v391.sqlite` | `9ebf39ec...` 继承冲突，未连接/修改 |
| 阶段八 static.sqlite | `e32f0cd4...` 未变 |
| GTFS ZIP | `3877dbc0...` 未变 |
| 2100 Fixture | `feaec244...` 未变 |
| `data/tickets.db` | `67e6c6e2...` 未变 |
| `data/policies.md` | `bfef71389558e57a11f6d2459d7cc7ef79c1c77c8ff2e60152197e21c18a44ad`，与 HEAD/Baseline 一致 |

> 本轮曾为诊断临时改写 `data/policies.md`，发现 Baseline 冻结身份不一致后立即恢复 HEAD 原始字节；最终无差异。D9/P01 交易规则没有修改，运行时只做已批准 D9 的展示投影。

## 2. Bug 审计

### 数量

- P0：**0**
- P1：**7**
- P2：**6**
- P3：**0**

### P1

| ID | 问题 | 根因 | 修复/状态 |
|---|---|---|---|
| A01 | 截图 `'list' object has no attribute 'get'` | `railway_cards.names_for/trips_view`、`railway_queries` 假设所有容器元素是 dict；历史/扁平/嵌套容器和静态 fallback 的 `data` 可能是 list | 新增 `web/result_rows.py` 显式适配 dict/flat/nested/None；所有相关调用链共用；严格类型检查；FIXED |
| A02 | Qwen 109 班 50/50/9 后 `observed_token_budget_exhausted` | 模型自动翻三页，三个完整 ToolMessage 进入上下文，prompt 31,831 + completion 234 > 32k | 大页只向模型投影前 3 条；total/returned/next_cursor 保留；提示默认不自动翻页；Trace 保真；FIXED（离线+Qwen B 当前页50验证） |
| A03 | 政策 H 被 RAG 守卫阻断 | P01/P02 原始语料与已批准 D9 冲突；`成功退款` 政策句被当作执行声明 | 不改冻结语料；运行时 D9 投影（P01/P02/P03）+ 守卫区分政策句/执行句；离线测试；当前 H Live 未复验 |
| A04 | DeepSeek H `finish_reason=length` / `model_output_truncated` | `max_output_tokens` 默认 512，完整政策答复 578 被截断 | 默认 1024，允许上限 2048；不无限提高；Deep H3 不再截断但旧语料投影未生效 |
| A05 | 快捷“查余票”只发泛化澄清 | 首屏无 `ft_*` 状态，未携带默认事实 | 显式 `2026-11-05 / AOH / HGH`；真实 109 查询与 operation；FIXED |
| A06 | `web.interaction.history` / `interaction` 未初始化旧异常 | 当前树已有 `history`，无局部 `interaction`；实际复现不出 | 未用空函数/吞异常；新增 AST/接口契约测试；MONITORING |
| A07 | 完整选车→席别→乘客→库存→报价→确认 UI | 原版 UI 没有该单页流程；四步是单乘客 | 不伪造；四步真实 1 order/1 txn/2 proposals；完整多人 UI PARTIAL/BLOCKED |

### P2

| ID | 问题 | 修复/状态 |
|---|---|---|
| B01 | 首屏 20 张卡全铺开 | 默认 3 张 + 其余滚动；FIXED |
| B02 | 快捷卡站名“出发站未提供” | 静态 ID→站名补全；FIXED |
| B03 | 铁路工具完成后本次处理仍“处理中” | 识别 `railway_tool_result`；FIXED |
| B04 | 运行工具列表为空 | `interaction.observe` 识别铁路事件；FIXED |
| B05 | 铁路查询无追问/空建议 | 追问 builder 识别铁路事件；G7541 建议；FIXED |
| B06 | 预算/截断错误文案通用 | 明确“安全预算已停止/结果保留/新建会话”；FIXED |

## 3. 代码修改

- `web/result_rows.py`（新增）：dict、扁平 list、嵌套 list、None、缺字段适配。
- `web/railway_cards.py`：`names_for`/`trips_view` 使用适配器；静态站名 fallback；默认 3 卡 + 其余滚动。
- `web/railway_queries.py`：`result_card`/候选/历史使用适配器；非 dict result 明确提示。
- `web/conversation.py`：按 batch 适配、`show_business` 不再假设扁平/嵌套。
- `web/runtime.py`、`web/user_features.py`、`web/user_layout.py`：结果容器统一适配。
- `web/interaction.py`：铁路工具运行记录、状态去重、快捷显式查询。
- `web/run_view.py`：`railway_tool_result/error` 阶段映射。
- `web/presentation.py`：V3.9 工具标签。
- `target/rag.py` / `rag_service.py`：D9 运行时政策投影；不修改冻结语料。
- `target/rag_faithfulness.py`：政策句中的“成功退款”不当作执行声明。
- `target/deepseek_runtime.py` / `bailian_runtime.py`：默认输出 1024，上限 2048。
- `target/followups.py`：铁路事件证据。
- `target/v39/store.py`、`scripts/run_v39_tests.py`：独立审计命名空间。
- `tests/v39/test_v310_stability.py`：新增 12 项（适配、快捷、阶段、工具、追问、Token、政策守卫）。

未改：D9/P01 交易服务、旧 8 工具、V3.9 11 工具 schema、Agent.chat/Trace 公共字段、Baseline、正式 103、GTFS 原件、产品 DB。

## 4. 测试结果

| 范围 | 结果 |
|---|---|
| V3.9 + 本轮 | **312 passed / 0 failed / 0 skipped**（`v39-tests-final9`） |
| 旧完整回归 | **1640 passed / 11 failed / 1 skipped** |
| 旧失败/跳过 ID | 与 sealed **完全相同**，无新增 |
| 浏览器 | **47/47**，8 截图，PageError/Console/RequestFailed **0/0/0** |
| 四步 | 1 order / 1 transaction / 2 proposals；确认前 0 |

旧 11 失败/1 skip 是历史基线，不是本轮新增；没有 skip/xfail 或降低断言。

浏览器覆盖：1600×1100/390×844 浅深、四快捷、默认查询 3 卡、追问、新/历史会话、右栏三模式、四步、错误恢复、无溢出。

## 5. 真实 API

| Provider | HTTP | Tokens | 结果 |
|---|---:|---:|---|
| Qwen qwen3.8-flash | **14 / 15** | **77,881 / 80,000** | A-E 成功；H 初次 `rag_answer_inconsistent`，重试曾通过；最终 D9 运行时投影未再用 Qwen 复验 |
| DeepSeek deepseek-flash | **15 / 15** | **79,049 / 80,000** | A-E 成功；H 初次 `rag_answer_inconsistent`，H2 输出截断；H3 无截断但仍读到旧语料、未正确应用最终投影 |

- 每次 HTTP 200 不等于 Agent 成功；H 的失败/截断是真实证据。
- 无自动重试；达到每 Provider 15 次上限后停止。
- 费用：**UNKNOWN**，不写 0。
- 证据：`live-api-summary.json`、各 `live-*/http-requests.json`、`results.json`。

## 6. 保护资产

- 产品 DB / GTFS / Fixture / tickets：未变。
- `simulation-v391.sqlite`：继承冲突仍 `BLOCKED`，未触碰。
- `data/policies.md`：临时改动已恢复 HEAD 精确 SHA；无最终差异。
- API 账本：只追加 Qwen/DeepSeek 真实请求，未截断/重建；开工/结束 SHA 见下方文件。
- 未修改正式 103/B，未修改历史报告/ZIP，未 commit/push/merge/tag。

## 7. 最终验收

```text
IMPLEMENTED: YES（限定本报告）
TESTED: YES（312/0/0；旧 1640/11/1 ID 不变）
LIVE_API_VERIFIED: PARTIAL
BROWSER_VERIFIED: YES（47/47，Mock 离线）
REGRESSION_VERIFIED: YES（旧失败/跳过 ID 不变）
PROTECTION_VERIFIED: PARTIAL（产品 v391 来源冲突仍 BLOCKED；其余保护资产未变）
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
最终状态: PARTIAL
```

未完成/阻塞：

1. H 政策最终实时复验未完成（Qwen/DeepSeek 请求额度已满；当前投影仅离线验证）。
2. 完整多人交易 UI 未完成。
3. 产品 `simulation-v391.sqlite` 来源冲突仍未解决。
4. 正式 103/B、Bridge、独立审查未执行。
5. `interaction.history/UnboundLocal` 旧异常当前不可复现，仅 MONITORING + 契约测试。
6. API 费用 UNKNOWN。
