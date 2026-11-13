# Ticket Agent QA-09 工业级修复报告

2026-11-11 · PASS · 分支 `feat/ticket-agent-v36-stabilization` · HEAD `68f6a5c80ab6fadde3815d0e6e1a0371392d81c9`

开工工作区干净、暂存区为空，本地领先跟踪引用 4 个提交。任务书中的 `8a6ccf36688c9cab803d46ba0bbf652290132e19` 是整理 Git 前的历史基线。现场证据见 [Git 开工记录](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/git-opening.json) 和 [保护清单](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/protection-manifest.json)。

## 目标与根因

| 问题 | 原始证据和根因 | 整改 |
|---|---|---|
| QA-09-A 经停路径 | 两家原始候选使用 `result.data.0.stop_id` / `stop_name`。真实经停结果的 `data` 是包含 `trip` 和 `stops` 的对象。旧门控用前缀判断路径。 | 用与 Registry 相同的只读 RailwayStatic 读取结果，按实际 DSL 点号路径和数组索引核验。 |
| QA-09-B 指定车次 | 原 DeepSeek 省略 `train_no`。冻结 GTFS 在该区间第一页首班是 G7541。 | 要求精确过滤和选中行的 `trip_short_name` 等值断言。经停 `trip_id` 引用同一已核验行，并校验日期。显式请求给出日期及两个可核验站点 ID 时，查询必须使用同一日期和区间。 |
| QA-09-C flag | 历史候选缺少顶层 `enabled`。首轮 Qwen 把该字段放进 `args`。 | DSL 校验要求步骤顶层显式布尔值，校验顺序与结果。生成上下文使用实际 Schema，并提供合法及非法示例。 |
| QA-09-D 经停数量 | 历史候选断言 2 站。冻结 GTFS 的 G7331 `5l000G733102` 在 2026-11-05 的完整 `data.stops` 有 9 个元素，AOH 为首站，HGH 为第三站。 | 用真实数组验证长度及元素断言。Prompt 明确区分全程站数、样本数组和区间端点。 |

GTFS 数据库 SHA-256 为 `e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`。三条原始候选与隔离库中的 CREATE 快照逐项一致，均保持 PENDING。最终只读复查三条均 REJECTED，并命中原缺陷。见 [真实输出样本](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/schema-audit-delivery.json)、[历史候选回归](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/qa09-regression-delivery.json)。

## 质量门和改动

- `target/scenario_generator.py` 统一创建、编辑、人工审核的规则入口，持久化规则版本、请求目标和选定适配器。在独立 `quality_reviews` 表追加每次创建、编辑和人工批准尝试的判定。批准失败的审计记录保留，整批状态保持原样。
- `target/scenario_v310.py` 提供共用 DSL 语法和 flag 字段规范，限制路径长度，记录具体步骤、字段和错误码。执行器继续使用原 Registry 和业务 Service。
- `target/scenario_static_review.py` 用本地 GTFS 证明静态断言，校验原始请求的明确车次、日期、站点、经停检查和只读范围。候选评估只调用允许的静态查询方法。
- `target/scenario_output_contract.py` 用版本化 SQLite DDL、价格和二维码纯函数及已验证运行结构检查动态路径。结构已核验的动态结果仍需批准后执行取得实际值。
- `web/scenario_generator.py` 显示当前隔离预算的真实剩余额度。正式审核状态和执行入口继续由现有控件管理。
- `tests/test_scenario_qa09.py` 验证真实 GTFS、正负样本、引用、规则旁路、重复与审核历史，并以可信参考计划的真实 Registry 输出校对动态路径。
- 本报告和 `PROJECT_STATUS.md` 记录证据。保护清单中的原始候选、账本、业务库、正式测试、B 快照和旧报告均以 SHA-256 核对。

## 双模型 Live 和浏览器

隔离批次 `395a7ae50ae74ed4bc17bc2407ffe86e`。使用本机 Edge 经真实生成页面触发，实际 4 次 HTTP，均 200，0 次自动重试。发送前原子预留，未知用量会锁住后续发送。历史账本和批次继续保留。请求、响应、请求 ID、模型用量、候选及创建审计逐项对齐。

| 模型 | HTTP | Prompt Token | Completion Token | 总 Token | 费用 |
|---|---:|---:|---:|---:|---|
| DeepSeek | 2 | 16,575 | 1,029 | 17,604 | UNKNOWN |
| Qwen | 2 | 16,496 | 1,422 | 17,918 | UNKNOWN |
| 总计 | 4 / 20 | 33,071 | 2,451 | 35,522 / 120,000 | UNKNOWN |

单次输出上限 4,096，实际最高 732。4 条候选保存成功，人工批准 0，候选执行 0。隔离库的执行记录为空。质量门的实际判定保留两个时间点。

| Provider | 候选 | 创建判定与规则版本 | 最终只读复查 | 审核状态 |
|---|---|---|---|---|
| deepseek | AI-GEN-3b48cd4ccaf549c2 | PASS · 2 | REJECTED | PENDING |
| bailian | AI-GEN-a3188d8afc044c39 | REJECTED · 2 | REJECTED | PENDING |
| deepseek | AI-GEN-b674b96e2daa480f | PASS · 4 | PASS | PENDING |
| bailian | AI-GEN-4839ee70d0344fd8 | PASS · 4 | PASS | PENDING |

首轮 DeepSeek 缺少请求要求的 `metrics.order_count=0` 检查，创建判定依照当时的 /2 规则保存，/4 规则复查拒绝。首轮 Qwen 缺少顶层 `enabled`。两家复验候选在最终规则均通过。最后的超长路径防护在已有候选上只读复查，无额外请求。

