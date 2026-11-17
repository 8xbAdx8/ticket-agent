# 前端交互与浏览器 E2E

本轮在本机离线 Streamlit 和真实浏览器执行，未发起真实模型或远端追踪。实际浏览器与 Streamlit AppTest 分开列出；自动化替身不能作为真实 Live 证明。

|交互|实际结果|
|---|---|
|页面加载、进入测试工作台|真实浏览器通过|
|Legacy Mock 执行查票、Trace 展开和工具 JSON|真实浏览器通过；Trace `60b72e1043f34eb3b1cbe889337d4696`|
|切换 LangChain Mock、独立查询|真实浏览器通过；另有独立 Trace|
|变异 hallucinated_train 开关、执行和质量卡|真实浏览器看到虚构 G9999 注入和检出|
|恢复正常、连续执行|真实浏览器通过|
|测试按钮快速双击|修复前两条记录，修复后一次；下一次有意点击生成第二条|
|并发按钮快速双击|修复前两组记录，修复后仅一组两个对照记录|
|刷新后回放|真实浏览器以保存的会话 ID 恢复 Trace；不恢复模型上下文|
|Qwen 模式、离线禁用与中文原因|真实浏览器通过；未发送真实请求|
|场景、case ID、输入、步数、全部八开关、重置、错误提示、Trace/JSON、确认和 rerun|由离线 Streamlit AppTest 分项覆盖，见 `tests/test_v33_app.py`、`tests/test_unlimited_live_ui.py`、`tests/test_lab_audit_regression.py`；不声称每项都经真实浏览器手工操作|
|浏览器完全关闭后重开、跨标签/多用户长时并发、慢速 Live 双击|本轮未验证；回放须保留会话 ID|
|DeepSeek/Qwen 的真实发送、LangSmith 远端|本轮禁止真实请求，未验证|

检测到请求失败时保留实际错误和侧写；密钥本身不会显示。所有 API 执行仍需用户主动确认。

本轮源码测试提交 `08560abd8d111c70da1dd63e58659c113cd02b15`；交接文档所在提交以 `git rev-parse HEAD` 为准。离线回归：679 项通过，103 个子测试通过；JUnit 失败 0、错误 0、跳过 0。真实模型、Embedding、LangSmith 请求均为 0。原始文件核对 18369 项，变更 0 项。详细结果见 `docs/evidence/test_lab_audit/offline-report.json` 和 `protected-receipt.json`。
