# Ticket Agent V2 开发记录

日期使用 Asia/Shanghai；记录真实执行，区分 B 的报告结论与 A 的实现自测。

## 2026-10-13 接手 V1 与 B 资料

- 分支起点：`30b21da57f432677d8e12cd76e24a8e0895c35f3`，建立 `feat/a-ticket-v2`；原标签 `handoff-a-20261012` 保留在 `e719956d7c82bd6392c25916d3c193be7e4b452e`。
- 工作区原来仅有两份新提供的未跟踪资料：根目录 `B_缺陷分析报告.md`、`B的总结_测试层.docx`。原样保留，Word 仅只读提取正文。
- 阅读契约、Agent/Provider/工具/业务/RAG/Trace、V1 四份交接手册。与 V1 标签对比 `target/`、config、seed、policies 无差异。
- B 报告声明 100 用例 95 通过/5 失败，DEF-01..05 为 F03/M11/F14/F13/T25；此为引用 B 的结果，不是 A 重跑确认。
- 实际目录检查未发现 `judge/`、`results/execution.jsonl` 或 B 的测试用例；不运行不存在的 judge，不改 B 断言。
- 配置检查只输出是否存在 Key：当前无 API Key，provider=mock。真实模型仅准备接入/验证脚本，联网待验证。
- 新增 `scripts/reproduce_v2_defects.py`：按 B 原输入在五个独立库和 Trace 路径复现；业务日期冻结 2026-10-13，用于可比的 V1/V2 观察，不代表 B 完整回归。
- B/C 影响：契约、原证据/数据库/Trace 不动；原始 B JSONL 不在仓库，后续需 B 提供或独立运行。
- SHA：基线准备提交后在下一条记录登记；每个缺陷另行提交。

- 实际复现命令：`.venv/Scripts/python.exe scripts/reproduce_v2_defects.py --output-dir docs/evidence/v2/v1_reproduction --label v1-before-fixes`；五个 A 观察目标均未满足（0/5），成功复现 B 描述的五个现象。每个场景独立模拟库，原始 Trace 追加至独立子目录；观察 JSON 包含实际输入/参数/回复。
- V1 证据和手册另存只读快照 `docs/evidence/v2/v1_snapshot/`；manifest 保留契约、原库/Trace、开发记录、原始 B 资料与 V1 文档哈希。不会将 A 复现 Trace 冒称为 B 的原始执行 JSONL。

基线提交：`f8bb30a76edf0d1f381cdc4ffd18edeb4caf5a9d`。

## 2026-10-13 DEF-01 交通方式与席别一致性

- 原始现象：F03 等价输入“查明天北京到成都高铁”→“那机票呢”，V1 发出 kind=机票/seat_type=二等座；实际 Trace 在 `v1_reproduction/DEF-01/`。
- 原因：旧 args 带 seat_type，默认经济舱的 fallback 永远不生效。
- 最小修改：`target/providers.py` 新增 `_seat_for_kind`，隐式不兼容旧席别重置默认；显式不兼容输入先澄清；`target/tools.py` 拒绝 kind/seat_type 错配。
- 新增 A 自测 `tests/test_v2_defects.py` 两项：复现 F03 的参数/路线/日期，显式公务舱、错配澄清和工具校验。自测 helper 同时核对完整契约字段。
- 新增日志入口 `scripts/run_v2_selftests.py`，仅运行 A 的 unittest，拒绝覆盖日志，脱敏本地路径。
- 实际命令：`python scripts/run_v2_selftests.py --log docs/evidence/v2/def01_unit.txt`，2 个自测通过。未改 Agent 返回结构或 contract。
- B/C 影响：旧错误 kind/seat 参数现在会被拒绝，正常切换可运行；需 B 重新跑 F03 及明确席别用例。真实模型只获得工具参数校验，不能据 Mock 推断真实行为。
- 待处理：DEF-02..05、六变异/全链路回归、真实 Provider 验证准备。
- SHA：提交后在下一条登记。

DEF-01 提交：`3b7cb0449df6a501ca7218a96b072cf5400c49e3`。追加 `def01_contract_unit.txt` 同样 2 个自测通过。

## 2026-10-13 DEF-02 双向交通方式与上下文继承

