# Ticket Agent 建单导航与数据库回执真实联合诊断报告

日期：2026-11-11（Asia/Shanghai）。结论：**PARTIAL**。HEAD `8a6ccf36688c9cab803d46ba0bbf652290132e19`，分支 `feat/ticket-agent-v36-stabilization`。未提交、推送或修改生产交易数据库。

## 1. 现场与范围

开工有10个跟踪文件修改及大量R1未跟踪成果，均保留。开工Git状态及6089项现场SHA：`artifacts/runtime/v310-ui-receipt-repro-20261111/opening.json`。本轮只改提案展示/导航、确认后的回执判定与已提交状态的只读核验；Service交易、D9/P01、公开八工具/十一工具、Agent公共契约、Provider选择及Baseline未改变。

原有等待动效和R1成果不是本轮新增，Git总diff不能全归入本轮。原正式103仍BLOCKED，本轮不重新计分。

## 2. 两个根因与历史原件

### A. 导航缺失

旧`web/v39_bridge.py:render`只在右栏顺序渲染待确认内容；右栏前方还有时钟、查询等模块，没有监听有效proposal变化的定位逻辑。`web/scroll_bridge.py`只管理聊天区，不能定位右侧。因此提案已持久化、聊天有预览，并不意味着右栏会展开或滚动到卡片。

修复：`web/proposal_navigation.py`读取原共享Read Model的owned pending_proposals，按真实提案顺序选最新有效提案，打开已有移动信息栏，并用独立一次性DOM滚动请求定位真实ID容器。新提案触发一次，普通rerun不反复抢滚动；不确认任何操作。`web/v39_bridge.py`显示提案ID、操作、实际报价绑定的日期/车次/区间/席别/人数/金额。撤销、过期、确认后的提案由数据库过滤，不冒充待确认。

### B. DATABASE_RECEIPT_NOT_VERIFIED

实际历史索引：`artifacts/runtime/v33/user/web-eb51577f2f13/session-replay.json`；提案`P0e0424544d8548a398b27f267de76475`。原生Service结果是`CONFIRMATION_SECRET_LOST`，不是SQLite提交成功后读取丢失。`target/v39/service.py:235`的confirm检查worker启动epoch及仅保存在内存的Secret；不匹配时将proposal置SECRET_LOST、使确认token失效，然后返回该状态。

旧`web/business_actions.py`在没有order/idempotency成功凭据时，统一追加`DATABASE_RECEIPT_NOT_VERIFIED`，掩盖了具体拒绝原因。

独立只读SQL证据：`historical-database-proof.json`。订单0、hold建单证据0、原生confirm回执0；提案SECRET_LOST，令牌invalid_reason=SECRET_LOST、used_at为空。**有提案和失效标记的数据库写入，没有成功建单、锁座或支付。**没有理由将其包装为成功，也不能恢复失效Secret。

修复保留原安全边界：失效凭据给出具体原因，旧FAILED历史不删；界面禁止确认无法由当前worker持有凭据的提案。Service交易和Secret机制本身不改写。

## 3. 回执四分法与防重

| 凭据 | 页面/操作状态 | 行为 |
|---|---|---|
| 明确拒绝，或事务异常后新快照证明未创建 | FAILED | 保留原错误；回滚异常沿用原抛出语义 |
| Service可能提交、回读失败，或返回成功但缺乏持久凭据 | UNKNOWN | 原回执保留，提示可能已提交；禁止自动重建/支付 |
| 原生幂等回执、owned订单、匹配hold及区间一致 | SUCCEEDED | 以提交后的事实展示PENDING_PAYMENT或PAID |
| 已有订单但hold/归属/库存证据不一致 | PARTIAL / BUSINESS_INCONSISTENT | 停止后续交易，要求核查 |

实现：`web/receipt_verification.py`、`target/v39/receipt_proof.py`、`target/v39/read_model.py`、`web/business_actions.py`。确认仍走原trusted UI→Service→SQLite transaction→commit→readonly read-back。相同提案的UNKNOWN再次确认只回读，不重跑Service；跨提案若前次结果未解明，禁止新的建单或关联交易。原生成功JSON不额外改字段，以维持独立Oracle与幂等回执的逐值匹配。

