# Ticket Agent V3.9：原离线/在线CMD适配报告

2026-11-03；实施状态 **IMPLEMENTED、TESTED**，本次启动适配无阻塞。既有正式103、Bridge和V3.9.1独立审查状态不因此改变，不宣称项目全绿或交易系统已经最终验收。

证据根目录：`artifacts/runtime/v39-implementation-launchers-20261103-165445/`。修改前只读检查原文为precheck.md，Git/6706文件开工SHA为before.json；原CMD逐字节副本在original-cmd/。没有覆盖既有11项跟踪修改或未跟踪成果。

## 1. 修改前检查结论

分支feat/ticket-agent-v36-stabilization，HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`，暂存区空。两个CMD均在项目根目录，使用setlocal和UTF-8控制台，无start；直接调用同一PowerShell启动器，传递offline/live及%*，保留退出码/错误pause。

完整启动链：CMD → powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass → scripts/Start-TicketAgent.ps1 → .venv-v35/Scripts/python.exe → scripts/launch_app.py → 同一web/app.py。依赖探测顺序仍为.venv-v35/.venv-deepseek/.venv-v3/.venv，未安装/升级依赖。PowerShell用PSScriptRoot、Python用__file__定位ROOT，启动工作目录为ROOT。

默认离线8501、在线8502及忙端口后续29个候选的原逻辑不变；显式-Port仍精确选择。浏览器自动打开、NoBrowser、RuntimeRoot、进程停止逻辑均未改。

离线已有TICKET_WEB_OFFLINE_ONLY=1、TICKET_DISABLE_LOCAL_SECRETS=1、AGENT_PROVIDER=mock、AGENT_ENGINE=legacy，本次不重复设置。在线保持原DeepSeek优先/百炼单独配置回落及模型、端点、凭据解析。PowerShell在线会先从Windows用户级配置补齐缺失/空白的进程配置；Python bootstrap对届时进程环境优先、再补.env/用户配置。因此不能把bootstrap单独的优先级误写为整个Windows启动链绝不受前置用户配置影响。build_environment/model_config的既有模型解析也未改。本机.env不存在；未输出真实凭据。离线不加载本地凭据，在线原有加载方式保留。

registry.enabled()默认0、只接受值'1'；web/app.py据此显示“出行服务→全国铁路模拟出行”，原咨询/四快捷功能和两个其他工作空间保留。API bootstrap的名单不包含该变量，build_environment复制继承环境且不删除它，故仅需在CMD子进程启动前设置。

## 2. 唯一产品修改及SHA

两个CMD都只在setlocal后增加同一行，其余字节完全保留；移除新增行可还原原文件SHA。

```diff
 @echo off
 setlocal
+set "RAILWAY_SIMULATION_ENABLED=1"
 chcp 65001 >nul
