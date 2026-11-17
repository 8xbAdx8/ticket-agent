# 成员 A 最终交付清单

报告日期：2026-10-12（Asia/Shanghai）。运行证据时间：2026-10-12T20:11:38.809590+08:00。

核验实现版本：`e719956d7c82bd6392c25916d3c193be7e4b452e`；分支 `feat/a-ticket-handoff`。报告最后文档提交可用 `git rev-parse handoff-a-20261012` 取得（Git 提交不能把自身 SHA 写进自身内容；最终 SHA 另在交付回复中给出）。

数据来源：当前源码、`docs/contract.md`、Git 提交、`docs/evidence/verification.json` 及对应实际日志。所有运行结果均为 Mock 或本地模拟响应，未联网测试真实模型。

勾选仅表示成员 A 已实际完成并有开发证据；未勾选表示待完成/待人工确认，不能由计划替代。功能状态遵循【已实现并验证】【已实现但未验证】【部分实现】【尚未实现】。B/C 的正式测试和验收由本人独立确认。

## 1. 三人分工与接口

- [x] A：Agent、Provider、模拟业务、工具、RAG、CLI/Web、Trace、接口与自身基本自测，材料在仓库。
- [x] B：交付运行与复现手册，不替 B 写正式断言平台/缺陷评级。
- [x] C：交付进度/验收/拍摄/技术说明，不编造正式测试成绩。
- [x] `docs/contract.md` 原文件保持不变，SHA256 `bfe2f8ebf1ec02b831765286652e50344d1cfcc24d5179bd8ffd78fe6e8c0381`。
- [x] Python 入口 `from target.agent import Agent; Agent().chat(session_id,message)` 可运行；多轮使用同实例。
- [x] 保留 reply/tool_sequence/steps/finish_reason/total_latency_ms 及全部既有字段。
- [x] `steps[].calls[]` 六字段、计时与 stop/max_steps_exceeded 已核验。

## 2. 源码、配置与环境

- [x] `config.py`：模型配置、路径隔离、北京时间、MAX_STEPS/TTL。
- [x] `target/__init__.py` 与 `target/agent.py`：包及主循环、sessions、Prompt。
- [x] `target/providers.py`：Mock、6 变异、OpenAI 风格适配器。
- [x] `target/tools.py`：8 schema、校验、dispatch 与 HTTP 请求。
- [x] `target/mock_core.py`：SQLite 事务与票务状态/库存。
- [x] `target/mock_api.py`：可选 FastAPI 外壳。
- [x] `target/rag.py` 与 `data/policies.md`：检索及 15 条虚构政策。
- [x] `target/trace.py`：契约 JSONL 追加与计时。
- [x] `data/seed.py`：30 高铁/5 机票/7 天/2100 条新数据，默认不覆盖。
- [x] `cli.py`、`run_demo.py`、`web/app.py`、`cases/demo.json`。
- [x] `README.md`、`requirements.txt`、`requirements-lock.txt`、`.gitignore`。
- [x] `tests/test_core.py`、`tests/test_agent.py`、`tests/test_provider.py`、`tests/test_web.py`（A 自测）。
- [x] `scripts/smoke.py`、`scripts/handoff_example.py`、`scripts/read_legacy_doc.py`、`scripts/generate_handoff.py`。
- [x] 用户原始 `成员A任务书_被测抢票智能体.md`、`订票.doc` 保留；Word 正文已只读抽取。
- [x] 原 `data/tickets.db`、`traces/traces.jsonl` 原地保护，均未提交到 Git；可在新机器生成/保留业务证据。
- [x] 实际环境记录：Python 3.12.14；openai 3.29.0；streamlit 1.65.0；fastapi 0.143.0；uvicorn 0.54.0；pandas 3.0.6；pytest 9.1.1。完整传递依赖见 `requirements-lock.txt`。
- [ ] B/C 自己的电脑安装/运行确认（A 本机通过不等于其他电脑通过）。

## 3. CLI / Web / 模型

