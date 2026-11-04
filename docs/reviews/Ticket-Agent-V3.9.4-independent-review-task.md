# Independent Review Task — Ticket Agent V3.9.4

## 状态

```text
IMPLEMENTED: YES
TESTED: YES (development; final counts below)
LIVE_API_VERIFIED: NOT_RUN（本轮无真实模型调用）
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
BLOCKED: product v391 DB source conflict; formal 103/B; Bridge
```

## 审查范围

1. **默认用例**：查余票、问政策、看订单、退票费率、四步快速体验、右栏三模式、P06、四快捷/占位。
2. **查余票**：真实 GTFS 静态车次；上海/杭州候选；默认优选；无库存/无车次正常状态；模拟库存不冒充实时余票。
3. **四步**：真实本地闭环；proposal/confirm；确认前 0 订单/交易；新会话重开；不接外部铁路/支付。
4. **右栏**：三模式、来源/版本/数量、分页、六态错误分类；不写聊天级错误。
5. **错误隔离**：右栏查询、Agent 请求、交易操作各自状态；新请求/新会话不继承旧错误；旧成功卡不在失败时复用。
6. **原版 UI**：三栏、聊天、右栏、四快捷、模型设置、历史、开发者/测试台、16px/1.7；不得重设计。
7. **保护**：GTFS/static/2100/103/B/旧 tickets/旧 V1 文档/历史证据；不得修改 D9/P01、旧8工具、Agent.chat/Trace、Baseline、正式103。
8. **数据库**：`data/v39/simulation-v391.sqlite` 不连接/不修改/不删除/不回滚；新测试只用 `v394-*`；GTFS 只读。
9. **无真实模型**：本轮应无 Qwen/DeepSeek HTTP；检查 API 账本未新增、无 Key 输出。

## 复现命令

```powershell
# V3.9.4 全套（离线，198+）
.\.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v394-implementation-20261104-025000

# 旧全范围（期望保留 11 failed/1 skip，不新增）
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v391-d9-lifecycle-20261103-150639/run_old_regression.py old-regression-v394-final

# 浏览器（需先以隔离库启动离线服务；默认 Mock）
# 参考 artifacts/runtime/v394-browser-final2/*.js、results.json
```

浏览器必须用：
`RAILWAY_SIMULATION_ENABLED=1`、`RAILWAY_SIM_DB_PATH=artifacts/runtime/v394-.../simulation.sqlite`、`TICKET_WEB_OFFLINE_ONLY=1`、`AGENT_PROVIDER=mock`。
禁止对 `data/v39/*` 启动服务。

## 必须检查

- 默认余票是否真的来自 GTFS，而不是旧 Fixture；站名候选是否真实。
- 默认日期 2026-11-05 是否在 GTFS 中；109 是否与实际 `total_count` 一致。
- 模拟库存是否来自 `railway_check_inventory`；无库存是否正常显示。
- 四步 proposal/confirm 是否真实；确认前 0 orders/transactions；支付是否本地模拟。
- 右栏失败是否不显示顶部通用红色错误；新会话是否清空；旧成功卡是否不被失败请求复用。
- 浏览器四规格/手机右栏/横向溢出/输入框/结果卡。
- 旧回归新增失败（尤其 `test_ticket_submit_once...`、p0 demo、test_v33 failure-not-replace）是否修复；若未修复列出。
- 保护资产 SHA 与继承冻结 DB 冲突。
- 无真实 API 调用/费用/Key 输出。

## 禁止

- 重做原版 UI、删除功能、修改 D9/P01、扩大工具白名单、修改旧8工具/Agent.chat/Trace/Baseline/正式103。
- 修改 GTFS 原件或连接 `data/v39/simulation-v391.sqlite`。
- 真实铁路/支付/模型 API（除非用户单独授权）。
- Commit/Push/Merge/Tag/Bridge。
- 将开发测试、浏览器通过或四步单乘客当作完整验收/独立审查。

## 期望回执

```text
VERDICT: GO_FOR_USER_ACCEPTANCE | BLOCKED
DEFAULT_CASES: PASS/FAIL
RAILWAY_QUERY: PASS/FAIL
QUERY_STATE_ISOLATION: PASS/FAIL
ORIGINAL_UI: PASS/FAIL
V394_TESTS: passed/failed/skipped
OLD_REGRESSION: passed/failed/skipped; new failure IDs
PROTECTION: ...
LIVE_API: NOT_RUN
```
