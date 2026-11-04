# Ticket Agent V3.9.4 — Railway Query Fix Report

## 1. 根因

### A. 默认查余票失败

旧 `web.user_features.ticket_search_panel` 调用 Agent `query_tickets`，实际数据源是固定 Fixture `data/fixtures/train-v1.json`，覆盖 `2026-10-20` 至 `2026-10-26`。默认日期是“明天”（现场 2026-11-05），超出覆盖；同时“上海/杭州”在 GTFS 有 5/4 个候选站。结果是“静态 GTFS 有车、默认表单却查不到”，并被捕获成通用“本轮查询未完成”。

### B. 右栏错误提示

`web.railway_queries.result_card` 只映射少量错误码；`STATIC_DATA_IDENTITY_MISMATCH`、`INVALID_RAILWAY_ARGUMENTS` 等落到通用文案。右栏默认日期/站点与默认用例不一致。

### C. 顶部红色错误残留

`web.conversation._chat_body` 只检查 `session.error`，没有区分“上一请求”与“当前侧栏查询”。`web.user_features.query` 失败把 Agent 错误写入 `session.error`；下一次 rerun 顶部继续显示。右栏查询失败本身不写 `session.error`，所以两类错误被混在一起。

## 2. 修复

| 文件 | 修复 |
|---|---|
| `web/railway_defaults.py`（新增） | 统一默认日期/路线/席别；真实 GTFS 车站解析（城市名显示候选、默认优选上海虹桥/杭州东）；Registry 查询；首班模拟库存；六态分类。 |
| `web/user_features.py` | 高铁默认用例改走 V3.9 GTFS + 模拟库存；无库存/无车次正常空状态；侧栏失败写 `session.panel_error` 并清除 `session.error`；Feature Flag 关闭时保留旧 Fixture 兼容路径。退票/P06 表单补稳定默认输入。 |
| `web/demo.py` | 四步快速体验改为真实 GTFS + V3.9 Service 的本地闭环；不调用模型；下单/支付仍走 proposal+confirm；显式确认复选框。 |
| `web/demo_legacy.py`（兼容） | Feature Flag 关闭的旧测试环境使用旧 Agent 演示路径，不删除历史行为。 |
| `web/railway_queries.py` | 右栏默认日期/路线统一；六态状态与来源/版本/数量；查询异常封装为行状态；不写 `session.error`。 |
| `web/conversation.py` | 当前请求错误显示后清除会话级 `session.error`；保留 audit/trace，避免旧错误污染下一次。 |
| `target/v39/store.py` | 仅新增 `v394-` 隔离命名空间；旧保护路径不变。 |
| `scripts/run_v39_tests.py` | 允许 `v394-implementation-` 隔离输出前缀。 |

## 3. 实测

- 默认路线：`2026-11-05 / 上海虹桥(AOH) / 杭州东(HGH)`。
- 静态结果：**109 班**；返回 20；`has_more=true`；`gtfs-20261101-063437`。
- 模拟库存：首班 G7541，`SIMULATED_AVAILABLE`，20 张；不是12306。
- 城市候选：上海 5、杭州 4；默认选择可见且明确。
- 右栏三模式：车次 109；车站 5；经停 G7541 10 站。
- 默认查余票不再产生“本轮查询未完成”；无库存/无车次是正常状态。
- 四步：stage 4；1 order / 1 transaction / 2 proposals；订单 PAID。
- 顶部错误：侧栏查询失败不写 `session.error`；当前错误显示后清除；新会话无旧错误。

## 4. 错误分类

```text
INPUT_INVALID      空/非法参数，提示补充输入
FOUND              真实静态车次/车站
NOT_FOUND          没有匹配；正常空状态
DATA_UNAVAILABLE   静态库身份/读取异常
TOOL_EXECUTION_FAILED 权限/上下文/工具失败
INTERNAL_ERROR     未预期异常；开发者保留诊断
```

用户端不显示 Python 堆栈、SQLite 路径或内部异常；开发者空间/Trace 保留异常类型、request_id、堆栈。

## 5. 保留

- 原版三栏、聊天、右栏、四快捷入口、模型设置、历史/开发者/测试空间不变。
- 旧 8 工具、V3.9 11 工具、Agent.chat 十字段、Trace 五字段、Baseline、D9/P01、确认机制不变。
- 未接真实铁路/支付 API；未新增铁路数据 API；未调用真实模型。
- `data/v39/simulation-v391.sqlite` 未连接/修改/删除/回滚；继续 `PRODUCT_DB_PROTECTION=BLOCKED`。

## 6. 证据

- `artifacts/runtime/v394-probes-20261104/v394-probes.json`
- `artifacts/runtime/v394-browser-final2/results.json`
- `artifacts/runtime/v394-browser-final2/rail-results.json`
- `artifacts/runtime/v394-browser-final2/error-recovery.json`
- `tests/v39/test_v394_defaults.py`
