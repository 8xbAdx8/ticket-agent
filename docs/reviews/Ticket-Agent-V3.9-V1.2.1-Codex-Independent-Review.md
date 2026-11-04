# Ticket Agent V3.9 V1.2.1 — Codex 第三轮独立架构审查

日期：2026-11-03，Asia/Shanghai。裁决：**BLOCKED**。

本轮只新增本报告。不修改 PROJECT_STATUS、架构原件、SQL/JSON、源码、测试、配置、项目数据库；不执行项目迁移，不 Commit/Push/Merge/Tag，不调用真实模型、铁路、支付、Embedding或Bridge。内存 SQLite 执行及样例数据不代表产品实现或正式成绩。

## 1. 审查范围与现场状态

仓库 D:/codexproject/ticket-agent；分支 feat/ticket-agent-v36-stabilization；起始与核验 HEAD 均为 4340b6640025be95e8300a3d625a32cfb431e35d。暂存区为空。起始工作区已有8个已跟踪修改和18项未跟踪条目，完整状态见附录A。开始前报告文件不存在，没有覆盖已有报告。

完整读取架构正文966行、审查包16个文件（含要求的14个文件及README/protection-check），并对SQL与正文、工具与权限、测试与整改矩阵作交叉核验。V1.0/V1.1/V1.2正文哈希仍匹配；已有25份核心源码索引匹配，关键入口另作现场检索。没有仅根据DeepSeek的verification作结论。

本轮使用 .venv-v35/Scripts/python.exe -B，从stdin运行标准库/现有jsonschema，只创建内存数据库；没有新增依赖、临时项目数据库或独立脚本文件。SQL探针和原始结果完整附在本报告，方便复现。

原有6074条路径的起始聚合指纹为：
5c466cd37583df21c057e508cf325c936f44106961f6c78c92a874603ebd9394。
写报告前重复计算相同。最终核对方式：排除本新增报告，重复该集合计算并检查Git仅增加本报告。

## 2. SHA256、结构与材料一致性

- file-sha256清单19/19匹配；清单自身哈希与verification引用一致。
- 包内13个JSON可解析，工具11个且名称唯一，与permissions一致。
- 56个测试ID唯一、T001–T056连续，缺失ID=0、重复ID=0、字段结构缺项=0；每项13字段，legacy_id允许空。
- SQL在开启外键的内存SQLite 3.53.1可执行：21表、19个显式索引、0触发器。自动索引不计入19。
- 去除schema文件头注释/尾空行并统一换行后，SQL正文与主文档SQL代码块逐字一致。
- 4个Mermaid源码块已检查，未渲染；不宣称图形渲染通过。
- schema通过执行只说明语法/结构可创建，不证明资金、库存、权限正确。
- 内存 journal_mode=memory。没有把内存验证冒充文件WAL或多进程并发验证。

### 2.1 清单逐文件结果

| 文件 | SHA256 | 比对 |
|---|---|---|
| docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.1.md | 3c8f228e1c31252a8fe709387000aa1d1f65d6decc2ae9807c4299aa8d78a093 | 匹配 |
| docs/reviews/Ticket-Agent-V3.9-Architecture-Design.md | 2626ef47a2d91dce7b3674ed566a07d744098b51e9ff9493b8326b9ddb8b7e9a | 匹配 |
| docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.1.md | 516734d706ff4f43ba3b9b1dc01cf347097288cbadc7e6ae0d3f8a45d1bd036f | 匹配 |
| docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.md | 6dc6d755df212a5c33fc7f830d7c34df05873918f8c93d31916dfe3b2f53e8d3 | 匹配 |
| docs/reviews/Ticket-Agent-V3.9-Bridge-Evidence-Gap-20261102.md | 4c9ddb3a651c7c362043296181723039b7a064ee126a230a081b5f81b3173631 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/README.md | e1cf3deae19665cf9862309cb967d82fcfb36cc6f7a8e05d3def8c9fd27cb358 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/architecture.json | 67511b798af5932f3e2cb3b08fdd920ca64b71f27e1dd39c86924ed49a2e405d | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/baseline.json | 6639306dbc8f47cda01d891949413d369c2013cd034c706e8a7e3c46a22a2f66 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/codex-review-request.md | 0d4b0dedd8954a0e9fa4c1691743be8d35096916f6a85700f895e37a3f967a26 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/decision-record.json | a5d467eeb136074a4feefc20818effc9cbf3d93b35cc94d1b0f33549c5b6ab96 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/permissions.json | ec927fe34fc571ec85849da80244a83a75f0f6787a102b2610cafc93e34a8585 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/risk-list.json | 842986396543bc32ec6100b6eed8daefc325d01a6b6e99d1cfaf7834b28b738e | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql | 749ac7a608eb9414815b3a6509846fbf8d71ccaa0f2d973c71780350f1f02dab | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/test-matrix.json | 5b1ef37b5c30d90b2c30b8ef2350380a8c3b36ead6eda5884b43a14c61e36f13 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/tool-schemas.json | b28adfc24340c1da4f008b1ff96f0d7f80d9ec3dc4af8c6e52073362455c6ae4 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/sequence-mapping.json | eba0f5f6692563f5b1bed0fda1cbe6dbd70819ead1c541568e7315ef2faed4e1 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/wiring-matrix.json | b40f12027bceea719771e251c61d2c78ea8c3146a817a8c22dcbdf4a26a40980 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/remediation-matrix.json | 91d76861a24e4791279c15220f7aa8d0d8e1e4375551d2fc7794fc549452fc18 | 匹配 |
| artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/protection-check.json | 0e6e935705c3b3bfa91826afc017606931fa5ed19fa6c8151d4661b11eb984b2 | 匹配 |

额外计算两个不在自包含清单中的文件：
- file-sha256.json：8ff23f79e036b2cd1395ef1e7bb0fbd9b998d9c2f303856a452fc1be6950a75e
- verification.json：29c90a29e74401e36597f63cb66254f360cb9fc4ee341dfe18f9857b6bf382ff

前者有verification交叉引用；后者是本轮观测哈希，不是第三方签名或真实性证明。DeepSeek的23/23自检不作为Codex验收成绩。

## 3. F01–F13 全量复审

“设计闭合”不表示实现/运行通过；NOT_VERIFIED表示本轮没有相应真实实现可执行。原问题修复与新发现分开评价。

