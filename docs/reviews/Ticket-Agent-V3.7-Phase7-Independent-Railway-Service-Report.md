# Ticket Agent V3.7 阶段七续做：独立铁路查询服务报告

更新：2026-11-02（Asia/Shanghai）。本轮整体 **PARTIAL**，达到离线工程交付范围，停止等待用户验收；没有提交、推送、合并或进入其他阶段。

## 1. 状态与验收结论

| 项目 | 本轮结论 | 实际证据与限制 |
|---|---|---|
| Fixture | COMPLETE | 原2100行固定数据和SHA256不变，原阶段七45项全部通过；正式Baseline仍强制Fixture |
| Snapshot | PARTIAL | 没有取得可独立核验的真实快照原件/采集回执；未导入快照，Snapshot SHA256为null |
| Live Adapter | COMPLETE（工程/离线协议层） | 独立服务、三类查询Client、TrainSource余票接线、严格校验、超时/隔离/停服测试完成 |
| Live Source | BLOCKED | 已获用户只读查询授权；真实中转查询取得部分结果，余票接口302，经停站所需余票定位未成功，且来源未独立核验 |
| 交易隔离 | COMPLETE（查询服务边界） | 不连接业务DB、无登录或交易接口；本地HTTP与实际状态核验通过；不代表真实铁路交易验收 |
| 正式103条计分 | BLOCKED | 本轮未恢复配套B执行器，未重新计分，不存在“103条通过”结论 |

**Live Adapter完成不等于Live Source完成。** 真实接口授权已获得，当前阻塞不是待授权。未将合成协议测试结果、Fixture或来源声明当作真实快照。

所有本轮证据位于：`artifacts/runtime/v37-phase7-railway-service-20261102-005728/`（下称证据目录）。入口为`verification.json`；原始运行日志和所有中间失败均保留。

## 2. 开工核查与Skills

现场仓库为`D:\codexproject\ticket-agent`，分支`feat/ticket-agent-v36-stabilization`，HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`。阶段七历史c889b08及后续归档记录作为历史证据，未当作现场HEAD。

读取PROJECT_STATUS、阶段七报告/verification、TrainSource/Snapshot/mock_core、导入/验证脚本、train_data/runtime及旧测试后，在实施前生成`preimplementation-review.md`。工作区原有PROJECT_STATUS、视觉样式/设计源码、frontend-design Skill及两份安装/视觉报告均受保护。开工文件清单2317项、保护清单5538项记录在`before.json`。

按需使用项目原版Skills：

- `eval-audit`：发现旧45项缺少独立HTTP边界、协议污染、并发/熔断覆盖；只检查文案或Schema不能证明数据库未变化；来源自述不能证明真实性；正式103缺执行器不得借本轮测试补称正式成绩。采纳实际HTTP、本地SQL/文件哈希、错误分类与失败ID差分建议。
- `write-code-eval`：把非法输入、十项禁止命令、UNKNOWN/null、来源混淆、重复记录、查询关联、时间戳、限流/熔断、停服和库存/订单/支付/退改不变转换为明确输入、预期及失败条件。规则表在实施前审查，实现在新增85项测试中。
- 未采纳新增LLM Judge、重写B断言、改旧断言/skip、引入新评测依赖、运行上游交易功能和将自签来源升为COMPLETE；这些不适用于客观隔离规则或超出授权/证据。Skill建议本身没有计入测试通过。

## 3. 架构与能力范围

`Ticket Agent → LiveTrainSource → TrainAssistantAdapter → RailwayQueryClient → 127.0.0.1独立FastAPI服务 → 查询Provider`。

服务由独立进程启动/停止，仅监听127.0.0.1。复用现有FastAPI/Uvicorn/HTTPX/requests/Pydantic，没有增加或修改依赖。四个公开HTTP入口：

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/health` | 能力/来源/原站请求计数，明确交易禁用 |
| POST | `/v1/trains/search` | 余票查询 |
| POST | `/v1/trains/route` | 经停站查询 |
| POST | `/v1/trains/transfer-search` | 中转查询 |

无Shell、通用命令、用户指定URL、登录、乘客、订单、候补、锁座、支付、退改接口。route/transfer通过独立HTTP及Client提供；没有增加八个Agent公开工具，也没有声称自然语言Agent已经具备新的经停站/中转工具。

协议版本1.0，包含operation、query、query_id、requested_at、data_as_of、source_type、provider、状态、trains/stops/transfers、来源元数据及结构化错误。所有原有状态保留。未知价格null、未知余票UNKNOWN/null；明确0才是售罄。失败不当作无匹配或售罄，查询成功不表示出票成功。转乘分段日期缺证据时为null，未凭出发日期补造跨日日期。

