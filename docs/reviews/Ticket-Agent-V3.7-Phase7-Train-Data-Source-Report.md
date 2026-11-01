# Ticket Agent V3.7 阶段七：Fixture、快照与数据源隔离

更新时间：2026-11-01T21:12:17.300021+08:00（Asia/Shanghai）。**阶段总体PARTIAL；Fixture COMPLETE；Snapshot PARTIAL（离线适配已验证，缺真实原件）；Live BLOCKED / LIVE_SOURCE_BLOCKED_PENDING_AUTHORIZATION。** 本轮没有接入或查询真实12306数据，没有正式103重计分。

## 1. 目标与交付范围

统一TrainSource查询体系、固定Fixture、严格本地快照验证/导入、真实来源及时间/状态展示、演示事务隔离。沿用当前阶段五/六未提交工作，只增量开发；未提交、推送或进入下一阶段。没有爬虫、登录、验证码、Cookie或真实交易网络实现。

## 2. 实施前架构审查

现场分支`feat/ticket-agent-v36-stabilization`，HEAD `c889b082dd4bd07e3514038a69362b71dd21915c`，暂存区空。先读项目状态、阶段0/6报告与verification、正式103恢复报告及B原目录/expect、数据/双Agent/工具/运行/页面/回归代码；没有`from web.app import ...`。实施前报告`artifacts/runtime/v37-phase7-train-data-source-20261101/preimplementation-review.md`先于应用代码建立。

原seed以固定随机种子20261012、业务today起7天、30高铁+5机票线路生成2100行；日期会滚动，随机数固定不等于绝对日期可复现。原mock_core查询经过_conn，会在缺DB时建库、回收过期锁，不能当纯只读真实数据源。查询、锁座/下单/退改共享演示inventory。未找到有真实采集来源证明的车次快照；政策/RAG缓存、历史Trace和B输出不作为12306原件。

## 3. 三个设计问题

**15条功能准确性用例的数据稳定：** 新增固定2026-10-20至26日2100行版本Fixture，价格/库存/日期和SHA锁定，纯Fixture接口不依赖当前时钟/快照。Baseline及TICKET_TEST_MODE=1强制Fixture，固定业务时钟；原Profile不读Override的规则保持，数据选择独立于模型Override，正式入口仍禁外网。每案例使用隔离演示事务库，原seed不改；45项新增之一逐行核对该固定时钟下seed初始2100行与固定JSON完全一致。普通既有演示会话保留自身业务日期和交易库存，来源明确标注“会话日期与演示库存”，不重置历史库，也不把它当正式重计分。**没有宣称15条/103条B正式通过。**

**快照缺少车次/余票：** 分别返回FOUND、NO_MATCH、NO_AVAILABILITY、AVAILABILITY_UNKNOWN、SNAPSHOT_MISSING、SNAPSHOT_EXPIRED、OUT_OF_COVERAGE、SOURCE_UNAVAILABLE、INVALID_SNAPSHOT、LIVE_DISABLED；Fixture缺失另为FIXTURE_MISSING。声明范围内没有实际记录日期也保守OUT_OF_COVERAGE，不声称近10天完整覆盖。未知价格/库存保留null；不可用工具ok=False，不当售罄/成功，不用Fixture补票。

**真实信息与模拟订单：** Snapshot不把任何余票写入演示DB，也不因查票建立演示库；新候补/锁座/建单/改签拒绝，要求明确切回Fixture并重新查询。此阶段未实现从快照车次映射新演示库存的桥接，避免相同车次号混淆。原演示订单支付、退款/取消仍依归属、确认、状态及幂等规则。界面提示不会向12306提交、真实锁座/扣款，真实查询不代表交易成功。

## 4. 数据源抽象与修改文件

`target/train_source.py`提供TrainSource Protocol、FixtureTrainSource、SnapshotTrainSource、无网络实现的LiveTrainSource。SourceChoice为不可变配置，每轮ContextVar冻结选择及校验时间；Baseline/Test优先覆盖外部选择。保存来源受现有CALL_LOCK保护、不发请求；换源重建Agent、清除旧工具记忆而保留UI历史，页面/Legacy提案绑定来源，不能沿用旧预览。读取配置、Provider切换和渲染不授予外部数据联网权限。

