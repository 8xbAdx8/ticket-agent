# 成员 A：Ticket Agent V2 开发完成报告

生成日期：2026-10-13（Asia/Shanghai）。分支：`feat/a-ticket-v2`。
经过回归的源码提交：`1804518c9a312ec0d4ab8cb000124e37ee551887`；本手册是该源码之上的文档提交。
最终交付提交用 `git rev-parse HEAD` 确认；交付标签计划为 `handoff-a-v2-20261013`，仅在检查通过后建立，解析标签可得到最终 SHA，避免文档声称包含自身的提交哈希。
V1 标签保留：`handoff-a-20261012` → `e719956d7c82bd6392c25916d3c193be7e4b452e`。
所有运行结果均为 A 自测；业务虚构。成员 B 报告的 V1 95/100 是其提供的结论，A 未获得完整 judge/用例/原始 execution.jsonl，不能宣称 V2 正式 100/100。


## 开发范围与实际成果

项目用于智能体测试比赛：在可控的虚构票务环境中观察工具选择、参数、顺序、多轮状态及异常处理。A 负责被测 Agent/Provider/8 工具/模拟业务/RAG/CLI/Web/Trace 和本模块自测；B 负责正式用例、断言、指标、缺陷判定；C 跟进问题、最终验收、报告与录屏。

V2 沿用 V1 的架构，逐项修复 5 个报告缺陷，没有重写业务、测试层或契约。

| 状态 | 实际内容 | 证据或限制 |
|---|---|---|
| 【已实现并验证】 | DEF-01..05 的 Mock 行为修复 | 13 个缺陷自测 + 五个同输入复现目标通过 |
| 【已实现并验证】 | 原入口、8 工具、主循环、CLI、HTTP 模拟服务、默认 RAG、Trace | 28 自测、10 项冒烟、32 Mock Trace；工具 Schema 不变 |
| 【已实现并验证】 | Web 对话、回放、变异恢复及本地启动 | Streamlit AppTest + health；人工验收仍待 C |
| 【已实现并验证】 | 六变异保留、V1 文件保护与证据隔离 | audit_first.json；25 原文件哈希一致 |
| 【已实现并验证】 | 真实 Provider 本地传输适配与预检入口 | 3 项新增 SDK 桩检查；远端调用未执行 |
| 【已实现但未验证】 | 真实远端模型 Function Calling / V2 Prompt 的模型遵守效果 | 无 Key，待验证；不等于 Mock 结果 |
| 【已实现但未验证】 | 可选本地向量 RAG 分支 | 当前默认字/词重叠打分；未装模型做实测 |
| 【部分实现】 | 候补监控与身份控制 | 仅任务凭据、固定模拟用户；无持续监控/生产登录 |
| 【尚未实现】 | 实际票务/资金/改签、B 正式 V2 评价、C 最终作品与录屏 | 前两项业务不在本次模拟范围；后两项由 B/C 负责 |

## 架构与核心代码说明

CLI/Web/Python → Agent.chat → Provider.chat → 工具调用 → dispatch 校验 → mock_core/HTTP 或 RAG → 工具结果回传 Provider → 最终回复与 Trace 追加。默认 MAX_STEPS=8；每轮可有多个工具调用，工具次数不等于模型步数。

`target/agent.py` 保留主循环：接收消息、维护 session 历史、累计工具步骤、把结果以 tool_call_id 交还模型、停止或截断；SYSTEM_PROMPT 是行为约束，不是正确性的形式保证。
`target/providers.py`：Mock 是规则剧本，OpenAIProvider 才请求远端模型。`_transport_kind` 处理明确选择/省略继承/含糊澄清；`_seat_for_kind` 避免二等座混入机票；`_write_intents` 和 `_policy_question` 区分咨询与操作；`_summarize` 按真实工具结果区分售罄和幂等支付。
`target/tools.py`：原 Schema 不变，在 dispatch 的既有校验通路中新增 kind/seat_type 一致性检查，异常继续用 error/ok=false 表示。
`target/mock_core.py`、`target/rag.py`、`target/trace.py` 在 V2 未修改。SQLite 事务/锁座有效期/幂等订单和支付沿用 V1；RAG 按政策段落 doc_id 分块并以字/词重叠排序，返回 TOP_K=3；不是 BM25，也不是本次验证过的向量检索。
Trace 每次 chat 保存一行 JSONL，默认 traces/traces.jsonl，可用 AGENT_TRACE_DIR 隔离；耗时用 perf_counter，单位整毫秒，不包括写盘耗时。Mock tokens=0；model 字段的默认名称不代表调用过该真实模型。