Adapter只做参数、来源、关联、状态、字段和响应体大小校验、标准化与错误分类，不操作业务DB。既有TrainSource事件旁证保留查询来源及实际run关联。Live车次详情不充当演示库存写入依据。Fixture/Baseline不访问服务；源选择保留既有控件key和会话字段，保存源设置不立即查询。

### 安全与运行限制

localhost主机/对端校验；POST仅JSON，4KB上限，重复key和多余command等字段拒绝；拒绝浏览器Origin、Cookie、Authorization；固定客户端协议头。关闭文档/通用代理入口。最大并发2、每分钟20请求；连续3次失败熔断30秒；客户端默认12秒、零重试（仅可显式配置最多一次连接/超时重试），2MB响应上限。

真实Provider每查询最多6次原站请求、8秒总时限检查及2秒连接/读取超时；默认整个进程12次外部请求预算，本次实际9次。无自动上游重试。原站调用时序受网络库分段超时影响，未宣称硬实时截止。

仅固定HTTPS主机`kyfw.12306.cn`的GET，固定六条公共站名/init/余票/经停/中转路径。禁重定向、Cookie持久化、账号认证、环境代理/netrc/TLS降级；站名缓存处于服务私有临时目录。启动器不导入web.app，不读取Ticket Agent业务库或登录凭证，并移除继承的模型/追踪凭据环境变量。

### 外部源码身份与分发

用户指定项目：`https://github.com/tensor-x/12306-train-assistant`。

- 固定GitHub Commit：`4183eac1302087e5724506e79453a92145053a95`；GitHub签名状态未验证，不称供应链已签名。
- 根目录5个文件已静态审查，含README、SKILL和client.py；上游包含登录/交易能力，未把其SKILL安装进本项目，也未执行CLI/main。
- client.py：198593字节，SHA256 `65dbb61a59efcadb51c0d79529eead54a0d0d1b08abcd66438b6640f628a2a00`；Git blob `4d6a35be13a662160ad40c189bfd6e65d5d470bf`，取得文本后重新计算匹配。
- 原版仅保存在被忽略runtime目录供审查/本地执行。根目录未提供LICENSE，未将外部源码vendor到产品或声称可再分发许可。部署时须另行提供该哈希原件。
- Provider核验原始字节后直接compile到非__main__模块，固定调用query_left_ticket、query_route、query_transfer_ticket及route必要的只读train_no定位；没有参数拼接子命令。
- 出站能力白名单同时约束这些方法的内部网络请求。未把固定SHA等同于安全沙箱；依赖人工静态审查和出站约束，升级SHA需重新审查。

## 4. 修改文件与原因

| 文件 | 原因 |
|---|---|
| `target/railway_protocol.py`（新） | 严格独立查询协议与状态/未知值/来源校验 |
| `target/train_assistant_adapter.py`（新） | loopback Client、三查询方法、TrainSource Adapter与错误处理 |
| `services/__init__.py`、`services/railway_query/__init__.py`（新） | 独立服务包 |
| `services/railway_query/app.py`（新） | 四入口、限流并发熔断、请求边界与来源审计 |
| `services/railway_query/providers.py`（新） | Disabled、显式合成测试、固定SHA真实查询Provider |
| `scripts/railway_query_service.py`（新） | 独立启动器、默认关闭、真实访问显式启用 |
| `tests/test_railway_query_service.py`（新） | 85项协议、权限、安全、实际状态和停服检查 |
| `target/train_source.py` | Live源惰性接线，保留Fixture和原公开工具契约 |
| `web/train_data.py` | 来源、请求/观测时间、UNKNOWN及不可用状态提示 |
| `web/presentation.py` | 车次卡片区分真实只读查询与合成协议测试 |
| `web/user_layout.py` | Live价格未知显示“未提供”，避免显示¥None |
| `PROJECT_STATUS.md` | 增量记录本轮真实状态，不覆盖历史结论 |
| 本报告 | 审查、部署、测试、来源与阻塞交付索引 |

未修改mock_core、train_snapshot、原导入/验证脚本、Provider模型选择、费用授权、SYSTEM_PROMPT、TOOLS、DIMENSIONS、103原始断言、B数据、数据库及依赖。既有视觉文件的未提交差异不是本轮改动。

## 5. 测试执行与证据

使用`.venv-v35` Python3.12.14。`checks.py`复用现有regression_center隔离副本，校验冻结P0 v2包15份Fixture、覆盖当前源码，独立DB/Trace/TEMP，清除真实凭据、禁止外部socket和远程追踪。全部pytest为离线测试或本地合成HTTP，不含真实模型/API得分。

