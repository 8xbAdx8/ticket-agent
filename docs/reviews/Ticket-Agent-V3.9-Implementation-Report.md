# Ticket Agent V3.9 正式实施交付报告

时间：2026-11-03，Asia/Shanghai。开发者：Codex；DeepSeek Harness 尚未独立审查。

**结论：PARTIAL。** 已完成可实际运行的静态查询、模拟库存/价格、11 工具、双引擎提案与界面确认、支付/取消/退改事务及离线工程验证；没有达到“V3.9 完整验收通过”。D9 保持待决，原始 T046 有证据冲突，若干矩阵表述需澄清，Harness 独立审查尚未执行。原有 11 项失败和唯一 Skip 保留。正式 103 仍 BLOCKED，计分 0 条。

收尾补记（V2）：最后 Git 核查另发现空的 `data/v39/simulation.sqlite`，已保留并列入交付，不再把本轮数据库清单限定为测试/浏览器目录。首份审查ZIP保留为较早快照，最终以 `review-package-v2.json` 及 `verification-v2.json` 为准。下文新增套件最终证据为 `guarded-suite-isolated/`，旧 `guarded-suite-delivery/` 原日志不覆盖。

证据根目录：`artifacts/runtime/v39-implementation-20261103-130321/`，以下未注明根的运行证据均相对于此目录。开工原件、失败批次和中间批次全部保留。

## 1. 开工状态、授权与保护

- 实际工作区：`D:\codexproject\ticket-agent`；没有切换工作副本。
- 分支：`feat/ticket-agent-v36-stabilization`；HEAD：`4340b6640025be95e8300a3d625a32cfb431e35d`，本轮未提交、推送、合并或打标签。
- 开工暂存区为空。已有 8 个跟踪文件修改：PROJECT_STATUS、train_source 和 6 个 Web 展示/来源文件；另有未跟踪架构、原型、铁路服务和 Skill。开工文件详见 `before-corrected.json`。本轮保留这些成果，PROJECT_STATUS 仅增量增加本轮记录。
- 开工 manifest 实际覆盖 6550 个现有文件。首次比较脚本曾遗漏历史清单独有路径，已直接读取全部路径重算；`before.json` 原件保留，`before-corrected.json` 是本轮实际基线，不采用首次误报的缺失结论。
- V1.2.2 原始审查包 22 项 SHA 核对一致；原件不修改。其设计通过声明未作为事实依据。
- 最终 `checks-final-protection.json`：1892、4056、5538 三组相对于开工均无新增差异。旧 4056 的两个账本历史差异及旧 5538 的百炼追加差异保留原结论；不将这些开工前差异计成本轮新增问题。
- `checks-final-contracts.json`：SYSTEM_PROMPT、TOOLS、DIMENSIONS 的 AST 哈希均不变。公共 Agent.chat 十字段、Trace 工具五字段保留。
- GTFS ZIP `3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`、阶段八数据库 `e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`、2100 Fixture `feaec244decbe9ed25f42b5fa7767bb4fb65d76e5313d8b1a52db14826b29217` 及旧 `data/tickets.db` 均保持开工哈希。

## 2. 实际文件变更