- 原始现象：M11 第三轮“还是高铁吧”仍查询机票，V1 实际 Trace 位于 `v1_reproduction/DEF-02/`。
- 原因：机票关键词能覆盖 kind，但明确高铁未被识别；反之若一律默认高铁，又会破坏“后天呢”等省略问法。
- 修改 `target/providers.py`：`_transport_kind` 区分明确高铁/机票、省略继承、两种都提到或切换目标不明的澄清；处理“不要机票，还是高铁”这类明确否定。路线/日期/合法席别继承同一份旧参数，只覆盖当前明确指定值；单个城市需明确出发/到达角色。
- 新增三个 A 自测：M11 双向切换，公务舱省略/改日期/部分或整段路线切换，含糊交通/城市和否定表达澄清。
- 实际命令：`python scripts/run_v2_selftests.py --log docs/evidence/v2/def02_unit.txt`；累计 5 个 V2 自测通过，helper 校验契约字段/工具序列一致。
- B/C 影响：省略问法不再默认切换；含糊问题可能无工具调用且要求澄清，B 需按需求确认，不能把澄清误判为漏调用。
- 风险/限制：仍是公开的 Mock 规则，不是通用语义理解。真实模型需要对应 Prompt 与联网验证；DEF-03..05 待修。
- SHA：本缺陷提交后登记于后续记录。

DEF-02 提交：`7fe5502a7ed5c6b1a35ef46e486cba02641a1586`。

## 2026-10-13 DEF-03 无票、可售与空结果的回复

- 原始现象：F14 返回二等座 0 票，但用“为您查到以下车次”统一话术，不说明售罄或其他席别；V1 Trace 在 `v1_reproduction/DEF-03/`。
- 修改 `target/providers.py` 的 query_tickets 汇总：检查所有返回行的 seats_left，区分售罄、可售及混合库存、空匹配。售罄提示一等座/商务座等查询建议，并明确尚未查其他席别，不承诺有票。
- 不增加额外 query_tickets，不改参数/工具数量/Trace 契约，不干扰正常无票购买转 monitor_seat。
- 新增三个 A 自测：售罄与单次工具、可售/空结果区别、混合库存不可售标记。
- 初次 `def03_unit.txt` 出现 1 个自测失败：空结果否定句仍包含“已售罄”字样，不利于明确区分；改为“空结果不能用于判断库存是否耗尽”。保留首次失败日志，不修改断言换通过。
- 实际复验 `python scripts/run_v2_selftests.py --log docs/evidence/v2/def03_unit_retry.txt` 累计 8 个 V2 自测通过。
- B/C 影响：F14 回答现在提供“查询其他席别”的建议，不声称未经工具证实的余量；如果 B 希望主动验证其他席别库存，须再确认额外调用与 R5 规则口径。本轮没有修改 B 的断言。
- 待处理：DEF-04/05、完整回归、真实模式准备；本缺陷提交 SHA 后续登记。

DEF-03 提交：`5a57f16b7568c0467b4328c61c9c19f722141d1a`。

## 2026-10-13 DEF-04 重复支付的用户提示

- 原始现象：F13 第四轮支付返回 duplicate_pay=true，却仍回复“支付成功”；V1 Trace 在 `v1_reproduction/DEF-04/`。
- 原因：Provider 汇总没读取已经存在的后端幂等标记。
- 修改 `target/providers.py` 的 pay_order 汇总，重复支付明确回复“订单已支付，本次没有重复扣款。”；不改后端、不增契约字段、不改支付幂等状态。
- 新增 A 自测：四轮复现，检查第二次调用仍成功/duplicate_pay=true，明确提示、仅一个订单、paid 状态、库存总量未再次扣减。
- 实际命令 `python scripts/run_v2_selftests.py --log docs/evidence/v2/def04_unit.txt`，累计 9 个 V2 自测通过，返回字段仍与原契约相同。
- B/C 影响：可通过既有 result_preview 中短结果的 duplicate_pay 与回复观察；不得将本轮模拟扣款描述成真实支付验证。B 需重跑 F13 及正常支付/退款用例。
- 待处理 DEF-05、全回归/真实模式准备；SHA 后续登记。

DEF-04 提交：`1ed67d53ef6626ff217a7f74b2cce93e523632cb`。

## 2026-10-13 DEF-05 政策咨询与写操作分离