实际最终命令（工作目录项目根目录）：

```powershell
.venv-v35\Scripts\python.exe artifacts/runtime/v37-phase7-railway-service-20261102-005728/checks.py targeted-final
.venv-v35\Scripts\python.exe artifacts/runtime/v37-phase7-railway-service-20261102-005728/checks.py full-final
```

内部执行的完整参数、cwd、源码manifest、开始/结束时间见对应`summary.json`。JUnit、pytest.log、results.json位于每批次`snapshot/ticket-agent/artifacts/runtime/railway-tests/`。

| 范围 | Passed | Failed | Skipped | 说明 |
|---|---:|---:|---:|---|
| 原阶段七45项（targeted-r1） | 45 | 0 | 0 | 双--case参数仅最后一个生效，实际只运行旧45项，不冒称合并测试 |
| 新测试最终targeted-final | 85 | 0 | 0 | 2026-11-02 01:33:51–01:33:55 |
| 全量full-final | 1441 | 11 | 1 | 01:33:51–01:36:24；另199子测试通过，进程exit1 |
| 历史阶段七/视觉基线 | 1356 | 11 | 1 | 原证据保留；本轮新增85通过 |

中间批次完整保留：targeted-r2为72通过/1失败（新测试原先预期过宽泛错误码，修为实际QUERY_CORRELATION_MISMATCH）；r3为77通过/1失败（Windows停服可能超时或拒绝连接，保留SOURCE_UNAVAILABLE核心断言，接受两种底层原因）；r4=78通过、r5=84通过。旧测试、旧断言、skip没有修改。中间完整回归1434/11/1、1440/11/1均不替代最终结果。

最终11个失败及唯一skip与历史阶段七、视觉基线进行逐ID比较，完全相同；原45项在最终全量中也全部通过。完整ID与错误栈在`regression-comparison.json`及最终summary/JUnit中。失败仍集中于原5份DeepSeek/Qwen默认选择、费用授权控件/导航、追问/UI测试；本轮没有判断为环境问题、测试过时或已修复。正式103本轮执行数量为0。

85项包括固定三方法和全部禁止命令、未知值/坏JSON/重复字段与车次/来源/日期/时间戳/查询关联、服务不可用/超时/重试上限、限流/并发/熔断、GET/POST边界与上游路径能力、实际Uvicorn停服、独立SQLite五类表及文件字节不变、Baseline不联网和来源标记。不是只看返回文案，也未取代B独立断言。

## 6. 获授权真实查询

2026-11-02 01:16:26起，对2026-11-03上海虹桥→杭州东进行三次服务操作，零自动重试。详细输入、输出、时间和SHA见`real-service/probe.json`，公网HTTP逐次旁证见`real-service/origin/origin-requests.jsonl`。

| 操作 | 服务结果 | 外部情况 |
|---|---|---|
| left-ticket | SOURCE_UNAVAILABLE | 站名/init成功，leftTicket/queryG返回302，未跟随重定向 |
| route（G7301） | SOURCE_UNAVAILABLE | 必要的余票train_no定位再次302；实际经停接口调用数0 |
| transfer-ticket | AVAILABILITY_UNKNOWN | lcquery/queryG返回200，规范化保留10个真实中转方案；数量/价格/分段日期未知保持未知 |

原站HTTP尝试共 **9次**：站名JS 3次200、init 3次200、余票2次302、中转1次200。不是9次模型请求，也不是三个接口全部成功。模型、Embedding、LangSmith、真实交易请求均0。

没有为绕过302启用Cookie、认证或增加其他接口；未把失败回落到演示库存。查询元数据`source_verified_independently=false`、`real_time=false`、`data_as_of=null`。不接受未经证实的编码价格，故本轮真实价格全部null。

真实试探基于`full-r1/source-manifest.json`时点；后续加强了客户端行关联校验、转乘站名规范化和请求计数隔离，未再次调用真实服务。不能把早期真实响应称为最终版本全部端到端验证。最后版本有85项和全量离线验证。

只保留原站响应体SHA及公开规范化查询结果，未保存可能带订票密串的原站完整响应体。这保护了非必要字段，但也意味着当前材料不是可重新导入的完整原始Snapshot，更不是独立采集证明。Snapshot SHA为null；Fixture和合成响应均未写入Snapshot目录。见`snapshot-materials.json`。

## 7. 浏览器验收

Playwright + 本机Edge156.0.4314.50，1600×1100与390×844，浅/深四规格。独立副本、Mock Agent、本地明确标注的合成查询服务，屏蔽外部请求；浏览器没有进行真实铁路查询。

