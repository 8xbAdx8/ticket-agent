# Ticket Agent V3.9.1 统一铁路产品实施报告

- 日期：2026-11-03（Asia/Shanghai）
- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 状态：**IMPLEMENTED / TESTED（开发验证）**；`INDEPENDENTLY_REVIEWED = NOT_RUN`；`ACCEPTED = PENDING_USER_ACCEPTANCE`。
- 不是 COMPLETE，不是独立审查通过，不是 B 方正式 103 成绩。

## 1. 本轮改动

1. **统一用户入口**：移除“咨询与演示业务 / 全国铁路模拟出行”二选一 radio；用户工作空间直接渲染统一铁路助手。
2. **统一工作区**：左侧主区为真实静态车站/车次/经停/报价/自然语言对话；右侧为本人订单、待确认操作、当前行程、D9/P01 政策摘要。表单、对话、订单使用同一 V3.9 服务。
3. **自然语言**：确定性离线 Planner 实际调用 `railway_search_stations`、`railway_query_trips`、`railway_get_order` 等注册工具；增加 D9/P01 政策回答、经停结果摘要；不编造车次/时间/订单。
4. **D9 落地**：产品 `policy_profile=CHANGED_REFUND_P01`、`approved=true`；改签后退款、部分退款后改签剩余 ACTIVE、多次退款、失败保留与重试均已接线。
5. **统一订单生命周期**：三人购票→支付→退一→改签两人→退一→退最后一人；每一步通过真实 SQLite 验证订单、items、hold、库存、交易、退款和守恒。
6. **两个 CMD**：均启动同一个 `web/app.py`；local `RAILWAY_SIMULATION_ENABLED=1`，保留在线/离线 Provider 差异；未使用 setx。
7. **历史问题**：T046 采用原始 GTFS 实际 `30:51:00`→`2026-11-03T06:51+08:00`；T031 使用两个独立提案/进程竞争、失败记录、幂等重放和新提案重试，未伪造 UI 拒绝事件。
8. **测试**：新增/保留 T057–T076，全部真实 SQLite 断言；V3.9/V3.9.1 全套 164 passed / 0 failed / 0 skipped；T057–T076 20 项全部通过并各有 db-probe。

## 2. 统一 UI

页面标题：`Ticket Agent · 铁路出行助手`。

- 顶部不显示业务模式二选一。
- 主区：查找行程、选择站/车次、经停、模拟席别、乘客、报价、建单、对话。
- 右侧：待确认卡、本人订单、乘客明细、退款/改签入口、当前行程、政策与费用。
- 原有侧栏保留：用户工作空间、开发者工作空间、测试控制台、模型设置、主题、历史会话。
- 受保护旧页面/旧 CSS/旧 key 不被覆盖；`web/conversation.py` 保留。
- 铁路会话支持新建/清空/本次浏览器内的历史会话选择；订单仍按当前会话展示。
- 离线/在线 CMD 都加载同一个统一页面；在线模式不发起 V3.9 真实模型/铁路/支付请求，页面明确提示本地模拟边界。

## 3. 静态数据与 Agent

- 唯一静态入口：`target/v39/static.py`。
- 实际数据库：`artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite`；SHA `e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`。
- 原始 GTFS ZIP SHA `3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`。
- 3169 stations、11588 effective trips、107669 stop times、187 quarantine。
- 车次/站名/经停/跨日/服务日均走只读 Adapter；表单和 Agent 使用同一 Registry `dispatch`。
- 站名歧义要求选择；不存在的站/车次明确拒绝；不编造实时余票或官方票价。
- Legacy/LangChain 均通过 `target/v39/registry.py`；真实在线 Provider 未授权直接调用 V3.9，页面使用本地确定性模拟并记录限制。

## 4. D9 与资金

- D9：`APPROVED`，`CHANGED_REFUND_P01`，`approved=true`，仅 V3.9 本地模拟。
- 每乘客最多一次成功退款；每订单最多一次成功改签；失败保留 FAILED；新提案可重试。
- P01：`>48h 5%`、`24h ≤ t ≤ 48h 10%`、`<24h 20%`，整数分 half-up，基数为当前有效乘客价格快照。
- 改签退差不占乘客退款名额；改签后仍可退剩余 ACTIVE；全部退款后 `CANCELLED`。
- 真实浏览器四规格流程金额示例：3×二等座 36000 分；退甲 11400 净退款/600 手续费；乙丙改一等座后补 12000；再退乙 17100/900；退丙 17100/900；最终 `paid 48000, credit 45600, fee 2400, face 0, net 2400`，所有库存释放。

## 5. 测试结果

