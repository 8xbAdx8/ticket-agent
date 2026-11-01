# Ticket Agent V3.7 正式103条用例原始评测执行器恢复报告

更新时间：2026-11-01T20:08:10.337492+08:00（Asia/Shanghai）。最终状态：**BLOCKED**。

阻塞代码：`BLOCKED_WAITING_FOR_ORIGINAL_B_EXECUTOR`。已找回有历史哈希旁证的旧B执行器副本，但**无法验证它是当前103条用例的配套版本**；未执行任何正式计分。103条未运行，不计为103个Skip，更不计为通过。

## 1. 任务边界与现场状态

项目`D:\codexproject\ticket-agent`，分支`feat/ticket-agent-v36-stabilization`，HEAD `c889b082dd4bd07e3514038a69362b71dd21915c`。阶段六已完成离线工程验收且两处限定源码差异获准；阶段五/六工作仍未提交。本次只做来源恢复审查及文档/证据，不改Agent、UI、业务、配置权限、正式输入/断言或旧测试，不进入阶段七。

读取PROJECT_STATUS、阶段六报告及verification、case catalog/内嵌expect、B manifest和历史结果、旧交接/开发记录、scripts/tests、ignored artifacts和本地Git。开工2303文件清单、1892保护清单当前值、4056历史清单及Git状态见`artifacts/runtime/v37-formal-103-regrading-20261101/before.json`；本阶段开工已与阶段六299项源码清单核对一致。

## 2. 搜索范围、命令和限制

- 当前目录：`web/datasets/`、`tests/`、`scripts/`、`docs/`、`cases/`、`artifacts/`（包括ignored的judge/cases副本）；主项目根目录无judge源码。
- Git：60个现有引用（31本地分支、22远端跟踪引用、3历史标签、4 Codex引用），`git log --all` 175条记录、446条reflog记录、4509项可达/重日志对象条目；未fetch或连接GitHub。完整引用和提交清单保存在refs/all-log/reflog/objects日志中，未切分支或更改引用。
- `git fsck --full --no-reflogs --unreachable`只读发现495项不可达对象（2 commit、273 tree、220 blob），未使用lost-found或恢复覆盖。随后`git cat-file --batch-all-objects`枚举4989个本地对象，扫描3033个blob，无大于2MB的未扫描blob；没有发现支持trains_from_tools的候选Python判据源码。只记录命中元信息，不导出无关对象内容。
- 36个现存压缩包只读列目录，未执行/解压覆盖；9包包含旧`b_test_source_manifest.json`等引用条目，**均没有judge源码条目**，不能当成执行器交付。
- 同项目相关副本只读补查`D:\codexproject\ticket-agent-v36-backup-20261028-001`、`D:\codexproject\_release_ticket_agent_20261031`，未找到额外judge/cases候选；旧`E:\3AIproject\agent_test\ticket-agent`不存在。未切换工作副本。
- 普通搜索有424行访问错误；上级权限只读补查仍有1194行访问错误。未修改ACL、删除或清理目录。搜索不是对不可读内容或整台电脑的“绝对不存在”证明；具体stdout/stderr完整保留，不能把rg返回2当作完整成功。

关键实际命令（均用于只读审查，不是执行103）：

```powershell
git for-each-ref --format="%(refname) %(objectname) %(subject)"
git log --all --date=iso-strict --format="%H %ad %an %s"
git reflog --all --date=iso-strict --format="%H %gd %gs"
git rev-list --objects --all --reflog
git fsck --full --no-reflogs --unreachable
git cat-file --batch-all-objects --batch-check="%(objectname) %(objecttype) %(objectsize)"
.venv-v35/Scripts/python.exe artifacts/runtime/v37-formal-103-regrading-20261101/audit_inventory.py
.venv-v35/Scripts/python.exe artifacts/runtime/v37-formal-103-regrading-20261101/audit_provenance.py
```

