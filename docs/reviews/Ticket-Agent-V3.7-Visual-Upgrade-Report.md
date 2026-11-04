# Ticket Agent V3.7 前端视觉升级交付报告

日期：2026-11-02（Asia/Shanghai）。范围：三个现有 Streamlit 工作空间的视觉与响应式展示；不是新的业务阶段。

## 1. 结论与起始状态

**展示层升级与本地隔离验收完成，等待用户确认。** 最终 Edge 四规格主检查 **112/112**、补充检查 **32/32**；本次前后完整离线回归均为 **1356 passed / 11 failed / 1 skipped，199 subtests passed**。失败与跳过的完整用例集合相同，没有新增回归，亦未修复或隐藏原11项失败。

分支 `feat/ticket-agent-v36-stabilization`，HEAD 始终为 `4340b6640025be95e8300a3d625a32cfb431e35d`。开工已有上一任务的 PROJECT_STATUS.md 修改、未跟踪 frontend-design 原版目录与安装报告；全部保护，不清理、恢复、暂存、提交或推送。

已阅读 PROJECT_STATUS、阶段0和阶段1报告、当前主题/页面/卡片/布局/浏览器验收及回归隔离实现。使用已安装原版 `frontend-design`，先形成设计系统与布局方案，再对照铁路票务主题审视后实施；未改写 Skill，未机械调用与本次目标无关的评测 Skill。

## 2. 设计系统与三个工作空间

设计方向为铁路运行台：用线路几何、清楚的数据对齐、票据行与证据表表达产品属性。只有欢迎区使用一处线路装饰，不加入假车次、假实时指标、虚构运行状态或额外口号。

| 项目 | 设计值 |
|---|---|
| 浅色主色板 | 瓷白 `#F3F6FA`、纸白 `#FFFFFF`、铁路蓝 `#1555C4`、深蓝 `#162E49`、灰蓝 `#607188`；警示琥珀方向 `#B86E17`，正文警示色使用更深的 `#8C5B0A` |
| 深色 | 背景 `#101D2D`、面板 `#172B40`、浮层 `#20364D`、文字 `#E6EFF8`、次级文字 `#A3B6CD`、交互 `#8DB7FF`、边界 `#304760` |
| 状态语义 | 成功绿、失败红、等待琥珀、无法判定紫、跳过/缺失灰蓝；原7种标签与判定含义不变，主题切换只改变颜色值 |
| 字体 | 标题/车次优先本机 Bahnschrift，中文回落 Microsoft YaHei UI；正文 Segoe UI Variable/Segoe UI/微软雅黑；代码保留等宽字体。不安装或加载外部字体 |
| 字号 | 12/13/14/16/20/28/36 为层级参考；欢迎标题桌面38px、手机28px，指标34px；正文行高1.7–1.9，数值采用等宽数字 |
| 间距与形状 | 4/8/12/16/24/32px；控件8px、票据12px、主面板18px，浮层单独阴影；普通矩阵用行距和边界，不铺满同款卡片 |
| 交互 | 选中导航、主按钮、开关统一主题色；键盘焦点2px；disabled、错误、等待仍可区分；减少动态效果偏好生效 |

布局沿用既有 Python 组合与用户端 Grid/Flex，内容左对齐；金额按用途右对齐。没有迁移框架、增加依赖或重构业务组件。

```
用户： 侧栏 | 产品栏 / 会话入口
            独立滚动对话与票据 | 行程 / 订单 / 六功能入口
            来源与费用说明 / 固定输入框
开发： 侧栏 | 会话与运行 / Baseline和实验配置
            配置 | 实际事件轴 | 证据与原始详情
            LangSmith 状态与授权操作
测试： 侧栏 | 批次身份 / 指标寄存区
            七维度矩阵 / 原始证据入口
            既有变异、判定、历史、报告导航
手机： 用户对话优先、功能抽屉；开发三栏纵向展示；测试沿原有移动规则排列。
```

| 空间 | 实际改造 | 保留的行为 |
|---|---|---|
| 用户 | 线路欢迎区、完整宽度快捷入口、对话层级、主题输入框、票价/时刻对齐与票据虚线、订单收据、政策引用区、确认区域和弹层视觉 | 现有六功能、来源说明、示例政策、非真实出票/扣款/退款、确认和费用授权、输入框与独立滚动模型 |
| 开发者 | 标题与配置层级、三栏面板、事件轴、选中事件、技术字段与表格、LangSmith 状态卡；窄屏自动纵向展示 | Prompt/白名单/权限/Provider/模型配置、实际执行与Trace、检索证据、只读历史、上传/GET核验和远端一致性能力 |
| 测试 | 指标字体与层次、七维度表头/行、证据表格、主题和控件视觉；实验室也使用同一设计系统 | 独立测试入口、原103条和七维度口径、A/B/Mock/Live归属、原变异/判定/历史/报告入口；画面中201等数字仍为历史B快照，绝非本次重评 |

## 3. 修改文件与业务保护

