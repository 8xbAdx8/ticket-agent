# Ticket Agent V3.9.4 — Default Use-Case Matrix

日期：2026-11-04。默认环境：离线 Mock、V3.9 Feature Flag 开启、隔离 `artifacts/runtime/v394-*`；不调用真实模型/铁路/支付。

| # | 用例 | 默认输入 / 入口 | 实际调用链 | 数据来源 | 前置 | 预期 | 本轮实际 | 模型费用 | DB 写入 | 确认 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 查余票 | 右栏/常用功能“查余票”；上海/杭州；2026-11-05；高铁/二等座 | `user_features.ticket_search_panel` → `railway_defaults.resolve_trips` → Registry `railway_search_stations`/`railway_query_trips`/`railway_check_inventory` | GTFS 阶段八 + 本地 `railway-demo` 库存 | Feature Flag；静态库只读；隔离 V39 DB | 静态真实结果；有/无模拟库存都正常显示 | **FOUND 109 班，页 20，首班 G7541 模拟余票 20**；上海 5/杭州 4 候选，默认优选上海虹桥/杭州东 | 0（不经模型） | 首次库存 materialize（隔离库） | 无 |
| 2 | 问政策 | “问政策”面板；全部分类 | `policy_browser_panel` → 本地政策文件/RAG 本地数据 | 项目示例政策 | 无 | 政策有 doc_id/原文；不要求订单 | P01/P02/P03/P06/P08/P11/P12 均可浏览；默认不检索也能看到目录 | 0 | 否 | 无 |
| 3 | 看订单 | “看订单”→“查询我的订单” | Agent `query_order` + `order_read_model` 只读 SQLite | 当前会话 `tickets.db` | 当前用户/会话 | 空订单正常；不偷建订单；不跨用户 | 新会话返回空状态，不创建订单；读取失败有独立提示 | 离线0；Live会话才可能计费 | 否（只读） | 无 |
| 4 | 退票费率 | “退票费率”；已支付、¥500、3天后、12:00、未改签 | `refund_calculator_panel` → `target.order_refund.calculate` | 本地政策计算 | 无实际订单也可咨询 | 解释 P01；不自行退款 | 默认输入有值，提交显示 P01 费率/手续费；不要求订单 | 0 | 否 | 无 |
| 5 | 四步快速体验 | “开始快速体验”→查询→确认下单→确认支付→查单 | `web.demo` → 真实 GTFS + V3.9 `Service.quote/propose/confirm/order` | GTFS + 隔离模拟库 | Feature Flag；隔离 DB | 4步真实本地闭环；确认；新会话重开 | **stage 4；1 order / 1 transaction / 2 proposals / 6 inventory events**；订单 PAID | 0 | 是（隔离库） | 两个 checkbox + 按钮 |
| 6 | 右栏查车次 | “铁路查询”→查车次；上海虹桥/杭州东/2026-11-05 | Registry 三工具；结果卡在聊天区 | GTFS | Feature Flag | 真实候选、数量、来源、分页 | **共 109 条，返回20，has_more**；G7541 等真实车次 | 0 | 仅 page_event 审计 | 无 |
| 7 | 右栏查车站 | “铁路查询”→查车站；上海 | Registry `railway_search_stations` | GTFS | Feature Flag | 列出真实 5 站 | **共 5 条**：上海/上海南/上海虹桥/上海西/上海松江 | 0 | page_event | 无 |
| 8 | 右栏查经停 | “铁路查询”→查经停站；G7541/2026-11-05 | Registry `railway_query_trips`→`railway_trip_stops` | GTFS | Feature Flag | 候选班次→真实经停 | **G7541 / 5l000G75410A，10 站**；结果卡显示经停记录 | 0 | page_event | 无 |
| 9 | P06 行李 | “行李费用（P06）”；成人/25kg/50×40×30 | `target.baggage.calculate_baggage` | 本地 P06 | 无 | 免费/超重/费用/尺寸说明 | 免费20kg、超5kg、¥25、尺寸符合；不推断未定义尺寸收费 | 0 | 否 | 无 |
| 10 | 四快捷/占位/其他 | 查余票、问政策、看订单、退票费率；输入框占位；铁路查询默认 | 原 UI 入口 | 上述 | — | 点击有明确下一步，不必然失败 | 四快捷入口均可见；查余票默认用例真实成功；空订单/无库存是正常空状态 | 取决于入口 | 取决于入口 | 交易入口保留 |

## 状态映射

- `FOUND`：真实静态结果，有数量/来源/版本。
- `NOT_FOUND`：无匹配车次/车站；不显示为异常。
- `INVENTORY_SOLD_OUT` / `INVENTORY_NOT_CONFIGURED`：正常模拟库存状态，不伪造余票。
- `INPUT_INVALID`：空站名、非法日期/参数。
- `DATA_UNAVAILABLE`：静态库身份/读取异常。
- `TOOL_EXECUTION_FAILED`：权限/上下文/工具执行失败。
- `INTERNAL_ERROR`：未预期异常；用户只看到通用提示，开发者空间保留 trace/堆栈/request_id。

## 不产生未授权交易

- 默认查余票、车站、经停、政策、退票计算、P06 均不创建订单/支付/退款。
- 四步体验只有用户点击两个确认复选框和按钮后才 `propose+confirm`；未确认前数据库 orders/transactions 为 0。
- 测试 T100 验证：查询后、确认前 0 orders / 0 transactions / 0 proposals。

## 证据

- 自动化：`tests/v39/test_v394_defaults.py`（T077–T100）。
- 浏览器：`artifacts/runtime/v394-browser-final2/results.json`、`rail-results.json`、`error-recovery.json`。
- SQLite 探针：`artifacts/runtime/v394-probes-20261104/v394-probes.json`。
