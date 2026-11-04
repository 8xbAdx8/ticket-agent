# Ticket Agent V3.9.4 — Phase 0 Audit Report

日期：2026-11-04（Asia/Shanghai）。执行者：DeepSeek/Codex，开发自测；不是独立审查。

## 1. 开工现场

- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 暂存区：0
- 工作区：74 项（18 个已有跟踪修改 + 大量 V3.9/V3.9.1/V3.9.2/V3.9.3 未跟踪成果）
- V3.9.3 历史测试：`174 passed / 0 failed / 0 skipped`；旧回归历史：`1441 passed / 11 failed / 1 skipped`，另有199项子测试。
- 本轮没有清理、重置或改写任何历史未提交成果；新增 V3.9.4 修改见 Git 差异报告。

## 2. 现场关键事实

### 2.1 原版 UI

`web/app.py` 仍为 `出行助手 → web.conversation.user_page`；原左导航、聊天、右栏、四快捷入口、模型设置、历史会话、开发者/测试空间保留。V3.9.3 的 `web/railway_queries.py` 右栏三查询与 `web/v39_bridge.py` 服务仍存在。

### 2.2 实际默认失败复现

默认 `查余票` 表单：

- 入口：右栏“常用功能 → 查余票” → `web.user_features.ticket_search_panel`
- 默认：上海 / 杭州 / 2026-11-05 / 高铁 / 二等座
- 旧实现：调用 Agent `query_tickets`（旧 Fixture 数据源）
- 旧 Fixture 覆盖：`2026-10-20` 至 `2026-10-26`
- 直接复现：`query_tickets('上海','杭州','2026-11-05','二等座','高铁')` 返回 `NO_MATCH` / 0 行；日期在覆盖外。
- Agent 侧还会优先调用旧 `query_tickets`，而 V3.9 上下文/模型说明要求铁路静态查询；这就是“静态数据存在但默认查询未完成”的分层错位。
- 旧 `ticket_search_panel` 捕获异常后统一显示“本轮查询未完成，请核对数据来源和运行记录”，没有暴露真实状态（输入/无结果/数据不可用）。

### 2.3 四步快速体验

`web/demo.py` 旧实现：

- 引擎 `legacy`，`live=False`
- 第一步消息：`查明天上海到杭州的高铁二等座`
- 使用旧 `query_tickets` Fixture（覆盖 2026-10-20..26）
- 当前日期 2026-11-04 → “明天” 2026-11-05，超出 Fixture 覆盖；四个步骤无法开始。
- 演示入口声称“独立、无模型费用”，但业务依赖与默认日期不一致。

### 2.4 右栏铁路查询

`web/railway_queries.py`：

- 日期默认 `date.today()`（现场 2026-11-04），出发/到达默认“北京南/上海虹桥”；本身有真实 GTFS 车次，但默认值与其他默认用例不一致。
- 错误只映射 4 个 code；`STATIC_DATA_IDENTITY_MISMATCH`、`INVALID_RAILWAY_ARGUMENTS` 等会落到“查询未完成，请核对条件或稍后重试”。
- 查询失败只记录在 `session.railway_queries`，不写 `session.error`；这是正确的隔离基础，但缺少六态分类。

### 2.5 顶部通用红色错误

`web/conversation.py` 顶部 `_chat_body` 在 `session.error` 存在时始终显示通用错误。`session.error` 在 `Conversation._send` 开头清空，但：

- 侧栏 `user_features.query` 失败会把 Agent 错误留在 `session.error`，下一次 rerun 顶部继续显示。
- 因此会出现“聊天区为空、顶部红色错误”的残留现象；它不是订单错误，也不一定是当前铁路查询错误。
- 这是状态生命周期问题，不是查询数据问题。

## 3. 数据与保护

