# 独立全国铁路静态原型（V3.8阶段八）

仅本地比赛演示/开发测试，`LOCAL_DEMO_ONLY`，权利链`RIGHTS_REVIEW_PENDING`，不得公开分发。不是生产Agent工具，不导入web、target或阶段七查询服务。Python标准库，无服务进程、网络功能或新依赖。

原件读取：`artifacts/runtime/railway-dataset-preparation-20261102-gtfs/`固定GTFS ZIP/许可/来源。数据库只允许新建到独立runtime路径，拒绝覆盖任何现有文件；不要把数据复制到本源码目录。原ZIP及原始评估材料不改。CC BY 4.0为仓库声明，Parser/OSM等上游权利仍待审查；不能据此称完全合规。

从项目根目录运行（将`<本轮证据目录>`替换为已忽略的runtime路径）：

```powershell
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli import --db <本轮证据目录>/static.sqlite
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli info --db <本轮证据目录>/static.sqlite
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli stations --db <本轮证据目录>/static.sqlite 哈尔滨
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli station --db <本轮证据目录>/static.sqlite VNP
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli trains --db <本轮证据目录>/static.sqlite 2026-11-02
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli trip --db <本轮证据目录>/static.sqlite 01000K516502 2026-11-02
.venv-v35\Scripts\python.exe -m prototypes.railway_static.cli direct --db <本轮证据目录>/static.sqlite VNP AOH 2026-11-02
```

`Dataset`提供相同六类只读Python接口。所有结果带静态来源/版本/SHA、无余票/票价/交易能力标记；availability为UNKNOWN，不能解释为0或售罄。NO_MATCH表示当前条件没有有效静态班次，OUT_OF_COVERAGE表示日期超范围，QUARANTINED表示班次已隔离。没有票务交易和换乘推荐能力。

所有日期参数是**始发服务日**，不是中途站日历出发日。跨日保留秒偏移并加到Asia/Shanghai服务日上，47:53:00对应次日23:53，不做模24。若要按乘客中途站出发日搜索，需另行授权设计，当前未实现。

原始9表每行raw_json和原字段保留；秒值/序号、坐标来源与隔离状态为派生字段/独立表。有效视图排除整个异常trip，原始数据不删不修；shape缺失仅标SHAPE_UNAVAILABLE，不隔离正常时刻。站名搜索返回候选，直达必须明确stop_id；不合并同名站或共享坐标。复车次别名表保持空，不采纳缺乏充分核验材料的推断别名。

查询使用SQLite `mode=ro`；导入失败保留新的诊断产物、不覆盖恢复，也不能使用未成功提交metadata的数据库。时间异常、来源匹配和地理真实性是不同概念。

独立测试：设置`PHASE8_DB`为实际导入数据库、`PHASE8_OUT`为新测试证据目录，运行`.venv-v35\Scripts\python.exe -m unittest discover -s prototypes/railway_static/tests -v`。测试加载真固定全量数据，额外小样本只用于原数据没有出现的exception_type=2等边界；不改旧tests/正式103。