| F | DeepSeek声称 | 实际证据、独立复现 | 是否完整解决及新风险 | 实施门禁影响 |
|---|---|---|---|---|
| F01 | 写锁内再查幂等 | 正文773–787明确写锁内复查，同事务回执，实质修订 | 流程设计闭合；未运行真实双进程确认服务。不同owner Worker拒绝与客户端重放须区分，见C08 | 不将未执行说成并发通过 |
| F02 | 所有库存使用完整键 | hold/change/event均有完整6元键；S23不同trip同index可分别存储 | 身份键问题已解决；引用完整性仍见C04 | 不能把完整列集合等同有效归属 |
| F03 | 新hold完整目标+source归属 | 正文616–629补齐RETAINED/NEW；S18拒绝NULL来源，但S16/S19接受不存在/其他用户来源 | 部分解决；C04 | 阻塞库存归属验收 |
| F04 | 退款唯一关联、同订单、累计上限 | S03–S11显示跨订单、超额、缺关联仍能写入；S22正确拒绝同refund两笔成功 | 未完整解决；C02/C03/C05 | 阻塞资金验收 |
| F05 | scope/item_ids贯通 | 工具增加条件参数，ITEMS无item_ids被jsonschema拒绝；正文725要求归属验证 | 接口实质修复；重复item_ids/FULL+子集未定义，部分退款后人数/hold/改签仍见C06 | 完整生命周期仍阻塞 |
| F06 | 单确认Worker+可靠路由 | 正文850–856明确非owner不标SECRET_LOST；token表有owner_worker_id | 限定单Worker可接受；owner生命周期/路由/重启部署未完整，见C08，运行NOT_VERIFIED | 不能宣称任意多Worker |
| F07 | 业务失败提交、拒绝不执行、技术回滚 | 正文757–767三类结果已区分 | 分类设计修复；失败手续费/明细重试未闭合C05，T016/T018回执语义仍需具体化 | 金融失败链仍阻塞 |
| F08 | 事务外PRAGMA，每连接FK | 正文862–876顺序正确；内存DDL可执行；故障时正确事务可回滚为0表 | 设计改善，WAL/路径/多连接迁移实现NOT_VERIFIED；Python executescript陷阱C09 | 不得照抄错误驱动调用 |
| F09 | 半开区间、专属优先、歧义拒绝 | 正文882–886有确定性规则；但S01/S02跨域引用被允许 | 同优先级策略改善；完整范围/NULL有效期/priority含义仍需明确，C01 | 跨域价格验收阻塞 |
| F10 | 56项可复现 | 56/56结构齐全；实际内容仍有陈旧/矛盾，C07及第6节逐项审阅 | 未完整解决；不把字段齐全算可复现 | 必须修正关键资金/失败测试 |
| F11 | 历史SHA记录、原件缺失 | 两原件仍缺，历史SHA记录存在；本机3080无监听 | 缺口披露已修正；原件NOT_VERIFIED，旧包对可变Gap文件引用失配C11 | 不通过Bridge派发任务 |
| F12 | 当前权限与配置快照重校验 | proposals增加配置字段，正文825–835及permissions要求全部入口重校验 | 设计层已补齐；实际代码仍未接通，双引擎运行NOT_VERIFIED | 不能降低现有权限，实施后反向测试 |
| F13 | proposal_id UNIQUE | S15在新quote/newhold/不同幂等键下仍报UNIQUE(proposal_id) | DB约束独立复现有效；这是局部通过，不是103通过 | 此项结构门禁满足 |

## 4. 独立发现：7项P1、4项P2

未确认已实现的P0漏洞；目前没有V3.9业务实现可据此证明产品越权。下列P1是架构进入实现前应关闭的问题，不是对生产行为的虚构结论。

### C01｜P1｜价格规则跨场景/跨版本关联未封闭（F09、疑点A）

位置：[schema.sql:70](D:/codexproject/ticket-agent/artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql:70)、同文件23行；正文192–227、882–886。
证据：quotes外键仅(rule_id,rule_version)，不含scenario_id/dataset_version。S01场景A报价引用RB（场景B）成功；S02数据v2报价引用v1规则成功，foreign_key_check仍为空。

影响：选择错误作用域的规则也能生成自洽外键记录。正文选择规则没有给出完整的scenario/dataset/seat过滤谓词，不能仅由“共享域隔离”推导已防护。
整改：联合FK或同等强度的事务校验，明确规则选择完整作用域、报价/规则身份一致。定义valid_until=NULL为无上界与priority字段的确切含义；不能凭trip优先策略忽略其余身份。
验收：跨scenario/dataset拒绝并零报价/订单/库存变化；合法专属/通用选择、NULL上界、半开边界、同优先级歧义均给确定输入和结果。

### C02｜P1｜退款关联与金额仍只部分封闭（F04、疑点B）

位置：[schema.sql:266](D:/codexproject/ticket-agent/artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql:266)、295/307/329行；正文659–660、707–714、725。
证据：S03订单A请求关联B的item成功；S04 A交易关联B请求成功；S05 A交易分摊关联B的item成功；S06退款明细9000大于item面值2000仍成功；S07 REFUND=9999大于request.net=1900及paid=6000仍成功；S08分摊合计4001与交易6000不一致仍可保存。

边界说明：这是直接SQL反例，不证明未来服务一定允许越权。正文确有“同订单校验”“ACTIVE/owner校验”“合计相等”“累计上限”的要求，不能忽略这些声明。但未给出覆盖request/transaction/allocation/item所有组合的完整验证契约、失败处理和对应确定性反例；当前不能将“声明”当已验证防线。

整改：明确由DB强制的复合关联（可在明细/分摊冗余order_id建立联合FK），以及必须在同一BEGIN IMMEDIATE内执行的金额聚合/剩余可退校验。退款gross、fee、net、交易amount、allocation sum必须逐项对应同一订单/请求；成功前检验，不靠事后日志。
验收：S03–S08通过DB拒绝或受测事务级验证器拒绝；即使更换幂等键、并发、跨同用户不同订单，也不能多退/错退。仅新增文本或LLM自检不算关闭。

### C03｜P1｜交易类型关联CHECK只有单向条件（F04、疑点C）

位置：[schema.sql:266](D:/codexproject/ticket-agent/artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql:266)，尤其287–288行；正文659。
证据：refund_id IS NULL OR type=REFUND只表达“有refund_id时必须REFUND”，没有表达“REFUND必须有refund_id”。S09 REFUND无refund_id成功；S10/S11改签补款/退差无change_id成功，成功退款唯一索引因NULL而无法覆盖这类交易。

已有效部分：S12/S13正确拒绝PAYMENT附带refund/change；S14正确拒绝PAYMENT+CREDIT，类型/方向对应已改正。
整改：类型与引用做双向约束：REFUND必须refund_id且无change_id；CHANGE_*必须change_id且无refund_id；PAYMENT两者均无。继续保持已有方向约束和幂等唯一约束。
验收：S09–S14所有非法变体均拒绝；每种合法交易成功；不能以NULL绕过成功退款唯一性。

### C04｜P1｜RETAINED来源和实际库存没有引用完整性（F02/F03、疑点D）

位置：[schema.sql:133](D:/codexproject/ticket-agent/artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql:133)、373行；正文614–629。
证据：来源只有非NULL CHECK，没有source_hold/source_order外键，也没有segment到库存主表的完整FK。S16不存在的来源成功，S17不存在的库存主键成功，S19其他用户HB/OB来源成功。S18仅验证NULL被拒绝，不能代表来源有效。

影响：完整6元键已经解决编号碰撞，但“有这些列”仍不能证明归属；可能形成幽灵区间、跨订单保留、无法对账/正确退回的sold。
整改：关联实际库存全主键、源hold/源order；在事务内检查源hold属于源order、owner/scenario/dataset和完整区间身份、源有效数量、订单当前hold一致。新hold必须完整覆盖目标集合，RETAINED只转归属、不增减余额。
验收：不存在/跨用户/跨订单/错误库存来源拒绝；全部/部分/无RETAINED三类成功、故障回滚和后续退款事件均守恒。不用只测“不为NULL”代替有效性。

### C05｜P1｜失败退款的费用及重试明细语义不完整（F04/F07、疑点H）

位置：[正文664–670](D:/codexproject/ticket-agent/docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.1.md:664)、707–714/757–761；schema329行。
证据1：fee_total写sum(refund fee)而未限定成功。内存样例RFA=FAILED、fee=100：未过滤合计100，成功退款合计0。失败应无实际费用；按字面求和会破坏net_paid=current_face+fee_total。
证据2：refund_items对order_item_id无条件唯一。S20在保留失败明细后新请求重退同item被UNIQUE拒绝。这里有前提：若失败完全不落refund_items而仅成功才写，可避免此问题；现稿未明确成功事实表与失败尝试明细边界。

整改：费用只计成功且实际保留的费用；失败/待处理交易与明细不得计入已退款/费用。明确refund_items是“成功退款事实”还是“尝试明细”；若只写成功，需说明失败选择明细如何审计，若保存尝试，则采用仅成功唯一的完成记录/索引方案。
验收：失败→新proposal重试成功→再退剩余item；失败费用累计为0，不占成功退款名额，保留失败审计，不需要删除失败证据或人工清库。

### C06｜P1｜部分退款后的全聚合和状态仍不足以确定（F05、疑点H）