- GTFS DB：`e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`；实测 3169 站、11588 有效车次、107669 有效经停、187 隔离。
- 2026-11-05 上海虹桥(AOH)→杭州东(HGH)：真实静态 **109 班**；上海候选站 5、杭州候选站 4。
- 模拟场景 `railway-demo`：容量 SECOND=20；首班 `G7541` 模拟余票 20（本地库存，不是12306）。
- `data/v39/simulation.sqlite`：`a429b20be1242a4f6ea81c749df4a7718e6adf5138e973870821e97772c286fe`（未改）。
- `data/v39/simulation-v391.sqlite`：`9ebf39ecd8fd4caa277d6fa993ef0bbbeeb99355ab997d23a37678d0c44af939`（继承的冻结冲突，未连接/未修改/未删除/未回滚）。
- 本轮所有新测试使用 `artifacts/runtime/v394-*`；Store 只新增 `v394-` 允许前缀；GTFS 静态库只读。

## 4. 默认用例清单（整改前）

| # | 默认用例 | 默认输入/入口 | 旧调用链 | 旧实际结果 | 模型费用 | DB写 |
|---|---|---|---|---|---|---|
| 1 | 查余票 | 上海/杭州/2026-11-05/高铁/二等座 | Agent→`query_tickets` fixture | NO_MATCH / 0；侧栏显示通用失败 | 离线0；Live可能1+ | 否（但未完成） |
| 2 | 问政策 | 右栏“问政策” | `search_policy`/本地RAG | 有政策资料；不依赖订单 | 取决于会话 | 否 |
| 3 | 看订单 | “看订单” | Agent `query_order` + SQLite只读 | 空订单正常；新会话0 | 离线0 | 否 |
| 4 | 退票费率 | “退票费率” | `refund_calculator_panel` | 本地计算；不要求订单 | 否 | 否 |
| 5 | 四步快速体验 | “开始快速体验” | Agent `query_tickets`/create/pay/query | 2026-11-05超Fixture；无法开始 | 否 | 否（失败） |
| 6 | 右栏查车次 | 铁路查询/北京南→上海虹桥/today | Registry→GTFS | 可查询；默认值不一致 | 否 | 仅page_event |
| 7 | 右栏查车站 | 铁路查询/上海 | Registry→GTFS | 可查询；错误映射不足 | 否 | 仅page_event |
| 8 | 右栏查经停站 | G531/today | Registry→GTFS | 默认车次/日期不保证匹配 | 否 | 仅page_event |
| 9 | P06行李 | 行李费用面板 | `calculate_baggage` | 本地计算 | 否 | 否 |
| 10 | 其他预设 | 四快捷入口/模型设置/占位 | 原入口 | 部分默认依赖旧Fixture | 会话决定 | 否 |

## 5. 整改决策

1. 默认查余票改用同一 V3.9 Registry + 真实 GTFS：`web/railway_defaults.py`，默认 `2026-11-05 / 上海虹桥 / 杭州东 / SECOND`；城市名仍保留，显示候选并默认优选主要车站。
2. 默认模拟库存只通过 `railway_check_inventory` 读取；无库存/未配置显示正常空状态，不伪造余票。
3. 四步快速体验改为本地 GTFS + V3.9 Service 的确定性流程；不调用模型、不接外部铁路/支付；下单/支付仍走 proposal/confirm。
4. 右栏默认值与默认用例统一；六态分类；结果卡显示来源、版本、数量、分页。
5. 侧栏错误写入 `session.panel_error`，不污染 `session.error`；顶部错误显示后清除，旧请求不污染下一次；新会话独立。
6. 保留原 UI 三栏、聊天、右栏、四快捷入口、模型设置、历史/开发者/测试空间、16px/1.7 可读性；不做重设计。

## 6. 整改前证据

- V3.9.3 浏览器：`artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/ui-sealed/`
- V3.9.3 测试：`.../junit.xml`（174/0/0）
- 本轮整改后证据：`artifacts/runtime/v394-implementation-20261104-023000/`、`artifacts/runtime/v394-browser-final2/`