## 五项修复及对应提交

| 缺陷/用例 | V1 现象 | V2 最小修改 | 实际状态 | 源码提交 |
|---|---|---|---|---|
| DEF-01 / F03 | 交通切换后席别未重置：沿用二等座查询机票 | 按 kind 校验席别，隐式旧席别重置；显式冲突先澄清 | A Mock 复现目标通过；待 B 确认 | `3b7cb0449df6a501ca7218a96b072cf5400c49e3` |
| DEF-02 / M11 | 机票不能切回高铁：第三轮仍查询机票 | 明确方式覆盖、省略沿用、含糊澄清；路线日期只覆盖明确部分 | A Mock 复现目标通过；待 B 确认 | `7fe5502a7ed5c6b1a35ef46e486cba02641a1586` |
| DEF-03 / F14 | 无票回复不准确：0 票行也被统一列为查询成功 | 按库存区分售罄/可售/空匹配；建议其他席别但不承诺余量 | A Mock 复现目标通过；待 B 确认 | `5a57f16b7568c0467b4328c61c9c19f722141d1a` |
| DEF-04 / F13 | 重复支付话术错误：duplicate_pay=true 仍说支付成功 | 读取已有幂等标记，明确已支付且没有重复扣款 | A Mock 复现目标通过；待 B 确认 | `1ed67d53ef6626ff217a7f74b2cce93e523632cb` |
| DEF-05 / T25 | 支付政策咨询误路由：支付关键字挡住政策检索 | 咨询走 search_policy 并引用；明确支付/取消才允许操作 | A Mock 复现目标通过；待 B 确认 | `3504fd18a2ff83ee7861b5a5396d52e7a7942c15` |

根因、逐轮实际回复与风险见 `V1_V2缺陷修复对照.md`。DEF-03 未增额外工具调用；DEF-04 沿用已存在 duplicate_pay 字段；DEF-05 不把关键字直接当作写操作授权。

## 文件位置与职责