位置：[正文716–729](D:/codexproject/ticket-agent/docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.1.md:716)、631–641、937–945；schema184/237/110行。
证据：3退1只描述active2/refunded1/remaining hold，没有规定orders.passenger_count、holds.quantity、hold_segments.quantity的历史/有效数量语义，也没有完整的改签字段更新清单。最终全退的hold终态、改签后item是否仍算ACTIVE、失败/重试子状态迁移均未完整定义。orders.passenger_count和holds.quantity不能为0，因此不能简单将它们当“有效人数”在终态置0。

影响：后续可能按历史3人而非有效2人改签/释放；若把改签后有效item标为CHANGED而财务只求ACTIVE，面值会漏计。部分退款后补款须以当前有效票面4000而非net_paid4100为基准，否则差额少100。
整改：明确历史人数与有效人数、每item剩余占用、当前hold量、全退终态、有效item集合、改签全字段清单及计算基准。D9选择与技术一致性分开：政策不允许则明确拒绝；允许则须有完整转换，不能交由模型或实现者猜。
验收：第8节八步骤每字段可由唯一规则推导；历史已退item不复活，目标报价人数为2，补款/费用/库存数量与快照一致。未授权分支保持拒绝。

### C07｜P2｜56项结构齐全，但计数文字与可复现性仍有缺陷（F10、疑点E）

位置：[test-matrix.json:3](D:/codexproject/ticket-agent/artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/test-matrix.json:3)、651/831行；remediation-matrix89行、risk-list62行。
实际56项不是缺5项：T001–T056连续且唯一。51是陈旧描述，尾注又写46。全部13字段非空（legacy_id允许空），但很多setup只写paid order/mixed/target quote。
未修复实例：T044仍1234×1.5=1851（没有半分）；T022随机100操作没有seed/操作表；T056支付技术故障写no order，会错误删除既有待支付订单；T051同时要求重叠拒绝和新报价用新规则；T029/T033/T012仍多分支混用。
整改：先修陈旧文字；再给确定数据、时钟、注入点和单一预期，加入S01–S25对应边界。第6节逐项记录，不以字段数代替覆盖。
验收：另一位工程师可按矩阵独立复现；真正半分用1235×15000/10000，单价1853、3人5559；支付故障保留原PENDING_PAYMENT订单。

### C08｜P2｜单确认Worker限制明确，部署/重启仍未充分具体化（F06、疑点F）

位置：[正文848–856](D:/codexproject/ticket-agent/docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.1.md:848)、805–808；schema390行。
改善：非owner只拒绝，不再误标SECRET_LOST；没有未经授权恢复secret的设计路径。
缺口：owner_worker_id是稳定逻辑角色还是每次启动新ID，如何防双活、识别旧owner死亡、处理路由缓存/滚动重启，均未规定。若启动新ID且只允许旧owner置lost，提案可能永久WRONG_WORKER；若复用ID又允许旧进程存活，可能双活。Sticky session也不自动等价于独立确认服务的可靠路由。
整改：指定单实例部署/排他机制、逻辑owner+启动epoch、重启失效流程及路由责任；两并发客户端须路由同owner。“两个独立owner Worker均返回回执”不在当前承诺内。不得伪装多Worker已验收。
验收：旧owner停机→新进程启动→旧提案受控失效/重提；错误Worker不更改状态；双活被阻止；路由失败明确报错。当前部署验收NOT_VERIFIED。

### C09｜P2｜Python驱动的事务执行方式必须落到迁移契约（F08）

位置：[正文862–876](D:/codexproject/ticket-agent/docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.1.md:862)。
内存独立复现：将BEGIN放入脚本再执行DDL并注入故障，rollback后0表；先conn.execute(BEGIN)再conn.executescript(DDL+故障)，该Python模式下rollback后仍21表。后者隐式提交导致“单事务DDL”落空。
这不是断言已存在错误迁移代码——目前没有迁移实现。整改：明确兼容驱动API的执行方案，避免此调用组合，测试要在中途DDL处失败而非fault=none。迁移/每连接FK设置已正确，WAL文件行为仍未验证。
验收：任何中途DDL故障0已提交业务表；FK每连接为1；新库路径不能等同受保护库，包含规范化/同文件别名防护。

### C10｜P1｜INTEGER声明没有保证金额与库存为整数

位置：[schema.sql:266](D:/codexproject/ticket-agent/artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql:266)、43行；正文“整数分/库存数量”不变量。
证据：S24 amount_fen=0.5的PAYMENT被接受；S25 held=0.5被接受。表非STRICT，CHECK只有正负/容量，不校验存储类型。
影响：若依赖SQL的INTEGER字样防止小数，半分资金或半个人库存会落库；只在显示层取整会破坏对账。
整改：在关键表用适当STRICT/typeof CHECK或同等不可绕过验证，服务入口严格整数（拒绝bool、非整数float、NaN等）；价格/退款全程整数算法，不能悄悄截断。
验收：S24/S25以及小数金额/人数/容量全部明确拒绝，合法整数兼容；不得通过四舍五入伪造约束通过。

### C11｜P2｜旧V1.2包引用的Gap说明已变化，需保留差异

位置：旧V1.2 file-sha256.json引用的docs/reviews/Ticket-Agent-V3.9-Bridge-Evidence-Gap-20261102.md。
证据：旧预期0d58fdac23152d8b3d3e34a0d739e1b6804a051524d7960790fabe8bba96d5d6；现场4c9ddb3a651c7c362043296181723039b7a064ee126a230a081b5f81b3173631。旧V1.2清单为16匹配/1差异，V1.1清单13/13。三个旧架构正文均未变化。
这是本次开工前已有更新，不归咎本轮审查；也不是4056两账本差异。整改：记录该Gap修订的版本/差异，后续独立版本或只追加，不改旧清单来掩盖历史失配。
验收：可区分旧包时点和新Gap版本，原件缺失事实/历史SHA不变，不凭重新生成文本冒充历史原件。

## 5. SQL独立复现证据

精确schema载入sqlite3.connect(':memory:')，foreign_keys=1，journal_mode=memory。每探针使用SAVEPOINT并回滚；没有访问业务数据库。25个边界探针不等同25个产品测试。

ACCEPTED表示数据库允许，不自动等于合法业务；REJECTED也不自动等于架构整体通过。S20是带“保存失败明细”前提的重试阻断；S23是预期应允许的完整键正向检查。S12–S15、S18、S21、S22是独立证实有效的局部约束。

| ID | 操作 | 实际结果 | 证据 |
|---|---|---|---|
| S01 | scenario A quote references scenario B rule | ACCEPTED | foreign_key_check=[] |
| S02 | v2 quote references v1 rule | ACCEPTED | foreign_key_check=[] |
| S03 | order A refund request contains order B item | ACCEPTED | foreign_key_check=[] |
| S04 | order A transaction links order B refund | ACCEPTED | foreign_key_check=[] |
| S05 | order A payment allocation moves to B item | ACCEPTED | foreign_key_check=[] |
| S06 | refund item gross exceeds original item fare | ACCEPTED | foreign_key_check=[] |
| S07 | refund transaction exceeds request net and paid_total | ACCEPTED | foreign_key_check=[] |
| S08 | allocation sum differs from transaction amount | ACCEPTED | foreign_key_check=[] |
| S09 | REFUND without refund_id | ACCEPTED | foreign_key_check=[] |
| S10 | CHANGE_SUPPLEMENT without change_id | ACCEPTED | foreign_key_check=[] |
| S11 | CHANGE_REFUND without change_id | ACCEPTED | foreign_key_check=[] |
| S12 | PAYMENT incorrectly links refund | REJECTED | CHECK constraint failed: refund_id IS NULL OR transaction_type='REFUND' |
| S13 | PAYMENT incorrectly links change | REJECTED | CHECK constraint failed: change_id IS NULL OR transaction_type IN ('CHANGE_SUPPLEMENT','CHANGE_REFUND') |
| S14 | PAYMENT incorrect CREDIT direction | REJECTED | CHECK constraint failed: (transaction_type IN ('PAYMENT','CHANGE_SUPPLEMENT') AND direction='DEBIT') OR (transaction_type IN ('CHANGE_REFUND','REFUND') AND direction='CREDIT') |
| S15 | same proposal creates second order with fresh quote/hold | REJECTED | UNIQUE constraint failed: v39_orders.proposal_id |
| S16 | RETAINED nonexistent source hold/order | ACCEPTED | foreign_key_check=[] |
| S17 | hold segment references nonexistent inventory row | ACCEPTED | foreign_key_check=[] |
| S18 | RETAINED null source identifiers | REJECTED | CHECK constraint failed: inventory_role <> 'RETAINED' OR (source_hold_id IS NOT NULL AND source_order_id IS NOT NULL) |
| S19 | RETAINED foreign owner source hold/order | ACCEPTED | foreign_key_check=[] |
| S20 | failure detail retained then new refund retry | REJECTED | UNIQUE constraint failed: v39_refund_items.order_item_id |
| S21 | negative or overcapacity inventory | REJECTED | CHECK constraint failed: held + sold <= capacity |
| S22 | two successful transactions for same refund | REJECTED | UNIQUE constraint failed: v39_transactions.refund_id |
| S23 | different trips same index distinct change segment records | ACCEPTED | foreign_key_check=[] |
| S24 | fractional money despite INTEGER declaration | ACCEPTED | foreign_key_check=[] |
| S25 | fractional inventory despite INTEGER declaration | ACCEPTED | foreign_key_check=[] |

