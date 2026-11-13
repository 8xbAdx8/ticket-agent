# V3.11-R2 测试工作台验收报告

日期：2026-11-12（Asia/Shanghai）。本轮只改 UI/导航、配置和测试，不调用真实模型 API。

## 1. 项目现场

```text
HEAD:    68f6a5c80ab6fadde3815d0e6e1a0371392d81c9
branch:  feat/ticket-agent-v36-stabilization
worktree: dirty（既有并行修改 + 本轮 UI 修改）
```

本轮新增证据目录：`artifacts/runtime/workbench-r2-20261112/`。旧证据、旧报告、数据库、API 账本未覆盖。

## 2. 原始问题

上一轮 `artifacts/runtime/workbench-five-nav-tests-2/results.json`：

```text
2219 passed / 134 failed / 1 skipped
```

不能预设全部是旧导航；本轮重新读取了原始 results/JUnit/pytest.log 和每个失败堆栈，并建立逐项清单。

## 3. 134 项失败归因

完整逐项清单：

- `artifacts/runtime/workbench-r2-20261112/134-failures.json`
- `artifacts/runtime/workbench-r2-20261112/134-failures.csv`

原始 134 行，按相同测试 ID + 相同异常尾部去重后 121 个唯一失败。分类统计：

| 分类 | 唯一失败数 | 说明 |
|---|---:|---|
| A 旧导航合同失效 | 33 | 仍在设置 `测试总览`、`测试实验室`、`RAG 知识库`、`Trace 分析`、`本轮质量分析` 等旧 radio 值；与新五入口合同冲突 |
| B 页面路由/名称 | 0 | 未发现新的独立路由名称错误 |
| C 测试环境/Provider | 86 | 离线执行器清空 Provider 环境、`RAILWAY_SIM_DB_PATH` 未设置、sandbox marker、protected database namespace 等 |
| D 真实业务功能回归 | 0（在本批异常中） | 没有把任何失败直接判成真实业务回归 |
| E 测试夹具不兼容 | 2 | `web.demo` 缺 `service`/`ctx` 的旧夹具状态 |
| F 未知 | 0 | 已全部落入上述类别；详情仍以 CSV 原始异常为准 |

这不是“134 项已修复”的声明，而是**全量归因结果**。A 类测试尚未全部迁移；C 类需要修测试环境/夹具而不是改五入口；E 类需要更新历史 demo 夹具。原始日志保留在 `original-134-*`。

## 4. 代码修改

### 4.1 单一配置源

新增：

```text
web/workbench_config.py
```

内容：

```python
WORKBENCH_PAGES = (
    "AI 场景总测试",
    "质量分析",
    "RAG / 多轮 / 安全",
    "边界与异常测试",
    "性能测试",
)
```

- `web/app.py` 从这里导入导航；
- `web/consistency_audit_view.py` 的 `TITLES` 直接引用 `WORKBENCH_PAGES`；
- `tests/test_workbench_five_nav.py` 从同一配置读取期望值；
- 无 Streamlit/target import，不产生循环依赖。

### 4.2 `trace_page` 参数

`trace_page(trace_dirs)` 保留历史位置参数契约，但明确 `_ = trace_dirs`：该页数据来自当前 run，不使用旧 trace 目录列表。没有改调用签名。

### 4.3 路由

`web/app.py`：

- 测试工作台 radio 只使用 `WORKBENCH_PAGES`；
- 旧九入口路由分支删除；
- 旧 `workspace_page` 自动归一为第一页；
- 用户工作空间、开发者工作空间保留。

### 4.4 测试

- 新增 `tests/test_workbench_five_nav.py`；
- 更新 `tests/test_v311_abc_integration.py` 的旧“新+历史路由”断言为五入口；
- 未删除测试，未增加 skip/xfail，未放宽业务断言。

## 5. 专项测试

```text
tests/test_workbench_five_nav.py
tests/test_ui_pro.py
tests/test_scenario_workbench.py

12 passed / 0 failed / 0 skipped
```

JUnit：`artifacts/runtime/workbench-r2-20261112/targeted-junit.xml`。

旧路由迁移复验：

```text
test_workbench_has_all_new_and_historical_routes   PASS
test_workbench_has_exactly_five_navigation_entries PASS
```

## 6. 完整回归

### 6.1 原始 134 结果

```text
2219 passed / 134 failed / 1 skipped
```

保留于 `artifacts/runtime/workbench-r2-20261112/original-134-*`，未修改。

### 6.2 本轮干净环境尝试

以测试用 dummy Provider 环境直接运行：

```text
1947 passed / 166 failed / 57 errors / 1 skipped
```

该尝试暴露出更多历史环境/沙箱问题（`RAILWAY_SIM_DB_PATH`、`sandbox_marker_required`、protected namespace），不是导航改造导致。结果保存在 `artifacts/runtime/workbench-five-nav-clean.log`，未作为 PASS。

### 6.3 结论

**完整回归仍为 FAIL / NOT PASS。**