- 健康服务：44/44检查通过，20张截图。覆盖保存配置不发请求、源标签/UNKNOWN/请求与观测时间、查询前后实际DB字节不变、来源切回Fixture的历史隔离、演示订单及模拟支付四规格流程、输入框和横向溢出。
- 实际停止服务后：24/24通过，4张截图。SOURCE_UNAVAILABLE、不回落Fixture、不创建订单或库存DB；停服态DB未生成，记录null/null而非伪造哈希。
- PageError均0。健康组Console Error16：8条被主动阻断的外部SVG加载、8条原有react-json-view错误。停服组Console Error8：均为外部SVG阻断。两组failedRequests分别8/8，blocked外部请求分别8/8；不能称Console和网络失败为0。
- 截图命名`healthy-{desktop|mobile}-{light|dark}-*.png`及`unavailable-*-source-unavailable.png`，SHA索引见`screenshot-index.json`。JSON中保留console、requestfailed及阻断分别记录。
- `browser-provenance.json`证明当前Web/Client/TrainSource与浏览器副本哈希一致。浏览器之后只修正服务拒绝请求应计0次原站尝试的线程局部计数，并补一项测试；最终离线测试覆盖，未声称浏览器服务副本与最终所有文件完全一致。
- 任务创建的Web、合成和真实服务均已核对进程身份后停止，停止回执保留；未结束其他用户服务。

## 8. 部署/复现（以下为操作说明，不代表又执行了真实查询）

默认无外部访问：

```powershell
.venv-v35\Scripts\python.exe scripts/railway_query_service.py --provider disabled
# 本地协议演示，明确SYNTHETIC_TEST_FIXTURE
.venv-v35\Scripts\python.exe scripts/railway_query_service.py --provider synthetic-test
```

真实Provider须提供固定SHA的外部client.py，并使用一个不存在的新证据目录：

```powershell
.venv-v35\Scripts\python.exe scripts/railway_query_service.py --provider train-assistant --upstream-client <已核验的client.py路径> --allow-live-queries --evidence-directory <新的证据目录>
```

另一个终端启动现有Agent前，按会话选用Live源并显式设置`TICKET_RAILWAY_QUERY_ENABLED=1`、`TICKET_RAILWAY_QUERY_URL=http://127.0.0.1:8540`。测试模式`TICKET_TEST_MODE=1`强制Fixture，配置不得绕过。停止服务用Ctrl+C；服务停止后查询明确不可用。不要在未经调查302原因时直接反复启动真实Provider重试。

## 9. Git与保护核验

最终HEAD及分支与开工一致，暂存区为空；没有提交或推送。`before.json`、`final-git.json`保存前后状态；`implementation.patch`是本轮四份既有源码差异，新文件另由`code-inventory.json`记录；`working-tree.patch`含原有视觉修改，不能全部归因本轮。

本轮保护核验：5538项当前保护内容无变化；原阶段七1892项无变化；历史4056项相对历史manifest仍有开工即存在的两个API账本差异，本轮二者字节不变，不回滚用户此前追加。B方manifest七份文件哈希匹配，103条catalog/原expect和旧测试保持不变。SYSTEM_PROMPT、TOOLS、DIMENSIONS承载文件及Baseline/Override模块本轮均无变化。细目和SHA见`protection-verification.json`。

最终源码与`full-final/source-manifest.json`对照；文档在测试后增量更新，未冒称测试运行时已含新报告。`git diff --check`结果及未跟踪文件逐项清单见最终Git证据。

## 10. 未解决事项与后续材料

1. 提供合法真实快照原件、采集时间/时区、覆盖日期/席别/价格/未知字段说明及独立采集回执；原件与回执必须能区分，来源自述不够。当前无可确认的Snapshot SHA。
2. 调查官方只读余票302及经停站定位失败，在不启用登录、用户Cookie或交易接口的前提下取得稳定公开查询证据；最终版本三方法真实成功及独立核验完成前Live Source保持BLOCKED。
3. 上游无LICENSE，外部源码升级/再分发需另行确认许可和重新审查。精确SHA加载不是OS沙箱。
4. 原11项失败、唯一skip、正式103执行器缺口和已有react-json-view Console问题均保留，需要独立授权任务处理。
5. 未把查询服务车次变为演示交易库存，没有接入真实下单/支付/退改。route/transfer当前仅为独立查询能力；如需新增用户入口/Agent工具，应单独设计并保护公开契约。

本轮不再追加真实请求，不自动进入其他阶段。等待用户验收及上述原件/来源材料。
