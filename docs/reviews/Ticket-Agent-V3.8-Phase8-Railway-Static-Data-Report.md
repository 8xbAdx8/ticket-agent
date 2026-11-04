# Ticket Agent V3.8 阶段八：全国铁路静态数据隔离与准入

2026-11-02，Asia/Shanghai。最终状态：**COMPLETE_WITH_RESTRICTIONS**。独立离线原型工程完成，仅限`LOCAL_DEMO_ONLY`，数据权利状态`RIGHTS_REVIEW_PENDING`；不表示完全合规、可公开分发或已接入生产Agent。

## 1. 开工审查

仓库`D:\codexproject\ticket-agent`；分支`feat/ticket-agent-v36-stabilization`，HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`。开工暂存区为空，所有既有未提交源码、视觉修改、Skill、报告保留。读取项目状态、阶段七报告及verification、全国数据评估及原准备目录、原始来源/许可/坐标、Fixture、B方manifest和历史保护清单；重新计算哈希后才开始导入。

证据目录：`artifacts/runtime/railway-static-phase8-20261102-184912/`（下称本轮目录）。下载、网站、API、RailGo、12306、模型和Embedding访问均未执行。没有增加依赖。

| 核验对象 | 实际结果 |
|---|---|
| 原始Release | gtfs-20261101-063437 |
| 固定Commit | adb0852237d7d4a529c9ee4daa9d7d5ebb1b6ab8 |
| 原ZIP大小 | 62,375,903字节 |
| 本轮重算SHA256 | 3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030 |
| feed_version | 20261101 |
| 原2100条Fixture SHA256 | feaec244decbe9ed25f42b5fa7767bb4fb65d76e5313d8b1a52db14826b29217 |
| 原数据准备材料 | 34文件开工冻结并与旧核验清单对应；本轮全部不变 |
| runtime忽略状态 | `git check-ignore`确认被忽略；没有将大型数据放入源码目录 |

没有复制62MB ZIP到新源码目录。原件仍在`artifacts/runtime/railway-dataset-preparation-20261102-gtfs/`；派生SQLite为本轮目录`static.sqlite`，与业务数据库隔离。

## 2. Skills审查与采纳情况

实际读取项目原版`eval-audit`和`write-code-eval`，未修改Skill。

- **eval-audit / Evaluator design，发现风险**：只过滤188条行会让同班次其他停站继续可查。采纳整班次视图隔离、全量集合相等及逐班次API拒绝核验。
- **Error analysis，已有实际证据**：从旧评估的时间、坐标、shape、站名及别名类别出发，不造“质量分”。原188/187清单只作为交叉核验，不作为导入器预填结果。
- **Human review / 无法确认**：来源表匹配不等于地理真实性，来源声明不等于权利清晰；保持未核验状态。
- **Pipeline hygiene，保留边界**：新原型测试与正式103、生产回归分开，不更改历史失败或skip。
- **write-code-eval，采纳**：以原ZIP、各服务日期、原始停站/ID和固定SHA作为输入，设置明确通过/失败条件；测试既验证文案标识，也验证完整原始字段、数据库状态、整班次集合、所有日期和API。
- **未采纳**：LLM Judge、在线验证、猜别名、自动加24小时修复、改正式判据和接生产。理由分别为客观规则不需模型、越出离线授权或缺少可信证据。无LLM Judge，Judge校准不适用；Skill建议本身未计为通过。

完整开工发现及确定性规则表保存在`preimplementation-review.md`。

## 3. 新增文件与隔离架构

所有功能位于`prototypes/railway_static/`，没有改动target、web、services或旧tests。仅用Python标准库。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 独立原型包，不被生产导入 |
| `models.py` | 固定来源身份、静态能力与权利状态封装 |
| `schema.py` | 独立SQLite、原始表、质量/隔离/别名表及有效视图 |
| `importer.py` | 原件/材料校验、CSV全量导入、原字段与raw_json保留 |
| `quality.py` | 主键/外键、坐标来源、质量统计 |
| `quarantine.py` | 独立计算到发矛盾，整班次隔离 |
| `calendar.py` | 明确service日期、exception 1/2和扩展小时计算 |
| `query.py` | 六类SQLite只读查询 |
| `cli.py` | 独立CLI，不启动服务或Agent |
| `tests/test_static.py` | 最终51项本轮专属测试 |
| `README.md` | 命令、服务日含义、数据边界、使用限制 |

另新增本报告，PROJECT_STATUS仅在末尾追加阶段八记录；辅助脚本/日志/数据全部放本轮忽略目录。

独立库包含source_metadata、source_stations、source_trips、source_stop_times、source_calendar_dates、source_shapes、source_routes、source_agency、source_translations、source_feed_info，以及station_coordinate_quality、trip_quarantine和trip_aliases。

原始CSV字段和raw_json保留；arrival_seconds、departure_seconds、sequence_index为独立标准化列。原始字符串不变，未删除任何原始班次或停站。source_metadata记录版本、Release、Commit、SHA、下载回执、导入时间、Asia/Shanghai、许可声明及权利审查状态。

导入器只允许不存在的runtime数据库目标，拒绝现有数据库和业务目录；失败不覆盖或自动清理文件。查询使用SQLite `mode=ro`并验证数据身份。没有网络模块、生产模块导入、UI、订单、库存、支付或换乘推荐逻辑。

## 4. 原件导入与隔离结果

九个GTFS文件全部通过CSV标准解析器导入，包括3,928,885条shape点与6,246条translation记录。没有简单按逗号分割；最终测试逐行比较**九文件的全部原始字段和raw_json**。

| 指标 | 本轮独立计算 |
|---|---:|
| 原始站点ID | 3,169 |
| 原始trip | 11,775 |
| 原始经停 | 109,729 |
| 本站arrival > departure记录 | 188 |
| 唯一隔离trip | 187 |
| 有效trip | 11,588 |
| 被整体排除的经停 | 2,060 |
| 有效经停 | 107,669 |
| 有效视图隔离班次经停泄漏 | 0 |

每条隔离记录都保留trip_id、站点、序号、原始到发时间、ARRIVAL_AFTER_DEPARTURE类型和原件SHA。`trip_quarantine`有188条异常旁证，按DISTINCT trip_id得到187班次；有效视图排除这些班次的**全部**经停。原始两表仍有11,775/109,729行。

测试从原ZIP另行使用独立秒值计算重建188条、187个ID，不借用隔离函数结果。核验原始trip减隔离trip的集合恰为11,588，既没有泄漏隔离班次，也没有错误丢失正常班次；有效经停集合与独立计算完全一致。另逐个验证187班次的trip API和起终站直达查询不返回该班次。未自动修复或补24小时。

## 5. 其他数据质量准入

- **坐标**：26站标`UNVERIFIED_DERIVED`；3,143站标`SOURCE_TABLE_MATCHED`。所有记录`independently_verified=0`，保存原经纬度、来源SHA和原坐标表匹配条目，不自动补坐标、不计算精确距离。
- **Shape**：3,558个空shape_id完整保留，Python/CLI班次结果标`SHAPE_UNAVAILABLE`；仅缺shape不触发隔离，测试比较此类正常班次集合未丢失。
- **同名站**：23组同名不同ID完整保存；搜索返回候选，直达要求stop_id，同名输入返回AMBIGUOUS_STATION，不自动选择。即使站名唯一，也须明确ID。
- **共享坐标**：27组，保持各站身份并记录共享ID关系，不去重。
- **别名**：trip_aliases为空。表结构要求来源、有效期、核验状态与证据引用；没有推测写入G1202/G1203映射，亦未把上轮一致性样本当成充分独立证据。
- **完整性**：六项外键检查、已检查主键/组合键重复均为0。不能由完整性通过推断全国完整或地理准确。

## 6. 日期、跨日与查询语义

calendar_dates逐日确定service是否开行：exception_type=1增加，2移除；移除优先，不使用feed_version推断。真实数据中的全部95个日期都逐日核对有效班次集合；原数据没有type=2，另外使用独立小库验证实际SQL查询对type=2的移除行为，不以小样本替代全量验收。

覆盖日期2026-10-17至2027-01-19。日期边界外返回OUT_OF_COVERAGE；范围内条件无有效班次返回NO_MATCH。已存在但某日不开行的车次也返回NO_MATCH。

所有日期参数均为**始发服务日**，不是中途站所在日历出发日；这是当前CLI/Python接口的明确口径。`47:53:00`保留172,380秒偏移，以2026-11-02为服务日得到2026-11-03T23:53:00+08:00；真实K5165终到`30:51:00`得到次日06:51。未做模24转换。

六类功能：站名搜索、指定ID站点详情、指定日期有效班次、指定trip全程停站、起终ID/服务日直达、数据版本/覆盖/质量元数据。直达匹配明确ID且起点sequence小于终点，按服务日过滤并排除完整隔离班次，结果保留原时刻及实际时区日期时间。

所有结果附data_source=CHINESE_RAILWAY_GTFS、data_type=STATIC_SCHEDULE、real_time=false、availability_available=false、fare_available=false、booking_available=false、版本/SHA和本地使用限制。余票为UNKNOWN、价格null；NO_MATCH不是售罄，也不表示实时接口失败。

## 7. 实际测试与命令

环境复用`.venv-v35`，无新依赖，无浏览器/UI改动，未运行生产完整回归。

实际导入使用本轮脚本调用：

```python
from prototypes.railway_static.importer import import_dataset
import_dataset("artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite")
```

导入28.37秒，独立数据库893,722,624字节；`import-receipt.json`保存全部表统计与元数据。源码未包含该数据库或原件。

实际最终验收命令：

```powershell
.venv-v35\Scripts\python.exe -B artifacts/runtime/railway-static-phase8-20261102-184912/run_tests.py
.venv-v35\Scripts\python.exe -B artifacts/runtime/railway-static-phase8-20261102-184912/export_and_cli.py
```

| 范围 | Passed | Failed/Errors | Skipped |
|---|---:|---:|---:|
| 最终阶段八测试 | 51 | 0/0 | 0 |
| 六类实际CLI入口 | 6 | 0 | 0 |
| 首轮（保留日志） | 49 | 0/0 | 0 |

最终51项约32.50秒；相比首轮补强原字段对比，增加范围内不存在开行日期和信息接口实际质量/覆盖检查。中间50项全通过记录亦保留。没有删除失败测试或增加skip。

测试覆盖全部固定数据、全部95日期、每个隔离班次与其全部经停、坐标/shape/同名/共享/别名、日期移除、扩展小时、直达反向/歧义、来源语义、只读及禁止业务目标。六类CLI使用实际`python -B -m prototypes.railway_static.cli`进程，完整命令和输出哈希见`cli-results.json`。

测试和CLI进程装有拒绝socket连接/DNS/发送/绑定的审计钩子，观察到网络尝试0。原型静态检查没有网络或生产模块导入，导入/查询没有调用外部工具。原始ZIP、Fixture、旧业务/保护内容前后哈希核验不变；独立库测试前后哈希也一致。没有真实模型或铁路请求。

原有1441 passed / 11 failed / 1 skipped、199子测试为上轮历史成绩，本轮未重跑、未修复、未改写。正式103未重新执行计分，仍BLOCKED；不得将新51项称为正式103通过。

## 8. 证据与Git

本轮目录包含：before.json、after.json、source-manifest.json、source-sha256.json、import-receipt.json、quality-report.json、quarantine-manifest.json、coordinate-quality.json、alias-manifest.json、test-results.json、unittest.log、cli-results.json、六类CLI输出、git-verification.json、verification.json、开工审查及辅助脚本。

source-manifest区分新增原型源码与原始外部材料；原始ZIP/SHA/来源文件保留原目录，static.sqlite和质量清单明确为派生文件。verification.json索引最终哈希和结果，原始分析材料没有覆盖。

最终分支/HEAD与开工一致，暂存区为空，`git diff --check`通过。既有非忽略文件仅PROJECT_STATUS增量追加；原34份准备材料、5538项保护文件、阶段七报告/verification及既有截图均不变。原1892清单无差异；4056历史清单仍只有开工已存在的两份API账本差异，本轮无新增差异，不回滚历史追加。B方catalog仍103条、manifest七文件匹配，旧tests及expect均未变。

本轮只新增独立原型、本报告和忽略的运行产物，末尾追加PROJECT_STATUS。没有提交、推送、合并、切换分支或修改原TrainSource、UI、工具、Prompt、业务数据库。

## 9. 限制与后续

工程完成不解除权利限制：仅本地比赛/开发，未确认可公开分发；坐标来源和全国完整性没有官方独立证明。已隔离时间矛盾，没有修复原数据；正常集合保留不等于每条正常数据均经人工验真。别名表仍为空，别名查询覆盖不足；不支持按中途站日历日自动折算搜索、复杂换乘或真实票务能力。

生产版本/UI仍保持原样；V3.8只是本轮独立原型阶段标识，不表示已发布或迁移正式系统。阶段七Snapshot/Live Source、正式103等遗留状态不因本轮完成而升级。

完成后停止，等待用户验收；不得自动接入Agent或开始阶段九。
