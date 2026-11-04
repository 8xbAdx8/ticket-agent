# V3.9.3 回归、数据库及保护报告

证据 `artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/audit-pre-docs.json`：新V39 174/0/0；旧主测试1441/11/1，199子测试通过。V392原JSON同为1441/11/1+199；历史报告1640为合并通过数。失败和Skip逐ID一致，无新增旧失败（最终批次）；未修改旧测试。

旧失败ID：

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

唯一Skip：`tests/test_p2_scenarios.py::test_no_approved_p2_scenarios`。正式103仍BLOCKED，不计入新成绩。

中间启动器健康探测超时的第12失败保留；独立重跑及最终完整重跑通过该项，原因未定位。见old-regression-final/launcher-recheck/regression-sealed。

1892/4056/5538三组与本轮开工对比均0变化/0缺失；历史差异不回滚。SYSTEM_PROMPT/TOOLS/DIMENSIONS AST一致；Baseline未扩展。两个cursor可选字段是用户明确批准例外，其他铁路Schema语义一致。原103/expect/B、2100Fixture、GTFS、阶段八DB、旧库/日志/审查包保护。

冻结simulation-v391.sqlite本轮不连接，仅字节hash，462848字节 / 9ebf39ecd8fd4caa277d6fa993ef0bbbeeb99355ab997d23a37678d0c44af939；历史来源冲突仍BLOCKED。旧simulation.sqlite及两库SHM/WAL不变。主百炼账本314598字节/cecbf4...不变；新49请求独立usage保留，金额未知。

七个本轮查询测试库通过mode=ro核对，报价/提案/订单/交易0，foreign_key_check为空。资金库存生命周期沿用sealed-suite中的真实SQLite服务测试和T057–T076二十份探针；静态铁路数据不冒充真实库存或价格。未修改事务源码、DDL、D9/P01。

Git完整HEAD差异包含历史18项；本轮范围见实施报告和opening-to-current.patch。git diff --check退出0，暂存空，HEAD4340b6640025be95e8300a3d625a32cfb431e35d，未Commit/Push/Merge/Tag。最终状态及hash另见git-final.json/verification.json。

额外发现：V3.9.2交付目录113项封装清单112匹配，verification.json的封装字段与ZIP内原件不同。ZIP SHA匹配历史记录，ZIP内回执SHA匹配旧清单，只有zip_sha256和sha_manifest_sha256两个值发生差异。原件均未改，不将此项计为旧清单通过；详情见prior-seal-investigation/comparison。最终文档补记后的Git/保护清单见git-final-sealed.json、protection-final-sealed.json。
