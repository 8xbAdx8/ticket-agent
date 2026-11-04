# Ticket Agent V3.9.4 — Implementation Report

日期：2026-11-04（Asia/Shanghai）。执行者：DeepSeek/Codex，开发自测；不是独立审查。  
本轮是可靠性整改，不是产品重设计；未调用真实 Qwen/DeepSeek/铁路/支付 API。

## 1. 状态

```text
IMPLEMENTED: YES
TESTED: YES (开发自测；最终数字见第 6 节)
LIVE_API_VERIFIED: NOT_RUN（本轮无真实模型调用）
INDEPENDENTLY_REVIEWED: NOT_RUN
ACCEPTED: PENDING_USER_ACCEPTANCE
BLOCKED:
  - data/v39/simulation-v391.sqlite 继承的来源未知差异（PRODUCT_DB_PROTECTION=BLOCKED）
  - 正式 103/B 执行器
  - Bridge
```

不是 COMPLETE；未 Commit/Push/Merge/Tag。

## 2. 开工与保护

- HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`
- 分支：`feat/ticket-agent-v36-stabilization`
- 暂存：0；工作区 74 项（含 V3.9.3 历史未提交成果）
- 未清理/重置其他工作区；新增修改见 Git 差异报告。
- GTFS 静态：`e32f0cd4...`；3169 站、11588 车次、107669 经停、187 隔离。
- `data/v39/simulation.sqlite`：`a429b20b...` 未改。
- `data/v39/simulation-v391.sqlite`：`9ebf39ec...` 继承的冻结冲突；本轮未连接/修改/删除/回滚。
- 所有新测试/演示使用 `artifacts/runtime/v394-*`；Store 只新增 `v394-` 允许前缀。

## 3. 实际修改

| 文件 | 原因/内容 |
|---|---|
| `web/railway_defaults.py`（新增） | 统一默认日期/路线/席别；真实 GTFS 车站候选与优选；Registry 查询；首班模拟库存；六态分类；默认路线 109 班。 |
| `web/user_features.py` | 查余票默认高铁用例改 V3.9 GTFS + 模拟库存；无库存/无车次正常空状态；侧栏失败写 `panel_error`，不污染 `session.error`；Feature Flag 关闭时保留旧 Fixture 兼容路径；退票/P06 默认输入。 |
| `web/demo.py` | 四步快速体验改为真实 GTFS + V3.9 Service 的本地闭环；0 模型；proposal/confirm 保留；确认复选框；新会话/结束可重开。 |
| `web/demo_legacy.py`（新增兼容） | Feature Flag 关闭的旧测试环境保留旧 Agent 演示，不删除历史行为。 |
| `web/railway_queries.py` | 右栏默认统一 2026-11-05 上海虹桥→杭州东/G7541；六态状态、来源/版本/数量；异常封装；不写会话通用错误。 |
| `web/conversation.py` | 当前请求错误显示后、在对话渲染完成后清除；旧错误不污染下一次；不在错误存在时展示旧成功车次卡。 |
| `target/v39/store.py` | 仅新增 `v394-` 隔离命名空间。 |
| `scripts/run_v39_tests.py` | 允许 `v394-implementation-` 输出前缀。 |
| `tests/v39/test_v394_defaults.py`（新增） | T077–T100 共 24 项默认/查询/状态/交易测试。 |

未修改：旧 8 工具、V3.9 11 工具定义、Agent.chat 公共字段、Trace 字段、Baseline、正式 103、D9/P01、GTFS 原件、旧数据库、独立审查 ZIP。

## 4. 默认用例结果

| 用例 | 结果 |
|---|---|
| 查余票（上海/杭州/2026-11-05/二等座） | 真实 GTFS **109 班**，当前 20，模拟余票 20；上海 5/杭州 4 候选，优选上海虹桥/杭州东。 |
| 四步快速体验 | **4/4**；1 order / 1 transaction / 2 proposals；订单 PAID；无真实支付。 |
| 右栏查车次 | 109 条；来源/版本/当前页/下一页。 |
| 右栏查车站 | 5 条。 |
| 右栏查经停 | G7541，10 站。 |
| 退票费率 | 默认 ¥500、3天后、已支付；显示 P01。 |
| P06 行李 | 25kg/50×40×30；P06，超5kg，¥25。 |
| 看订单 | 新会话空状态；不偷建订单；只读本人库。 |
| 政策 | 本地资料/P01；不要求订单。 |

矩阵详见 `Ticket-Agent-V3.9.4-Default-Use-Case-Matrix.md`。

## 5. 查询状态与隔离

- `FOUND` / `NOT_FOUND` / `INPUT_INVALID` / `DATA_UNAVAILABLE` / `TOOL_EXECUTION_FAILED` / `INTERNAL_ERROR`。
- 右栏查询状态存在 `session.railway_queries`；失败不写 `session.error`。
- 侧栏查询失败写 `session.panel_error`，清除 `session.error`；不污染聊天顶部。
- 顶部当前错误在对话渲染后清除；Trace/audit 保留。
- 新会话独立；无跨用户订单读取。
- 普通用户不显示堆栈/数据库内部信息。

## 6. 测试

| 范围 | 结果 |
|---|---|
| V3.9.3 基线 | 174/0/0（历史） |
| V3.9.4 新增 T077–T100 | 24 项 |
| V3.9/V3.9.4 全套 | **198 passed / 0 failed / 0 skipped**（`v394-implementation-20261104-025000`） |
| T057–T076 | 20/20；20 db-probes |
| 旧全范围 | **1640 passed / 11 failed / 1 skipped**；失败/ skip ID 与 sealed **完全相同** |
| 浏览器 | **34/34**，8 截图，PageError 0 |

未使用 skip/xfail 降低断言；原有 11 失败/1 skip 不删除、不隐藏。

## 7. 浏览器

- 四规格：1600×1100/390×844，浅/深。
- 原版 UI/四快捷/默认查余票/四步闭环/右栏三模式/无溢出/手机右栏/错误恢复/新会话清空/退票与 P06 默认值。
- 证据：`artifacts/runtime/v394-browser-final2/`；报告 `Ticket-Agent-V3.9.4-Browser-Report.md`。

## 8. 已知问题

1. 旧回归历史 11 失败/1 skip 保留（非本轮修复目标）；本轮最终 1640/11/1，失败/ skip ID 与 sealed 完全相同，新增兼容性失败已修复。
2. 未执行真实 Qwen/DeepSeek；`LIVE_API_VERIFIED=NOT_RUN`，无模型费用。
3. 原版 UI 完整三人退改签浏览器交易流程未执行；V39 tests/probes 覆盖业务，不能把查询/四步单乘客当完整退改签验收。
4. `data/v39/simulation-v391.sqlite` 来源未知差异仍未解决；未连接/修复。
5. 正式 103/B、Bridge、独立审查未执行。
6. 默认日期固定为 2026-11-05；GTFS 覆盖之外需按真实数据调整默认用例，不能硬编码为成功。
7. 浏览器 DataFrame 单元格文本不做像素/文本断言；SQLite/测试直接断言真实行。
8. 兼容层 `web/demo_legacy.py` 仅在 Feature Flag 关闭的旧测试环境使用；产品开启 V3.9 时走新 GTFS 流程。

## 9. 证据与 SHA

- 测试：`artifacts/runtime/v394-implementation-20261104-025000/`
- 默认/四步探针：`artifacts/runtime/v394-probes-20261104/v394-probes.json`
- 浏览器：`artifacts/runtime/v394-browser-final2/`
- 旧回归：`artifacts/runtime/v391-d9-lifecycle-20261103-150639/old-regression-v394-final/`
- 最终报告/清单/独立审查 ZIP 另见交付目录与 SHA256 清单。