兼容说明：原已版本化的过期提案评估依赖`error=DATABASE_RECEIPT_NOT_VERIFIED`，本轮保留这个旧适配码，增加准确的`failure_reason=PROPOSAL_EXPIRED`及FAILED，页面明确显示过期；不改旧断言。SECRET_LOST则显示其具体原因。

UNKNOWN/PARTIAL已纳入本地回放与展示映射，不会误走成功动画或因旧六状态字典触发KeyError。公共Trace字段不扩展。

## 4. 真实模型与预算

批次：`UI-RECEIPT-REPRO-20261111`。独立目录：`artifacts/runtime/v310-v311-r1-ui-receipt-20261111/`。

复用已有DeepSeek/Qwen配置；实际HTTP由持久SQLite预算及SQL触发器限定总8、各4、输出≤2048、禁止重试。另在`budget-probe/`验证额度/输出拦截，属于离线预留测试，不能计入真实HTTP。原R1账本不重置。

| 指标 | DeepSeek | Qwen |
|---|---|---|
| HTTP实际发出/200响应 | 4 / 4 | 4 / 4 |
| CREATE_ORDER真实模型提案 | 是 | 是 |
| 工具/参数 | create与pay有效 | 首次误用G7331作trip_id；真实查询纠正后库存与create有效；保留首次错误 |
| 实际建单及Oracle | PENDING_PAYMENT、ACTIVE hold | PENDING_PAYMENT、ACTIVE hold |
| 支付提案来源 | 真实模型 | 原可信页面Registry（不是模型成绩） |
| 支付及Oracle | PAID、唯一支付流水 | PAID、唯一支付流水 |
| 模型多轮完整文字 | 建单与支付均完成 | 建单提案已生成，但下一轮最终文字被额度阻断 |

合计8 HTTP，Prompt=41060、Completion=1221、Total=42281 Token，费用UNKNOWN。无真实铁路、支付、Embedding或LangSmith请求。真实支付金额为0的说法不用于模型成本；模型费用未知，没有记成零。

真实请求上下文包含原静态Adapter/Registry产生的有效报价、路线及合成姓名，首句保留“我要买G7331的票，名字叫三三，二等票”。这不是无前置数据的冷启动全工具链验收；DeepSeek前置只读查询由可信页面准备，不能冒充模型自主查询。Qwen确实自主查询车次、纠正trip_id、查库存，再建单。

原始HTTP响应保存为`raw-http/`的脱敏JSON，不保存认证头/Key；失败的本地预算准入也保留一条记录，它未发出HTTP，不计成第9次网络请求。各HTTP用量见`final-budget.json`，真实模型/工具审计在各case的conversation/traces下。

## 5. 浏览器与数据库证据

最终按实际provider核验的汇总：`verified-live-results.json`。DeepSeek/Qwen各13项有效检查、各26项SQL Oracle不变量通过。两个独立数据库均只有1个订单、1笔成功PAYMENT；建单前订单0，建单后PENDING_PAYMENT/hold ACTIVE且交易0，支付后PAID/hold CONSUMED、金额一致。建单和支付是两个用户分别确认的操作。

真实批次浏览器：原UI、原Conversation、真实模型、真实Registry与Service。第一版等待条件过早、默认Provider识别及React Aria checkbox定位造成脚本失败，原日志全部保留。后续继续原真实proposal时使用**同worker、显式受信测试用户的诊断恢复fixture**，没有重建Secret或改写模型结果；这不能冒充产品无中断端到端链路通过。

真实截图：DeepSeek在`browser-deepseek-continuation-r2/`，Qwen在`browser-live-continuation/`。每个Provider均桌面1600×1100/手机390×844浅深主题。最终有效检查PageError0，Console6/Network6均为主动阻断的既有fonts.gstatic.com图标。

最终UI增量另做无模型浏览器补验：`artifacts/runtime/v310-ui-receipt-repro-20261111/browser-final-offline/`，四规格24项通过，8截图，PageError0，阻断字体Console12/Network12。不把这个离线fixture当成Live模型成绩。

刷新保持原安全契约：显示数据库仍有效的提案及只读说明，**不恢复历史操作授权、Secret或可写会话**；已支付订单恢复后仍PAID，没有新增交易。若要求刷新后可继续确认，需独立设计可信活动会话恢复，不能仅靠URL中的sid授予写权限。该部分仍是验收缺口。