| 文件/目录 | 职责 |
|---|---|
| config.py / requirements*.txt | 环境开关、模型配置与实际依赖冻结 |
| target/agent.py / providers.py | 主循环、会话和两种模型提供者 |
| target/tools.py / mock_core.py / mock_api.py | 工具 Schema/校验、模拟票务业务、可选 HTTP |
| target/rag.py / data/policies.md | 政策检索与虚构知识库 |
| target/trace.py / data/seed.py | 执行记录、隔离模拟库初始化 |
| cli.py / web/app.py / run_demo.py / cases/demo.json | 命令行、网页、离线演示与原示例输入 |
| tests/test_v2_defects.py | 13 个 V2 缺陷自测；每例独立库/Trace |
| tests/test_v2_provider.py | 3 个 SDK 桩自测，不是远端模型测试 |
| scripts/reproduce_v2_defects.py | B 五个报告输入的 A 对照观察，冻结业务日期 |
| scripts/run_v2_selftests.py / smoke.py | 实际运行日志与全入口冒烟；拒绝覆盖证据 |
| scripts/validate_real_provider.py / v2_api_example.py | 真实预检/显式验证、经过运行的原 API 示例 |
| scripts/audit_v2_evidence.py / generate_v2_handoff.py / check_v2_handoff.py | 哈希/契约审计、实际资料生成 V2 文档、再生成与 JSON/示例一致性检查 |
| docs/contract.md | 原团队契约，未修改 |
| docs/v2_development_log.md / docs/evidence/v2/ | 连续 V2 开发记录、复现与验证原始证据 |
| docs/handoff/*_V2*.md / V1_V2缺陷修复对照.md | A/B/C 新交接材料；V1 文档仍保留 |

本轮源码/脚本修改由 Git 自动整理（相对于 V2 接手起点）：

- `scripts/audit_v2_evidence.py`
- `scripts/reproduce_v2_defects.py`
- `scripts/run_v2_selftests.py`
- `scripts/smoke.py`
- `scripts/v2_api_example.py`
- `scripts/validate_real_provider.py`
- `target/agent.py`
- `target/providers.py`
- `target/tools.py`
- `tests/test_v2_defects.py`
- `tests/test_v2_provider.py`

文档生成脚本在本次交接文档提交新增。完整 V1 项目目录职责仍见原 `A_开发完成报告.md`，该历史报告不能当作最新 V2 成绩。

## 8 工具接口（由实际 Schema 整理）

| 工具 | 必填 | 可选 | 主要返回/语义 |
|---|---|---|---|
| `query_tickets` | from_city, to_city, date | seat_type, kind | trains/count；行含 kind、seat_type、seats_left、价格/路线/班次；本次 HTTP 实际字段：trains, count |
| `monitor_seat` | train_no, date, seat_type | duration_min | task_id/status/duration_min 等监控凭据（无后台监控守护进程）；本次 HTTP 实际字段：task_id, train_no, date, seat_type, duration_min, current_seats, status |
| `lock_seat` | train_no, date, seat_type, passengers | 无 | lock_id/expire_at/ttl_seconds；unit_price/count 和锁座信息；本次 HTTP 实际字段：lock_id, train_no, date, seat_type, passengers, unit_price, count, expire_at, ttl_seconds |
| `create_order` | lock_id, passenger_ids, contact | 无 | order_id/status/amount/train_no/date；重复创建标记可能返回；本次 HTTP 实际字段：order_id, phone, train_no, date, seat_type, passengers, amount, status, created_at, lock_id, idempotent_hit |
| `pay_order` | order_id | pay_type | order_id/status；重复支付另有 duplicate_pay=true；本次 HTTP 实际字段：order_id, status, pay_type, amount, duplicate_pay |
| `cancel_order` | order_id | reason | status；已支付退款含 fee/fee_rate/refund/policy_ref，未支付直接取消；本次 HTTP 实际字段：order_id, status, amount, fee, refund, fee_rate, policy_ref |
| `query_order` | 无 | order_id, phone | 指定 ID 返回单个订单；按本人查询返回 orders 列表；本次 HTTP 实际字段：order_id, phone, train_no, date, seat_type, passengers, amount, status, created_at, lock_id |
| `search_policy` | question | 无 | hits；每条含 doc_id/content/score；本次 HTTP 实际字段：question, hits, count |

任何失败通过既有 error 表示；长 result_preview 截断，不能假定能 json.loads；完整后端结果可查看 http.json 或 API 回传历史。

## 实际验证与证据

环境：Python 3.12.14；openai 3.29.0、streamlit 1.65.0、fastapi 0.143.0、uvicorn 0.54.0、pandas 3.0.6、pytest 9.1.1。完整冻结见 requirements-lock.txt。
28 个 A 自测=保留 V1 12 + 新增缺陷 13 + SDK 桩 3。首次 DEF-03/05 开发自测失败日志保留，修正源码后复验通过，没有为通过而改 B 规则。

| 检查 | 实际执行命令（当时使用 .venv Python） | exit | 日志 |
|---|---|---|---|
| unit | `python -m unittest discover -s tests -v` | 0 | `docs/evidence/v2/regression/unit.txt` |
| demo | `python run_demo.py` | 0 | `docs/evidence/v2/regression/demo.txt` |
| once | `python cli.py once 帮我查明天上海到杭州的高铁` | 0 | `docs/evidence/v2/regression/once.txt` |
| batch | `python cli.py batch cases/demo.json` | 0 | `docs/evidence/v2/regression/batch.txt` |
| chat | `python cli.py chat` | 0 | `docs/evidence/v2/regression/chat.txt` |
| trace | `python cli.py trace` | 0 | `docs/evidence/v2/regression/trace.txt` |
| python_example | `python scripts/handoff_example.py` | 0 | `docs/evidence/v2/regression/python_example.txt` |
| http_agent | `python cli.py once 订明天上海到杭州的高铁并支付` | 0 | `docs/evidence/v2/regression/http_agent.txt` |
| http | `python -m uvicorn target.mock_api:app --host 127.0.0.1 --port <free-port>; HTTP 8 tools` | 0 | `docs/evidence/v2/regression/http.json` |
| web_health | `python -m streamlit run web/app.py --server.headless=true --server.port=<free-port>` | 0 | `docs/evidence/v2/regression/web_health.txt` |

其他真实执行：`run_v2_selftests.py --log docs/evidence/v2/full_unit.txt --pattern 'test*.py'`、`reproduce_v2_defects.py --output-dir docs/evidence/v2/v2_reproduction --label v2-after-fixes`、`v2_api_example.py --output-dir docs/evidence/v2/api_example`、`validate_real_provider.py --output-dir docs/evidence/v2/real_preflight`、`audit_v2_evidence.py --output docs/evidence/v2/audit_first.json`。
六变异仍按原入口开启：日期偏移 +1、跳过锁座、重复查询、候补循环直到 8 步、政策误路由、引用删除；详细实际参数/回复在 regression/python_examples.json。恢复开关后用新 Agent/会话/库，不能只换 session_id 隔离库存。

## 真实模型状态与限制

当前没有 API Key。`preflight.json` 明确 api_key_present=false、real_model_tested=false、real_trace_count=0：**真实模型待验证**。

已实现 OpenAI 风格 Chat Completions 适配器，SDK 测试桩检查调用 ID/工具结果回传、错误和最大步数，不能算模型自主决策测试。Prompt 已增加 V2 规则，第三方端点是否支持全部协议需实测。

有合法有效 Key 时，由使用者通过安全环境注入 `AGENT_API_KEY`，不要写入源码、文档、录屏或聊天。配置 `AGENT_PROVIDER=openai`、服务方提供的 `AGENT_BASE_URL` 和支持工具调用的 `AGENT_MODEL` 后，重启进程并显式运行：

```powershell
$v2Real = "artifacts/runtime/real-" + [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts/validate_real_provider.py --output-dir $v2Real --run
```

这是实际远端 API 调用，可能产生服务方费用。没有 --run / 没有 Key / provider 不是 openai 时仅预检。8 个独立场景覆盖单轮、多轮交通切换、工具回传、查锁下单、RAG、工具故障、正常停止、强制 MAX_STEPS=1；每个场景使用临时虚构库。上限场景是人为缩小步数的验证，不能据此称模型自然死循环。
每个 result.json 保存输入、完整消息（含工具参数/结果和服务器 call_id）、实际回复/Trace、耗时、调用错误与“完成情况待确认”；finish_reason=stop 不保证业务成功。模型认证/网络失败也会保存失败回复，不能当作成功。Mock 与真实附件放在不同目录，不与 V1 Trace 混用。
协议参考：[OpenAI Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。本次未迁移 API 或新增契约字段。


目前 5 个报告问题在 A Mock 复現与单元测试层已修复，但仍待 B 回归判定。Mock 自然语言是有限规则，不支持任意复杂否定、城市别名或多意图；保守写操作识别可能澄清。数据只覆盖初始化当天到后六天，旧库不会自动刷新。finish_reason=stop 也可能是错误回复；不能作为成功率。
后续建议：B 先独立确认五个 xfail 与售罄建议口径；配置真实工具调用模型后执行隔离验证；再按真实失败样本扩展 Mock 或 Prompt。向量检索/生产认证/持续候补是后续范围，不用来替代本次修复。

## Git 对应记录

| SHA | 实际提交内容 |
|---|---|
| `f8bb30a76edf0d1f381cdc4ffd18edeb4caf5a9d` | chore(v2): preserve V1 baseline and reproduce five reported defects |
| `3b7cb0449df6a501ca7218a96b072cf5400c49e3` | fix(DEF-01): normalize seats when switching transport kind |
| `7fe5502a7ed5c6b1a35ef46e486cba02641a1586` | fix(DEF-02): distinguish explicit transport switches from omitted context |
| `5a57f16b7568c0467b4328c61c9c19f722141d1a` | fix(DEF-03): distinguish sold-out seats from available and unmatched services |
| `1ed67d53ef6626ff217a7f74b2cce93e523632cb` | fix(DEF-04): explain duplicate payment without changing idempotent backend |
| `3504fd18a2ff83ee7861b5a5396d52e7a7942c15` | fix(DEF-05): route payment policy questions without unintended writes |
| `1804518c9a312ec0d4ab8cb000124e37ee551887` | test(v2): verify regressions and prepare isolated real-provider validation |

成员 A 开发交接状态：**有条件交接**。被测 V2 的 Mock 运行与原契约可交给 B 独立回归，C 可验收/拍摄 Mock；正式测试成绩、真实模型段落和最终作品需相应责任人确认。