附录B含实际执行的完整探针程序和原始JSON结果。没有向项目添加测试文件或篡改正式断言。

## 6. 测试矩阵完整性与逐项审阅

真实数量56、声明count=56；无缺失/重复ID，无结构缺项。remediation/architecture中F10文字51、risk-list文字51、test-matrix尾注46，应修订为真实数量；不是推测缺了某五项。

以下全部是设计审阅，未运行T001–T056。行号指test-matrix.json中test_id所在行。

| 测试ID | 行 | 审阅结果/整改方向 |
|---|---:|---|
| V39-T001 | 6 | 跨用户报价方向正确；setup未给确定报价/时钟/用户值。 |
| V39-T002 | 21 | 跨用户读订单方向正确；需固定响应脱敏与不可存在性处理。 |
| V39-T003 | 36 | 跨用户确认方向正确；错误码目前二选一。 |
| V39-T004 | 51 | 共享库隔离方向正确；需给A/B具体订单集合。 |
| V39-T005 | 66 | 响应丢失重放方向正确；没有具体订单/金额/原始响应。 |
| V39-T006 | 81 | 确认只传proposal_id，改动payload的可信边界/注入入口仍不明确。 |
| V39-T007 | 96 | 服务端生成key时，如何制造新key重放需说明；不能依赖不存在的客户端参数。 |
| V39-T008 | 111 | 非owner不置SECRET_LOST方向正确；只验证拒绝，未证明路由。 |
| V39-T009 | 126 | owner重启方向正确；缺owner ID/boot epoch生命周期。 |
| V39-T010 | 141 | proposal=T边界明确拒绝；但没有给固定T。 |
| V39-T011 | 156 | 补写锁内回执查询是实质修复；区分并发客户端与不同owner Worker。 |
| V39-T012 | 171 | 写pay=T但仍PAID或EXPIRED二选一；hold到期边界未确定。 |
| V39-T013 | 186 | 政策B链路只写paid old/target quote，没有确定账务、人数和区间。 |
| V39-T014 | 201 | 业务退款失败提交方向正确；未覆盖失败明细保存后再退。 |
| V39-T015 | 216 | 补款成功6000→7200，算术正确；缺固定quote和库存。 |
| V39-T016 | 231 | 补款故障预期no change receipt，与三类结果中业务失败留FAILED回执需区分。 |
| V39-T017 | 246 | 退差成功6000→5400，差额600正确。 |
| V39-T018 | 261 | 退差失败no change receipt，需明确业务失败还是技术故障。 |
| V39-T019 | 276 | 任意refund1000/fee0缺对应item及政策；不是完整合法场景。 |
| V39-T020 | 291 | Baseline flag隔离方向正确；未覆盖双引擎和实际dispatch。 |
| V39-T021 | 306 | 40进程杀1仍精确20成功；需barrier/超时/重试策略，且hold未必sold。 |
| V39-T022 | 321 | 仍写random 100/mixed，未固定seed及操作序列。 |
| V39-T023 | 336 | 全部目标RETAINED方向正确；没有接后续退款的归属验证。 |
| V39-T024 | 351 | 部分RETAINED方向正确；if free不是确定初始条件。 |
| V39-T025 | 366 | 全部NEW满员方向正确；需要固定目标容量/已售。 |
| V39-T026 | 381 | 跨车次完整key方向正确；用G1/G2名称还需具体内部trip_id。 |
| V39-T027 | 396 | 跨日期完整key方向正确；日期没有年份和具体库存。 |
| V39-T028 | 411 | 跨席别完整key方向正确；缺实际容量/旧占用。 |
| V39-T029 | 426 | 跨dataset写NEW/REJECT二选一；拒绝时inventory_delta又写占用目标，矛盾。 |
| V39-T030 | 441 | 成功后同item再退方向正确；错误码和新旧请求键应确定。 |
| V39-T031 | 456 | 并发同item需区分同proposal重放和不同proposal拒绝，不能混为one receipt。 |
| V39-T032 | 471 | 3 pax/request4没有给具体合法/非法item集合，不是金额上限测试的完整定义。 |
| V39-T033 | 486 | WRONG_WORKER或route A二选一；成功转发后proposal仍PENDING不成立。 |
| V39-T034 | 501 | PRAGMA顺序改正；fault=none不能证明DDL故障回滚。 |
| V39-T035 | 516 | 权限撤销拒绝方向正确；需覆盖Legacy/LangChain/UI三入口。 |
| V39-T036 | 531 | flag关闭拒绝方向正确；需明确当前配置读取和线性化时点。 |
| V39-T037 | 546 | 切Baseline拒绝方向正确；不应仅检查UI。 |
| V39-T038 | 561 | fault after token?仍有问号；应给确定注入点。 |
| V39-T039 | 576 | 库存写故障原子回滚方向正确。 |
| V39-T040 | 591 | 支付账本故障保留PENDING_PAYMENT，方向正确。 |
| V39-T041 | 606 | 审计故障全回滚方向正确。 |
| V39-T042 | 621 | 完整部分退款链路仍无金额/每item/hold终态，且受D9未决影响。 |
| V39-T043 | 636 | 固定费100/3=34,33,33正确；缺基本票价。 |
| V39-T044 | 651 | 1234×15000/10000=1851无半分；不是宣称修好的舍入边界。 |
| V39-T045 | 666 | 10,20,30规范position正确；标题dup没有重复序号输入和错误预期。 |
| V39-T046 | 681 | 47:53跨日结果正确；需给具体内部trip和原始字段。 |
| V39-T047 | 696 | 187 set未给具体样本/全覆盖选择，不能视为187逐项验证。 |
| V39-T048 | 711 | proposal唯一性方向正确，本轮S15独立证实。 |
| V39-T049 | 726 | 专属规则优先方向正确；需完整scenario/dataset/seat过滤。 |
| V39-T050 | 741 | 多匹配拒绝方向正确；具体两条规则、NULL有效期和priority关系未给。 |
| V39-T051 | 756 | overlap rejected却期望new quote uses new rule；激活策略矛盾。 |
| V39-T052 | 771 | 49/36/12小时费率算术正确；无48/24小时边界及半分手续费输入。 |
| V39-T053 | 786 | 业务支付失败held 2→0、失败回执方向正确；文案rollback_assertion不是回滚要求。 |
| V39-T054 | 801 | 固定seed用于初始化，不等于修复T022随机100操作；same IDs需限定独立场景/DB。 |
| V39-T055 | 816 | 业务支付失败提交记录/回执方向正确。 |
| V39-T056 | 831 | pay前已存在order，技术回滚应保留原order；expected_db写no order错误。 |