| 文件 | 修改原因 |
|---|---|
| `PROJECT_STATUS.md` | 增量记录当前阶段及证据，保留历史。 |
| `config.py` | 仅TICKET_TEST_MODE=1固定业务时钟，默认时钟保留。 |
| `data/fixtures/train-v1.json` | 新增固定2100行SYNTHETIC_TEST_FIXTURE，原seed/政策/业务库不改。 |
| `docs/reviews/Ticket-Agent-V3.7-Phase7-Train-Data-Source-Report.md` | 阶段七19项交付报告。 |
| `scripts/import_train_snapshot.py` | 本地显式导入CLI，无采集。 |
| `scripts/validate_train_snapshot.py` | 本地验证CLI，无API。 |
| `target/diagnostics.py` | A内部事实核对改读实际已验SHA来源；七维度/B判据不改。 |
| `target/mock_core.py` | 内部查询转TrainSource，保留原Fixture SQL与事务；非Fixture新获取型写操作拒绝。 |
| `target/providers.py` | 仅非Fixture结果摘要和快照购票提示，未知余票不比较/补0；Prompt不改。 |
| `target/reschedule.py` | 非Fixture来源在事务前拒绝新改签，不改费率/差价/归属等规则。 |
| `target/train_snapshot.py` | 严格格式/隐私/来源/SHA验证及不可覆盖原子导入。 |
| `target/train_source.py` | 三源接口、冻结选择、Fixture/Snapshot查询、禁用Live、独立事件/sidecar和写边界。 |
| `tests/test_train_sources.py` | 45项独立客观验证，不修改旧测试。 |
| `web/conversation.py` | 实际来源/错误附近展示与各来源统一输入区安全说明；提案绑定来源。 |
| `web/developer_workspace.py` | 接入既有工作区的来源设置，不另建应用。 |
| `web/presentation.py` | 车次卡片按真实来源元信息标注；未知值保持未知。 |
| `web/runtime.py` | 会话选择、锁定/冻结、清记忆、旧提案来源绑定与Snapshot查询不建演示库。 |
| `web/train_data.py` | 会话来源选择、北京时间/覆盖/状态与演示边界展示。 |
| `web/user_features.py` | 独立查票面板来源/不可用显示，换源清旧选择。 |
| `web/user_layout.py` | 右栏来源文案/推荐票价标签与当前源一致，不改布局CSS。 |

原tools.py权限检查、Schema和web/evidence.py保持字节不变；未改Baseline/Developer Override权限或模型选择/费用授权。原seed、政策、订单费率/差价规则和历史业务库不改。

## 5. Fixture验证

Fixture ID `ticket-trains-v1-20261020`，文件`data/fixtures/train-v1.json`，SHA256 `feaec244decbe9ed25f42b5fa7767bb4fb65d76e5313d8b1a52db14826b29217`；2100行、每天300、7天。文件仅库存，不复制users/订单/锁座身份数据，标记SYNTHETIC_TEST_FIXTURE。固定SQL初始状态全量逐行比较通过；纯Fixture同输入在更换系统业务日期、禁止网络/快照后结果不变；上海→杭州次日二等座查询3条、最高51张、73元；热点零余票保留，不保证永远有票。

Fixture缺失/哈希错误明确停止，无外部替代。Fixture资源随代码包定位，不能随可替换业务根目录丢失。正式/回归时钟固定2026-10-20T12:00:00，整个最终回归设置TICKET_TEST_MODE=1；旧测试自行明确日期的隔离场景仍保留。默认用户演示日期行为保持，sidecar区分固定模板与独立会话事务状态，模板clock不冒称实际采集时间。

## 6. 快照导入与验证

`validate_train_snapshot.py`验证本地JSON，`import_train_snapshot.py`显式导入；不采集网络。严格schema1/重复及未知字段、时间/时区/未来时间、覆盖/观测日期、车次/地点/重复/席别/时刻/车程、非负有限价格/整数库存及null未知、来源分类/声明、隐私和SHA。快照不允许手机号、身份/订单/锁座数据、凭据或邮件等个人信息；未知字段不静默接受。

原件与处理查询结果分开。导入保持输入字节，使用fsync+排他硬链接原子创建文件，原件和独立receipt均不覆盖。receipt故障可留下孤立原件，读端因无有效回执而拒绝；不伪称两文件跨文件事务原子，也不清理历史孤立原件。相同ID/字节重复导入拒绝，新内容用新SHA文件留史。

合成数据只允许SYNTHETIC_TEST_FIXTURE，禁止进入项目data/real；本轮测试与浏览器输入均在独立runtime，**没有真实快照导入**。真实用户原件将来还需明确来源使用权、匹配来源证据SHA。域名/格式和权利声明只是准入信息，不等于已证明真实采集，receipt明确source_verified_independently=false，页面如实说明。故Snapshot状态PARTIAL。

## 7. 来源与时间标注