```

| 文件 | 修改前SHA256 | 修改后SHA256 |
|---|---|---|
| 启动_离线模式.cmd | 76fed972c54ac08ffb5b675b0d89481f9d380060e78ca8a10472ec3ca2ee7b86 | efe43f56208393f230c6bed2a04957b44f001e39e9e98bf7b491bfc8146f7c8f |
| 启动_在线模式.cmd | 16d5ab630a55908e6ad19e04e77ffd658a628a5eabb0d5e3be6a92f4bf5ccf07 | fc6754d3cf00922b9fec48dc60a178adc42f0cf2b943d4a6cfa7d57a689c3d45 |

其他修改：PROJECT_STATUS.md增量登记；新增本报告及证据目录。没有修改PowerShell/Python启动器、web/app.py、铁路业务/UI源码、config、旧CSS、测试或依赖。文件SHA及完整双CMD diff见cmd-edit.json和checks-final.json/checks-final-cmd.patch。

变量仅属于setlocal脚本及其子进程，没有setx/用户级/系统级环境写入；registry的默认0不变，不把全局Feature Flag硬编码成1，也不扩大Baseline工具白名单。此开关不代表真实铁路、支付或V3.9 Live能力授权。

## 3. 两个原始CMD实际启动与环境传递

直接通过cmd.exe /d /c调用根目录原文件，从独立非项目工作目录启动。测试额外使用已有-NoBrowser、-RuntimeRoot、-Port参数，将旧票务模拟库、铁路库、Trace、用量放入本批目录；未触碰产品默认库，默认参数实现不改。只读的Python启动探针记录解释器、argv、cwd及白名单环境，未记录Key。

| 项目 | 离线 | 在线 |
|---|---|---|
| 原始CMD启动/HTTP健康 | 通过 | 通过 |
| 实际解释器 | .venv-v35/Scripts/python.exe | 同左 |
| Streamlit目标/cwd | web/app.py / ROOT | 同左 |
| 子进程RAILWAY_SIMULATION_ENABLED | 1 | 1 |
| 主Provider/Engine | mock / legacy | deepseek / langchain |
| 主模型 | mock-offline | deepseek-flash |
| 原LC工具集 | all | read_only |
| TICKET_WEB_OFFLINE_ONLY | 1 | 0 |
| 测试父环境Flag | 仍为0 | 仍为0 |

实际测试端口51093/51103为-Port隔离参数，不是修改后的默认端口。servers.json及offline-r2/live-r2/processes/保存完整链路证据，server.log保存健康成功日志。脚本通过原%*正常接收所有参数。

预检3/3通过：原离线、在线DeepSeek配置、在线只有百炼配置（bailian/qwen3.8-flash）。在线使用测试假Key占位、清真实凭据、PYTHONPATH注入仅本批有效的socket/DNS非回环阻断和本地凭据发现抑制；实际child模式仍为Live，未改成Mock。这证明启动与配置传递，不证明真实Key、供应商连接或余额有效。未点击主聊天发送、费用授权或远端上传，实际模型/Embedding/LangSmith/铁路/支付请求为0。两种模式用量目录均无模型requests.jsonl。

铁路专用Conversation本来就live=False，初始为独立Mock模拟，与主会话Provider隔离。在线主会话保持Live，铁路静态查询无需用户改选Mock；开发者若主动把该铁路会话改为在线Provider，现有拒绝仍保留，不在本轮开放新Live路径。

## 4. 静态数据、真实查询与数据库隔离

- 实际静态路径：`artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite`，由target/v39/static.py相对自身文件定位；SHA `e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`。
- 原始GTFS ZIP SHA `3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`，本轮未修改/下载/爬取。沿用已有来源和授权限制，不声称实时开行/实时余票/官方票价。
- Dataset以SQLite URI mode=ro打开。独立探针在非ROOT cwd实际查询、验证只读拒绝写入，前后SHA相同。未把静态库导入旧业务库，未更换成Fixture或本地造假记录。
- 2026-11-04北京南VNP→上海虹桥AOH，实际返回39班；首班G547（240000G54700），经停13站，查询含带时区到发时间。两个CMD页面均实际调用同一只读Adapter完成车站、车次、经停查询，8份页面查询记录保存于browser-r2/results.json，包含STATIC_SCHEDULE/real_time=false及page_operation来源，不冒充Agent模型Trace。
- K5165 trip=01000K516502、服务日2026-11-02，原始30:51:00换算为2026-11-03T06:51:00+08:00；独立static-query-results.json保存完整结果，无生产时间逻辑修改。
- 用户所列data/v39/simulation.sqlite是原v1模拟库，保持SHA `a429b20be1242a4f6ea81c749df4a7718e6adf5138e973870821e97772c286fe`。V3.9.1页面实际默认新文件为data/v39/simulation-v391.sqlite，本轮前后均不存在；只在本批独立RAILWAY_SIM_DB_PATH初始化测试库。旧票务DB、原空v1库、静态DB三者不混用。8轮UI查询均orders=0、transactions=0、FK无违规。

## 5. 实际浏览器验收

Edge156.0.4314.58 + 现有Playwright；每种模式分别1600×1100/390×844 × 浅色/深色，共8组合。**160/160检查通过，24截图，8轮实际查询/数据库只读探针**。

| 验收项目 | 离线4规格 | 在线4规格 |
|---|---|---|
| 原四快捷功能/四面板入口 | 保留并可返回 | 保留并可返回 |
| 铁路模拟入口和页面 | 通过 | 通过 |
| 北京南/上海虹桥明确选站 | 通过 | 通过 |
| 静态车次与经停到发时刻 | 通过 | 通过 |
| 原模型选择不变 | Legacy Mock | DeepSeek Live |
| 开发者空间/测试控制台入口 | 保留 | 保留 |
| 整页横向溢出 | 无 | 无 |

截图在browser-r2/，各组合original-panels/static-trains/static-stops各1份；例如live-desktop-dark-original-panels.png、live-mobile-light-static-trains.png、offline-mobile-dark-static-stops.png。实际查看桌面/手机及两主题代表截图，非生成图片。宽表在自身容器内滚动，未改任何布局/CSS。

PageError=0；测试脚本错误=0；Console Error=16；requestfailed=16；主动拦截外网请求=16，均为Google字体图标SVG被离线策略阻断，不宣称Console全零。旧工作空间只验入口、四快捷功能和往返保留，不声称重新人工验收全部旧业务；更广旧功能由完整回归另证。

首轮工具问题保留：启动探针最初按启动早期sys.argv中的streamlit文本筛选失败（实际已健康），改为实际app路径/端口参数；首轮浏览器innerText未包含下拉框input值，改用inputValue。旧日志、第一版脚本和截图未覆盖，未通过降低断言、skip/xfail或修改产品源码迎合测试。测试服务已按真实CMD父子链验证归属后停止，仅终止本轮进程。

未验证：真实API/真实Key有效性、真实外部铁路服务、实体手机软键盘。本轮经cmd.exe实际执行原始文件，以-NoBrowser避免弹出用户浏览器；Explorer双击与自动开浏览器分支沿用原实现，未声称本次通过鼠标双击重新验证该系统关联。

## 6. 回归与安全结果

| 测试 | Passed | Failed | Skipped | 证据 |
|---|---:|---:|---:|---|
| 旧完整回归 | 1441 | 11 | 1 | regression/results/，另199子测试通过 |
| V3.9兼容全套 | 164 | 0 | 0 | v39-compatibility/，含双引擎/Baseline/权限反例 |
| 实际CMD配置预检 | 3 | 0 | 0 | servers.json及preflight日志 |
| 实际CMD服务启动 | 2 | 0 | 0 | servers.json、两份server.log |
| Edge八组合 | 160 | 0 | 0 | browser-r2/results.json |

原回归与V3.9.1最近完整批次逐ID比较：added/removed/outcome_changes均空，11失败和唯一Skip完全同ID，原问题没有被描述为已修复。失败原文/ID见checks-final.json及原始pytest日志。未改任何旧测试或正式103断言，未加skip/xfail，B正式103仍BLOCKED未计分。

命令（已有证据目录不可覆盖，复现须使用全新目录并调整测试控制器输出）：

```powershell
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v39-implementation-launchers-20261103-165445/start_cmds_r2.py
node artifacts/runtime/v39-implementation-launchers-20261103-165445/browser.js
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v39-implementation-launchers-20261103-165445/static_probe.py
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v39-implementation-launchers-20261103-165445/run_old_regression.py regression
.\.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v39-implementation-launchers-20261103-165445/v39-compatibility
```

旧回归是冻结P0输入+当前源码独立副本，外网阻断、清凭据，仅分开计量tests/v39，没有忽略其他旧测试。V3.9套件使用独立DB/Trace/输出并检查两个默认DB。公共Agent接口、SYSTEM_PROMPT/八TOOLS/DIMENSIONS、Baseline完整文件及PS/Python启动器SHA保持开工值。Flag仅在两CMD添加，不绕过任何确认/权限边界。

## 7. Git及保护核验

本轮修改2个CMD、PROJECT_STATUS.md，新增本报告和独立证据目录。原11项跟踪修改及全部既有未跟踪成果保留。HEAD/分支不变、暂存空；git diff --check=0，已有LF/CRLF提示不进行全局规范化。没有commit/push/merge/tag/release、Bridge或Harness调用，没有修改旧数据库或删除证据。

1892、4056、5538组在**本次开工前后无差异**。相对上次已批准清单，账本`artifacts/runtime/api-usage/bailian/dbc4325ea7a9515b7a04/requests.jsonl`在本轮开工前已多1853字节：274579字节、SHA `87cfd3ed6b6dfdff0ecd8b1b7bc50f6e4726c5511d240b7d7bd417bd3f5b3776`；原已批准272726字节前缀完整。来源未独立确定，本轮没有修改；保留为开工现场差异，不改原清单、不冒称历史零差异或新的用户批准。before.json/opening_protection_deltas及最终回执分别记录历史差异/本轮前后变化。

上轮只读独立审查v2 ZIP原件保持SHA，但它不包含本次启动脚本更新；以本报告和CMD新SHA作为增量交付，不把旧ZIP冒充当前最新启动文件。交易代码仍需此前安排的人工独立审查，当前工作不构成独立验收。

## 8. 用户启动说明

1. 若还开着旧服务，在**自己原来的启动窗口**按Ctrl+C停止；仅刷新旧页面可能仍使用旧进程配置。
2. 双击原来的启动_离线模式.cmd或启动_在线模式.cmd。无需额外PowerShell、环境变量或第二个启动命令；在线沿用原凭据配置/缺Key提示。
3. 在用户工作空间上方“出行服务”选择“全国铁路模拟出行”，查询车站、车次与经停；选择“咨询与演示业务”返回原四面板。
4. 铁路入口显示静态数据与本地模拟业务，不是12306实时查询、真实锁座、出票、扣款或退款。原在线咨询发送的费用确认机制保持不变。

本次状态IMPLEMENTED、TESTED；无本轮启动/静态数据阻塞。未修复旧11项失败，未推进其他阶段。等待用户验收。