| 文件 | 修改原因 |
|---|---|
| `web/design.py` | 只变更 `theme()` 的主题 token 和 `COLORS` 的主题语义色引用；其余函数及状态标签 AST 不变 |
| `web/design.css` | 统一字体/层级、导航、控件/焦点、票据/订单/政策、开发者三栏、测试矩阵/表格、弹层和移动适配 |
| `web/user_layout.css` | 欢迎线路图形、用户空间表面、快捷入口、对话与输入框、右栏间距；保留原视口网格和滚动尺寸规则 |
| `PROJECT_STATUS.md` | 增量记录实际视觉进度、前后测试结果、证据与剩余问题；保留上一任务记录 |
| 本报告 | 交付范围、设计系统、截图、验证、diff和风险索引 |

没有改动 app.py、conversation.py、developer_workspace.py、competition_view.py 或 LangSmith 源码；没有修改任何现有测试、103条原始断言、B方快照、DIMENSIONS、Prompt、八工具 Schema、Provider、费用授权、写操作策略、SQLite 或 RAG 业务逻辑。

原显式 key、无 key 控件的标签/调用参数、session_state 与路由代码均未变。`design.py` 除 `theme()` 外所有函数 AST 一致，LABELS 一致。原 eval-audit、write-code-eval、新安装 frontend-design 及安装报告字节保持。

核验：**1892保护文件0变化**；本次开工记录的 **5538数据/证据文件0变化**；B manifest **7/7** 文件匹配，case catalog 为 **103条**。这是完整性保护，不是103条正式计分，原执行器阻塞状态不变。

## 4. 测试隔离、命令和实际回归

使用原 `scripts/regression_center.py:prepare`：校验冻结P0 v2包的证据/缓存后创建独立副本，覆盖当前源码；仅共享现有 `.venv-v35` 依赖，不进行新安装。业务库、Trace、账本、TEMP均在各新副本中。移除进程真实凭据、关闭本地secrets/自动追踪，Python socket守卫与浏览器route均仅允许loopback。未访问原正式库或真实API。

环境：Python **3.12.14**，Streamlit **1.65.0**，本机 Edge **156.0.4314.50**（Playwright，headless）。浏览器复用此前安装的 Playwright，不增加项目依赖。

根目录实际入口命令：

```powershell
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v37-visual-upgrade-20261102/harness.py tests baseline
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v37-visual-upgrade-20261102/harness.py tests candidate
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v37-visual-upgrade-20261102/harness.py tests candidate-final
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v37-visual-upgrade-20261102/harness.py tests candidate-final-r2
```

各入口在隔离副本执行 `python -B scripts/v37_tests.py --out <副本>/artifacts/runtime/visual-regression`；独立pytest basetemp。原始完整命令、cwd、开始/结束时间、退出码见各 `summary.json`，pytest.log/results.json/junit.xml位于对应副本的上述目录。

| 批次/北京时间 | Passed | Failed | Skipped | 子测试通过/失败 | 退出码 |
|---|---:|---:|---:|---:|---:|
| 修改前baseline，11-02 00:22:37–00:25:32 | 1356 | 11 | 1 | 199 / 0 | 1 |
| 首次完整candidate，11-02 00:31:08–00:34:27 | 1356 | 11 | 1 | 199 / 0 | 1 |
| 开关样式收尾candidate-final，11-02 00:35:59–00:38:57 | 1356 | 11 | 1 | 199 / 0 | 1 |
| 历史按钮悬停收尾后candidate-final-r2，11-02 00:48:21–00:50:27 | 1356 | 11 | 1 | 199 / 0 | 1 |

四批失败/跳过集合相同，逐项差分见 `regression-comparison.json`；最终363个运行相关源码/配置/数据文件与实际被测副本哈希相同。没有删测试、改判据、加skip/xfail或把失败包装成通过。

原失败分布：`test_deepseek_direct_send.py` 3、`test_followups_continuous.py` 1、`test_followups_mvp.py` 1、`test_qwen_langsmith_ui.py` 5、`test_unlimited_live_ui.py` 1。仍是既有模型选择/费用授权入口/历史UI断言契约问题，不在本次展示层任务内修复。唯一P2未获人工批准的skip保持。

Mock/离线测试如上；真实模型/API与人工验收本次均未执行，不能记为通过。正式B103有效重评分仍0。

## 5. 真实浏览器结果及问题记录

服务分别在独立副本端口8531–8535启动，只绑定127.0.0.1。四规格为1600×1100与390×844，各浅/深主题。最终命令：

```powershell
node artifacts/runtime/v37-visual-upgrade-20261102/browser.js before-r2 8531
node artifacts/runtime/v37-visual-upgrade-20261102/browser.js after-r4 8535
node artifacts/runtime/v37-visual-upgrade-20261102/probes.js
```