| 文件/目录 | 本轮修改原因与结果 |
|---|---|
| `target/v39/store.py` | 独立命名空间、路径保护、WAL/FK、原子初始化/checksum、单活租约与续租/释放 |
| `target/v39/schema.sql`、`hardening.sql` | 从原 V1.2.2 派生可执行迁移；原件保留；补全库存归属、RETAINED、账本、分摊、退款状态与规则约束 |
| `target/v39/static.py` | 固定 SHA 的阶段八只读 Adapter、站点/车次/经停/区间/服务日、分页与来源元数据 |
| `target/v39/pricing.py`、`accounting.py` | 整数分、half-up、固定费分摊、时间半开与优先级/歧义拒绝、成功账本汇总 |
| `target/v39/context.py`、`registry.py`、`tool-schemas.json` | 可信上下文、11 工具统一验证/分发、Baseline/开关/白名单/权限隔离、8 次工具尝试限制、Trace 旁证 |
| `target/v39/service.py`、`lifecycle.py`、`policy.py` | 报价、提案、仅内存确认秘密、原子建单支付/取消/退票/改签、业务失败与技术回滚、D9 默认拒绝 |
| `target/v39/planner.py` | 明确标注的确定性离线对话演示 Provider，不是真实 LLM，不可确认交易 |
| `target/v39/README.md`、`__init__.py` | 使用、测试、迁移/回滚边界和独立模块入口 |
| `target/agent.py` | 增量接入统一注册表和每轮尝试上限；原 Prompt/公开返回结构不改 |
| `target/langchain_agent.py` | 复用原 create_agent/ToolNode，注册表、权限、参数和服务与 Legacy 一致 |
| `web/railway_simulation.py` | 用户入口、查询/经停/报价、确认卡、本人订单、离线对话、D9 禁用入口、新建独立场景 |
| `web/app.py` | 仅开关开启时新增铁路入口；旧四面板/聊天、开发者工作台、测试控制台保留；铁路配置会话可被现有编辑器选择 |
| `scripts/run_v39_tests.py` | 全新输出目录、网络/凭据隔离、源码 manifest、原始日志、JUnit 和逐项结果 |
| `tests/v39/` | 新增数据库反向测试、56 项执行映射、真实静态原件校验、双引擎、单活/多进程与本机 RPC 验证 |
| `PROJECT_STATUS.md`、本报告 | 长期状态及交付索引。未删除历史结论 |
| `data/v39/simulation.sqlite` | 本轮窗口出现的默认新库，380928字节；无订单/交易/报价/提案/库存/审计事件。仅保留、只读核验，不删除或重置 |

未修改依赖、CSS、旧测试、正式103内容、B快照、`target/p2_*`、旧业务数据库和保护证据。未启用 Bridge 或接入真实铁路/支付。完整名单与源文件 SHA 见最终 manifest；`working-tree.patch` 包含跟踪文件差异，未跟踪新源码以 manifest 和审查 ZIP 为准。

## 3. 对 V1.2.2 的定点工程修正

新迁移仍为 **22 张 STRICT 表、20 个显式索引**，当前为 **37 个触发器**；不沿用原件“7 个触发器已经充分”的自我结论。

1. Worker 增加 singleton slot 唯一约束；租约在 `BEGIN IMMEDIATE` 内原子获取/续租/释放。相同 epoch 才能续租，旧 Worker 无法覆盖新 owner。UTC 规范化，不比较混合时区字符串。单确认进程是部署限制，不宣称任意多 Worker。
2. hold segment 校验父 hold/quote 的 scenario、dataset、trip、date、seat、区间和剩余数量；父 hold 身份不可变。RETAINED 还验证当前订单/source hold、owner、完整库存键与数量。保留段不增加 held/sold。
3. change segment 按角色验证目标：NEW/RETAINED 指向新报价，RELEASED 指向原报价，避免让释放的旧线路错误引用新线路。
4. 交易必须从 PENDING 开始；PAYMENT/REFUND/CHANGE_* 引用与资金方向保持双向约束；allocation 的 order/change 与交易一致。最终交易和分摊不可篡改；成功必须完整分摊。
5. 退款请求和明细按 REQUESTED/PENDING→SUCCEEDED/FAILED 迁移；成功前核对同一订单、活跃乘客、票面、逐人净退款和交易。失败请求及失败交易保留；失败手续费不计入成功余额。审计和库存事件不允许 UPDATE/DELETE。
6. 价格唯一索引作用域加入 dataset/priority，并只约束 ACTIVE；同 rule/version 时间重叠拒绝，同优先级不同规则歧义拒绝；trip 规则优先；旧报价冻结所有金额/规则版本并以 SHA 检查。
7. 退完后数量合法为 0，但初始数量仍为 1–6。金额、人数、数量等服务入口拒绝 bool、float、NaN、字符串。Scenario/规则和库存新增记录的数据版本一致。
8. 订单首次写入校验 quote/hold/owner/session 与库存身份；已过出发时间不允许锁座。场景“重置”创建新命名空间，不删除旧账本。

