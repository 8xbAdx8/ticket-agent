# Ticket Agent V3.1 Live 缺陷注入开发报告

日期：2026-10-18。成员A负责实现和本模块自测，B负责正式质量判定，C负责验收与演示。

结论：【已实现并验证】六种变异已接入实际LangChain执行路径，且六种均取得真实DeepSeek触发证据。正常默认Live仍只有两个只读工具；写变异必须显式启用独立模拟沙箱。工程可以交B复测，不能把本轮注入结果当作B的正式Agent质量成绩。

## 基线与保护

- 实际接手分支 `codex/deepseek-manual-no-total-cap-20261017`，HEAD `94efc0cdeec3c1c179976cca36980ce4c607981a`；任务给出的 `82d769...` 不是本地接手HEAD。
- 功能分支 `codex/ticket-agent-v31-live-faults`。GitHub初次fetch被不可达本地代理阻止；不使用代理的fetch也连接重置，无法确认远端最新提交。以本地最新代码实施，没有重置或覆盖远端。
- 保护622个原文件（原数据库、历史Trace、历史证据、正式及手动账本）和25个B原始判据/结果文件，最终哈希均未变。`docs/contract.md`未改，公开10字段和calls五字段未改。
- 正式历史预算保持5/5。用户另行明确授权本轮真实请求；在线场景使用全新隔离库和各自最多5次的测试账本，不删除、重置或覆盖旧账本。

## 六种原始语义与适配

| 名称 | Legacy原始位置及行为 | 新框架注入点和实际行为 | 真实证据 |
|---|---|---|---|
| date_offset=1 | providers._parse_date：解析日期后加一天 | FaultRun.arguments：保留模型原参数，实际query_tickets日期加一天 | 模型请求2026-10-19，实际执行/数据库返回2026-10-20 |
| route_error | MockProvider.chat政策分支：政策问句错走query_tickets；不是城市交换 | search_policy调用被执行层路由到query_tickets，沿用北京→上海的原默认规则；不改数据库 | 政策请求实际得到车次数据，模型说明没有政策结果 |
| no_citation | MockProvider._summarize：省略最终引用，原检索结果保留 | 原search_policy真实执行后移除返回给模型的doc_id/source及内容中的编号；保留完整前后结果 | 模型说明无doc_id，没有编造P编号 |
| repeat_call | 默认查票分支生成两个query_tickets调用 | 一个模型工具请求触发两次真实只读执行；记录同一call_id下execution_index=1/2 | 模型请求1次，Python执行2次；不冒充模型重复请求 |
| infinite_loop | monitor_seat完成后不断再次监控，直到旧主循环上限 | 执行策略在收到真实monitor_seat后有限重入；每次检查工具次数，达到Agent步数停止 | 模型请求1次、真实监控3次，max_steps_exceeded |
| skip_lock | 有余票购买分支跳过lock_seat，用LK_INJECTED_MISSING尝试create_order，原后端拒绝 | 模型lock_seat请求在沙箱路由到原create_order，使用同一无效lock_id；不取消后端约束 | 两次真实create_order均被后端拒绝，0锁/0订单；正常对照1锁/1订单 |

原有Legacy判据见 `tests/test_agent.py` 和B六变异55组；新增确定性测试在 `tests/test_fault_injection.py`、`tests/test_live_faults.py`。语义一致不表示三个执行器在同一代码行注入：Legacy仍保持原Provider行为，新增路径采用工具包装/结果变异/有限执行策略，不在最终回复中替换文字来伪造成功。

## 架构与文件