- A 类旧导航测试 33 个未全部迁移；
- C 类环境/夹具 86 个需要测试夹具或执行配置修复；
- E 类 2 个 demo 夹具需要更新；
- 原始 134 日志未删除；
- 没有把“旧路由测试改掉”当成“业务已通过”。

## 7. 浏览器验收

已完成的真实浏览器操作：

```text
桌面 1600×1050：五入口、顺序正确、旧入口不存在、无横向溢出
手机 390×844：  五入口、顺序正确、旧入口不存在、无横向溢出
主题：浅色/深色切换
Console Error: 0
PageError: 0
```

证据：

- `artifacts/runtime/workbench-r2-20261112/desktop-1600.png`
- `artifacts/runtime/workbench-r2-20261112/mobile-390.png`
- `artifacts/runtime/workbench-r2-20261112/mobile-390-collapsed.png`
- `artifacts/runtime/workbench-r2-20261112/browser-five-nav-results.json`

**未完成：**从用户对话→点击 `开始本轮测试`→生成/校验/执行/Judge/汇总的完整浏览器流程。测试控制台当前没有受控会话 + 离线确定性 Workbench 模型，因此该项为 **NOT_RUN**，不能用空状态截图冒充完整 E2E。

## 8. 五板块数据一致性

代码/测试已确认：

- `consistency_audit_view.current_test_run()` 读取当前 session + POINTER；
- 只有 `competition_page` 的「开始本轮测试」调用 `Workbench.execute`；
- `quality_page`/`rag_page`/`lab_page`/`trace_page` 只调用 `_current()/_result()`；
- 未完成 run 时统一显示：

```text
请先在「AI 场景总测试」完成一次 AI 测试。
```

- `test_scenario_workbench.py` 中同一 run/只读/空状态测试通过。

## 9. 保护文件

原始保护清单：`docs/reviews/independent-review-v2/opening.json`（5587 项）。

本轮重算：

```text
checked: 5587
unchanged: 5584
differences: 3
missing: 0
```

差异：

1. `tests/v39/test_acceptance_budget_v2.py`：已批准预算测试例外；
2. `artifacts/runtime/api-usage/bailian/.../requests.jsonl`：历史 Qwen 请求账本追加；
3. `artifacts/runtime/api-usage/deepseek/.../requests.jsonl`：历史 DeepSeek 请求账本追加。

本轮 UI 改造没有重置基线，没有删除历史差异；不能写 5587/5587。

## 10. Git 状态

```text
HEAD: 68f6a5c80ab6fadde3815d0e6e1a0371392d81c9
branch: feat/ticket-agent-v36-stabilization
worktree: dirty，未 commit / push / merge / tag
```

## 11. 已知问题

1. A 类 33 个旧导航测试尚未全部迁移；完整回归未通过。
2. C 类 86 个环境/Provider 失败需要独立执行夹具修复；本次未把它们伪装成业务失败。
3. E 类 2 个 `web.demo` 夹具需要更新。
4. 浏览器完整业务流程 NOT_RUN；只完成五入口/空状态/响应式/主题。
5. 未调用真实模型 API；本报告不含 Live 新成绩。
6. 页面列表已单一来源，但 `web/app.py` 与 `consistency_audit_view.py` 的函数签名仍需整合者保持同步。

## 12. 独立审查

独立只读子 Agent 对五入口 UI 的结论：**CONDITIONAL_PASS**。

- 五入口/顺序/顶层工作空间通过；
- 页 1 唯一启动、页 2–5 只读/空状态通过；
- 条件：旧历史测试未迁移、截图覆盖不足、完整回归未通过。

R2 全量审查（含 134 项和浏览器完整流程）**NOT_RUN**：没有把 UI 子 Agent 的 CONDITIONAL_PASS 扩大成 R2 全部 PASS。

详见 `docs/reviews/V311-R2-WORKBENCH-INDEPENDENT.md`。

## 13. 下一步计划

1. 按 A 类清单迁移 33 个旧导航测试：直接测底层模块或改新五入口，不恢复旧导航。
2. 为 C 类建立统一离线测试夹具（`RAILWAY_SIM_DB_PATH`、sandbox marker、Provider dummy），不修改生产业务逻辑。
3. 修复 2 个 `web.demo` 夹具。
4. 用受控 session + 确定性离线 Workbench 模型完成浏览器完整流程并区分 Mock/ Live。
5. 重跑完整回归，逐 ID 对比；只在该轮全绿后更新 `PROJECT_STATUS` 为 UI 验收 PASS。

## 最终状态

```text
五入口导航:        PASS
单一配置源:        PASS
页 1 唯一启动:      PASS
页 2–5 只读:        PASS
空状态无虚假数字:    PASS
浏览器导航/响应式:   PASS
浏览器完整流程:     NOT_RUN
134 失败归因:       完成（33 A / 86 C / 2 E / 0 B / 0 F）
134 失败修复:       PARTIAL（A 未全部迁移，C/E 未修）
完整回归:           FAIL（未达到全绿）
保护文件:           5584 unchanged + 3 差异
独立审查:           CONDITIONAL_PASS（UI）；R2 全量 NOT_RUN
Overall:            PARTIAL
```
