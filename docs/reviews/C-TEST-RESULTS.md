# C 端测试结果

## 隔离专项

使用 `.venv-v35\Scripts\python.exe`，在独立源码副本执行下列命令。副本由现有回归工具和已校验的 P0 fixture 建立，配置离线模型、网络守卫和新 SQLite。

```powershell
python -B -m pytest tests/test_consistency_audit.py tests/test_competition_view.py tests/test_scenario_workbench.py tests/test_team_selective_metrics.py -q -p no:cacheprovider --basetemp <独立目录> --junitxml <证据目录>/junit.xml
```

| 范围 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|
| 四层一致性 | 4 | 0 | 0 |
| 原测试总览与主应用 AppTest | 10 | 0 | 0 |
| 新工作台 | 8 | 0 | 0 |
| 开工时已有的团队指标专项 | 9 | 0 | 0 |
| 合计 | 31 | 0 | 0 |

另有 30 个既有子测试通过。新工作台 AppTest 对五个入口逐一实际渲染，检查同一运行身份、第二至第五板块没有执行入口、换会话后结果被拒绝。原测试总览用例包含 `AppTest.from_file("web/app.py")`，执行通过。没有运行正式 103 条评测，没有生成截图。

## 运行证据

批次根为 `artifacts/runtime/v310-c-workbench-20261111-231748-45b50f/`。专项原始证据在 `targeted-sealed/process.log`、`targeted-sealed/junit.xml`、`targeted-sealed/setup.json`。以下三个运行保存于 `targeted-sealed/snapshot/ticket-agent/artifacts/runtime/v310-c-workbench-runs/`。

| Run ID | 生成 / 校验 / 执行 | 验证 |
|---|---|---|
| `9e82e3dde70b45fca7b4ac803d53bb7f` | 2 / 1 / 1 | Legacy 实际铁路查询，重复候选拦截，客观通过，受控 Judge 通过，导出 SHA 校验 |
| `e39b263593d244ce9b9912b8fbf18e7e` | 2 / 1 / 1 | LangChain 实际铁路查询，客观通过，Judge 越界引用被降为无法判定 |
| `ea459fc9dd1844efa4743ca2ca86467e` | 1 / 1 / 1 | 实际隔离 M8 双并发探针，检测到重复，常规业务通过率无样本 |

每个运行的 `summary.json`、`manifest.json`、`sha256.txt`、`judgements.jsonl`、`run_events.jsonl` 与单案执行文件用于复核。同一批三个运行彼此独立，均为生成与评判可控替身、被测 Agent 真实离线执行。每个示例运行实际覆盖 1/42，42 是固定指标空间，专项样本没有遍历所有节点。查询用例 SQLite 无订单产生。真实 API HTTP 0 次，Token 与费用无实际记录。评委入口 `--check-only` 和 Live E2E 为 `NOT_RUN`。

## 交付判定

```text
PIPELINE_IMPLEMENTATION: PASS
CONVERSATION_SNAPSHOT: PASS
AI_CASE_GENERATION: PARTIAL
SANDBOX_EXECUTION: PASS
AI_JUDGEMENT: PARTIAL
RUN_ID_GATE: PASS
SEVEN_DIMENSION_COVERAGE: PARTIAL
CONSISTENCY_AUDIT: PARTIAL
MUTATION_ANALYSIS: PARTIAL
FIVE_BOARD_UI: PARTIAL
EXPORT: PASS
TARGETED_TESTS: PASS
FULL_REGRESSION: PARTIAL
LIVE_E2E: NOT_RUN
INDEPENDENT_REVIEW: NOT_RUN
OVERALL: PARTIAL
```

生成和评判已完成接口与确定性验证，真实模型待验收。四层审计缺 A 端观测。五板块已经过隔离 AppTest，主导航仍由整合者接线。完整回归通过本轮新增失败检查，团队历史参考的三条失败 ID 未获得。