- `target/fault_injection.py`：【已实现并验证】统一标识、严格配置、逐轮FaultRun、参数/路由/引用变异、ContextVar审计、独立统计。`AGENT_MUTATIONS`或`Agent(mutations=...)`是三个模式共用入口；旧全局providers.set_mutation继续留给Legacy，避免污染框架会话。
- `target/agent.py`：【已实现并验证】兼容原chat入口；增加可选mutations和set_mutations，改变配置时清除内存检查点，历史JSONL不删。
- `target/langchain_agent.py`：【已实现并验证】框架middleware记录模型请求，包装真实工具执行，检查授权、白名单、实际执行次数，保留原始/实际参数、完整结果及真实失败。没有生成虚假的AI tool_calls。
- `target/langchain_model.py`：【已实现并验证】仅离线模型学会对缺引用的工具结果给出诚实说明；没有改写真实DeepSeek的最终回答。
- `target/providers.py`：【已实现并验证】引用统一标识，并给原六变异加旁证通知；原决策及返回行为保持。
- `target/deepseek_runtime.py`：【已实现并验证】显式full_sandbox验证目录、标记、本地后端、独立DB/Trace/账本及正数预算，HTTP发送前复查工具白名单。默认read_only不变。
- `scripts/create_fault_sandbox.py`：【已实现并验证】仅新建独立沙箱，不覆盖已有目录或数据。
- `scripts/verify_live_faults.py`：【已实现并真实运行】默认只预检，带--run才执行真实API；场景独立进程，零SDK重试，外部故障停止后续场景；保存实际结果而非预设成功。
- `scripts/summarize_faults.py`：【已实现并离线运行】汇总旁证，可读取B的独立布尔判定文件，不修改原Trace。
- `web/app.py`、`cli.py`：【已实现并离线验证】六开关与执行器绑定，显示阶段、applied/blocked/未触发等结果；Web恢复会清空当前会话记忆，不删历史。

## 独立模拟写沙箱

`DEEPSEEK_LIVE_TEST_PROFILE=full_sandbox`与`AGENT_LC_TOOLSET=all`必须同时明确设置。沙箱在项目artifacts/runtime独立子目录，含创建器生成的标记；DB固定为tickets.db、Trace为traces、预算为requests.db，禁止HTTP业务后端，累计请求预算必须1～5。

默认Live仍只注册query_tickets/search_policy。锁座否定、支付授权、本人订单、库存、锁座时效和创建订单幂等仍由原代码校验。skip_lock只取消该次无效lock_id调用的编排前置检查，不取消用户购买授权、不取消后端锁座约束、不豁免预算或白名单。LangChain Mock的写变异也必须使用同样的显式沙箱；Legacy原行为不变。

## 实际离线验证