浏览器首轮两家各 7 项通过。第二轮 Qwen 10 项通过，含回执请求 ID、PENDING、禁用执行按钮、空 Trace、刷新不重复生成。第二轮 DeepSeek 已生成并保存，首次检查中通用定位器取到折叠 JSON 中的隐藏节点。页面原始文本包含请求 ID，另一次零请求重新打开通过 5 项，核对 PENDING、Trace 和刷新前后 SQLite 行。一次预检错误来自脚本的主机白名单缺少仓库已配置的 Qwen 端点，该尝试消耗 0 请求。修正白名单后沿用原配置。相关页面 PageError 0，外部图标请求按测试环境网络规则阻断，Console 与 Network 原始事件保留。

证据见 [原始请求与响应](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/raw-http/)、[Live 预算](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/live-budget.json)、[逐笔请求](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/live-requests.jsonl)、[质量门结果](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/quality-gate-results.json)、[浏览器汇总](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/browser-results.json)、[DeepSeek 截图](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/live-round2-reopen/reopen-deepseek/reopened.png)、[Qwen 截图](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/live-round2-reopen/generation-bailian/result.png)。

## 回归与隔离

使用现有 P0 冻结包、当前源码及 SHA-256 一致的静态 SQLite 副本。测试进程禁用本地密钥和外网连接。新测试中的交易验证使用可信确定性参考计划和隔离 SQLite，所有 Live 生成候选的批准和执行均为 0。正式 103 条原始执行器状态仍为 BLOCKED。

| 范围 | Passed | Failed | Skipped | 证据 |
|---|---:|---:|---:|---|
| QA-09 新增专项 | 53 | 0 | 0 | [原始 JUnit](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/pytest-qa09-final-delivery/junit.xml) |
| 相关模块含专项 | 222 | 0 | 0 | [原始 JUnit](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/pytest-targeted.xml) |
| 完整项目 | 2079 | 11 | 1 | [原始 JUnit](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/pytest-full.xml) |
| 历史冻结对照 | 2023 | 11 | 1 | [原始统计](../../artifacts/runtime/v310-v311-qa-product-20261111/pytest-full-final/summary.json) |

完整项目另有 199 个子测试通过、0 个子测试失败。完整命令、日志、逐 ID 比对见 [运行命令](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/pytest-full-delivery/command.json)、[完整日志](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/pytest-full-delivery/pytest.log)、[回归比对](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/pytest-full-delivery/summary.json)。

### FAILED ID

**unchanged**

- `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_configured_online_default_is_deepseek_and_render_never_calls_agent`
- `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_direct_send_permission_is_session_and_provider_specific`
- `tests/test_deepseek_direct_send.py::DeepSeekDirectSendTests::test_qwen_still_requires_its_original_checkbox`
- `tests/test_followups_continuous.py::ContinuousFollowupsTests::test_qwen_ten_clicks_survive_timeout_and_saved_replay`
- `tests/test_followups_mvp.py::FollowupRuntimeTests::test_qwen_ui_consent_automatically_includes_followups_offline`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_empty_qwen_run_has_a_clear_reason_and_disabled_export`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_explicit_history_selection_is_preserved_and_model_is_explained`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_live_fee_consent_does_not_follow_a_different_provider`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_qwen_panel_rejects_another_provider_record_without_export`
- `tests/test_qwen_langsmith_ui.py::QwenNavigationTests::test_qwen_stays_active_after_opening_integration_center`
- `tests/test_unlimited_live_ui.py::LivePageTests::test_bailian_user`

### SKIPPED ID

**unchanged**

- `tests/test_p2_scenarios.py::test_no_approved_p2_scenarios`


## 独立审查与保护

独立只读 Agent 复核 PASS。审查发现并复核了适配器降级、遗漏目标查询、错误区间和日期、动态路径及引用失效、只读计划混入业务写操作等缺口。另核对了错误批准的审计留存、超长数字索引、浏览器定位器和 4 条真实 HTTP。最终审查范围内无剩余 P0/P1。完整项目回归由开发验证单独记录。见 [独立审查](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/independent-review.json)。

开工 SHA-256 清单共 8563 项。原账本、GTFS、候选、数据库和历史证据的最终比对见 [保护核验](../../artifacts/runtime/qa09-fix-live-20261111/run-20261111-160800-054851/protection-final.json)。百炼原账本开工时的 516,264 字节前缀经 SHA-256 核对完整。用户确认首段外部追加的 9,379 字节作为结束基线。后来在原账本继续观测到外部追加，保留原件并在保护报告中独立记录。QA-09 的四个请求 ID 与原账本追加记录无重叠。Git 暂存区为空，`git diff --check` 通过。没有提交或推送。证据目录下各运行保留原始结果。

## 验收

| 项目 | 状态 |
|---|---|
| TOOL_SCHEMA、STOP_PATH_VALIDATION、TRAIN_ID_VALIDATION | PASS |
| STOP_COUNT_VALIDATION、FLAG_SCHEMA、PROMPT_ALIGNMENT | PASS |
| QUALITY_GATE、HISTORICAL_REGRESSION | PASS |
| DEEPSEEK_LIVE、QWEN_LIVE | PASS |
| BROWSER_E2E | PASS |
| SQLITE_ISOLATION、API_BUDGET | PASS |
| FULL_REGRESSION | PASS |
| INDEPENDENT_REVIEW | PASS |
| PROTECTED_ASSETS | PASS |

**PASS。** 当前证据覆盖两家模型的 QA-09 小样本。动态交易行为和任意场景语义继续由获准后的独立执行检验。符合进入下一轮 AI 测试体系验收的 QA-09 前置要求，候选仍需人工审核，正式 103 条评分继续 BLOCKED。