helper只用标准库、rg和Git，未导入候选执行器或Agent。实际子命令及返回码在inventory/provenance及*.stdout/stderr中；第一次清单helper有dict语法错误并在执行前退出，修正后完成读取，不计为任何测试失败或通过。部分首次手工rg命令使用不存在的猜测文件名/PowerShell字面glob失败，随后按实际路径搜索，未将其当成无源码证明。

## 3. 找到的旧候选与SHA256

找回11组`b-rerun/judge/`，共66个源码文件；六个judge模块在所有副本中哈希相同。5组含101个旧用例，6组含103个旧用例。旧103与当前103的ID、输入及其他字段一致，但42条原expect缺少当前trains_from_tools字段。旧101额外缺X17/X18。

| 候选根目录 | 用例数 | 与当前正式用例的差异 | 身份结论 |
|---|---:|---|---|
| `artifacts/runtime/def06-def07-40a9bb00/b-rerun` | 101 | 缺X17、X18；42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-4d0b328f/b-rerun` | 101 | 缺X17、X18；42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-58c4f33c/b-rerun` | 101 | 缺X17、X18；42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-85046476/b-rerun` | 103 | 42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-9d5ad0dc/b-rerun` | 103 | 42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-a80ce208/b-rerun` | 101 | 缺X17、X18；42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-b74f2bad/b-rerun` | 101 | 缺X17、X18；42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-b9777e03/b-rerun` | 103 | 42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-dbf66c7d/b-rerun` | 103 | 42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-de82adef/b-rerun` | 103 | 42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |
| `artifacts/runtime/def06-def07-f94101c1/b-rerun` | 103 | 42条expect缺trains_from_tools | 旧版B副本有哈希旁证；当前103版本UNVERIFIED |

| 旧源码文件 | 实际SHA256（所有副本相同） |
|---|---|
| `judge/__init__.py` | `06f6d0117ecd321634d72da36614765836b24776e3491297be9bfbcef3b28fc3` |
| `judge/_runner.py` | `c9c3d02f624ee11f10855f91fc861a0bf3c273a8036e7d3d2dd0415e2e1cc9a3` |
| `judge/executor.py` | `a536cb45fd417dd04c20b0a2d75a6a65a3df670997465bc6b1df0c77f7f88c72` |
| `judge/llm_judge.py` | `c6903e59167a0124b934e996b4e8b401036fc6891fb18a6328890b5aea98bba5` |
| `judge/metrics.py` | `c55f6c7e80df27233149938881d4a0656887661cf0e9dbd739e6c55d0efc1b43` |
| `judge/trace_assert.py` | `069014d9e8101fcf43a2a4025a983f8e1f273b5ec46892c0045d13f962a25c37` |

哈希清单：`historical-candidate-protection.json`；旧候选未复制为新正式runner、未修改或执行。

## 4. 来源与版本证据、九项身份问题

历史`b_test_source_manifest.json`共8份，记录B原件与A隔离副本的sha256/copied_sha256；旧6模块实际哈希与清单匹配。清单JSON内容与本地已提交版本一致；checkout采用CRLF、Git blob采用LF，因此部分清单**原始字节SHA不同**，已同时记录工作区SHA/Git blob SHA、换行规范化及解析JSON相等证据，不冒称字节相同。

可核验例：`docs/evidence/deepseek/minimal-20261017/regression/b_test_source_manifest.json`在精确路径首次加入提交`c6def7111cf4cebaabfa4c068417849b7077480b`（2026-10-17）；`docs/evidence/deepseek/def06-def07-20261016/attempt-1/b_test_source_manifest.json`可追到`2a8da2f867e2356f623816a4d08e4fb9bbc3d37e`。完整8份清单、精确路径首次加入提交、follow历史在provenance-audit及manifest-addition日志中。follow可能沿用重命名/复制来源，不能拿其更早日期充当精确路径首次提交。

当前103目录首次加入提交`3ac5d04a1f3a209fa474ae6c4f0024e3218b68b7`（2026-10-25）；B历史manifest称执行日期2026-10-20、被测源码SHA为`0af2712276258fee02573da33688a836738814c6`。这是**被测Agent版本**，不是B执行器的Git提交，不能互换。

| 身份问题 | 审查结论 |
|---|---|
| 确实来自B原始交付？ | 有A当时“原样复制B判据”的历史说明及提交哈希清单，可验证旧副本一致性；未取得B原始当前版本仓库/交付包，当前103配套来源仍UNVERIFIED。 |
| 对应哪个版本？ | 可绑定上述A归档提交和旧6模块SHA；B原始执行器提交未知，当前C5版本未恢复。 |
| 可核验SHA？ | 有，见第3节和8份已提交清单；SHA仅证明文件一致，不自动证明作者或当前适配性。 |
| 使用原始103？ | 六组有旧103，五组仅101；旧103缺当前42条expect中的新字段，不能称完全一致。 |
| 使用原始expect？ | 与当前expect不完整匹配，关键差异为trains_from_tools；不能忽略或自行补写。 |
| 断言独立于Agent？ | trace_assert为独立规则代码，通过契约输出判定，未调用Agent自检；详见第6节。 |
| 会修改历史/正式成绩？ | 原executor会在自身ROOT/results覆写execution.jsonl或execution_langchain.jsonl并写ROOT/artifacts/runtime/btest；在原件目录运行不符合保护要求。本次未运行。 |
| 需要外部API？ | executor默认强制Mock/本地SQLite，标准规则不需要；llm_judge另有可联网分支，不属于此次许可，不运行。外层仍需网络守卫和清空凭据。 |
| 能否隔离运行？ | 旧实现有子进程/逐case库目录，可在新副本隔离；但当前版本身份门禁未满足，未进入正式执行步骤。 |

## 5. 当前103、原始expect及历史结果完整性

原目录`web/datasets/b_v32_20261020/`原manifest列出的7文件全部SHA通过；目录本身103条且ID唯一，当前JSON与HEAD解析内容一致。catalog实际SHA256：`8e8cb2807311c868afe99eb6fb658463b178e33455c791b8752aab50f0adbfdc`。expect内嵌每个case，项目根当前cases/仅A演示及RAG输入，不是原B拆分cases_*.json。

维度分布：功能准确性15、工具调用25、RAG15、多轮12、安全18、边界12、性能6。原engines字段保留，适用Legacy101、LangChain100；此为定义审查，不是新增执行/Skip结果。

`case-integrity.json`保存103条Case ID、完整case/input/expected规范JSON SHA256和来源；输入投影仅排除expect、expected使用原expect，未替换相对日期或改断言。文件SHA与规范JSON SHA含义分别说明。每条actual_output/original_assertion_results/execution_time均null，状态NOT_RUN_BLOCKED。

B原结果中的C5检查Legacy42次、LangChain40次共82次。旧trace_assert只提供C1—C4，42条当前expect的trains_from_tools被静态确认完全不读取。这是执行器版本不匹配的直接证据；历史82次检查记录不能用来反向实现C5评分器。

## 6. 原始断言独立性与方法审查

读取旧executor、_runner、trace_assert和llm_judge源码。旧trace_assert根据外部原expect、契约turns/steps/calls/reply判定：R1漏调用、R2禁用工具、R3参数子集和末次参数、R4先后顺序、R5重复调用、R6终止状态、C1关键词/任一关键词、C2禁词、C3政策doc_id、C4耗时及ENTRY异常；亦保留原allow_rules与must_call_ok规则。不只是JSON格式检查或工具次数测试。

trace_assert导入config用于相对日期，未导入target.agent/providers或Agent的自评。_runner调用Agent作为被测对象，负责stdin/JSON输出、fault/mutation setup和多会话切换；这不等于拿Agent内部judgement替代B判据。标准executor不调用llm_judge；独立llm_judge有启发式/真实模型评分分支，未获授权且不作为正式断言替代。

局限：当前旧规则缺C5，不能据通用R1—R6判“当前103完整覆盖”。旧executor对未知expect字段不报错，因此直接混用新catalog可能产生虚假的高通过率。未通过修改旧judge、删除字段、增加skip或从101/101与100/100历史结果推导新标准来规避。

本次采用`eval-audit`本地审查方法，发现/风险/证据/处理见eval-audit-findings.json。`write-code-eval`未用于写新评分器，因为本任务禁止重造原断言；没有LLM Judge调用、下载新框架或新依赖。

## 7. 执行门禁与最终状态

**BLOCKED / BLOCKED_WAITING_FOR_ORIGINAL_B_EXECUTOR**。原因是与当前103完整expect对应的B原始执行器无法确认，不是Agent正式断言失败，也不是把旧11项失败改判。

未建立实际评测副本、未导入或运行旧judge、未运行pytest完整回归、未重新调用阶段六“核验103配置”按钮、未改写正式结果库。没有有效重计分命令、执行日志或新PASS/FAIL成绩可交付。

| 本次正式计分项目 | 结果 |
|---|---|
| 有效计分用例 | 0 |
| 未运行（NOT_RUN_BLOCKED） | 103 |
| PASS / FAIL / SKIP | 未产生（JSON中均null，非0/0/103） |
| 正式断言失败原因 | 不适用，未执行；阻塞原因是版本/原件缺失 |
| 新真实模型/Embedding/LangSmith/12306请求 | 0 |

历史1311 passed / 11 failed / 1 skipped、199子测试是阶段六A离线回归，原11失败/唯一Skip保留；不拿它替代此次B正式计分。阶段六COMPLETE与本次BLOCKED可以同时成立。

## 8. 环境、历史命令与恢复条件

现场解释器：`D:\codexproject\ticket-agent\.venv-v35\Scripts\python.exe`，Python3.12.14；安装版本及当前requirements-v35-lock SHA在environment.json。旧A隔离脚本使用.venv-deepseek/.venv-v3/.venv及B外部目录；尚未恢复B原始环境锁、固定时钟策略和原执行器Git版本，不能假定与当前环境相同。

历史命令只作为来源线索，**本次未执行**：

```powershell
python -m judge.executor
python -m judge.executor --id F03
python -m judge.metrics
python scripts/verify_v3_def06_def07_offline.py --b-root <B原始目录> --baseline <旧保护清单> --out <独立输出目录>
```

旧verify脚本会同时跑A完整测试、B多个任务并复制旧target/data，不能直接把它当本轮最小正式执行入口。将来需在不修改原断言/被测业务的前提下评审隔离外壳：固定Baseline/时钟/fixture/政策、独立DB/Trace、剥离凭据、禁外网和真实API、输出完整原始Worker结果及逐规则断言。取得原件并验证后才讨论实际命令，不能把计划命令写为已运行。

## 9. 103条逐项未运行登记

本表不是执行结果；完整input/expected/case SHA在case-integrity.json。没有实际输出或断言失败可填，不伪造PASS/FAIL/SKIP。

| Case ID | 维度 | 本次状态 | 原因 |
|---|---|---|---|
| E01 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E02 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E03 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E04 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E05 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E06 | 边界 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| E07 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E08 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E09 | 边界 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| E10 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E11 | 边界 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| E12 | 边界 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F01 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F02 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| F03 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| F04 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F05 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F06 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F07 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| F08 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| F09 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F10 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F11 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F12 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| F13 | 功能准确性 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| F14 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| F15 | 功能准确性 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| M01 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M02 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M03 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M04 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M05 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M06 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M07 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M08 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M09 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M10 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M11 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| M12 | 多轮 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| P01 | 性能 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| P02 | 性能 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| P03 | 性能 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| P04 | 性能 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| P05 | 性能 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| P06 | 性能 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| R01 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R02 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R03 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R04 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R05 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R06 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R07 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R08 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R09 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R10 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R11 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R12 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R13 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R14 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| R15 | RAG | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X01 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X02 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X03 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X04 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X05 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X06 | 安全 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| X07 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X08 | 安全 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| X09 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X10 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X11 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X12 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X13 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X14 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X15 | 安全 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| X16 | 安全 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| X17 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| X18 | 安全 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T01 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T02 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T03 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T04 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T05 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T06 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T07 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T08 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T09 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T10 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T11 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T12 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T13 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T14 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T15 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T16 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T17 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T18 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T19 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T20 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T21 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T22 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T23 | 工具调用 | NOT_RUN_BLOCKED | 缺C5配套实现 |
| T24 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |
| T25 | 工具调用 | NOT_RUN_BLOCKED | 完整版本身份未通过准入 |

## 10. 缺少的B方材料

请队长或B方提供与2026-10-20正式103目录完全对应的原始交付：

1. 完整`judge/`（特别是支持trains_from_tools/C5的trace_assert.py、传递权威列车证据的_runner.py、executor.py及metrics.py等真实依赖模块），保留原文件字节。
2. 原始`cases/cases_*.json`及expect，配套变更说明/适用引擎规则；与当前catalog逐条无损对应，不能为本轮临时补写/减弱。
3. B执行器仓库的准确Commit/Tag或原始ZIP与SHA256、来源交付记录；被测Agent的0af2712不能替代执行器版本。
4. 原始运行命令、Python和依赖锁、种子/政策版本、相对日期/固定时钟、每case setup/fault/mutation的执行说明，以及JUnit/JSON/CSV原运行记录（如有）。
5. 确认正式结果输出路径和旧执行器副作用，以便只在新副本运行、保留完整Worker输出和日志、不覆写任何历史成绩。

不请求API Key、密码或新联网授权。若原件确实无法提供，必须另行明确任务授权设计新的A评测体系，并保持非B正式归属；本任务不执行该替代方案。

## 11. Git与保护核验

本任务应用/配置/测试源码修改0；Git可见净改动仅PROJECT_STATUS.md与本报告，保留原全部未提交工作。HEAD/分支不变、暂存区空、git diff --check通过；未Commit/Push/Merge，未reset/clean/stash/切换分支。

1892保护文件相对本任务开工当前基线零差异（包含阶段六已批准两源码的当前SHA），4056获准历史基线零差异；仍保留原阶段六1892旧清单及两处批准例外，不冒称原旧SHA均相同。正式103/expect/B7文件、旧测试、SYSTEM_PROMPT、TOOLS、DIMENSIONS、阶段五/六299源码以及阶段六报告/verification、72+28截图、账本/Trace/数据库均保持开工值。候选旧B源码及cases也只读，另有哈希锁。

最终verification.json给出逐文件比较、Git前后状态、原清单/阶段六批准引用和报告/状态SHA。此次只新增审查产物、报告与项目状态更新，不触碰阶段七或权限实现。

## 12. 证据索引与停止

- `artifacts/runtime/v37-formal-103-regrading-20261101/before.json`：开工Git/文件/保护基线。
- `inventory.json`及refs/all-log/reflog/objects/history-paths/rg stdout/stderr：完整搜索范围与返回码。
- `provenance-audit.json`、manifest-addition日志、all-local-object-scan.json：提交/哈希/版本及对象搜索证据。
- `case-version-differences.json`：42条expect差异；case-integrity.json：103条原始哈希及NOT_RUN登记。
- `execution-gate.json`：BLOCKED门禁，明确没有正式执行。
- `environment.json`、eval-audit-findings.json、historical-candidate-protection.json：环境、独立性审计与旧候选保护。
- `verification.json`、final-git-check.json：最终保护/修改范围和Git证据。

审查完成即停止，等待B当前103配套原始执行器。未产生新正式成绩，不能将BLOCKED包装为PASS。