命令：

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/verify_v3_def06_def07_offline.py --b-root <B原始目录> --baseline artifacts/runtime/v31-faults-20261018/regression-baseline.json --out artifacts/runtime/v31-faults-20261018/delivery-regression
```

完整B判据回归时SDK环境151项全部通过；最后审计又增加2个边界测试，并执行 `scripts/run_deepseek_review_offline.py --out artifacts/runtime/v31-faults-20261018/post-review-regression`，最终SDK环境153项全部通过、原V3环境102通过/51跳过、原V2环境51通过/102跳过，10项Mock入口冒烟通过。A使用B原断言的隔离副本回归：Legacy101/101、LangChain Mock100/100、六变异55/55，专项44通过/0失败/3 N/A，pytest Legacy101通过/2跳过。这里是A复跑，不冒充B已对V3.1独立复测。

新增测试覆盖正常关闭、六项触发、无效日期、未触发/不适用、组合配置顺序、隔离、恢复、真实SDK回传、未知引用拒绝、工具次数、请求预算耗尽、有限循环、沙箱限制和Web绑定。Agent步数、模型调用次数、工具次数分别记录终止原因。原最大步数/Token未知/脱敏测试继续通过。

开发中曾暴露：测试语句不属于已有授权语法；测试SQLite连接未显式关闭导致Windows清理失败；重构后工具失败结果缺少error包装。均已修正并回归，失败日志保留在证据development-attempts中，不把首轮失败覆盖成成功。

## 真实API运行与判定

模型deepseek-flash，官方地址，thinking=disabled，SDK重试0。两批共12个场景，真实生成请求27次，27次HTTP200；输入42,038、输出3,733，共45,771 Token。用量来自SDK事件与账本交叉核对。实际费用未知，未查询余额或账单。

首批9场景使用18次请求；指定班次后的3个独立补充场景使用9次请求。首批skip_lock和infinite_loop因模型请求确认班次而未到达注入点，保留为not_triggered。补充输入不修改原结果、不手动代模型调工具。

按run×变异计：请求注入8次，其中实际applied6次、未触发2次、失败0、阻止0。条件注入成功率为6/(applied+failed+blocked)=6/6；若按所有请求计则6/8。六种唯一变异均至少一次真实触发。不能把6/6写成Agent质量100%。

Agent行为观察：日期场景指出返回日期不同但没有自动完成纠正查询；错路由场景说明没有政策结果；缺引用场景说明doc_id不可用；重复执行未引起模型报错；跳锁座时后端拒绝，模型两次尝试锁座均被注入层转换，最终API回复保存在原事件中，应用抛tool_execution_failed；循环由执行器有限终止。

**Agent缺陷检出率、错误恢复率：【尚未由B正式判定】，统计字段为null，不填0%或100%。** 正常stop不等于业务成功，HTTP200不等于成功下单。全工具正常对照只生成待支付模拟订单，没有支付、取消或他人订单查询。

## 证据与Git

公共证据根：`docs/evidence/deepseek/v31-live-faults-20261018/`。summary.json包含总用量、12项核对和统计；live-01/、live-selected-02/各场景case.json含原输入、模型请求、实际执行、数据库计数、最终文字/异常和账本摘要，traces保留公共Trace、DeepSeek事件与mutation_runs。模型原文以model_final事件为准；限步提示是执行器生成的终止说明，不冒充模型最终回答。跳锁座失败没有正常契约返回，不能用通用失败提示替代原模型文字。

在线核心版本 `5af85b6d24ea31e089d63a334429968fe951bf58`。补充场景运行时测试输入及Web标签尚未提交，已如实记录在summary；随后03ef15f仅增加LangChain Mock写变异的沙箱检查。提交记录：

| 提交 | 功能与验证 |
|---|---|
| b7b6363 | 独立FaultRun、定义与变换；7项单元测试通过 |
| ae7bce8 | LangChain真实工具包装、六变异、沙箱和旁证；19项针对性测试通过 |
| fe9bafb | Web/CLI绑定、状态展示；23项UI/SDK测试及单独Web绑定测试通过 |
| 5af85b6 | 真实运行器、分开统计、后端失败包装修复；14项只读质量和24项变异测试通过 |
| c6b4fdb | 全工具沙箱标签、指定班次场景；9项UI/统计测试通过 |
| 03ef15f | LangChain Mock写变异也要求隔离；18项故障路径测试通过 |
| a1bc221 | 独立B判定合并统计CLI；真实旁证离线汇总通过 |
| fc5bc46 | 参数仅准备好不计成功、单步循环标blocked、CLI沙箱文案；28项故障测试及最终153项离线测试通过 |

最终文档/证据提交SHA以分支git log或最终回复为准，未合并main、未改标签、未强推。

## 已知限制与下一步

- 【尚未验证】V3.1的B独立正式评价、Live多次重复的稳定性、并发争抢、全部工具真实场景、思考模式。
- 【部分实现】模型恢复统计机制已实现；正式检出/恢复判据与结果须B提供。
- 每个Live变异仅一个成功触发样本，不能代表普遍可靠性；两个未触发样本证明需要区分模型澄清与注入失败。
- 正则只读话术检查不是通用语义判定器。缺引用时如模型自行给P编号，会保留原文并拒绝返回正常成功结果。
- 工具结果完整保存在旁证中；用量上限根据已观察Token估计，无法预先准确知道下一次输入Token。独立账本/最大请求/输出Token/超时仍为硬保护。
- 正常Web会话可能因切换变异而清空内存，历史文件保留。开关启用但工具不适用会明确报告，不扩大默认Live权限。
- 推送状态另见最终回复；Git网络不可达时不得声称已上传或已由B验收。
