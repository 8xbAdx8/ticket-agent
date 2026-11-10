# V3.11 冻结回归与保护

日期：2026-11-10（Asia/Shanghai）。HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`。整体 **PARTIAL**；未提交、未推送。

## 最终结果

R3：**1971 passed / 11 failed / 1 skipped**，另199子测试通过；退出码1。76项V311专项全部通过。没有新增skip/xfail，没有修改旧11失败或唯一Skip。R1=1929/11/1，R2=1970/11/1均保留，最终以R3源码绑定为准。

采用现有regression_center.prepare：校验原复测包冻结证据/缓存，覆盖当前源码，复制只读静态SQLite及原SQL，在独立工作副本、独立业务库、网络阻断、Python3.12.14/.venv-v35下运行；不在旧业务数据库执行测试。没有重装依赖。

实际命令：

```powershell
.venv-v35/Scripts/python.exe -B artifacts/runtime/v310-v311-20261110-implementation/regression.py full-regression-r3
```

内部完整命令及参数在R3 results.json：tests -q -p no:cacheprovider --junitxml=… --basetemp=冻结副本/artifacts/runtime/v310-ai-v2-tests。R3执行约242秒，原始stdout、JUnit和逐ID报告均保留。

## ID级比较

比较 `ai-test-v2-20261109/final-regression-r4/results/results.json` 的可信1891/11/1：失败/Skip集合无增减。总数量增加来自既有4项V310新DSL测试+本轮76项。预算测试授权重命名：原 test_token_warning_and_hard_reservations → test_token_warning_is_observability_not_a_hard_cap；它是明确已批准的/3政策测试差异，不是删除失败。原名在missing_ids保留并单独映射，不能当作全ID零变化。

原11失败：

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

## 保护

原5587清单不覆盖：5586一致；唯一差异为tests/v39/test_acceptance_budget_v2.py。

- 原SHA：4697eb838497f2ead1f3d304710a060acd03af5f651c8d69fd2e9832bebaa6cc。
- 本轮开工及批准SHA：c09730dc2fe33cc7226e7c934508fa1f8b1e4ae4bc54f22fb2a2f1712b14b37f。
- 用户已在本对话明确批准限定例外；本轮未再修改该测试。

原业务DB及WAL/SHM、原API账本、正式103/expect/B快照、GTFS及静态库均在保护范围且无新增差异。正式103仍BLOCKED，没有伪造原B方执行器。

## 证据身份

`artifacts/runtime/v310-v311-20261110-implementation/authorization.json`；SHA256 `b5519df9838dcee7e66066093f9ffdce9144c29933d16ab95347c1420a267bf5`

`artifacts/runtime/v310-v311-20261110-implementation/coverage-final.json`；SHA256 `d74fd76a772f23fdf9cf07b2478bac1a2ea3d170ec66532b81523955bf76a425`

`artifacts/runtime/v310-v311-20261110-implementation/budget-final.json`；SHA256 `239d9bb23b3ffebbe888a49ad0fa6e5aefe218042ad825b3d3696c513dc2333f`

`artifacts/runtime/v310-v311-20261110-implementation/database-verification.json`；SHA256 `0cc7acd2bd8a1f57b4257d36781ab578336a3b345b10dabec39d4d3f5bdd2996`

`artifacts/runtime/v310-v311-20261110-implementation/regression-comparison.json`；SHA256 `c017e1a47884bdd198357bf320a3bcda48ec82ef379c5b09ee43f966ba8c6a45`

`artifacts/runtime/v310-v311-20261110-implementation/protection-final.json`；SHA256 `91740a2751c4bc66d6b992b6159462639c99dcd64f1d35a6e7176fbe43a98ef3`

`artifacts/runtime/v310-v311-20261110-implementation/full-regression-r3/results/results.json`；SHA256 `02ba3c02b8cb80f2bf83d5ea1f53c1f66b155fc27d6a1d0ac695b1b39ffdc76b`

`artifacts/runtime/v310-v311-20261110-implementation/full-regression-r3/source-manifest.json`；SHA256 `658a05e00edcb12a299ea3ef4f8b494394f1fde05f78386cdd3e91591753ced0`