## 7. 双引擎、权限和兼容性

现有事实：target/tools.py仍旧八工具；target/agent.py:172从旧TOOLS生成definitions；target/langchain_agent.py:317/344从旧集合适配并拒绝新名称；target/execution_config.py:43只接受baseline/developer_custom，:90有旧受信CURRENT为空兼容；write_authorization.py:8是旧写集合；deepseek_runtime.py:162白名单仍旧集合；web/runtime.py:400为原页面权限检查。25源码索引哈希与阶段9.0一致。

V1.2.1的registry/profile/V39_WRITES/UI旁证是目标设计，尚未接线。设计要求Baseline永远旧八、flag关闭/权限撤销/配置修订后拒绝旧proposal、模型不接收secret，是正确方向；实际执行结果NOT_VERIFIED。本轮对工具JSON做现有jsonschema检查：11个schema合法；ITEMS缺item_ids被拒绝，重复item_ids及FULL加子集却仍可接受，需要定义拒绝或规范化规则，不能按reason推断授权。

订单历史读权限在权限矩阵按owner（可跨本人会话）定义；报价和提案绑定session。不能将“本人跨会话读历史”误报越权，也不能把该权限扩大到他人的订单/报价。确认必须由服务端注入可信身份，不能新增模型可控owner/session参数。

关闭新功能不得写V3.9库，也不得放大旧Provider白名单。不因本报告授权修改SYSTEM_PROMPT/TOOLS/DIMENSIONS或正式103；实施应获得用户对新profile/附录的确认。实际端到端Legacy/LangChain、UI、Provider均未执行，未用局部SQL探针冒充兼容通过。

## 8. 三人购票→部分退款→改签→失败→重试→退剩余人的推演

这是独立规格推演，不是调用V3.9服务。为检验资金给出明确假设：三人各2000分，两覆盖段；所有成功退款处于5%窗口；用户若批准政策B及部分退款后改签，余下2人改签各2500分，补款1000分。该假设不构成批准。政策A或子政策未批准时，第5步须拒绝，不能偷偷执行增强分支。

每段容量取10；初始仅本例占用。old/new sold为每个覆盖段的数量，不是全车总和。qty说明是推演需要的有效数量，现架构未定义持久字段如何同步；不能把这些期望数值说成实现输出。

### 8.1 金额与每位乘客（单位：分）

| 步骤 | paid_total | refunded_total | fee_total | net_paid | current_face | 乘客1 / 乘客2 / 乘客3 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 0 | 0 | 0 | 0 | 6000 | ACTIVE:2000 / ACTIVE:2000 / ACTIVE:2000 |
| 2 | 6000 | 0 | 0 | 6000 | 6000 | ACTIVE:2000 / ACTIVE:2000 / ACTIVE:2000 |
| 3 | 6000 | 1900 | 100 | 4100 | 4000 | REFUNDED:2000 / ACTIVE:2000 / ACTIVE:2000 |
| 4 | 6000 | 1900 | 100 | 4100 | 4000 | REFUNDED:2000 / ACTIVE:2000 / ACTIVE:2000 |
| 5 | 7000 | 1900 | 100 | 5100 | 5000 | REFUNDED:2000 / ACTIVE:2500 / ACTIVE:2500 |
| 6 | 7000 | 1900 | 100 | 5100 | 5000 | REFUNDED:2000 / ACTIVE:2500 / ACTIVE:2500 |
| 7 | 7000 | 1900 | 100 | 5100 | 5000 | REFUNDED:2000 / ACTIVE:2500 / ACTIVE:2500 |
| 8 | 7000 | 6650 | 350 | 350 | 0 | REFUNDED:2000 / REFUNDED:2500 / REFUNDED:2500 |

步骤6的失败请求可记录预期fee=250，但不能计入已收fee_total；步骤8成功后才从100变350。失败交易不计入成功CREDIT。
步骤7指重新提案、尚未确认，因此不改资金/库存；步骤8确认才退其余两人4750分。第1步尚未支付，稳定态面值等式不适用；从第2步起每行均满足net_paid=paid_total-refunded_total=current_face+fee_total。

### 8.2 状态与库存

| 步骤 | order | payment | refund | change | hold（英文说明保留验证边界） | held每段 | 旧sold每段 | 新sold每段 |
|---|---|---|---|---|---|---:|---:|---:|
| 1 | PENDING_PAYMENT | UNPAID | NONE | NONE | ACTIVE | 3 | 0 | 0 |
| 2 | PAID | SUCCEEDED | NONE | NONE | CONSUMED | 0 | 3 | 0 |
| 3 | PAID | SUCCEEDED | SUCCEEDED | NONE | CONSUMED/remaining_qty=2 expected | 0 | 2 | 0 |
| 4 | PAID | SUCCEEDED | SUCCEEDED | NONE | CONSUMED/remaining_qty=2 expected | 0 | 2 | 0 |
| 5 | CHANGED | SUCCEEDED | SUCCEEDED | SUCCEEDED | old CHANGED/new CONSUMED qty2 expected | 0 | 0 | 2 |
| 6 | CHANGED | SUCCEEDED | FAILED | SUCCEEDED | old CHANGED/new CONSUMED | 0 | 0 | 2 |
| 7 | CHANGED | SUCCEEDED | FAILED | SUCCEEDED | old CHANGED/new CONSUMED | 0 | 0 | 2 |
| 8 | CANCELLED | SUCCEEDED | SUCCEEDED | SUCCEEDED | new hold final state NOT_DEFINED in design | 0 | 0 | 0 |

最终新hold终态在设计未明确，标NOT_DEFINED，不能臆造已通过。改签后的有效乘客应继续参与current_face，已退乘客的2000分历史保持不变；若使用item_status=CHANGED，必须明确“有效面值集合”，不能仍只统计ACTIVE却漏掉新票。

库存资金在上述期望规则下可守恒，但当前材料未提供唯一完整转换以证明可执行。NOT_DEFINED、失败费用过滤、成功明细/失败明细分离、有效人数/当前hold量和D9均须解决。只写“counts/ledger consistent”的T042不能证明该链路通过。

## 9. 历史成果保护与差异口径

| 资产 | 本轮核验 |
|---|---|
| 当前5538基线 | 开工5538/5538；最终5537匹配、百炼账本1项并行追加，见附录F |
| 阶段七当前获准1892 | 1892/1892匹配，含此前批准的限定差异 |
| 旧4056历史基线 | 4054匹配；DeepSeek既有差异不变，百炼在既有差异上本轮又追加8行，不能藏入旧差异，见附录F |
| 阶段八产物 | 38/38匹配 |
| 数据准备原始材料 | 34/34匹配 |
| 阶段9.0源码索引 | 25/25匹配 |
| 正式103 catalog/B manifest | 103条；7/7哈希匹配；不执行、不重新计分 |
| V1.0/V1.1/V1.2正文 | 三份原件哈希匹配 |
| V1.1旧清单 | 13/13 |
| V1.2旧清单 | 16/17；Gap说明既有修订，见C11 |
| 默认旧tickets.db | SHA 67e6c6e2fb51432dbc4e4c8a97849b2347f5fb811cd2922f6bc9fb06e93cc54e，匹配 |
| 项目data/v39/simulation.sqlite | 不存在；本轮未创建 |
| Bridge两历史文档 | 缺失，NOT_VERIFIED；历史预期SHA保留 |

Fixture SHA feaec244decbe9ed25f42b5fa7767bb4fb65d76e5313d8b1a52db14826b29217；
GTFS ZIP SHA 3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030；
阶段八DB SHA e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69。

两账本差异为artifacts/runtime/api-usage/bailian/dbc4325ea7a9515b7a04/requests.jsonl及deepseek/071347fb755d9c6ce0fd/requests.jsonl。原有差异不判为本轮新增；百炼本轮发生的追加单独披露，不回滚、不覆盖、不静默接受为新基线，见附录F。
历史回归1441 passed/11 failed/1 skipped、199子测试只保留为历史；本轮不运行、不删失败、不增skip，不声称当前全绿。