实际反向复现包含：原 V1.2.2 能接受跨 owner RETAINED，工程迁移拒绝；成功金额/分摊篡改、缺失退款/改签引用、跨 change 分摊、数量/日期/席别/版本混用均被拒绝。详见 `tests/v39/test_storage.py`、`test_hardening.py` 和 JUnit。

## 4. 数据库初始化、回滚与状态机

- 产品默认路径 `data/v39/simulation.sqlite`，只有打开已启用入口时才按需创建。本轮除隔离测试库与 `browser-final-r3/simulation.sqlite`，现场还存在上述空默认新库；没有初始化或迁移旧数据库。
- 每个写事务用 `BEGIN IMMEDIATE`；初始化逐条执行 DDL，不在事务中调用 executescript。`fail_after=8` 真实故障注入后数据库表数为 0；失败新文件保留，不覆盖修复。
- 连接必须 foreign_keys=1；WAL 在事务外设置；已有库迁移 checksum 不符立即拒绝。早期本轮测试库与最终迁移不兼容时保留原件，新建目录，不覆盖早期库。
- 应用回滚：停止该演示进程，以 `RAILWAY_SIMULATION_ENABLED=0` 重启；新库/账本/回执保留，旧入口及正式 Baseline 继续旧八工具。无旧库 DOWN migration、无删表/删库脚本。
- 订单主状态：PENDING_PAYMENT→PAID→CHANGED；未支付可 CANCELLED/EXPIRED/PAYMENT_FAILED；活跃乘客全退后 CANCELLED。支付、退款、改签另存各自状态，退款失败保留 PAID/CHANGED 及原库存。
- 支付失败/模拟超时立即恰好释放 held，不写成功扣款；技术 SQL 异常则 token、订单、库存、账本、审计和回执全部回滚。
- 改签按完整六字段库存键做 RETAINED/NEW/RELEASED，保留旧库存直至新目标及差价事务全部成功；补款/退差失败留下失败记录，旧业务不变。
- 每人票面与累计资金独立：`net_paid = successful debit - successful credit = active face + successful fee`。部分退款保留原始人数与已退款明细，改签只更新剩余乘客；旧报价/快照和已退款明细保留。

## 5. 工具、权限与双引擎

11 工具原版 Schema 从 V1.2.2 原件复制，哈希可对照；旧 `target/tools.py:TOOLS` 未改：

`railway_search_stations`、`railway_query_trips`、`railway_trip_stops`、`railway_check_inventory`、`railway_quote_fare`、`railway_create_order`、`railway_get_order`、`railway_pay_order`、`railway_cancel_order`、`railway_refund_order`、`railway_change_order`。

模型只能得到 proposal_id，Schema 不接收或返回确认 secret。秘密随机生成，仅保存在确认服务内存；数据库只存哈希与 owner/epoch/args/expiry 绑定。UI 显式勾选后通过可信服务确认，不把 token 交回模型；原始秘密不在日志、Prompt、ToolMessage 或审查包。

重复确认以服务端固定 key 和 request hash 返回原回执；`BEGIN IMMEDIATE` 内再次检查，不能由调用方改 key 重放。确认重验开关、身份、会话、scenario、EffectiveConfig revision/hash、Provider、工具白名单、写权限、Baseline 和 D9 policy hash。撤权/切 Baseline/关闭开关均不能执行旧提案。Worker B 返回 WRONG_WORKER，不误标 SECRET_LOST；原 owner 重启后旧秘密不恢复，需新卡。