用户聊天、独立查票面板、车次卡片及右栏都按实际来源显示；Fixture为固定演示/会话库存，Snapshot区分合成测试或用户提供且未独立核验的12306声明。采集时间换算北京时间，原始时间/时区、声明覆盖、实际有记录日期及整文件SHA在结果/事件/独立train-data-events sidecar可追溯。每次真实查询关联run/session/query ID，来源保存有独立选择记录。

公开Trace十字段/工具调用五字段不扩展；默认Fixture工具结果保留原trains/count形状。Snapshot兼容返回原车次字段和data_source元信息；独立sidecar记录实际来源，不能仅靠页面选择推断。旧记录不补造来源。所有模式real_time=false；禁用Live从不显示“实时查询成功”。

## 8. 过期与不可用处理

快照默认有效期3600秒，合法配置区间60—86400秒；验证时钟每轮冻结。过期、缺失、错误SHA/格式、缺回执、覆盖不足、无匹配、售罄及余票未知分开。没有记录的日期不当作已覆盖/无票。不可用结果含error、工具ok=False；Agent stop不等于业务成功。真实工具适配器被调用也不等于进入SQLite事务，写入拒绝另以_conn未进入及库存/订单回查证明。

## 9. 演示交易隔离

两个实际Agent的Snapshot查询不建立演示tickets.db；直接锁座与改签在DB事务前拒绝，页面同样检查来源。切回Fixture后先重新查询；源切换清旧Agent工具记忆、选择卡片和预览，保留原历史。现有支付40、退改59及面板45项通过，订单归属/确认/重复支付/取消规则保持；不新增真实锁座、订单或付款能力。

## 10. Legacy与LangChain兼容

均经原tools.dispatch权限边界调用mock_core.query_tickets，再进入TrainSource。专项在两个真实离线执行器中查询合成快照G9998，检查10/5公共结构、实际源事件和无DB。A内部事实审计从已验SHA快照独立读取权威车次，避免拿演示库误判快照；这是A运行旁证依据更新，不是补写B C5或改正式七维度。旧HTTP Mock不能传递会话源配置，非Fixture会话明确拒绝该路径，不静默跨源；Fixture原HTTP兼容测试保留。

## 11. 工具Schema及历史保护

target/tools.py和web/evidence.py相对开工字节不变；阶段六两处批准逻辑完整保留。SYSTEM_PROMPT/TOOLS/DIMENSIONS AST哈希与阶段六完全一致，未改名/参数/必填/数量、十字段及五字段。1892按本阶段当前获准基线零差异、4056历史零差异，全部旧测试字节不变；B原103/expect/7文件、政策、P2、Trace/数据库/Chroma/账本、阶段五/六报告和72+28截图保持。原阶段六旧清单和批准例外仍留存，不偷换“原旧1892字节全同”。

## 12. Skills审查

使用原版eval-audit检查实际混源、滚动时钟、错误语义、未知库存、审计权威、隐私/来源/在途配置；write-code-eval把已知失败模式转成明确输入、期望和失败条件，45个新增用例实际执行。原Skill SHA保持，无新依赖、Judge、外部框架或远程MCP。发现/风险/采纳/未采纳见skill-audit/code-eval-spec/skills-usage JSON。

未采纳默认爬虫/真实API（缺权限与边界）、LLM Judge（可确定性验证）及旧B替代计分（当前版本仍缺失）。实际发现的旧SDK Fixture路径问题和输入区21px变化均保留原始失败后修复，不改旧断言/增加skip。

## 13. 新增测试与命令

新增`tests/test_train_sources.py` **45 passed / 0 failed / 0 skipped**（包含于完整回归）；涵盖固定2100、双引擎来源、拒绝写、unknown、覆盖/失效/坏JSON/hash/receipt、原子失败、不可覆盖、合成不得入real、Live无socket/Fixture调用、CLI、在途冻结/CALL_LOCK及UI。非B正式测试。

```powershell
$env:PYTHONPATH=(Get-Location).Path
.venv-v35/Scripts/python.exe artifacts/runtime/v37-phase7-train-data-source-20261101/run_checks.py full-r6
node artifacts/runtime/v37-phase7-train-data-source-20261101/browser_acceptance.js browser-r4
```

复用原prepare冻结P0包15文件核验、独立snapshot/DB/Trace/temp；剥离凭据、禁外部socket、本轮测试源固定Fixture。实际内部命令为.venv-v35的python -m pytest tests -q --tb=short --junitxml=独立目录；起止时间、命令、退出码见full-r6/summary.json。数据导入CLI仅在合成临时文件执行，回执不声称真实采集。前序targeted-r1因测试root未放runtime有3失败，修正新测试路径后38通过；full-r1两新增兼容失败后均恢复。所有前序日志/JUnit保留，不覆盖旧产物。另full-r5因统一来源说明未保留“不会真实扣款”连续短语，引发原费用文案2个子断言失败（1356 passed / 13 failed / 1 skipped、197子测试通过）；仅修新文案恢复原安全短语，原断言不改，最终full-r6恢复199子测试通过与原失败集合。