| 范围 | 结果 | 证据 |
|---|---|---|
| 修改前四规格 | 76/76，28截图 | `before-r2-browser.json`及before-r2 PNG |
| 最终四规格主检查 | 112/112，48截图，PageError 0 | `after-r4-browser.json`及after-r4 PNG |
| 补充四规格 | 32/32，12截图，PageError 0 | `probes-r3.json`及probes-r3 PNG |
| 完整页面/滚动/输入 | 各检查点无页面横向溢出；单/多行输入在可用视口内；对话独立滚动，切空间保留会话ID；历史弹层在视口内 | 主检查中的geometry、scroll、session和popover记录 |
| 实际交互 | Mock查票、政策展开、模拟下单确认/订单、计算器、移动信息抽屉、历史弹层；同城无效查询正确拒绝；LangSmith和变异入口保留 | 截图、主检查、补充检查；实际Mock运行原件在browser-after-r4副本 |
| 键盘和主题 | 四规格发送按钮Tab焦点2px可见；开关选中色随主题；历史按钮悬停对比度浅色12.03:1、深色10.65:1；抽查8种文字/语义色对面板底色均≥4.5:1 | `probes-r3.json`，不扩展为完整WCAG认证 |
| Console | 主流程前后均12条：8条外部Material SVG被离线拦截，4条旧react-json-view错误；类别/数量均无新增 | before-r2 / after-r4 consoleErrors与blocked列表 |

中间原件全部保留：初版before 58/64中6项源于不正确的脚本假设（返回页面仍需存在旧车次卡、手机无需展开即可看政策来源）；改为检查会话ID并实际展开政策后76/76。after-r1另因点击被样式隐藏的switch input导致脚本超时，改点可见标签。补充首轮在移动下拉框未打开时查找option超时；加入真实键盘打开步骤后四规格完成。未通过产品代码或改正式测试来消除这些脚本问题，首轮日志/截图/错误保留。

开关配色与深色历史按钮悬停白底为真实截图发现的展示遗漏，均修CSS后重建副本、重跑完整回归和浏览器；增加按钮对比度检查。中间证据另存，不覆盖旧测试日志或截图。没有把旧108项检查冒充最终112项。

五个本次自建服务已停止；普通沙箱首次终止被系统拒绝后，核对每个PID对应本任务副本命令行，再经工具提权停止进程树，退出码均0，未停止用户其他服务。

## 6. 修改前后截图

截图在 `artifacts/runtime/v37-visual-upgrade-20261102/`。均为本次真实Edge截图，不使用生成图或历史截图冒充。

| 空间 | 桌面浅色修改前 | 桌面浅色修改后 |
|---|---|---|
| 用户 | [before](../../artifacts/runtime/v37-visual-upgrade-20261102/before-r2-desktop-light-welcome.png) | [after](../../artifacts/runtime/v37-visual-upgrade-20261102/after-r4-desktop-light-welcome.png) |
| 开发者三栏 | [before](../../artifacts/runtime/v37-visual-upgrade-20261102/before-r2-desktop-light-developer-events.png) | [after](../../artifacts/runtime/v37-visual-upgrade-20261102/after-r4-desktop-light-developer-events.png) |
| 测试控制台 | [before](../../artifacts/runtime/v37-visual-upgrade-20261102/before-r2-desktop-light-console.png) | [after](../../artifacts/runtime/v37-visual-upgrade-20261102/after-r4-desktop-light-console.png) |

其他规格的同名截图：将以上文件名中的 `desktop-light` 替换为 `desktop-dark`、`mobile-light`、`mobile-dark`，均有before-r2与after-r4原件。完整逐文件SHA256及可点击矩阵见 `screenshots.md` / `screenshots.json`。

最终用户场景后缀：welcome、tickets、policy、multiline、confirmation、order、calculator、popover；开发者：developer、developer-events；测试：console、formal-detail。额外probes-r3：validation、langsmith、laboratory。四规格全部留存。

## 7. Git diff、证据与未解决问题

本次展示层diff：`artifacts/runtime/v37-visual-upgrade-20261102/presentation.patch`。当前全部tracked diff另存 `working-tree.patch`，其中PROJECT_STATUS包含上一任务已有的安装记录，不把它算作本次新改动。新报告和原本未跟踪的Skill不出现在普通git diff内，最终文件清单另存 `verification.json`。

证据根目录还包括：before.json、originals/、design-plan.md、harness.py、browser.js、probes.js、scope-checks.json、regression-comparison.json、各批source-manifest、JUnit/原日志、browser-after-r4内真实Mock Trace/审计/演示库、服务器停止回执和最终verification。所有旧包、保护清单及历史证据保留原位置与内容。

剩余事项：

- 原11失败、唯一skip和正式103执行器阻塞保持；需要独立任务明确契约与恢复材料，不能由视觉升级宣布恢复。
- 原4条JSON组件Console错误仍在；本次不改运行数据/证据来掩盖。外部图标在离线条件被拦截是既有行为，没有新增字体网络依赖。
- 有效覆盖为Edge、固定桌面/手机视口和本地Mock。没有真人主观验收、真实Live/Embedding/LangSmith上传/GET、实际手机软键盘、Safari/Firefox或全站无障碍认证；瞬态加载动画未单独截获验收。
- 仍依赖Streamlit公开testid、既有key和React Aria DOM层级，未来Streamlit升级后需复核CSS；容器与滚动桥接的原弃用提示保留，未趁机改运行桥接。
- 没有产品功能或其他阶段开发、Git提交、推送、合并；当前修改留在工作区等待确认。