铁路页复用现有 Developer Override：原工具白名单及 lock/create/pay/cancel 权限映射约束铁路行为；开发者编辑后上下文和提案 hash 改变。Baseline 不扩大工具集；当前 V3.9 Live Provider 被拒绝，不修改旧 Live Provider 的选择或费用授权实现。

铁路对话是**确定性离线演示**，支持日期/站名查询、明确本人订单号的支付/取消/退款提案、引用报价建单等，含糊站名返回选择提示，不猜别名。真实 LLM 的语言泛化和新增 railway Live 调用不在本轮授权验证内。Legacy 与 LangChain 均实际执行同一注册工具和服务，生成提案后数据库订单数仍为 0，证明不是模型直接交易。

Trace 保持十字段和五字段；`railway_runtime_configuration` 旁证记录实际铁路白名单、scenario 和配置摘要；工具成功、业务完成、UI 操作分开。页面操作为 `aggregate_type=page` 审计，不冒充 Agent run 或比赛成绩。

## 6. D9 的严格待决状态

产品 `Policy()` 为 version=D9_PENDING、approved=False、profile=None，订单默认 policy_profile=D9_PENDING。不会偷偷采用 A/B。产品退款、改签和已支付订单取消入口拒绝执行，页面说明原因；普通下单、模拟支付、未支付取消和查询不受阻塞。

测试分别显式注入 `TEST_ONLY/P02_STRICT` 与 `TEST_ONLY/CHANGED_REFUND_P01`，并显式批准测试中的 partial_change/further_refund。仅这些测试验证 P01 5/10/20% 边界、一次改签及 3→1→2 流程，不能解释成用户批准。

仍需用户决定：A/B、改签后退款、部分退款后改签、分次继续退票、次数和 P01 手续费/时间边界的产品默认。批准后还需重新做退改 UI 浏览器验收；本轮默认产品退改 UI 只验证禁用边界。

## 7. 自动化结果和原始命令

最终执行记录以 `guarded-suite-isolated/results.json` 和 `old-regression-current/results/results.json` 为准。环境 Python 3.12.14，SQLite/依赖版本见结果 JSON；未安装新依赖。后者是冻结副本；最终新增的V3.9损坏库UI错误分支由新增套件验证，旧核心入口和115个旧测试文件与旧回归快照逐文件一致，详见 `test-source-coverage-v2.json`。

| 范围 | Passed | Failed | Skipped | 说明 |
|---|---:|---:|---:|---|
| 新 V3.9 套件 | 137 | 1 | 0 | 包含原始矩阵冲突 T046，未加 skip/xfail |
| 其中 V1.2.2 执行映射 | 55 | 1 | 0 | 有下述语义资格说明，不等于 56 项完全验收 |
| 原有测试全范围 | 1441 | 11 | 1 | 199 个子测试通过；新 V3.9 套件独立执行 |
| 正式 B 方 103 | — | — | — | BLOCKED，未执行计分；不能写成 103 通过 |

```powershell
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v39-implementation-20261103-130321/run_suite_with_ui_probe.py
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v39-implementation-20261103-130321/run_old_regression.py old-regression-current
node artifacts/runtime/v39-implementation-20261103-130321/browser.js browser-final-r3
```

以上输出已存在，复现时必须换全新目录，不能覆盖。旧回归采用修正 P0 冻结输入 + 当前源码的独立副本，清除凭据环境并禁止外网；`--ignore=tests/v39` 只把新增套件分开计量，未忽略任何开工前测试。ID 比较与阶段七 **full-final** 一致：added/removed/outcome_changes 都为空，11 failed 和唯一 Skip 完全同 ID；不能只比较总数。