## 14. 完整回归与浏览器

| 范围 | Passed | Failed | Skipped | 子测试通过 |
|---|---:|---:|---:|---:|
| 阶段六历史参考 | 1311 | 11 | 1 | 199 |
| 本轮最终full-r6 | 1356 | 11 | 1 | 199 |
| 本轮新增（已含上行） | 45 | 0 | 0 | — |

原11失败及唯一Skip ID逐项一致、新失败0、旧测试减少0。阶段二40/三59/四45/五9/六60全部保持。旧失败具体ID见regression-comparison.json，不宣称全绿，也未把旧失败一概当测试过时。

Edge 156.0.4314.50与既有Playwright，1600×1100/390×844各深浅色，**120/120真实DOM检查，32张实际PNG，32次离线Mock Agent运行**。核验Fixture/合成Snapshot、北京时间、过期/无匹配/售罄/范围外/unknown、Live拒绝、卡片及演示边界、库存/订单与来源SHA/run关联。四规格均无横向溢出、输入区上沿变化小于3px且底部在视口；r2曾因不同来源说明换行发生21px变化，修为统一真实文案后browser-r4重验通过；未改Grid/Flex、控件key或用force点击/注入session_state通过。

PageError 0，Console error 36，失败请求 8，外部拦截 8。Console明细计数：`{"Failed to load resource: net::ERR_FAILED": 8, "react-json-view error: src property must be a valid json object": 28}`。保留阶段六已知JSON查看组件错误和外部图标拦截，不伪报Console0或把所有错误都归外部资源。8520自建服务已停止，其他用户服务不动。

![桌面浅色合成快照](../../artifacts/runtime/v37-phase7-train-data-source-20261101/desktop-light-00-fresh.png)

![移动深色过期状态](../../artifacts/runtime/v37-phase7-train-data-source-20261101/mobile-dark-01-expired.png)

## 15. 正式103评测阻塞

仍为BLOCKED_WAITING_FOR_ORIGINAL_B_EXECUTOR，0有效计分、103 NOT_RUN_BLOCKED。旧B不支持42条trains_from_tools/C5，本阶段不运行旧judge、不改expect、不补写或反推B判据；45新Fixture/快照测试与历史1311通过均不替代15或103正式成绩。恢复报告/证据和历史七维度原值保留。

## 16. 真实请求数量

12306、真实模型、Embedding、LangSmith、真实锁座/支付/交易请求均**0**。仅localhost健康检查/浏览器连接；既有SDK单测使用离线替身/MockTransport，不能记真实Token或收费。未知余额/Token不补0；历史账本无变化。没有新依赖/包下载或联网接口研究。

## 17. Git与交付文件

分支`feat/ticket-agent-v36-stabilization`，HEAD `c889b082dd4bd07e3514038a69362b71dd21915c`未变，暂存区空，git diff --check通过。源码/测试/配置和保护哈希、Git前后状态及完整清单见verification/source-inventory/git-final-state JSON。更新PROJECT_STATUS固定12节并追加历史记录，未覆盖阶段五/六/103恢复报告。未Commit/Push/Merge/reset/clean/stash/切换分支。

## 18. 剩余风险与状态

Fixture COMPLETE；Snapshot PARTIAL（结构/导入/适配/隔离已离线验证，但没有合法取得的真实快照原件）；Live BLOCKED。来源/授权声明不是数字签名或数据真实性证明，receipt同理；有本地磁盘写权限的操作者不在本轮账户威胁模型内。Windows硬链接原子写依赖文件系统支持，故障保留原件并拒读，不自动修复历史；原HTTP Mock不支持会话Snapshot源。快照记录的票价/余票仍不保证实时可售，coverage声明不代表近10天都完整。旧11失败、既有JSON查看组件错误、固定模拟身份/凭证交回和既有RAG质量边界仍在；实体手机软键盘/真实模型风格/真实来源/实时接口均未新验。

## 19. 后续所需材料与停止

下一步先由用户验收本阶段离线工程；若继续Snapshot验收，需提供合法取得的原始文件、采集时间/覆盖/来源使用权及来源证明，先离线验证/hash导入，不将合成样例冒充真实数据。Live需另行确认合法官方接口、允许用途/字段/限流/网络范围并明确授权后才可实现和联网验证；本轮未证明接口存在或可用，保持禁用。正式103另需B当前版本原件。是否归档提交/推送须另行明确任务；本阶段交付即停止，不自动进入下一阶段。
