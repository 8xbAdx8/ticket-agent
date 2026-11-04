# Ticket Agent V3.9.1 实施与开发验收报告

2026-11-03；本轮批次：`artifacts/runtime/v391-d9-lifecycle-20261103-150639/`。本报告是Codex开发交付，不是Harness独立报告，也不是B方正式103成绩。原V3.9实施报告、V1.2.2原件、原56矩阵和失败批次保持不变。

## 1. 现场与授权

分支feat/ticket-agent-v36-stabilization；HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`。开工暂存区为空、已有11个跟踪文件修改和多项未跟踪成果，与用户所述“此前8个”存在数量差异：在8项之上已有Agent、LangChain和app的V3.9增量；全部按现场冻结，没有还原或覆盖。`before.json`记录6691个现场文件、三个保护组、Git状态和SHA。`baseline-source/`冻结本轮修改前V3.9源码/测试。

用户本次明确批准D9方案B，仅用于V3.9独立本地模拟。没有真实铁路/支付/模型接入，没有Bridge/Harness任务、Git提交推送或正式103重新计分。

## 2. 已实现政策和生命周期

- D9=APPROVED，profile=CHANGED_REFUND_P01，approved=true；可对改签后及部分退款后的剩余ACTIVE乘客退票，可在部分退款后改签剩余乘客。每订单最多一次成功改签，每明细最多一次成功退款。全部有效乘客退款后CANCELLED。
- 原旧P01半偶舍入与新half-up存在真实差异，已在业务修改前记录。旧服务不变；V3.9.1沿用V1.2.2整数分、逐有效明细half-up、>48h5%、24..48h10%、<24h20%。不得混用改签前后价格。
- 乘客当前quote引用+不可变价格快照，已退款乘客保持原金额/原快照；改签只更新ACTIVE乘客，新quote按剩余人数分摊。沿用C06，历史版本存snapshot，不重激活REFUNDED/SUPERSEDED。
- 提案冻结所选明细/价格/费用和quote/hold，确认重新核对；跨P01边界净额变化报PROPOSAL_PRICE_STALE，token与交易回滚，要求新卡确认新金额。
- FAILED退款留下正式请求、明细、失败REFUND交易和分摊；不释放库存，不记成功资金/手续费，不改变有效票面和主状态。同提案重放原回执，新提案可重试；两个独立提案竞争败方也有FAILED正式记录。
- PAYMENT、CHANGE_SUPPLEMENT、CHANGE_REFUND、REFUND仍分离。改签退差不标记乘客已退款、不释放其库存、不消耗其退款名额。
- 复用现有BEGIN IMMEDIATE、单确认Worker租约/内存秘密、事务回滚、资金balances和原子区间交换；没有绕过服务层直写业务库。

## 3. 修改文件及原因

相对于开工现场修改（这些文件中多数原本即未跟踪，不等于本轮从零创建）：

| 文件 | 原因 |
|---|---|
| target/v39/policy.py | 默认产品D9 B及规则读取，保留明确未批准/严格策略的拒绝验证 |
| target/v39/lifecycle.py | 冻结退款、失败尝试、当前价格校验、改签只更新有效明细、退款事件关联 |
| target/v39/service.py | 提案预览、最多两张退款卡、确认重校验、价格冻结；页面读/撤销/审计经服务层 |
| target/v39/store.py | 独立批次路径与migration002身份、原子初始化，拒绝隐式原库升级 |
| web/railway_simulation.py | 批准政策、有效乘客选择、毛额/手续费/净额、正确结果提示、服务层调用、稳定结果/确认容器和独立导航标识 |
| scripts/run_v39_tests.py | 新批次输出、嵌套矩阵SHA、两个默认DB前后保护 |
| tests/v39/fixtures.py | 新migration/quote快照夹具；原V1.2.2重现路径保留 |
| tests/v39/test_confirmation_rpc.py | 支持两个独立提案客户端进程竞争单确认Worker |
| tests/v39/test_lifecycle.py、test_pricing_policy.py | 新默认B下保留显式待批准拒绝和政策单元检查 |
| tests/v39/test_matrix.py | 明确T031独立竞争语义，读取版本化T046预期 |
| PROJECT_STATUS.md | 增量登记本轮事实、风险、后续审查；不删历史章节 |

新增产品/测试文件：`target/v39/policy_profile.json`、`item_prices.py`、`migration_002.sql`；`tests/v39/matrices/v391.json`、`test_v391_lifecycle.py`、`test_v391_constraints.py`。

新增文档：本报告、D9-Decision、P01-Compatibility-Assessment、Architecture-Addendum、T031-Remediation、T046-Revision及Browser-Report（同目录前缀Ticket-Agent-V3.9.1）。本批目录保存验证脚本、manifest、原始日志、数据库探针和审查包；不作为产品功能。

未修改accounting.py/registry.py：复用现有成功交易汇总及统一11工具注册链路。原SYSTEM_PROMPT、八TOOLS、DIMENSIONS、Baseline权限、旧CSS/旧控件key和正式103/B未改。新增key为`v39_navigation`、`v39_receipt`、`v39_confirmation_area`，解决确认提示消失时重绘丢失标签页；旧11失败不作为此次修复范围。

## 4. 数据库与回滚

原schema.sql/hardening.sql保持原SHA；新增002：逐人不可变价格快照、有效quote引用、退款价格引用/事件关联、终态退款明细/账本/分摊完整性，以及退款提案的有限并发。DDL验证为23张STRICT表、20显式索引、44触发器。

新空文件在同一原子初始化中应用001+002和分别校验checksum；002中途故障也回滚至零表。**所有v1库（包括旧空演示库）均拒绝隐式原地升级**，不补造历史价格快照。默认新入口指向simulation-v391.sqlite；本轮只初始化独立测试库，未创建产品默认新库。原空data/v39/simulation.sqlite SHA仍为`a429b20be1242a4f6ea81c749df4a7718e6adf5138e973870821e97772c286fe`。

部署/回滚：保持默认Feature Flag关闭；要演示需显式独立新路径与Flag、重启服务。关闭Flag并重启即可停用，保留新旧库、日志、回执，不逆向删列或删库。已有非空v1数据迁移须另行设计核实价格来源，本轮没有授权自动迁移或把新文件冒充旧数据升级。

## 5. T046与T031

T046直接读取固定GTFS：K5165 `01000K516502`、服务日20261102、终点30:51:00，整数秒独立换算和静态Adapter均为2026-11-03 06:51+08。原23:53预期缺乏该原件依据。只修订新矩阵V3.9.1-r1，原失败和原矩阵不变。详见T046-Revision及gtfs-original-probe.json。

T031用两个独立提案和两个客户端进程竞争单秘密持有者，真实SQLite保留成功及失败请求/明细/交易各一；原同提案重放仍幂等，不伪造失败行。失败注入、原失败回执重放、新提案重试、成功唯一、技术回滚见T031-Remediation、T069–072及额外测试。

## 6. 开发测试结果

环境Python3.12.14、SQLite3.53.1、Streamlit1.65.0；未新增依赖。最终源码测试结果：

| 范围 | Passed | Failed | Skipped | 证据 |
|---|---:|---:|---:|---|
| V3.9/V3.9.1全套 | 164 | 0 | 0 | batch-07/results.json、pytest.log、junit.xml |
| T057–T076补充映射 | 20 | 0 | 0 | 同一JUnit及20份db-probes |
| 原56 ID执行映射（新矩阵r1） | 56 | 0 | 0 | 同一JUnit；存在下述覆盖资格，不能称原全部设计无条件验收 |
| 原有全范围回归 | 1441 | 11 | 1 | old-regression-sealed/results/；199子测试通过 |
| B方正式103 | — | — | — | BLOCKED，未执行/计分 |

```powershell
.\.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v391-d9-lifecycle-20261103-150639/batch-07
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v391-d9-lifecycle-20261103-150639/run_old_regression.py old-regression-sealed
```

以上目录已存在，复现必须改成全新批次/子目录。旧回归使用冻结P0输入+当前源码独立副本、清凭据、阻断外网，`--ignore=tests/v39`只拆分新增套件计量，没有忽略任何旧测试。最终旧回归的added/removed/outcome_changes均空，11失败及唯一skip与开工前最近完整批次逐ID完全相同，未被修复或隐藏。ID和错误原文见checks-final.json及原始results.json。

失败历史：本轮batch-01的117/21/0（夹具新列占位和原T046冲突）完整保留；batch-02为138/0/0，batch-03/04为160/0/0，batch-05/06/07为164/0/0。未加skip/xfail。原V3.9的137/1/0及T046历史失败保持原件。

资金/库存探针：20份db-probes真实读取订单、明细、hold、区段、请求、交易、分摊、事件、价格快照和FK。合成夹具完整生命周期最终paid=8000、credit=7600、fee=400、active_face=0、net=400，全部库存释放。实际静态12区段浏览器例子另有不同金额，不混为同一组数据。

覆盖资格继续保留：T019为账本单元样本，不等于任意票价部分退款服务；T022的100次包括20次已退款后无效改签，不冒充成功改签；T029为更早的数据库拒绝；T054只保证场景/规则等业务输入ID，不重用秘密/能力ID。新生命周期专项补强有效退款/改签与守恒，是否满足旧矩阵更宽语义仍交独立审查判断。

## 7. UI与浏览器

四规格原始结果、截图、逐步实际数据库状态、Console/PageError/requestfailed分别统计见Browser-Report及本批browser目录。失败/中断批次全部保留；没有仅以局部检查数宣称四规格完成。未改旧四面板、开发者工作台或测试控制台。

## 8. Skills与独立性

eval-audit审计发现：旧P01舍入不同、有效价格出处不足、跨费率边界旧卡金额未重验、T031把重放当竞争、T046原件冲突、计数/正式成绩混淆风险。采纳差异先行、版本化矩阵、SQLite状态/账本/库存检查和逐ID比较，不把模型自评/格式校验当业务完成。

write-code-eval用于已知客观失败模式：明确输入、步骤、预期响应、DB/库存/资金变化、故障点；T057–076及附加约束/技术异常测试采用真实事务断言。没有引入LLM Judge、新依赖或降低旧/正式断言；不采用用Mock返回文本代替服务状态的捷径。Skill是审计/编写指导，不是自动证明器，不冒充已提供其不具备的能力。

## 9. 保护、Git与限制

1892组无新增差异。4056与5538组各有同一百炼requests.jsonl追加3735字节：原268991字节前缀SHA完整，当前272726字节SHA `75677a5f9fd4a769fbcc9ce417a94ab70643c44b458c7e6eb09c86899b019e06`；开工SHA `07782195950cd4f2a79851c0d577cf28ac28810aa9666992242400690ec6dcc7`。来源尚未确认，已询问用户，保留原件，**不得标成4056/5538零差异或自行批准新基线**。详见ledger-append-observation.json。当前真实访问归属不能仅由账本追加推断；本轮测试/服务清凭据并阻断外网、没有主动发起真实API。

GTFS ZIP、阶段八DB、2100 Fixture、103/B、旧业务DB、旧空V3.9库、历史报告/矩阵/ZIP和公共契约无本轮变化；此前历史基线差异不重复判作本轮新增。全部SHA、允许源码变化、Git前后状态和差异另存本批检查回执。暂存区为空，HEAD不变，无commit/push/merge/tag/release。

限制：实体手机键盘、真实LLM、长期运行、多独立确认Worker不在本轮验证；单确认Worker部署限制保留。旧11失败/1skip、正式103执行器BLOCKED和Bridge历史缺证据问题仍在；旧空库来源局限原样保留。P01/资金/库存结果需要独立复核，不能以自测代替验收。

## 10. 交付状态

- IMPLEMENTED：D9、本轮生命周期与约束整改已实现。
- TESTED：本地新增全套164/0/0；旧回归1441/11/1，旧失败ID不变；浏览器四规格128/128、20截图，逐步实际数据库核对通过。
- INDEPENDENTLY_REVIEWED：NOT_RUN。只准备新只读源码ZIP、SHA manifest和independent-review-task.md，未自动调用Harness。
- ACCEPTED：PENDING_USER_ACCEPTANCE，不标COMPLETE。
- BLOCKED：保护账本追加来源/新基线待用户确认；独立审查未执行。正式103继续单独BLOCKED，本轮不恢复计分。

下一步由用户确认保护差异并人工转交独立副本；Harness回传只读审查后由Codex复核，再决定整改/最终验收。不自动触发模型费用或Git操作。
