# 测试工作台五板块 UI 收敛：实施与验收报告

日期：2026-11-11（Asia/Shanghai）。工作区 `D:\codexproject\ticket-agent`，分支 `feat/ticket-agent-v36-stabilization`，HEAD `68f6a5c80ab6fadde3815d0e6e1a0371392d81c9`；未 commit/push/merge/tag。本报告只追加，不覆盖历史 `docs/reviews/`。

## 1. 改造前导航

`web/app.py` 原测试工作台导航为历史九入口加新五名称的混合集：

```text
测试总览 / 测试实验室 / AI 测试场景生成 / Trace 分析 / 质量分析
/ 模型对比 / RAG 知识库 / 集成中心 / V3.7 离线验收
+ AI 场景总测试 / 本轮质量分析 / RAG / 多轮 / 安全 / 边界与异常测试 / 性能测试
```

共 14 个 radio 选项。旧文档 `03_测试控制台.md` 的九页表与实际 `app.py` 已不一致；以实际源码和《测试端_改造对接说明.md》的五板块设计为准，旧表仅保留历史。

## 2. 改造后五板块

```text
01 AI 场景总测试
02 质量分析
03 RAG / 多轮 / 安全
04 边界与异常测试
05 性能测试
```

`web/app.py` 的 `WORKBENCH_PAGES` 为唯一来源；测试工作台 radio 只接收这五项。旧入口不再有可达路由。

## 3. 删除 / 合并

- 删除导航：测试总览、测试实验室、AI 测试场景生成、Trace 分析、模型对比、RAG 知识库、集成中心、V3.7 离线验收、历史质量分析。
- 合并：总览 + AI 场景生成 → 01；质量分析旧版 + 历史质量 → 02；RAG/多轮/安全 → 03；实验室异常注入 → 04；Trace 性能证据 → 05。
- 底层文件保留：`competition_view.py`、`laboratory.py`、`scenario_generator.py`、`trace_view.py`、`quality.py`、`comparison.py`、`rag_page.py`、`integrations.py`、`v37_console.py` 未删除；仅移除测试工作台导航入口，避免破坏历史导入/证据。
- 用户工作空间、开发者工作空间顶层入口保留。

## 4. 各板块实现

### 01 AI 场景总测试

- 入口：`web.consistency_audit_view.competition_page(sessions)`。
- 读取当前用户对话；一个主按钮 `开始本轮测试`。
- 生成、校验、隔离执行、AI 判定、汇总共用 `Workbench` 的同一个 `run_id`。
- 进度、用例生成/校验/执行漏斗、客观断言与 AI 评判分列表、链路覆盖矩阵、证据下载和历史记录都在该页。
- 无对话时显示“暂无可测试的对话”，不生成数字。

### 02 质量分析

- 入口：`quality_page(sessions)`。
- `_numbers` 展示四张指标卡：客观断言、AI 评判、链路覆盖、证据完整。
- 客观断言与 AI Judge 分列显示；功能/工具维度下钻；四层状态一致性；异常注入证据在单层折叠内。
- 不再作为独立历史页；名称统一为“质量分析”。

### 03 RAG / 多轮 / 安全

- 入口：`rag_page(sessions)`。
- 同一 run 的 `by_dimension` 中 RAG、多轮、安全三组切片；不分别启动测试。
- 本轮未执行的维度明确显示“本轮未执行该类场景”。

### 04 边界与异常测试

- 入口：`lab_page()`。
- 沿用现有 `scenario_workbench` 的注入引擎和 `summary['boundaries']`，按五类边界展示计划、注入、检出、检出率、关联用例；无新引擎。

### 05 性能测试

- 入口：`trace_page([])`。
- 只读本轮 `summary['performance']`：P50/P95、用例耗时、工具耗时、并发证据。
- 无并发时固定显示“本轮未执行并发场景”；不借用历史数据。

## 5. 核心代码修改

| 文件 | 修改 |
|---|---|
| `web/app.py` | 删除历史九入口和旧路由分支；`WORKBENCH_PAGES` 固定为五项；只改整合者路由 |
| `web/consistency_audit_view.py` | 页面 2 标题统一为“质量分析”；主按钮改为“开始本轮测试” |
| `tests/test_workbench_five_nav.py` | 新增五入口/顺序/顶层工作空间回归 |
| `README.md` | 增加五板块使用说明 |
| `00_总体契约.md`、`03_测试控制台.md`、`01_用户工作空间.md` | 从对接文档复制到项目并补充五板块/旧九页历史说明 |
| `现阶段总结.md` | 记录本次 UI 收敛状态 |
| `评审预览.html` | 五板块静态评审预览，不展示虚构成绩 |

未修改 A/B 独占业务文件；未修改 `web/runtime.py`、`web/design.py`、`web/evidence.py` 的共享契约；未改历史 `docs/reviews/` 报告；未改数据库/Trace/预算。

## 6. 统一 run_id