## 6. 确定性验证与完整回归

最终新增用例覆盖正常commit/重复确认、commit后读取失败UNKNOWN及只读核验、失效Secret、过期、拒绝、hold事务回滚、commit后辅助异常、模拟快照及实际新SQLite中的hold异常、支付唯一性、跨提案未解明结果拦截、首读失败、UNKNOWN/PARTIAL AppTest、报价身份及提案摘要。全部用例在独立测试数据库中运行；故障注入没有作用于旧数据库。

最终受影响模块专项 **438 passed / 0 failed / 0 skipped，另2个子测试通过**，其中本轮新增20项。单独故障/展示精选批次51通过，未混算入438。完整命令见`final-targeted-r2-command.json`。最终专项与完整回归数量以本目录`final-targeted-r2.xml`、`regression-result-r6.json`、`regression-id-comparison-r6.json`为准。全量冻结批次为2012 passed / 11 failed / 1 skipped，原11失败和唯一Skip逐ID零增减，不是全绿。此后补强经停dict结果的摘要防护、以及正常order/hold但确认回执仍未核验时保持UNKNOWN的边界，执行最终受影响模块专项，不冒充该全量快照已覆盖所有后续字节。

失败批次保留：r1缺隔离输出目录等产生7失败；全量r2未指定可写pytest temp产生439失败；r3的Windows PYTEST_ADDOPTS路径转义产生208失败；r4为2003/15/1，其中4个RPC通过在原断言下设置进程局部NO_PROXY后复验4/0。r5修正环境得到2010/11/1，随后完整冻结r6为2012/11/1。没有修改断言、skip或xfail规避失败。

## 7. 文件、保护与风险

本轮变更：

- `web/business_actions.py`：回执分类、只读核验、防重复写；
- `web/receipt_verification.py`（新）：分类纯函数；
- `target/v39/read_model.py`、`target/v39/receipt_proof.py`（新）：CREATE订单/hold持久证据；
- `web/proposal_navigation.py`（新）、`web/v39_bridge.py`：真实提案定位、摘要、失效说明；
- `web/conversation.py`、`web/request_motion.py`、`web/business_panels.py`、`web/session_store.py`：UNKNOWN/PARTIAL安全展示与回放；
- `tests/v39/test_ui_receipt_diagnosis.py`（新）：新增验证；
- `PROJECT_STATUS.md`和本报告：增量记录。

5590项此前当前保护基线零差异（旧百炼账本使用用户上一轮批准的结束SHA，不回滚）；本轮6089项现场清单只有声明的源码/文档变化。GTFS ZIP独立核验SHA为`3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`。阶段八static.sqlite、旧业务库、冻结simulation-v391.sqlite、正式103/B快照、原测试及所有旧账本保留。证据见`protected-assets.json`及最终manifest。

仍待解决：Qwen完整最终总结；无中断双模型建单→支付浏览器链路；可信可写刷新恢复；独立审查/用户验收。不得恢复失效Secret、自动重试交易或扩大本批次额度。整体PARTIAL；本批次额度已用完，停止真实调用，不自动开启下一批。

## 8. 最终证据索引

- 离线/保护/Git：`artifacts/runtime/v310-ui-receipt-repro-20261111/`。
- Live/预算/数据库Oracle：`artifacts/runtime/v310-v311-r1-ui-receipt-20261111/`。
- 历史持久状态附加核验：`historical-database-proof-extended.json`，对应报价hold数量0。
- 最终专项：`final-targeted-r2.xml`、`final-targeted-r2.log`、`final-r2-tested-source.json`。
- 全量：`full-r6-results.json`、`full-r6-pytest.log`、`full-r6-junit.xml`；逐ID比较`regression-id-comparison-r6.json`。
- 各失败批次、脚本与环境命令均保留。未将SDK/离线fixture计入8次Live成绩。

全量r6在启动前记录`full-r6-source-manifest.json`。随后变更的3个源码/测试文件在`full-r6-source-reconstruction/`中由最终源码减去已记录后续变更重建，逐字节SHA与启动前manifest一致；重建方式见`full-r6-source-reconstruction.json`，未覆盖原件。最终源码由`final-r2-tested-source.json`绑定438项受影响专项；两个批次的源码身份不混同。