- [x] 【已实现并验证】CLI once/chat/batch/trace；6 示例实际执行。
- [x] 【已实现并验证】run_demo 离线执行，默认隔离库与 Trace。
- [x] 【已实现并验证】Web 对话、会话、工具表、JSON、6 控件/恢复、错误提示、历史回放，AppTest 与服务健康检查通过。
- [x] 【已实现并验证】Mock 无 Key 可运行，明确标记离线剧本。
- [x] 【已实现并验证】真实 Provider 适配器本地模拟响应自测（ID/usage/坏 JSON/缺 Key）。
- [ ] 【已实现但未验证】真实模型 Key 配置、联网工具决策与端点兼容性实测。
- [ ] 【已实现但未验证】C 对实际浏览器画面/录屏操作的人工验收。

## 4. 8 工具与业务链路

- [x] query_tickets：参数、查询、无票/空结果；本地 HTTP 实测。
- [x] monitor_seat：已有无票班次监控凭据；本地 HTTP 实测。
- [x] lock_seat：按人数占库、TTL、返回 lock_id；本地 HTTP 实测。
- [x] create_order：有效锁、乘客一致、同锁幂等；本地 HTTP 实测。
- [x] pay_order：仅模拟 paid 状态，重复支付不扣库；本地 HTTP 实测。
- [x] cancel_order：pending 取消/paid 退款、人数回库、P01/P09/P12；基本自测及 HTTP 实测。
- [x] query_order：本人列表/单订单，拒绝他人；基本自测及 HTTP 实测。
- [x] search_policy：关键词检索及 doc_id/source；本地 HTTP 实测。
- [x] 【已实现并验证】主链路查→锁→下单→付→退、机票购付、无票候补、多轮 context。
- [x] 【已实现并验证】原始字段与工具名称保持兼容，不连接真实票务或支付。
- [ ] 【尚未实现】改签动作、儿童/学生优惠、凭证/折扣例外及身份证一证一票核验。
- [ ] 【尚未实现】候补后台轮询/自动兑现。
- [ ] 【部分实现】生产登录/多用户认证、高并发基准/压力测试、旧库自动升级/每日滚动数据。

## 5. RAG、变异与 Trace

- [x] 【已实现并验证】15 政策块、关键词检索、Mock 回复引用、来源片段。
- [ ] 【已实现但未验证】向量依赖/模型下载与真正向量检索实测。
- [x] date_offset=1：晚一天参数，单独实际触发。
- [x] skip_lock：query→create、后端拒绝不存在锁，单独实际触发。
- [x] repeat_call：同一步重复 query，单独实际触发。
- [x] infinite_loop：8 回合/反复监控，max_steps_exceeded，单独实际触发。
- [x] route_error：政策问题错 query，单独实际触发。
- [x] no_citation：search_policy 后省略引用，单独实际触发。
- [x] 六变异清除、Web 单会话字典隔离与正常恢复已核验。
- [x] 每轮 Trace 追加，计时冻结；返回与保存一致。
- [x] 测试使用隔离目录；原 Trace 历史未清空/覆盖。
- [x] `docs/evidence/mock_traces.jsonl` 有 32 条 Mock 素材，`python_examples.json` 的 label 标明注入。
- [ ] 【部分实现】跨进程写锁、分页回放/轮转、大量记录场景验证。

## 6. 已执行测试及证据

- [x] `python -m unittest discover -s tests -v`：12 个 A 自测通过；含业务、Agent、SDK 适配、Web AppTest。
- [x] `python scripts/smoke.py`：10 条实际命令/本地服务检查通过，退出码记录在 verification.json。
- [x] run_demo/once/batch/stdin-chat/trace/Python 示例执行日志齐全。
- [x] uvicorn 本地服务 health 与全部 8 HTTP 工具、HTTP Agent 购付链路通过。
- [x] Streamlit 真正启动，health 返回 ok；AppTest 发送实际消息。
- [x] 契约、原 DB、原 Trace 与首次 SHA256 相同。
- [ ] 成员 B 的正式方案、正式测试、缺陷分级、性能结论和成绩（由 B 完成）。
- [ ] 成员 C 的最终验收签字、实拍截图、讲解视频、正式参赛报告（由 C 完成）。