| 范围 | 结果 | 证据 |
|---|---|---:|
| V3.9/V3.9.1 全套 | **164 passed / 0 failed / 0 skipped** | `artifacts/runtime/v391-d9-lifecycle-20261103-213500-batch03/` |
| T057–T076 | **20/20 passed** | 同批 JUnit；20 个 db-probes |
| T031 | 通过 | 独立提案/进程竞争 + FAILED 记录 + 重试 |
| T046 | 通过 | 原始 GTFS `30:51:00` → 06:51；历史失败保留 |
| 旧全范围回归 | **1640 passed / 11 failed / 1 skipped** | `old-regression-unified/results/results.json` |
| 旧失败 ID | 与 sealed 完全相同 | `old-regression-comparison.json` |
| B 方正式 103 | BLOCKED，未执行/计分 | 独立保留 |

**旧 11 失败和 1 skip 未修复、未隐藏、未用 skip/xfail 制造通过。** 新增测试没有降低断言。

## 6. 浏览器验收

环境：Edge + 项目已有 Playwright；本地服务；不使用外部模型/铁路/支付。

| 规格 | 检查 | 截图 | 订单 |
|---|---:|---:|---|
| 1600×1100 浅色 | 21/21 | 5 | 完整生命周期 |
| 1600×1100 深色 | 21/21 | 5 | 完整生命周期 |
| 390×844 浅色 | 21/21 | 5 | 完整生命周期 |
| 390×844 深色 | 21/21 | 5 | 完整生命周期 |
| **合计** | **84/84** | **20** | **4 个真实 SQLite 订单** |

- 每个规格：查站→G531→三人建单→支付→退甲→乙丙改一等座→退乙→退丙。
- 每步真实读取 SQLite：order、items、holds、inventory、transactions、refund_requests、refund_items、inventory_events、FK。
- 四次最终均 `CANCELLED`、active 0、refunded 3、face 0、库存释放。
- 最终浏览器 DB 共 16 个订单（含早期失败批次）全部通过资金/库存/FK 守恒；见 `database-conservation.json`。
- 页面错误 0；Console error 4、外部阻断 4，均为 Google 字体图标请求被离线策略阻断；未声称 Console 全零。
- 自然语言：查询 `2026-11-06 北京南到上海虹桥` 返回 FOUND 20 条并列出 G531/G547/G1；政策咨询返回 D9/P01；未因对话创建订单。证据 `browser3/chat-results.json`。

## 7. 两个 CMD

| 启动 | 结果 | 截图 |
|---|---|---|
| `启动_离线模式.cmd -Port 8655 -NoBrowser` | 同一个统一 UI；Mock；无旧业务 radio；D9 可见 | `offline-final.png` |
| `启动_在线模式.cmd -Port 8656 -NoBrowser` | 同一个统一 UI；页面仅加载，未发送模型请求；无旧业务 radio；D9 可见 | `online-final.png` |

两个脚本仍设置 `RAILWAY_SIMULATION_ENABLED=1`，保留原在线/离线 Provider 差异；未 setx，未改系统环境变量。

## 8. 保护与差异

- HEAD/分支未变；无 commit/push/merge/tag。
- 2100 Fixture、GTFS ZIP、阶段八 DB、103/B、旧 tickets.db、V3.9.1 报告、历史失败批次保留。
- 1892 组无新增差异（沿用 V3.9.1 报告）。
- 4056/5538 账本：当前 274579 bytes / `87cfd3ed6b6dfdff0ecd8b1b7bc50f6e4726c5511d240b7d7bd417bd3f5b3776`（实际无空格）；此前 V3.9.1 报告记录 272726/`75677a...`。该追加发生在 V3.9.1 报告之后、本任务之前（尾部时间 2026-11-03T08:45Z），来源未归属；未删除、未截断、未回滚，未擅自批准新基线。
- 旧 V3.9.1 原始报告/矩阵/ZIP 不覆盖。

## 9. 限制

1. 单确认 Worker 限制保留；任意多 Worker 未实现。
2. 在线 CMD 仅页面启动验证，未发送 V3.9 对话，不声称真实 Live V3.9 工具验收。
3. 旧 11 失败/1 skip 仍存在，未被本轮修复。
4. 保护账本追加来源未确认，需用户确认基线。
5. B 方正式 103、Bridge 仍 BLOCKED；未安装/启用 Bridge。
6. 浏览器为 headless Edge 本地验收；实体手机、长期运行、真实手机软键盘未验。
7. `INDEPENDENTLY_REVIEWED=NOT_RUN`；本报告不是独立审查，也不是最终用户验收。

## 10. 状态

```text
IMPLEMENTED: YES
TESTED: YES (development only)
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
BLOCKED: independent review; ledger append source attribution; formal 103/B; Bridge
```