Bridge审计历史预期 e5b98464218d4c072dc460de335deaf1e0d8f9603df4ac1873a545a7ee2d52c1；
协作协议历史预期 bca032ba92b1888e91dc253013298ae082667cad8999394de3e6a4cced589337。
本机未发现3080监听；未安装/启用Bridge或派发任务。没有把缺口说明当作原件。

## 10. D1–D9用户决策清单

设计记录是提议，不是批准凭据。本轮不替用户批准。

| 决策 | 设计基准 | 状态/需确认 |
|---|---|---|
| D1 | 独立应用共享simulation DB；旧库不改 | DEFAULT_NOT_USER_APPROVED；新库路径/隔离需确认 |
| D2 | 相邻区间分段容量 | DEFAULT；需确认有效数量和守恒契约 |
| D3 | 模拟SECOND/FIRST/BUSINESS | DEFAULT；非真实席别 |
| D4 | hold900/quote600/confirmation300秒 | DEFAULT；时钟边界及实际使用检查 |
| D5 | 新11个railway工具，旧八保持 | DEFAULT；profile和Prompt附录/接线批准另列 |
| D6 | 模型只提案，服务端一次性secret/UI确认 | DEFAULT；仅单确认Worker限制需接受 |
| D7 | seed20261102，容量20/8/3等、每段1000分等 | DEFAULT_DEMO_VALUES；演示参数，不是铁路官方价格/库存 |
| D8 | 不统一旧订单历史 | DEFAULT；需接受分开历史 |
| D9 | A严格P02 / B允许改签后P01退款 | PENDING_USER_APPROVAL |

D9子决策：一次改签是否保留、部分退款后能否改签/继续退款、费率及舍入。未决定时应拒绝未授权分支；不能因为架构审查或数学推演自动启用B。

## 11. 最终裁决与正式实施准入

**BLOCKED。7项P1：C01–C06、C10；4项P2：C07–C09、C11。** SQL能创建、文件哈希匹配、F01/F13等局部设计修复都不足以覆盖关键资金/库存/数据隔离缺口。本轮不建议进入完整V3.9正式业务实现，不通过未准入Bridge派发任务。

GO要求：关闭所有关键P1，提供确切服务/数据库责任分配、状态转换和确定性反例依据。不能仅把DESIGNED改成RESOLVED，也不要求把尚未实现的产品伪称已验收。正式103/B/Bridge原阻塞独立保留，不把新增架构探针算入正式成绩。

## 12. 下一步实施建议与审查边界

交回DeepSeek作下一版设计整改：
1. 先修报价范围、资金关联双向CHECK、退款组合验证、RETAINED来源与实际库存引用。
2. 明确失败费用/失败明细/重试，以及有效人数、当前hold和全部状态迁移；固定第8节逐行预期。
3. 拒绝小数金额/库存，明确整数域和事务执行API。
4. 修正56项内容与陈旧数量，增加本报告反例；不修改原103或旧测试断言。
5. 固定单确认Worker的启动/排他/路由/失效契约，保留未来多Worker未实现状态。
6. 保存旧Gap修订差异，不改旧manifest；新包再交独立审查及用户决策。

本轮仅内存SQLite、样例数据、现有jsonschema和静态核验；无真实模型/Embedding/铁路/支付请求，无正式迁移、无浏览器验收、无文件WAL或真实多进程服务测试。未执行T001–T056及产品完整回归。不修改PROJECT_STATUS符合本次明确限制。

本报告文件为本轮唯一新增文件，其他工作区成果保留；完整SQL程序和运行结果随本报告保存，未另建证据目录。

## 附录A：开工Git状态

```text
 M PROJECT_STATUS.md
 M target/train_source.py
 M web/design.css
 M web/design.py
 M web/presentation.py
 M web/train_data.py
 M web/user_layout.css
 M web/user_layout.py
?? .agents/skills/frontend-design/
?? docs/reviews/Ticket-Agent-Frontend-Skills-Installation.md
?? docs/reviews/Ticket-Agent-Railway-Dataset-Assessment.md
?? docs/reviews/Ticket-Agent-V3.7-Phase7-Independent-Railway-Service-Report.md
?? docs/reviews/Ticket-Agent-V3.7-Visual-Upgrade-Report.md
?? docs/reviews/Ticket-Agent-V3.8-Phase8-Railway-Static-Data-Report.md
?? docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.1.md
?? docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.1.md
?? docs/reviews/Ticket-Agent-V3.9-Architecture-Design-v1.2.md
?? docs/reviews/Ticket-Agent-V3.9-Architecture-Design.md
?? docs/reviews/Ticket-Agent-V3.9-Bridge-Evidence-Gap-20261102.md
?? docs/reviews/Ticket-Agent-V3.9-Phase9.0-Architecture-Audit-Report.md
?? prototypes/
?? scripts/railway_query_service.py
?? services/
?? target/railway_protocol.py
?? target/train_assistant_adapter.py
?? tests/test_railway_query_service.py
```

## 附录B：实际执行的内存SQL探针完整程序

执行命令为 .venv-v35/Scripts/python.exe -B -，下列程序经stdin输入。ROOT只读取现有schema；所有CREATE/INSERT/UPDATE都在 :memory:；probe逐项SAVEPOINT回滚。没有用本脚本模拟产品身份校验或正式计分。