## 7. 已知 Bug/限制与交接风险

- [x] 已修复多轮旧工具混用、skip_lock 无效、HTTP 请求体不一致、人数回库错误、本人订单越权、非法状态支付等 MVP 问题，并有基本验证。
- [x] 已知限制详见 A/B/C 报告：Mock 意图有限、固定身份、无跨进程记忆、RAG 相关性有限、stop 也可能失败、预览截断、旧库不迁移。
- [ ] 尚未证实所有边界输入无 Bug；未被 A 自测覆盖的问题需 B 独立测试。
- [ ] 真实模型/向量结果与生产安全能力未验证，不能宣称全项目最终成功。
- [ ] 由队长协调 Key、赛事交付期限及 B/C 正式结果；未自行核定赛事政策/日期。

## 8. Git 与报告

- [x] 独立功能分支 `feat/a-ticket-handoff`；无 remote 推送、无 main 合并。
- [x] 核验实现最后提交 SHA：`e719956d7c82bd6392c25916d3c193be7e4b452e`。
- [x] 分阶段提交与持续开发记录，未伪造原不存在的历史。
- [x] 四份手册生成后对源码/Schema/证据哈希核验，额外清单 `docs/handoff/handoff_manifest.json`。
- [x] 最终文档提交通过交付标签 `handoff-a-20261012` 精确定位；完整 SHA 在最终交付回复给出。此文件不能自引用其自身提交 SHA；交付后用 `git rev-parse handoff-a-20261012` 和 `git status --short` 核对，标签在生成/审核完成后创建。

| 提交 SHA | 对应功能 |
|---|---|
| `bdb8370250b434f62865ac666fa08fb3c3c7541d` | chore: preserve supplied MVP baseline and start development log |
| `e9b5012cd6a65647eeedbdef236f9fe15f39d7e7` | feat(data): expand fictional inventory and isolate runtime paths |
| `144ab3f6c576077154dda08bbf0e866e00491679` | fix(tools): validate calls and enforce simulated order transactions |
| `03b63c8ea5ab082b66a11f3762b2e76b733feed1` | fix(agent): preserve multi-turn context and verify six mock mutations |
| `78ea322a8f8addc75ef6c22c5d855d726dea11bb` | feat(cli): isolate demos and capture reproducible handoff evidence |
| `8262db81838d45fe3d827d75ae8a4246a2304038` | feat(web): expose all mock controls and verify entrypoint workflows |
| `e719956d7c82bd6392c25916d3c193be7e4b452e` | docs(handoff): deliver source-backed A B C reports and final checklist |

## 9. 交付给 B/C 的材料

- [x] B：`docs/contract.md`、`docs/handoff/B_测试对接手册.md`、TOOLS schema、Python/HTTP 实例、变异触发/清除、隔离数据/Trace 方法。
- [x] B：`docs/evidence/python_examples.json`、`http.json`、`mock_traces.jsonl`、运行日志、A 自测源码（无正式评估代做）。
- [x] C：`docs/handoff/C_验收与演示交接手册.md`，容易理解的介绍、部署、逐项验收、失败取证、截图/8 分钟分镜。
- [x] C：A 报告、开发记录/提交、架构图、Prompt/源码定位、Mock 与真实模式说明及实际限制。
- [x] 三人共同使用 `docs/handoff/A_开发完成报告.md`、本清单、README 和开发证据。
- [ ] B 已阅读/成功运行并确认正式接收。
- [ ] C 已阅读/成功运行并确认验收拍摄条件。

**成员 A 开发交接状态：有条件交接。** B 可以独立开展 Mock 测试，C 可以准备/执行 Mock 验收与拍摄；真实模型实测、向量升级、正式测试成绩与最终人工验收仍待团队完成。未完成项保持未勾选。
