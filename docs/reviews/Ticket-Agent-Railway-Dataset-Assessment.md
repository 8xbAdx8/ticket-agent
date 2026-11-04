# Ticket Agent 比赛版全国铁路静态数据评估

评估日期：2026-11-02，Asia/Shanghai。结论：**可作为有条件使用的第三方静态比赛候选数据；不建议直接当作全国完整、无缺陷、官方核验的答案库。** 已完成原件下载、静态解析、质量评估及少量在线比对，没有接入产品或更改正式测试。

快照包含3,169个站点ID、11,775条班次和109,729条经停记录。主键及已检查外键可关联，但有188条到发时间矛盾、26座车站缺少原始坐标依据，且复车次别名信息有损。授权链和全国完整性仍待确认。进入下一阶段前，应先制定异常隔离与署名方案，并取得用户确认。

## 1. 数据源、版本和原件

| 项目 | 本轮取得的证据 |
|---|---|
| 仓库 | [wensimehrp/chinese-railway-gtfs](https://github.com/wensimehrp/chinese-railway-gtfs) |
| 下载前main最新Commit | `adb0852237d7d4a529c9ee4daa9d7d5ebb1b6ab8`，2026-10-13 18:08:37 UTC；GitHub标记签名verified |
| 最新Release | [gtfs-20261101-063437](https://github.com/wensimehrp/chinese-railway-gtfs/releases/tag/gtfs-20261101-063437)，2026-11-01 14:34:43北京时间发布 |
| Release标签对应代码 | 同上述Commit，已另取Git ref核对；代码日期不等于数据采集日期 |
| GTFS资产 | `output_gtfs.zip`，62,375,903字节；另有独立`lines.json`资产，本轮未下载后者 |
| SHA256 | `3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`，本地实算与Release digest一致 |
| 下载时间 | 2026-11-02 18:19:00–18:30:14北京时间，HTTP 200 |
| feed_version | `20261101` |
| 时区 | agency为`Asia/Shanghai`；跨境特殊时区未独立核验 |

原件及分析证据目录：[`artifacts/runtime/railway-dataset-preparation-20261102-gtfs/`](../../artifacts/runtime/railway-dataset-preparation-20261102-gtfs/README.md)。原ZIP未修改；SQLite仅为这个新目录内的分析数据库，不是业务SQLite。

固定版本README声明时刻来自RailGo-Parser，坐标来自OpenStreetMap，提供国铁范围的时刻与路线走向，不提供票价等信息。[来源说明](https://github.com/wensimehrp/chinese-railway-gtfs/blob/adb0852237d7d4a529c9ee4daa9d7d5ebb1b6ab8/README.md)

本轮背景审查的Parser HEAD是`65129548df7307160eab4c7f77c010bd0e4b69ed`，其README声明核心来源12306、95306。**未取得该Release实际采集时使用的Parser版本和逐记录原始采集回执**，不能将当前Parser HEAD当作Release实际依赖版本。[Parser资料](https://github.com/RailGoApps/RailGo-Parser/tree/65129548df7307160eab4c7f77c010bd0e4b69ed)

仅静态阅读上游README、LICENSE、生成器、CI及坐标表，没有运行上游爬虫、生成器或安装脚本，没有请求12306/95306，也未绕过任何访问限制。

## 2. 授权与使用限制

- GTFS仓库声明CC BY 4.0，原许可文本副本保存在`source/LICENSE`。公开使用应保留作者wensimehrp (Jeremy Gao)、源链接、许可与免责声明，并注明修改。GitHub签名和SHA证明版本/字节一致，不证明数据准确性或所有上游授权。[固定版本LICENSE](https://github.com/wensimehrp/chinese-railway-gtfs/blob/adb0852237d7d4a529c9ee4daa9d7d5ebb1b6ab8/LICENSE)
- OSM数据涉及ODbL及署名要求，派生数据库可能涉及相同许可义务。当前未取得坐标逐项提取来源与权利说明，不能断言GTFS整体CC BY声明已解决全部OSM授权问题。[OSM版权说明](https://www.openstreetmap.org/copyright)
- 当前Parser根目录未见LICENSE；“公开数据”声明不等于完整再许可证明。代码许可、采集权限和数据再分发权须分别确认。没有声称本轮已完全合规。
- RailGo API文档当前不要求Key，允许非商业用途，但禁止商业使用、公开接口中转；公开展示其信息需显著标注来源和链接。已启用自动限速，未给出可引用的固定QPS。本轮只做5次间隔至少5秒的查询，无重试、无全量抓取、无代理中转服务。[RailGo使用限制](https://api.railgo.dev/)
- API使用条件适用于本轮在线比对，不能自行推断其覆盖或取代GTFS/Parser/OSM的全部权利关系。个人学习、非商业比赛目的也不能自动消除上游授权风险。

建议比赛展示署名：`China Railway Timetable GTFS — wensimehrp (Jeremy Gao), CC BY 4.0`并链接源项目；坐标同时注明`© OpenStreetMap contributors`及ODbL；引用在线比对结果时注明RailGo并链接其文档。不声称官方背书。公开分发数据或上线前建议向发布者确认上游权利边界；本轮未代用户联系或发送消息。

## 3. 实际文件与统计

ZIP CRC检查通过，共9个GTFS文本文件；没有任意解压到现有数据目录。下表数量按实际CSV行计算，并对核心表另用独立CSV扫描复核。

| 文件 | 数据行 | 空单元格 | 完全重复行 | 主键/组合键重复行 |
|---|---:|---:|---:|---:|
| agency.txt | 1 | 0 | 0 | 0 |
| stops.txt | 3,169 | 0 | 0 | 0 |
| routes.txt | 11,775 | 0 | 0 | 0 |
| trips.txt | 11,775 | 3,558 | 0 | 0 |
| stop_times.txt | 109,729 | 0 | 0 | 0 |
| calendar_dates.txt | 21,233 | 0 | 0 | 0 |
| shapes.txt | 3,928,885 | 0 | 0 | 0 |
| translations.txt | 6,246 | 0 | 0 | 0 |
| feed_info.txt | 1 | 0 | 0 | 不另定义业务键；仅1行 |

3,558个空单元格全部是可选`trips.shape_id`，占班次30.22%；意味着这些班次没有形状引用，不能据此绘制完整线路轨迹。已检查的核心必需列缺失0、核心必需字段空值0、CSV字段数异常行0。总空值不是“3,558条坏班次”。

`calendar.txt`实际缺省。该源使用`calendar_dates.txt`的`exception_type=1`逐日列举开行日期；这符合GTFS允许的日历形式，不算缺文件缺陷。[GTFS参考](https://gtfs.org/documentation/schedule/reference/)

外键检查：`trips.route_id → routes`、`routes.agency_id → agency`、`stop_times.trip_id → trips`、`stop_times.stop_id → stops`、`trips.service_id → calendar_dates`及非空`trips.shape_id → shapes`，无效引用均为0。所有班次至少2停站，站点未被任何经停引用的数量为0。未运行第三方完整GTFS认证工具，不将这些检查称为全规范认证。

### 覆盖日期与过期口径

| 指标 | 结果 |
|---|---:|
| 全源最早/最晚服务日期 | 2026-10-17 / 2027-01-19 |
| 有记录的不同日期 | 95 |
| service_id数量 | 516 |
| 2026-11-02开行的trip数量 | 11,006 |
| 全部运行日已早于2026-11-02的trip数量 | 0 |
| 历史服务日期行（早于2026-11-02） | 4,374 |
| 无效日历日期行 | 0 |

过期班次按各trip所属service的**最后开行日期**判断，并用SQL独立复核；历史日期行不等于过期班次数。其余769条班次当日未开行，不代表过期。全源最大覆盖日不代表每一条车次都开到2027-01-19，查询必须按具体service过滤。

范围是第三方声明的国铁范围，并非包含全国所有城市轨道/地方铁路的通用数据集。缺少官方完整车次和站点分母，**不能给出全国覆盖率，也不能保证无成片遗漏**。

## 4. ID、复车次、跨线与车站编码

- `trip_id`采用内部长ID，例如G1为`24000000G10L`；`trip_short_name`是公开车次号。当前11,775个trip对应11,775个不同公开标签，未发现同标签多trip版本；这不证明内部ID在下一运行图仍稳定。
- 本源全部`route_id == trip_short_name`。因此11,775条route是车次标签维度，**不是11,775条物理铁路线路**；不能直接据此统计跨越了多少条京沪、沪昆等线路。跨线属性需另外的线路映射。
- GTFS中带“/”的复车次标签为0。真实样本显示G1202的RailGo `numberFull`是G1202/G1203，且停站段的trainCode确有变化；GTFS仅保留一个公开标签和全程内部ID，没有独立的复车次别名字段或逐站车次号字段。不能由“复标签0”推出“全国没有复车次”。按G1203等别名查找需要后续另行、可追溯地补映射。
- 精确`stop_id`重复0，但有23组同名不同ID，例如哈尔滨BAI/HBB、重庆西CXW/WWI；不应按站名直接合并或直接认定同名记录错误。需保留原ID并核实业务语义。
- 含转义电报码`UUH/`；本轮保留原值，未擅自去斜杠合并。该快照对去斜杠后的编码未发现碰撞，不代表其他版本不会碰撞。RailGo文档专门说明徐州东/雅周共码例外。[编码说明](https://api.railgo.dev/)

## 5. 数据质量问题

| 级别 | 发现 | 影响与建议 |
|---|---|---|
| 高 | 188条本站arrival > departure，涉及187个trip | 占经停记录约0.171%、班次约1.588%；会产生负停站时长，不能直接用于可靠换乘/时刻推理。建议先隔离187个trip，并请求上游核查，保留原件 |
| 高 | 复车次别名/分段车次号未完整保留 | 按别名查找可能漏车；不能简单把车次号当唯一长期实体ID |
| 中 | 26个站点在固定版coordinates.csv中无同名来源 | 生成器会用邻站插值/端点延用；有数值不等于真实测绘位置，避免用于精确距离或定位答案 |
| 中 | 3,558个trip无shape_id | 约30.22%的班次没有可引用轨迹，地图展示应标记缺失 |
| 中 | 23组同名不同站ID、27组共享坐标 | 需要保留标识与歧义，不自动删重；共享坐标可能来自同名记录或插值，不能全部算错误 |
| 高（验收范围） | 未有全国分母/独立官方比对/完整授权链 | 不可宣称全国完整、官方准确或完全合规 |

### 时间异常的证据

1,066个trip有合法超过24小时的时刻，最大`71:58:00`。分钟/秒或时间格式异常0、按序下一站到达早于前站出发0、停站序号不递增0、序号跳号0。这些通过项**没有抵消**本站到发顺序的188条矛盾。

188条中110条在终点、78条在中途站。例如：

- K7066，内部ID`02000K706610`，JMB第9停：到达47:53:00，出发24:15:00。
- K1024，内部ID`11000K10240A`，BJP第13停：到达37:06:00，出发37:00:00。

部分异常疑似与跨午夜日偏移或上游原始时刻有关，但目前未取得逐项原始证据，不能统一认定根因；也不能自动加24小时“修好”。完整188项见`quality-crosscheck.json`，原件未改。

### 坐标验证边界

站点经纬度缺失、零值及超出全球经纬度范围均为0，shape点范围异常0；有唯一同名来源的坐标与固定coordinates.csv在1e-6度容差内一致。26个未覆盖站点包括安康西、伊春西、成都龙泉驿等，完整清单另存。

README声明站点为WGS84；静态生成器还对线路shape做GCJ-02→WGS84转换，并对部分站点插值。本轮只验证声明、数值范围和源表一致性，**未独立验证坐标系或插值地理准确性**。

## 6. RailGo抽样比对

遵循官方[V1车次查询](https://api.railgo.dev/366464494e0)和[车站查询](https://api.railgo.dev/366547236e0)，请求实际数据服务`data.railgo.zenglingkun.cn`。本轮5次GET全部HTTP200，0重试，最短间隔5.133895秒，无全量抓取。请求、时间、原始响应与SHA256保存在`railgo-samples/`。

| 样本 | GTFS内容 | 比对结果 |
|---|---|---|
| G1 | 北京南06:30 → 上海虹桥11:24，7停 | 车次、始终站、全部站名/电报码/到发时刻一致 |
| K5165 | 哈尔滨20:20 → 黑河次日06:51，5停 | 全部停站与到发一致；GTFS终到30:51:00正确对应次日 |
| G1202 | 哈尔滨西09:17 → 上海虹桥21:50，22停 | 全部停站和到发一致；RailGo另给出G1203别名及分段变化，GTFS未完整保存 |
| VNP | 北京南 | 站名与电报码一致 |
| AOH | 上海虹桥 | 站名与电报码一致 |

三列车都在双方返回的2026-11-02开行日期集合内，分别有90、38、90个共同运行日。V1不指定查询日，因此保留了各自rundays，并以共同日期限定解释，没有拿不同运行图版本直接判错。该小样本不能推算全量准确率。

GTFS使用RailGo-Parser，与RailGo查询可能共享上游，以上是**一致性比对，不是独立官方真实性验证**。未进行12306人工核验，没有官方截图或人工验收成绩。官方网址`https://www.12306.cn/`仅作为后续人工核验入口，本轮自动请求数0。

## 7. 对比赛的适用性与下一阶段建议

建议**有条件进入独立离线数据原型设计**，先由用户确认：固定原ZIP和SHA，按日期取有效班次，单独标记/排除已检出的时刻矛盾，明确插值坐标与缺失shape，设计可追溯别名表，并在展示中保留第三方静态来源/版本/许可提示。异常隔离尚未实施，不应把这个建议当成已清洗完成。

不建议直接进入权威答案库或公开数据服务：全国完整性、异常根因、坐标精度、上游权利边界和官方人工比对均有缺口。公开分发前应确认OSM及其他上游义务。本轮没有接入/转换产品Snapshot，阶段七Snapshot PARTIAL、Live Source BLOCKED及正式103 BLOCKED的结论保持不变。

静态时刻不提供真实余票、票价、出票或支付。不得由“列车开行”推断“有票”，也不能将这份数据替换正式103条的固定Fixture、原expect或B方判据。

## 8. 可复核证据与执行

证据目录均以`artifacts/runtime/railway-dataset-preparation-20261102-gtfs/`为前缀：

- `download-receipt.json`、`commit.json`、`tag.json`、`release.json`：身份、下载回执与原件摘要。
- `source/LICENSE`、`source/README.md`、`source/gen_gtfs.py`、`source/.github_workflows_update.yml`、`source/coordinates.csv`：固定版本静态审查材料。
- `assess.py`、`quality-results.json`：九文件行数、空值、重复键、外键、运行日和时间检查。
- `verify_assessment.py`、`quality-crosscheck.json`：独立CSV/SQL复核、全部到发矛盾及缺失来源坐标清单。
- `sample_railgo.py`、`sample_compound.py`、`compare_samples.py`、`railgo-comparison.json`：受限抽样及逐停站比对。
- `SHA256SUMS.txt`：交付数据/源码副本/结果清单摘要；不把本地摘要当作独立真实性证明。
- `before.json`、`final-verification.json`：Git、所有既有非忽略文件和5538项保护内容前后核验。

实际命令均使用`.venv-v35\Scripts\python.exe`，按上述目录依次执行`download.py`、`assess.py`、`verify_assessment.py`、`sample_railgo.py`、`sample_compound.py`、`compare_samples.py`。未运行产品完整回归，未新增依赖；这里的检查不是103条正式评分。

使用`analyze-data-quality`和`build-report` Skills组织数据粒度、完整性、关联、时效、异常及证据交付。没有把Skill建议当成已验证事实。

## 9. 工程保护与停止状态

开工和结束分支`feat/ticket-agent-v36-stabilization`，HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`。既有视觉、阶段七续做、Skill及其他未提交工作保留。

本轮仅新增此报告、增量更新PROJECT_STATUS，以及在被忽略的独立准备目录写入原件与分析产物。产品源码、103条正式用例、expect、B快照、Mock数据库、Trace、费用账本均未修改。详细逐文件哈希与Git状态见`final-verification.json`。没有Commit、Push、Merge或业务测试成绩变更。

本次调查与数据评估完成，停止等待用户确认。未开发下一阶段功能。