```python
from pathlib import Path
import sqlite3,json
ROOT=Path(r'D:\codexproject\ticket-agent')
DDL=(ROOT/'artifacts/runtime/v39-architecture-v1.2.1-20261103-010456/schema.sql').read_text(encoding='utf-8')
c=sqlite3.connect(':memory:');c.executescript(DDL)
def ins(table,**v):
 cols=','.join(v);c.execute('INSERT INTO '+table+' ('+cols+') VALUES ('+','.join('?' for _ in v)+')',tuple(v.values()))
stamp='2026-11-03T08:00:00+08:00'
for tag in ('A','B'):
 ins('v39_scenarios',scenario_id=tag,name=tag,seed=1,dataset_version='v1',status='ACTIVE',config_json='{}',created_at=stamp)
 ins('v39_price_rules',rule_id='R'+tag,version=1,scenario_id=tag,dataset_version='v1',trip_id=None,seat_class='SECOND',base_fen_per_segment=1000,seat_multiplier_bp=10000,fixed_fee_fen=0,valid_from=stamp,valid_until=None,status='ACTIVE')
def quote(q,tag='A',rule=None,version='v1',trip='T',day='2026-11-03'):
 ins('v39_quotes',quote_id=q,session_id='S'+tag,owner_phone='U'+tag,scenario_id=tag,dataset_version=version,trip_id=trip,service_date=day,origin_stop_id='X',destination_stop_id='Z',origin_sequence=1,destination_sequence=3,origin_position=0,destination_position=2,seat_class='SECOND',passenger_count=3,rule_id=rule or 'R'+tag,rule_version=1,base_fen_per_segment=1000,seat_multiplier_bp=10000,fixed_fee_fen=0,segment_count=2,single_base_fen=2000,single_seat_fen=2000,base_total_fen=6000,seat_total_fen=6000,total_fen=6000,currency='CNY',quote_hash=q,status='CONSUMED',expires_at='2026-11-03T08:10:00+08:00',created_at=stamp)
def hold(h,q,tag='A',trip='T',day='2026-11-03'):
 ins('v39_holds',hold_id=h,quote_id=q,session_id='S'+tag,owner_phone='U'+tag,scenario_id=tag,trip_id=trip,service_date=day,seat_class='SECOND',quantity=3,status='CONSUMED',expires_at='2026-11-03T08:15:00+08:00',created_at=stamp)
def order(o,p,q,h,tag='A',key=None):
 ins('v39_orders',order_id=o,proposal_id=p,session_id='S'+tag,owner_phone='U'+tag,scenario_id=tag,dataset_version='v1',quote_id=q,hold_id=h,trip_id='T',service_date='2026-11-03',origin_stop_id='X',destination_stop_id='Z',origin_sequence=1,destination_sequence=3,origin_position=0,destination_position=2,seat_class='SECOND',passenger_count=3,total_fen=6000,paid_total_fen=6000,net_paid_fen=6000,order_status='PAID',payment_status='SUCCEEDED',refund_status='NONE',change_status='NONE',idempotency_key=key or o,created_at=stamp,updated_at=stamp,expires_at='2026-11-03T08:15:00+08:00')
def refund(r,tag='A',status='PENDING'):
 ins('v39_refund_requests',refund_id=r,order_id='O'+tag,scope='ITEMS',requested_fen=2000,refundable_fen=2000,fee_fen=100,net_fen=1900,status=status,prior_order_status='PAID',prior_total_fen=6000,idempotency_key=r,created_at=stamp)
def tx(t,kind='REFUND',direction='CREDIT',order_id='OA',refund_id=None,change_id=None,amount=1900):
 ins('v39_transactions',transaction_id=t,order_id=order_id,refund_id=refund_id,change_id=change_id,transaction_type=kind,direction=direction,amount_fen=amount,status='SUCCEEDED',idempotency_key=t,request_hash=t,created_at=stamp)
for tag in ('A','B'):
 quote('Q'+tag,tag);hold('H'+tag,'Q'+tag,tag)
 ins('v39_proposals',proposal_id='P'+tag,session_id='S'+tag,owner_phone='U'+tag,action='CREATE_ORDER',scenario_id=tag,execution_mode='developer_custom',config_hash='cfg',write_policy_hash='wp',feature_flag='1',baseline_id='base',provider='mock',tool_whitelist_hash='wl',config_revision=1,idempotency_key='P'+tag,request_hash='hash',payload_json='{}',state='CONFIRMED',expires_at='2026-11-03T08:05:00+08:00',created_at=stamp)
 order('O'+tag,'P'+tag,'Q'+tag,'H'+tag,tag)
 for i in range(3):
  ins('v39_order_items',item_id=tag+str(i),order_id='O'+tag,passenger_index=i,passenger_name='DEMO'+str(i),seat_class='SECOND',base_fen=2000,seat_fen=2000,fixed_fee_share_fen=0,fare_fen=2000,item_status='ACTIVE',created_at=stamp)
 for i in range(2):
  ins('v39_inventory_segments',scenario_id=tag,dataset_version='v1',trip_id='T',service_date='2026-11-03',seat_class='SECOND',segment_index=i,from_stop_id=str(i),from_sequence=i+1,from_position=i,to_stop_id=str(i+1),to_sequence=i+2,to_position=i+1,capacity=10,held=0,sold=3,updated_at=stamp)
 refund('RF'+tag,tag)
quote('QT',trip='T2',day='2026-11-04');hold('HT','QT',trip='T2',day='2026-11-04')
ins('v39_change_requests',change_id='CA',order_id='OA',old_hold_id='HA',old_quote_id='QA',target_quote_id='QT',target_trip_id='T2',target_service_date='2026-11-04',target_origin_stop_id='X',target_destination_stop_id='Z',target_origin_position=0,target_destination_position=2,target_seat_class='SECOND',difference_fen=0,status='PENDING',prior_order_status='PAID',prior_total_fen=6000,idempotency_key='CA',created_at=stamp)
tx('PAY',kind='PAYMENT',direction='DEBIT',amount=6000)
for i in range(3):ins('v39_transaction_allocations',allocation_id='AL'+str(i),transaction_id='PAY',order_item_id='A'+str(i),amount_fen=2000)
c.commit()
results=[]
def probe(pid,description,fn):
 c.execute('SAVEPOINT p')
 try:
  fn(); results.append(dict(id=pid,description=description,result='ACCEPTED',foreign_key_check=c.execute('PRAGMA foreign_key_check').fetchall()))
 except sqlite3.IntegrityError as e:results.append(dict(id=pid,description=description,result='REJECTED',error=str(e)))
 finally:c.execute('ROLLBACK TO p');c.execute('RELEASE p')
probe('S01','scenario A quote references scenario B rule',lambda:quote('BAD',rule='RB'))
probe('S02','v2 quote references v1 rule',lambda:quote('BAD',version='v2'))
probe('S03','order A refund request contains order B item',lambda:ins('v39_refund_items',refund_id='RFA',order_item_id='B0',amount_fen=2000,fee_fen=100,net_fen=1900))
probe('S04','order A transaction links order B refund',lambda:tx('BAD',refund_id='RFB'))
probe('S05','order A payment allocation moves to B item',lambda:c.execute("UPDATE v39_transaction_allocations SET order_item_id='B0' WHERE allocation_id='AL0'"))
probe('S06','refund item gross exceeds original item fare',lambda:ins('v39_refund_items',refund_id='RFA',order_item_id='A0',amount_fen=9000,fee_fen=450,net_fen=8550))
probe('S07','refund transaction exceeds request net and paid_total',lambda:tx('BAD',refund_id='RFA',amount=9999))
probe('S08','allocation sum differs from transaction amount',lambda:c.execute("UPDATE v39_transaction_allocations SET amount_fen=1 WHERE allocation_id='AL0'"))
probe('S09','REFUND without refund_id',lambda:tx('BAD'))
probe('S10','CHANGE_SUPPLEMENT without change_id',lambda:tx('BAD',kind='CHANGE_SUPPLEMENT',direction='DEBIT'))
probe('S11','CHANGE_REFUND without change_id',lambda:tx('BAD',kind='CHANGE_REFUND'))
probe('S12','PAYMENT incorrectly links refund',lambda:tx('BAD',kind='PAYMENT',direction='DEBIT',refund_id='RFA'))
probe('S13','PAYMENT incorrectly links change',lambda:tx('BAD',kind='PAYMENT',direction='DEBIT',change_id='CA'))
probe('S14','PAYMENT incorrect CREDIT direction',lambda:tx('BAD',kind='PAYMENT'))
probe('S15','same proposal creates second order with fresh quote/hold',lambda:order('DUP','PA','QT','HT',key='other'))
def segment(role='RETAINED',sh='NO_HOLD',so='NO_ORDER',trip='T',index=0):
 ins('v39_hold_segments',hold_id='HA',scenario_id='A',dataset_version='v1',trip_id=trip,service_date='2026-11-03',seat_class='SECOND',segment_index=index,quantity=3,inventory_role=role,source_hold_id=sh,source_order_id=so)
probe('S16','RETAINED nonexistent source hold/order',segment)
probe('S17','hold segment references nonexistent inventory row',lambda:segment(role='NEW',sh=None,so=None,trip='MISSING',index=99))
probe('S18','RETAINED null source identifiers',lambda:segment(sh=None,so=None))
probe('S19','RETAINED foreign owner source hold/order',lambda:segment(sh='HB',so='OB'))
def failed_retry():
 c.execute("UPDATE v39_refund_requests SET status='FAILED' WHERE refund_id='RFA'")
 ins('v39_refund_items',refund_id='RFA',order_item_id='A0',amount_fen=2000,fee_fen=100,net_fen=1900)
 refund('RETRY')
 ins('v39_refund_items',refund_id='RETRY',order_item_id='A0',amount_fen=2000,fee_fen=100,net_fen=1900)
probe('S20','failure detail retained then new refund retry',failed_retry)
probe('S21','negative or overcapacity inventory',lambda:c.execute("UPDATE v39_inventory_segments SET held=8 WHERE scenario_id='A' AND segment_index=0"))
def success_duplicate():
 tx('ONE',refund_id='RFA');tx('TWO',refund_id='RFA')
probe('S22','two successful transactions for same refund',success_duplicate)
def full_key():
 for trip,day,role in [('T','2026-11-03','RELEASED'),('T2','2026-11-04','NEW')]:
  ins('v39_change_segments',change_id='CA',scenario_id='A',dataset_version='v1',trip_id=trip,service_date=day,seat_class='SECOND',segment_index=0,role=role,quantity=3)
probe('S23','different trips same index distinct change segment records',full_key)
probe('S24','fractional money despite INTEGER declaration',lambda:tx('BAD',kind='PAYMENT',direction='DEBIT',amount=0.5))
probe('S25','fractional inventory despite INTEGER declaration',lambda:c.execute("UPDATE v39_inventory_segments SET held=0.5 WHERE scenario_id='A' AND segment_index=0"))
def failed_fee():
 c.execute("UPDATE v39_refund_requests SET status='FAILED' WHERE refund_id='RFA'")
 return c.execute("SELECT sum(fee_fen),sum(CASE WHEN status='SUCCEEDED' THEN fee_fen ELSE 0 END) FROM v39_refund_requests WHERE order_id='OA'").fetchone()
c.execute('SAVEPOINT fee')
fee_result=failed_fee();c.execute('ROLLBACK TO fee');c.execute('RELEASE fee')
print(json.dumps(dict(failed_fee_comparison=dict(unfiltered_sum=fee_result[0],successful_only_sum=fee_result[1]),sqlite_version=sqlite3.sqlite_version,foreign_keys=c.execute('PRAGMA foreign_keys').fetchone()[0],journal_mode=c.execute('PRAGMA journal_mode').fetchone()[0],tables=c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0],explicit_indexes=c.execute("SELECT count(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchone()[0],triggers=c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],results=results),ensure_ascii=False))
c.close()
```

