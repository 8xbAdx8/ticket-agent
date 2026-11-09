# V3.10 独立铁路模拟时钟实施与验证

日期：2026-11-05（Asia/Shanghai）。基于当前未提交的乘客提案修复继续增量实施，父HEAD仍c1620cb4e9e8df094494fc77ef3f0d07ef9928c3。本轮不提交/推送，不使用真实模型、铁路、支付、Embedding或LangSmith API。状态：IMPLEMENTED / OFFLINE_VERIFIED / BROWSER_VERIFIED（离线模型及真实本地数据）；INDEPENDENTLY_REVIEWED=NOT_RUN，ACCEPTED=PENDING_USER。

## 问题与选择

原业务Service使用真实系统时间，所以11月5日09:58无法为06:13的G7331建单。数据没有失效；原发车判断是正确的。本轮保留该规则，新增独立暂停业务时间，让静态铁路数据在未来现实日期仍能用于模拟交易。禁止把旧订单时间倒拨或删除发车限制。

默认模拟时钟从只读GTFS中非隔离班次对应的最早有效服务日午夜起步。当前实际数据给出的起点是 **2026-10-17 00:00（北京时间）**，不是硬编码生产日期。页面显示“铁路模拟时间 · 北京时间 · 已暂停（非现实时间）”。查询仍遵循GTFS实际服务日，不承诺数据未覆盖日期有车。

## 使用

1. 原离线/在线CMD仍可使用，不需要手动设环境变量。新建铁路会话默认启用独立模拟时钟，原模型/费用授权不变。
2. 旧会话已有真实时钟数据库时保留原绑定，不迁移订单。可点击右栏“新会话使用独立模拟时钟”，再点“新会话”；也可直接新建会话。
3. 默认暂停，现实中等待一晚、几个月都不会推进该场景的业务时间。锁座/报价/提案仍有原有效期，但按模拟时间计算。
4. 右栏“模拟时间控制（暂停中）”可推进1/10/15分钟、1小时或1天。时间不能倒拨，单次底层推进上限7天。推进立即按原规则释放已超时未支付占用。
5. 新会话创建新的clock_id/数据库；旧场景、订单和Trace保留，不是重置旧数据库。刷新/只读历史读取同一持久时钟，不重建预算或恢复确认Secret。
6. 跨模拟日期后有效Prompt日期和配置Hash更新，旧确认卡须重新生成；同一天内推进不会仅因时刻变化使配置失效，原过期规则仍有效。
7. 如需保持旧用法，可显式设置进程局部RAILWAY_SIM_CLOCK_MODE=real，但不会将已有模拟场景改回真实时钟。无setx或系统环境修改。

## 时间域与存储

| 用途 | 时间 |
|---|---|
| 发车、报价、提案、锁座、支付超时、退款P01、改签资格 | 独立暂停模拟时间，经原Service.now传递 |
| Worker租约和接管 | 真实UTC，暂停/推进不延长进程租约 |
| Trace、Run Events、HTTP/Token账本、模型耗时、会话索引updated_at | 原真实时间 |
| SQL业务行created_at/到期及业务事件 | 模拟业务时间，不能冒充真实操作时间 |
| 时钟推进事件 | 独立clock_events保存前后模拟值和真实recorded_at |

新场景默认目录 `artifacts/runtime/v310-simulation-clocks/<uuid>/`，clock.sqlite与simulation.sqlite分开。显式指定的**尚不存在的新隔离数据库**继续尊重原路径合同，并创建独立时钟旁证；已存在的库和原启动器v392-launcher日库不会自动套用模拟时间。产品data/v39路径禁止建立模拟时钟绑定。

每次推进用BEGIN IMMEDIATE+revision做并发检查，负数、布尔、过大步长和过期revision被拒；丢失clock文件不自动重建或回落真实时钟；SID和clock_id不匹配拒绝读取。模型没有推进时钟工具，原八工具/铁路十一工具Schema不变。运行中的Agent不能从页面推进时间。

## 修改文件