- `consistency_audit_view.current_test_run()` 从当前用户 session + `POINTER` / `abc_run` 读取唯一 manifest。
- 只有 `competition_page` 的 `开始本轮测试` 调用 `Workbench.execute(...)` 创建 run。
- `quality_page`、`rag_page`、`lab_page`、`trace_page` 只调用 `_result`/`_current`，不调用 `Workbench.execute`，不创建新 run。
- 页 2–5 未完成本轮时显示 `请先在「AI 场景总测试」完成一次 AI 测试。`，不展示 0/0、100% 或历史快照。
- `tests/test_scenario_workbench.py` 的同一 run/evidence 断言 11 项通过。

## 7. 单一启动入口

- 代码搜索：`Workbench.execute` 只在 `competition_page` 的按钮分支调用；页 2–5 无启动按钮。
- `开始本轮测试` 只在 `competition_page` 出现；页面空状态不显示数字。
- 点击前需要当前 session 有历史对话、在线模型授权；离线时提示模型请求不可用。

## 8. 浏览器验收

真实 Playwright（本地 Streamlit，离线 mock，无模型 API）：

```text
桌面 1600×1050: 五入口按序可见，旧入口 0，overflow false，PageError 0，ConsoleError 0
手机 390×844:   五入口按序可见，旧入口 0，overflow false，PageError 0，ConsoleError 0
```

证据：

- `artifacts/runtime/five-nav-1600-final.png`
- `artifacts/runtime/five-nav-390-final.png`
- `artifacts/runtime/five-nav-390-collapsed.png`
- `artifacts/runtime/five-nav-results.json`
- 浏览器脚本 `artifacts/runtime/r30-responsive.js`
- 页面切换五页均无异常；未完成本轮时页 2–5 只显示引导。

## 9. 自动化测试

```text
tests/test_workbench_five_nav.py + test_ui_pro.py + test_scenario_workbench.py
12 passed（导航 + UI 共享层 + Workbench 核心）
```

新增测试验证：

- radio options 恰好五项且顺序固定；
- 默认页为 AI 场景总测试；
- 顶层仍有用户工作空间/开发者工作空间/测试控制台。

## 10. 完整回归

本次 UI 合同改变了旧导航，仓库内仍有历史页面测试（`test_v33_app.py`、`test_v311_abc_integration.py` 等）断言旧九页/旧历史入口；它们不代表新合同，不能在未更新的情况下作为当前验收基线。

`scripts/v37_tests.py --out artifacts/runtime/workbench-five-nav-tests-2` 在当前离线执行器下得到 2219 passed / 134 failed / 1 skipped；失败包含大量旧路由/旧环境断言（且该执行器清空 Provider 环境），**不作为本 UI 变更的 PASS 证据**，也不删除原始日志。  
本次只对 UI/工作台相关的 12 项测试给出 PASS；完整回归需先同步旧导航测试到五页合同后再跑，不能把旧结果冒充当前成绩。

> 该结果不是“完整回归通过”。如果正式验收要求旧历史页面仍可导航，则与本次五入口产品目标冲突，应先由整合者确认合同，不应同时保留新旧入口。

## 11. 保护文件核验

以 `docs/reviews/independent-review-v2/opening.json` 的 5587 项 protected 哈希重算：

```text
checked: 5587
unchanged: 5584
differences: 3
missing: 0
```

差异：

1. `tests/v39/test_acceptance_budget_v2.py`：已批准预算测试例外；
2. `artifacts/runtime/api-usage/bailian/.../requests.jsonl`：前序 Qwen 真实请求账本追加；
3. `artifacts/runtime/api-usage/deepseek/.../requests.jsonl`：前序 DeepSeek 真实请求账本追加。

本次 UI 改造未修改上述保护内容；API 账本追加是历史真实请求，不是 UI 改造写入。不能声称 5587/5587 零差异。

## 12. 尚未解决

- 旧 `test_v33_app.py`、`test_v311_abc_integration.py` 仍断言旧九页路由，与本任务五入口合同冲突；未删除/跳过，需按新合同迁移测试。
- 未执行真实 Live 生成/判定（本任务不需要模型 API）；页 1 的完整业务流程只由现有 `Workbench` 测试/历史证据支持，不是本次新跑的真实模型成绩。
- 浏览器未完成用户对话→点击开始→生成/执行/判定的全流程；当前验证是导航、页面渲染、空状态和移动端布局。
- `评审预览.html` 是静态预览，不是运行证据。
- 独立只读 UI 审查：**CONDITIONAL_PASS**；详见 `docs/reviews/V311-R1-TEST-WORKBENCH-UI-INDEPENDENT.md`。

## 13. Git

```text
HEAD 68f6a5c80ab6fadde3815d0e6e1a0371392d81c9
branch feat/ticket-agent-v36-stabilization
worktree dirty (既有并行修改 + 本次 UI 修改)
未 commit / push / merge / tag
```

## 14. 独立审查

独立只读子 Agent 结论：**CONDITIONAL_PASS**。核心五入口/单启动/只读空状态通过；条件为旧历史测试未全部迁移、截图覆盖不足和轻微代码漂移。详见 `docs/reviews/V311-R1-TEST-WORKBENCH-UI-INDEPENDENT.md`；不写成无条件的独立 PASS。