- 原始现象：T25“锁座后必须在多久内完成支付”未调用工具；V1 Trace 在 `v1_reproduction/DEF-05/`。B 的 Word 总结也指出同类问题。
- 修改 `target/providers.py`：`_policy_question` 检查支付/锁座/订单领域与多久、有效期、自动等咨询特征；`_write_intents` 仅把明确命令/复合购付作为操作，疑问与否定不能触发支付/取消。支付命令优先于“我的订单”的查询快捷分支；已有订单上下文也不能把政策问法转成写操作。
- 新增四个 A 自测：P11/15 分钟问法、有订单的政策咨询/P12、明确支付本人订单、禁止支付与复合订票支付。检查订单仍 pending、没有错误 pay/cancel。
- 初次 `def05_unit.txt` 中复合购付被单独支付分支提前截获；保留失败日志，修正为先执行购买链路、create_order 后再按明确支付意图支付，不修改断言。
- 复验命令 `python scripts/run_v2_selftests.py --log docs/evidence/v2/def05_unit_retry.txt`；累计 13 个 V2 自测通过，契约 helper 通过。
- B/C 影响：T25 走 search_policy/P11；“支付我刚才的订单”仍走 pay_order；模糊写请求会澄清。B 需额外验证 T10–T16/X07 与自然问法，不能把 Mock 规则等同真实模型语义能力。
- 真实模型无 Key，下一阶段提供对应 Prompt 与分离证据的验证入口；正式 B 100 用例尚未运行。本缺陷提交 SHA 后续登记。

DEF-05 提交：`3504fd18a2ff83ee7861b5a5396d52e7a7942c15`。

## 2026-10-13 完整回归、真实接入准备与证据隔离

- `target/agent.py` 只补充 SYSTEM_PROMPT 的六项规则，主循环/返回结构不变；真实模型据此接收交通切换、售罄、重复支付、政策与写操作要求，但模型执行效果仍待联网验证。
- `tests/test_v2_provider.py` 新增 3 个模拟 SDK 自测：服务器 tool_call_id 与工具结果回传一致、工具 error 回传、MAX_STEPS 截断。这些 SDK 响应由测试桩产生，不是远端模型输出。
- `scripts/validate_real_provider.py` 新增默认预检及显式 `--run` 的验证入口；8 个隔离场景覆盖用户要求的 7 类验证（结束/上限分开）。记录实际会话、完整工具结果、Trace、配置摘要、耗时与异常；任务是否完成留待按真实回复确认。当前无 Key，仅生成 preflight，不生成真实 Trace。
- `scripts/smoke.py` 修改为新建目录且拒绝覆盖；默认保存在 `docs/evidence/v2/smoke-<时间>-<随机后缀>`，保留 V1 原始结果。命令、HTTP 8 工具与 Web 检查仍沿用现有实现。
- 实际运行 `python scripts/run_v2_selftests.py --log docs/evidence/v2/full_unit.txt --pattern 'test*.py'`：28 个 A 自测通过（V1 12 + V2 缺陷 13 + SDK 桩 3）。没有 B 测试层，不运行 judge。
- 实际运行 `python scripts/smoke.py --output-dir docs/evidence/v2/regression`：10 项命令/服务检查通过、32 条 Mock Trace，原库/Trace/契约哈希相同。unit 包含 Streamlit AppTest 对话、回放、恢复变异；Web health 是本地服务启动检查，不冒称人工录屏验收。
- 实际运行 `python scripts/reproduce_v2_defects.py --output-dir docs/evidence/v2/v2_reproduction --label v2-after-fixes`：5/5 A 观察目标满足；业务日期冻结与 V1 一致。不能据此宣称 B 正式 100/100。
- 实际运行 `python scripts/validate_real_provider.py --output-dir docs/evidence/v2/real_preflight`：无 API Key、没有 --run，状态“待验证”、真实 Trace 0 条。
- `scripts/audit_v2_evidence.py` 检查源码与回归哈希、25 个受保护原始文件、V1 标签、8 个工具 Schema、10 个顶层/5 个 calls 字段与工具序列；`--output docs/evidence/v2/audit_first.json` 全部通过。
- 六项变异在实际 Mock Trace 中再次确认：日期 +1、跳锁座导致创建失败、两次查询、8 步上限、政策误走查询、政策缺引用均仍可触发。A 的单元测试及审计同时检查恢复后的正常行为。
- B/C 影响：新增隔离命令和证据；工具及返回字段兼容。B 仍需独立复跑 100 用例并检查五个 xfail，C 可先录制 Mock 演示；真实模型段落必须待有效 Key 实测。
- 本模块 Git SHA 在下一阶段交接文档登记；源代码详解：Prompt 是发送给模型的行为约束，SDK 自测验证传输协议，最终模型是否遵守约束只能用远端真实响应确认。
- 新增 `scripts/v2_api_example.py`，实际执行 `--output-dir docs/evidence/v2/api_example`，用原入口 `Agent().chat` 四轮验证订票→政策→支付→重复支付；序列与提示符合预期，完整返回 JSON 和 JSONL 已保存。该示例独立临时库，不会重置用户数据库。