- target/v39/simulation_clock.py：新增持久暂停时钟、归属、原子推进、真实时钟变更审计及GTFS有效日读取。
- web/simulation_clock.py：新增场景绑定、旧场景保护、手动推进控制。
- target/v39/service.py、lifecycle.py：仅分离Worker基础设施时间；交易规则仍经原now处理，保留之前乘客修复。
- target/v39/registry.py：字典铁路结果附simulation_clock元数据，不改工具输入Schema或列表结果形状。
- target/v39/planner.py：离线铁路“今天/明天”遵循模拟日期，其他原Provider未改。
- web/v39_bridge.py：接入独立clock、日期明确的有效Prompt、原有单参数_service工厂兼容、时间控制。
- web/business_state.py：共享快照/只读恢复使用同一持久clock。
- web/session_store.py：新建空模拟会话也保存clock引用，防止首次刷新重置。
- web/user_layout.py、conversation.py：在原标题栏显示时间，不新增Grid行、不重做CSS、不换控件key。
- scripts/launch_app.py：两种模式默认demo，允许显式real后备；不改Provider、凭据、端口和API预算。
- tests/v39/test_simulation_clock.py：新增18项确定性实例，保留全部旧断言。
- PROJECT_STATUS.md：增量记录；本报告与证据索引。

## 验证与失败批次

V39最终suite-final：**387 passed / 0 failed / 0 skipped**（原乘客修复后369+本次18）。覆盖持久暂停、跨客户端revision、禁止倒拨/错误SID、丢失账本、推进后提案/报价/锁座过期、库存仅释放一次、发车拒绝仍存在、P01 >48h/48h/24h/<24h边界、租约真实时间与另一Worker拒绝、实际G7331建单、空会话刷新、Baseline拒绝、旧场景不迁移、配置跨日、启动器两模式。

旧完整回归结果及逐ID比较见test-summary.json（以最终old-regression-final原件为准，不把主用例与199子测试混算）。正式103仍BLOCKED，旧11失败/1Skip不被删除或宣称恢复。

真实Edge/Playwright：1600×1100浅/深、390×844浅/深，**36/36检查、8截图、PageError0**。Console16和网络16均为离线环境阻断外部fonts.gstatic.com图标，未说成零。流程：空会话时钟已持久化→真实GTFS查询→选择早班车→报价/确认建单→推进15分钟→真实SQL订单EXPIRED、held=0且UNPAID→刷新相同clock_id/current→新会话不同clock且不删除旧单→无横向溢出。脚本、每项原始检查和数据库探针在browser-02/。没有自动重试交易，没有真实Live浏览器验收。

首批suite-01的8失败分为本机失效HTTP代理阻断localhost RPC、原旧UI测试以现实时间买早班车和新空会话索引未落盘；suite-02发现8项兼容性问题（旧单参数工厂及显式新数据库路径）。原日志均保留，经代码兼容修复与仅测试进程NO_PROXY后suite-03为385/0/0。新增2项隔离/日期测试后最终387/0/0。未改旧断言或用skip/xfail规避。

browser-01发现新增独立提示行挤占原Grid，未强制点击绕过；将标签移入原标题栏后browser-02四规格真实交互通过。旧截图与错误原件保留。

## 证据与限制

证据根：`artifacts/runtime/v310-simulation-clock-20261105-101123/`。before.json保存开工Hash/原未提交工作；opening/为本轮实际起点，不把上次乘客修复算成本次新增。关键源SHA、保护比对、最终Git、测试汇总见verification.json、manifest.json、task.diff、test-summary.json。测试所有SQLite均隔离，冻结simulation-v391.sqlite只Hash不连接。

```powershell
$env:NO_PROXY='localhost,127.0.0.1,::1' # 仅当前测试进程及子进程
.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v310-simulation-clock-20261105-101123/suite-NEW
.venv-v35\Scripts\python.exe -B artifacts/runtime/v310-simulation-clock-20261105-101123/run_regression.py old-regression-NEW
node artifacts/runtime/v310-simulation-clock-20261105-101123/browser-clock.js browser-NEW 8731 server-clock-02
```

复跑浏览器需新的独立服务目录/端口，已有证据目录禁止覆盖。测试服务停止回执另存，不操作用户8502进程。无真实请求，故新增真实Token/费用无消费；历史账本不改。

限制：只读历史不恢复写权限；模拟时间暂停意味着必须手动推进才能验证超时；跨日期旧卡配置失效；已有真实时钟场景需新会话使用新模式。未独立审查、未用户接受、未重新计分正式103，不宣称项目COMPLETE或绝对无Bug。

最终旧回归：1441 passed / 11 failed / 1 skipped，另199子测试通过。与上一轮乘客修复批次逐ID完全一致，无新增旧测试失败。最终Git及保护比对以verification.json为准。
