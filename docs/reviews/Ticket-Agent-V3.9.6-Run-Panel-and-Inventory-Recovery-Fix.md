# V3.9.6 运行面板与库存查询纠错修复

2026-11-04。分支 `feat/ticket-agent-v36-stabilization`，HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`。保留既有未提交成果，无提交/推送。证据目录：`artifacts/runtime/v394-implementation-v396-run-panel-20261104/`。

## 1. 运行面板缩进

原因：`web/conversation.py` 将“本次处理与历史运行”包进默认关闭的expander，内容再叠加Streamlit展开区内边距和user_rail卡片内边距；`_run_summary_bar`还沿用宽屏3.1:1.6外层分栏，再把操作区二分，桌面两个按钮各约41px，文字变成“回…”。

修复：该区域改为右栏普通标题，摘要和跳转按钮上下排列，仅保留一层按钮分栏；右栏局部取消摘要sticky定位，避免滚动覆盖。按钮key、点击处理、历史选择、会话状态不变。没有改Agent/交易业务来解决布局。

Edge实际四规格（1600×1100/390×844，浅深色）：`after-fresh/results.json` 28通过/0失败，4张修复后截图；before中有4张原图。桌面按钮约164px，手机330px并自动分行；面板不在expander内、原四快捷入口保留、无横溢出。PageError0，Console8/网络失败8为主动阻止远端fonts.gstatic.com图标。初次after使用旧服务缓存模块产生的失败记录保留；新独立进程加载实际源码后验证通过，不将旧进程失败冒充新代码结果。原脚本测量曾包含Streamlit隐藏备用按钮，复验按实际可见按钮测量。

## 2. DeepSeek库存成功后整轮仍失败

原始会话：`artifacts/runtime/v33/user/web-d722d4b22677/traces/`，失败运行 `0747283de4ae492192b81d9da0f06224`。

实际链路：

1. `railway_check_inventory` 把中文“上海虹桥”“宁波”传入stop_id字段，返回 `STATION_ID_REQUIRED`。
2. 模型调用两次 `railway_search_stations`，取得唯一真实站点AOH、NGH。
3. 同一G7543、2026-11-04、一等座、1人区间用ID重查，返回模拟余票8张。
4. 原LangChain收尾逻辑仍因第一条失败执行而抛出 `tool_execution_failed`，没有返回本轮公共契约；界面继续显示上轮回答，右侧正确保留最新失败。

修复：新增 `target/v39/read_recovery.py`，仅识别本轮库存查询的 `STATION_ID_REQUIRED`。必须有后续已执行成功的唯一精确站名→ID查询作为证据，且库存重查除站点表示外所有参数完全一致、返回真实成功状态及整数available，才建立失败call_id→恢复call_id映射。`target/langchain_agent.py`收尾校验只豁免已证明恢复的那条读操作失败，并追加 `railway_read_recovered` 事件。

原失败的ok=false、Trace、用量、工具成功率全部保留。不同日期/车次/席别/人数/区间、站点歧义、未执行/失败重查、权限错误、未恢复失败仍然拒绝；不会恢复写操作，不扩大权限、不自动重试、不自动下单。拿到8张模拟余票不等于锁座或购票成功。历史失败运行原件没有修改。

## 3. 实际验证

```powershell
.venv-v35\Scripts\python.exe -B artifacts/runtime/v394-implementation-v396-run-panel-20261104/run_tests.py related-tests
.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v394-implementation-v396-run-panel-20261104/v39-tests-sealed
.venv-v35\Scripts\python.exe -B artifacts/runtime/v394-implementation-v396-run-panel-20261104/run_regression.py old-regression
node artifacts/runtime/v394-implementation-v396-run-panel-20261104/browser.js after-fresh
git diff --check
```

- 原滚动/用户功能/文案/政策聊天相关测试75通过，0失败/跳过。
- V3.9全套272通过，0失败/跳过；本轮新增13个库存恢复测试。实际Registry+阶段八只读GTFS+隔离SQLite测试，进入真实生产Live收尾分支，但模型为确定性离线替身，无真实API。成功纠错后仍保留第一条失败，正确返回8张和未锁座提示；未恢复分支依旧抛原错误。订单/报价/提案/交易表均为0。
- 旧完整回归1441通过、11失败、1跳过，另199子测试通过；失败和skip ID与V3.9.6上一批完全一致，未改旧断言/skip。结果退出码1，不能声称全绿。
- 四规格浏览器28/28；截图仅证明本轮布局，未伪称重新调用真实DeepSeek验证。
- 早期新测试因测试沙箱设置/marker缺失的失败批次完整保留，修复的是新测试环境设置，没有降低生产沙箱校验。

原始日志、JUnit、输入fixture、实际命令、Git/保护比较与源码SHA见证据目录和 `verification.json`。真实模型/铁路/支付/Embedding/LangSmith调用0。新增用户Live运行导致的账本追加按本轮截图对应现场单独留基线，不截断或回退；与本轮测试用量分离。

## 4. 修改范围与限制

- `web/conversation.py`、`web/user_layout.css`：仅运行区域布局。
- `target/langchain_agent.py`、新增`target/v39/read_recovery.py`：可证明的库存读纠错，不改变任何交易成功条件。
- 新增`tests/v39/test_v396_inventory_recovery.py`及`fixtures/v396-inventory-recovery.json`；更新PROJECT_STATUS与本文档。
- 公共十字段/工具五字段、原8/V3.9工具Schema、SYSTEM_PROMPT、DIMENSIONS、Baseline、D9/P01、数据库结构与原始数据均未修改。

IMPLEMENTED / TESTED（上述离线范围）；BROWSER_VERIFIED（面板布局）；LIVE_API_VERIFIED=NOT_RUN；外部独立审查未执行；ACCEPTED待用户。正式103、Bridge、冻结DB来源和历史11失败保持原状态。旧失败记录不会变成成功；新轮消息加载修复后代码才会采用新判定。需要时用原CMD重新启动服务，不需设置新变量。