该探针包装器调用同一 `scripts/run_v39_tests.run()` 并记录可能的UI初始化调用。最终运行器显式将UI数据库路径指定为本批次，前后检查默认库 SHA：均为 `a429b20be1242a4f6ea81c749df4a7718e6adf5138e973870821e97772c286fe`，没有变化。默认空库创建时间为14:01:08，落在首次新增AppTest批次窗口；单独及全量受监控复跑没有重现默认路径初始化，缺少当时调用栈，**不能确定归因于该测试或其他操作**。因此保留原件和这一来源局限，不清理、不宣称来源已独立证明。通用复现入口仍为 `python -B scripts/run_v39_tests.py --out <全新批次>`。

新增测试包含实际 SQLite/事件/明细/余额断言，而非只比较返回文案。40 个进程请求、8 个并行 SQLite writer 的容量 20 竞争中，20 成功/20 库存不足，held=20、sold=0；该测试私有建单路径专门验证数据库并发，不宣称生产支持多确认 Worker。另以两个独立客户进程访问同一个内存秘密持有者的本机测试 RPC，同 proposal 返回同回执，只创建一个订单/一次 held；租约双进程竞争仅一个获租。

库存/钱守恒、改签三类区间、跨日期/席别/车次/数据版本、退款失败重试、支付超时、技术故障四个点、丢响应重放、秘密重启丢失、准确 TTL 边界、前置权限撤销、整数/half-up 等均有原始结果。

中间失败批次保留：`static-r1` 的两个预期问题（异常记录数与 K5165）及 `final-r1` 的夹具问题。新增联系人校验正确拒绝了本轮新夹具中的 contact=demo/owner=user-A 不一致，已将**新夹具**改为其认证身份，并增加越权反例。旧断言完全未修改。

## 8. 矩阵的来源冲突和覆盖资格

- **T046 FAIL**：原矩阵写 K5165 服务日 2026-11-02 终到 `2026-11-03T23:53+08:00`。固定原件 trip `01000K516502` 终到原始 `30:51:00`，正确换算为 `2026-11-03T06:51+08:00`。原矩阵和该执行预期保留，故失败；另外测试真实原件与 `47:53:00`→次日23:53的通用换算都通过。不得改 GTFS 来迎合矩阵。
- **T031 语义未完全满足**：同 proposal 并发重放应得到同回执，不应伪造第二笔 FAILED 退款。F13 又阻止同 session/action/aggregate 的双 PENDING。当前测试证明只退一次、同回执、再次选已退乘客拒绝；没有声称已证明“两个独立退款提案竞争且额外保留失败 refund_item 行”。页面/Agent 拒绝事件留痕与正式 refund_request 历史是两回事，需独立审查澄清失败尝试模型。
- **T019**：7200/1000/6200 是成功账本汇总的独立单元断言，不是声称 3 个等票价乘客可任意退 1000 分且无手续费。完整服务账本守恒由 T042 等真实流程覆盖。
- **T022**：固定 100 次操作包含 20 次退款后的无效改签尝试；不将被拒绝操作称为成功改签。有效改签另由 T013–T028/T042/T056 覆盖。
- **T029**：强化后的数据库在构造跨 dataset 规则时即拒绝，比到 change 服务再拒绝更早，明细保持原样。
- **T054**：scenario/seed/价格规则/静态 trip ID 可复现；报价、订单和确认能力标识保持随机唯一，不能为满足“IDs”字样重用秘密或能力编号。
- 隔离表 **188 条异常记录、187 个不同班次**，原型有效班次11588、经停107669、车站3169已实查，不用记录条数冒充班次数。

逐 ID 结果、原始期望和资格说明见 `checks-final-matrix.json`。这些限制是 PARTIAL 的组成部分，不能只引用“55 PASS”宣称矩阵已完整验收。

## 9. 浏览器结果与设计

采用已安装 frontend-design 的层级/一致性原则，复用现有深浅设计系统；没有改 CSS、整体 Grid/Flex、旧控件 key 或旧会话变量。新控件均为 `v39_` 命名空间。旧工作空间、四面板和测试控制台继续存在；旧侧栏版本3.7标签保留，不冒充 V3.9 已发布。