## 附录C：SQL探针原始stdout

以下为本轮最终重复执行的原始stdout，ACCEPTED/REJECTED定义见第5节。它不是产品测试报告。

```json
{"failed_fee_comparison": {"unfiltered_sum": 100, "successful_only_sum": 0}, "sqlite_version": "3.53.1", "foreign_keys": 1, "journal_mode": "memory", "tables": 21, "explicit_indexes": 19, "triggers": 0, "results": [{"id": "S01", "description": "scenario A quote references scenario B rule", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S02", "description": "v2 quote references v1 rule", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S03", "description": "order A refund request contains order B item", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S04", "description": "order A transaction links order B refund", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S05", "description": "order A payment allocation moves to B item", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S06", "description": "refund item gross exceeds original item fare", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S07", "description": "refund transaction exceeds request net and paid_total", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S08", "description": "allocation sum differs from transaction amount", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S09", "description": "REFUND without refund_id", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S10", "description": "CHANGE_SUPPLEMENT without change_id", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S11", "description": "CHANGE_REFUND without change_id", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S12", "description": "PAYMENT incorrectly links refund", "result": "REJECTED", "error": "CHECK constraint failed: refund_id IS NULL OR transaction_type='REFUND'"}, {"id": "S13", "description": "PAYMENT incorrectly links change", "result": "REJECTED", "error": "CHECK constraint failed: change_id IS NULL OR transaction_type IN ('CHANGE_SUPPLEMENT','CHANGE_REFUND')"}, {"id": "S14", "description": "PAYMENT incorrect CREDIT direction", "result": "REJECTED", "error": "CHECK constraint failed: (transaction_type IN ('PAYMENT','CHANGE_SUPPLEMENT') AND direction='DEBIT') OR (transaction_type IN ('CHANGE_REFUND','REFUND') AND direction='CREDIT')"}, {"id": "S15", "description": "same proposal creates second order with fresh quote/hold", "result": "REJECTED", "error": "UNIQUE constraint failed: v39_orders.proposal_id"}, {"id": "S16", "description": "RETAINED nonexistent source hold/order", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S17", "description": "hold segment references nonexistent inventory row", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S18", "description": "RETAINED null source identifiers", "result": "REJECTED", "error": "CHECK constraint failed: inventory_role <> 'RETAINED' OR (source_hold_id IS NOT NULL AND source_order_id IS NOT NULL)"}, {"id": "S19", "description": "RETAINED foreign owner source hold/order", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S20", "description": "failure detail retained then new refund retry", "result": "REJECTED", "error": "UNIQUE constraint failed: v39_refund_items.order_item_id"}, {"id": "S21", "description": "negative or overcapacity inventory", "result": "REJECTED", "error": "CHECK constraint failed: held + sold <= capacity"}, {"id": "S22", "description": "two successful transactions for same refund", "result": "REJECTED", "error": "UNIQUE constraint failed: v39_transactions.refund_id"}, {"id": "S23", "description": "different trips same index distinct change segment records", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S24", "description": "fractional money despite INTEGER declaration", "result": "ACCEPTED", "foreign_key_check": []}, {"id": "S25", "description": "fractional inventory despite INTEGER declaration", "result": "ACCEPTED", "foreign_key_check": []}]}
```

## 附录D：迁移驱动与参数校验的补充实测

内存错误注入观察：显式脚本BEGIN时，故障后事务仍活动，rollback后表数0；先execute(BEGIN)再executescript时，故障后事务已不活动，rollback后表数21。这是本机Python/SQLite行为，不能推断尚未编写的项目迁移已经犯错。

现有Draft202012Validator对11个工具schema检查通过；ITEMS无item_ids=false；item_ids=['A0','A0']=true；FULL带['A0']=true。后两项需明确语义/去重或拒绝，不要把JSON合法当授权通过。

## 附录E：报告新增后的保护复核方法

排除本报告路径，重算开工6074条原有路径聚合。若无并行变化，应等于第1节指纹；本轮实际有百炼账本并行追加，实测及归因核验见附录F。Git只比附录A新增本报告。另重复19文件清单和5538/1892/4056/阶段八/原始材料核验。核验不把本新增报告混进旧集合，也不修改原清单。

## 附录F：最终实测复核与并行账本追加

报告生成后的复核发现一处并行变化：artifacts/runtime/api-usage/bailian/dbc4325ea7a9515b7a04/requests.jsonl。记录如下，未修改该文件，也未将其静默更新为获准基线。

| 项目 | 开工/原有前缀 | 最终观测快照 |
|---|---|---|
| 字节数 | 265146 | 268991 |
| 行数 | 550 | 558 |
| SHA256 | 280ebe3715eda682e7e85087db43b0884d029c62eaab22dbedd37215671d70b4 | 07782195950cd4f2a79851c0d577cf28ac28810aa9666992242400690ec6dcc7 |

逐行累计SHA找到265146字节处的原哈希，确认旧550行完整保留，末尾追加3845字节、8行。没有打印原始请求内容、密钥或其他敏感数据。写入方未核实，不能归因于用户或DeepSeek。本审查没有发起真实模型请求；账本出现新记录不能冒充为本审查主动调用的次数或验证成绩。

首轮最终6074路径原始聚合为f33f8bc989688c7f3561e326aeca5495b3a9b7a2f533cf555c666fab0db71d92，与开工不同。为定位差异，在确认原前缀完整的前提下，仅在计算中将该账本的哈希替换为开工哈希，得到5c466cd37583df21c057e508cf325c936f44106961f6c78c92a874603ebd9394，与开工完全一致。这仅是内存计算，没有替换文件或修改清单，证明覆盖集合中其余6073条原有路径无变化。

最终19/19交付清单、1892/1892当前获准清单、阶段八38/38、原始材料34/34、源码索引25/25、B七文件和103数量/哈希仍匹配。当前5538清单应如实记为5537匹配、1处上述追加；旧4056仍是两个差异文件，但百炼文件在既有差异上又发生了本轮追加，不能混淆时段。HEAD不变，暂存区空，git diff --check退出码0；报告无行尾空白；项目V3.9数据库仍不存在。

Git相对开工状态仅增加本报告。审查员的唯一文件写入为本报告；未清理、回滚、覆盖或批准并行追加。后续开工应现场重新核对，不沿用本报告观测快照作为自动授权。