Edge **156.0.4314.58** + 现有 Playwright，1600×1100/390×844 × 浅色/深色，最终 **36/36 检查、16 截图**：站点选择、静态车次/经停、模拟报价、未确认时禁执行、确认建单、模拟支付、D9 禁用、自然语言工具查单、横向无溢出。`browser-final-r3/results.json` 保存逐项和错误明细。

- PageError=0；Console Error=8；requestfailed=8；主动拦截外部请求=8。对应 Google 字体图标加载，未将这些错误隐去或宣称 Console 全零。
- 4 个独立浏览器会话各创建并支付一笔本地订单。最终只读数据库核验每笔 PAID、成功账本=净付款=活跃票面+手续费，库存 held=0、sold=4，每段与事件和约束一致，FK 无违规。见 `checks-final-browser.json`。
- 截图：`browser-final-r3/desktop-light-trains.png`、`desktop-dark-paid-order.png`、`mobile-light-paid-order.png`、`mobile-dark-chat.png` 等16份，不使用旧图冒充。
- 未验：实体手机软键盘、真实 LLM 语言泛化、批准后的产品退改 UI 全流程、长时间运行与任意多 Worker；不声称这些已通过。

## 10. Skill 使用、风险与独立审查

| Skill | 实际使用 | 采纳与未采纳 |
|---|---|---|
| eval-audit | 审查矩阵来源、历史失败ID、Mock/真实来源及工具成功/业务成功区别 | 采纳原件冲突保留、逐ID比较、状态断言、来源标记；不引入 LLM Judge，不以设计/哈希核验冒充执行 |
| write-code-eval | 为已知资金、库存、权限、幂等、价格和DDL失败模式写确定性反向检查 | 采纳明确输入/失败条件和实际DB断言；不改103/B/旧测试，不降低判据 |
| frontend-design | 铁路入口复用现有主题和信息层级，确认卡与交易状态突出 | 采用轻量展示组件；不扩展视觉重构或新增字体/依赖 |

P0/验收阻塞：D9 未批准；正式103原独立执行器仍不满足；Harness 独立审查尚未执行。P1：T046 与原件冲突；T031 独立失败尝试要求未完整证明；其余矩阵资格说明需审查。P2：空默认新库创建调用来源尚未独立确定（已冻结且复跑未变化）、新订单表仍有部分技术状态/标识、外部字体图标在离线时出现 Console 错误、实体手机/长期运行未测、旧版本品牌标签保留。

Bridge 仍 BLOCKED，未安装/启用/绕过；两份旧 Bridge 证据缺失原状态保留，不重写冒充。没有自动发起 DSH 模型任务或新增费用，不能伪造 Harness 独立报告。停止本轮演示服务器/测试写入后生成独立 ZIP、源码 SHA manifest、审查任务书；审查者需在独立解压副本中运行，不接触主工作区。详见 `independent-review-task.md`、`review-package.json` 和 ZIP 校验记录。

## 11. 最终交付与下一步

`PROJECT_STATUS.md` 已增量更新，区分设计、代码、开发测试、独立审查和最终验收。最终 `verification-v2.json`、`checks-postdefault-*`、`review-source-manifest-v2.json`、Git差异/状态、全部测试原始日志、浏览器图和审查任务/快照均保留在本批次；V1及中间收尾记录也保留。未提交或推送。

真实模型、Embedding、LangSmith、铁路、支付请求均为 **0**；本机 Streamlit、测试 RPC、Mock SDK/HTTP 替身和被拦截字体请求单独记录，不算真实 API 成功。

下一步须先由用户决定 D9，并确认 T046 原矩阵的更正依据和 T031 失败尝试语义；在已准入的人工转交方式及模型费用许可下执行 Harness 只读独立审查，再由 Codex复核缺陷、修复、复测及正式验收。不能因此自动启用 Bridge，也不能自动 Commit/Push/Merge/Release。
