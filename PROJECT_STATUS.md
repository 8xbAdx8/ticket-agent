# Ticket Agent 项目状态

> 本文件是长期状态索引，不替代代码、原始测试报告或 Git 历史。接手时先读本文件，再现场核对 Git 和相关证据；历史结论必须保留版本、时间及范围。
> 首次建立：2026-10-31（Asia/Shanghai，UTC+08:00）；现场检查记录时点：22:14:18。维护依据：本次用户任务及此前提供的交接报告。
> 首次建立任务只读取本地文件和 Git 元数据、建立本文档；未运行测试、启动服务、调用真实 API、联网、Commit、Push 或 Merge。后续阶段以第12节新增记录为准。

## 1. 项目基本信息

- 项目目标：以模拟票务 Agent 为被测对象，建立工具调用、业务约束、多轮交互、RAG、缺陷注入和质量审计的可复现验证闭环。
- 项目定位：智能体可靠性与测试工作空间；车次、库存、订单、支付均为自建模拟业务，不连接真实铁路、航司或支付系统。模型 API 可以是真实服务。
- 当前版本：界面明确显示 **3.7**，README 含 V3.7 增量；当前分支名仍含 V3.6。未确认统一发布版本号，不将分支名、界面版本和正式发布版本视为同一概念。
- 当前开发阶段：V3.7阶段七离线工程交付，总体PARTIAL；Fixture COMPLETE、Snapshot PARTIAL（缺真实原件）、Live BLOCKED。最终1356 passed / 11 failed / 1 skipped、199子测试，新增45通过；Edge四规格120/120、32截图。阶段五至七成果按本次用户授权归档，阶段六COMPLETE保留；103正式重评仍BLOCKED，未进入下一阶段。
- 项目路径：`D:\codexproject\ticket-agent`。
- Git 仓库：`https://github.com/8xbAdx8/ticket-agent.git`；当前分支：`feat/ticket-agent-v36-stabilization`。
- 当前 HEAD：以现场 `git rev-parse HEAD` 为准；本次阶段五至七归档前为 `c889b082dd4bd07e3514038a69362b71dd21915c`。源码归档SHA及推送结果见第7、12节最新记录与归档回执。
- 首次建立前（历史）：工作区干净、暂存区为空、非忽略未跟踪文件为0；本文档当时不存在。阶段1开始时仅有既有未跟踪本文及阶段0报告；最终状态见第12节。
- 环境：推荐 `.venv-v35`；其 `pyvenv.cfg` 记录 Python 3.12.14，历史回归报告也记录此版本；本次未启动解释器或重新验证完整依赖安装。

信息来源：现场 Git、根目录清单、`web/app.py`、`README.md`、`.venv-v35/pyvenv.cfg`、用户交接报告。统一发布版本待核实。

## 2. 技术架构

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：新增TrainSource、固定Fixture和本地快照校验/导入，独立会话来源选择及侧车事件；实时源没有网络实现，Provider配置不授予源权限。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：技术架构增量：target/dev_overrides、execution_config、prompt_config及profile_evaluation，冻结Baseline与会话Override；原Legacy/LC、Provider、RAG/费用与公共契约保留，sidecar独立。


> 2026-11-01阶段五更新：新增user_layout.py/css，用户端视口Grid/Flex、左聊天/右信息独立滚动、聊天外输入框；桥接仅辅助动态视口和会话滚动，不再写聊天高度。


> 2026-11-01阶段四更新：阶段四增量：target/order_read_model.py统一本人订单只读投影；web/user_features.py复用Conversation.send/Agent.chat与既有业务服务，纯计算与页面操作分层；不增加依赖、Provider或数据库。

| 层次 | 当前实现及边界 | 主要依据 |
|---|---|---|
| 前端 | Streamlit、Python 页面和 CSS；Agent 用户端、Agent 开发者端、测试控制台三个工作区 | `web/app.py`、`web/design.css` |
| 后端 | Python；CLI、应用运行层、模拟业务；FastAPI/Uvicorn HTTP 外壳为可选入口 | `cli.py`、`web/runtime.py`、`target/mock_api.py`、`requirements.txt` |
| Agent 框架 | Legacy 原生循环与 LangChain `create_agent` 两条路径；LangGraph 为依赖，不代表自定义图或完整持久化恢复已经交付 | `target/agent.py`、`target/langchain_agent.py`、`requirements-v35-lock.txt` |
| 模型 Provider | Legacy Mock、LangChain Mock、DeepSeek Live、百炼/Qwen Live；QwenCloud 地址和配置校验已入库 | `web/app.py`、`target/deepseek_runtime.py`、`target/bailian_runtime.py` |
| Embedding | text-embedding-v4、真实请求记录及本地缓存；缓存重放、离线哈希向量与真实 Embedding 必须区分 | `target/embeddings.py`、V3.5.2 API 报告 |
| RAG | Keyword、Vector、RRF Hybrid；Chroma、索引/缓存保护、引用与忠实度检查；旧48题与千题工程独立 | `target/rag_service.py`、`target/rag_store.py`、`target/rag_protection.py`、`target/rag_benchmark.py` |
| 数据存储 | SQLite 模拟业务/历史账本/缓存，Chroma 向量索引，JSON/JSONL 会话、Trace、事件和用量记录 | `target/tools.py`、`target/api_usage.py`、`web/session_store.py` |
| 测试框架 | pytest/unittest、Streamlit AppTest、离线 SDK/HTTP 替身、隔离回归中心；真实模型和人工验收另记 | `tests/`、`scripts/regression_center.py`、现有回归报告 |
| 追踪与审计 | 公共 Trace、run_events、审计旁证、运行/工具关联、历史只读恢复；LangSmith 是独立显式授权的可选集成 | `target/run_events.py`、`web/evidence.py`、`web/langsmith_panel.py` |

公共契约：`Agent.chat(session_id, message)` 返回十字段；工具调用为 `tool/args/ok/latency_ms/result_preview` 五字段。不得擅改。来源：`docs/contract.md`。

## 3. 已完成功能

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：Fixture固定2100行/日期/SHA；Snapshot离线适配、10类状态/unknown、只读与演示事务隔离已测，但真实原件缺失，不能标记真实接入完成。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：已完成并离线验证：会话编辑/原子revision/SHA、下一轮实际重建、双引擎dispatch拒绝、deny/confirm、模型/温度参数捕获、RAG迁移、只读历史快照、独立自定义评估。正式103仅身份核验，不标记断言通过。


> 2026-11-01阶段五更新：阶段五桌面双栏、移动单栏/展开右栏、深浅主题、顶栏/多行/客户化确认已实测；六入口与支付/退改业务复用不变。


> 2026-11-01阶段四更新：阶段四已实现并离线验证：查余票/政策速查/我的订单/退票费率独立面板、右栏行李和改签、首屏4快捷卡；当前订单统一状态/动作投影、不一致禁操作、保留真实Agent工具链及source=page。详见第12节新记录。

验证标记：“代码存在”仅代表静态检查确认；“历史验证”仅适用于原批次，不能替代当前源码的运行验收。阶段1新增隔离测试结果单列于第6节，不改写旧成绩。

| 模块 | 已实现内容 | 验证状态 |
|---|---|---|
| Agent/模型 | 双 Mock 引擎、DeepSeek 和百炼/Qwen 接入、工具协议往返 | 代码存在；有历史离线和真实模型证据；当前全量存在失败 |
| 模拟业务 | 查票、候补、锁座、建单、支付、取消、查单、政策检索共8工具；SQLite、幂等、身份与写操作确认 | 代码存在；历史 Live 模拟下单/支付证据；取消和异常场景有缺口 |
| RAG | 三检索模式、Embedding/Chroma、缓存与冻结输入保护、指标和忠实度审计 | 代码存在；旧48题有历史成绩；千题真实向量及回答质量未完整验证 |
| 变异测试 | Agent 八变异与独立 RAG 八变异 | 代码及历史矩阵存在；不代表每种变异均已完成当前 Live 验收 |
| UI/历史 | 三工作区、七维度历史总览、时间线、Trace/事件/旁证展示、保存及只读恢复 | 已提交；有历史 AppTest/截图；当前相关 UI 仍有回归失败 |
| 追问 | 基于实际证据的候选、模型选择、规则回退、保存回放和连续点击续聊 | 代码及历史离线替身验证存在；当前两个追问测试文件各有1项失败 |
| P2 | 候选生成、校验、具名人工审核门禁、隔离执行、逐轮及禁止工具断言 | 代码已提交；四批生成报告存在；批准目录目前仅 README，无批准场景文件 |
| 用量统计 | 累计 Live 预算改为非阻断统计；保留历史账本和未知值 | 代码及历史离线迁移报告存在；当前累计账单未核对 |
| V3.7阶段1 | 客户文案、演示来源/交易边界、运行与政策/追问诊断分层、导航显示名 | 新增6项离线验收通过；最终完整1098通过/11失败/1跳过，失败集合不变；阶段1.2移动端修复后四规格浏览器43/43通过，未提交 |

阶段二新增：原订单卡片PNG二维码、三入口统一显式演示支付、金额/归属/状态核验、支付方式持久化与幂等、刷新只读展示。验证为40专项通过、完整1138/11/1/199、浏览器108/108；详见第12节和阶段二报告。

阶段三新增：本人车次/日期订单匹配、候选选择与冻结费用确认、Decimal退票明细、卡片改签自动带入、完整快照和库存事务复核、P02禁退及独立页面事件；59项新增通过，四规格业务96/96通过。凭证交回仍未建模，打印记录采用保守拒退。

信息来源：上述源码、`docs/handoff/Ticket_Agent_作品介绍文档.md`、`docs/handoff/八工具Live模拟购票说明.md`、`docs/architecture/P2_AI测试场景生成方案.md`、`data/p2_scenarios/approved/README.md`、第6节报告。未把计划功能计入已完成。

## 4. 当前开发进度

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：阶段七离线交付停止等待验收；Fixture COMPLETE/Snapshot PARTIAL/Live BLOCKED，未进入下一阶段，未提交。

> 2026-11-01T20:08:10.337492+08:00 正式103恢复审查：正式103恢复任务已完成只读搜索，状态BLOCKED；找到11组旧B副本但不能用于当前103完整计分，42条trains_from_tools/C5配套实现缺失。阶段六离线工程COMPLETE结论保留，未开始阶段七。

> 2026-11-01T19:32:16.659908+08:00 阶段六更新：阶段六实施结束等待验收；1892清单中1890文件字节不变；target/tools.py与web/evidence.py两项限定源码差异已获用户明确批准。公开工具Schema与DIMENSIONS的AST哈希不变，原清单和原哈希完整保留；不将其描述为1892文件字节零差异。 阶段五未提交工作完整保留，未开始阶段七。提交推送、原11失败修复、真实数据接入均另行明确任务。


> 2026-11-01阶段五更新：阶段五交付待验收；旧版本39文件已提交Push到c889b082dd4bd07e3514038a69362b71dd21915c；阶段五源码/文档保持未提交。


> 2026-11-01阶段四更新：当前阶段四交付待验收；开发者实时Override、真实数据源、阶段五整页布局均未实施。新报告：docs/reviews/Ticket-Agent-V3.7-Phase4-User-Features-Report.md。

- 当前工作：阶段三已实现本人车次/日期匹配、单订单费用确认、卡片改签自动带入与事务复核；保持阶段二支付与全部历史证据。
- 最近完成并入库：P2 场景与逐轮断言、QwenCloud 配置校验、工作区时间线与开发者 LangSmith 面板、作品介绍与 Mock 截图，见第7节。
- 当前最小继续点：等待用户验收阶段三；阶段四与历史11失败分别另行明确范围，不自动启动。
- 未来每次重要功能、阶段、测试/验收、Provider/工具接入、架构调整、重要 Bug 修复、重要 Git 提交或新阻塞出现后，增量更新本文件的完成/未完成项、版本阶段、测试、Git、计划和风险。无需逐行代码更新。
- 每次更新前先查 Git，保护用户及并行修改；保留有价值的历史记录，旧结论注明过时范围并链接原证据。未知信息写“待核实”。未经用户批准不自动 Commit/Push/Merge。
- 本文件的维护是项目工作流程，不是已安装的后台任务；新对话仍需先读取本文件。本次不额外修改 AGENTS、README 或配置。

信息来源：本次用户维护要求、现场 Git、提交回执、现有失败报告。下一步尚待用户指定，不视为已获开发或联网授权。

## 5. 当前问题与阻塞

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：P0仍缺B当前103配套执行器；Snapshot缺合法原件/独立来源核验，Live缺接口权利与授权。原11失败及JSON组件Console问题保留。

> 2026-11-01T20:08:10.337492+08:00 正式103恢复审查：新增P0：BLOCKED_WAITING_FOR_ORIGINAL_B_EXECUTOR。旧6个judge模块与8份历史提交清单匹配，但当前103含42条旧实现不支持的trains_from_tools期望；禁止用旧版静默漏评。部分临时目录仍无读取权限。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：原11失败保持、T04未重验/批准场景0；缺B原始独立断言执行器，103仅配置与输入身份核验；真实模型风格/Embedding/远端LangSmith未重新验证；浏览器JSON查看组件12条Console错误尚未独立根因复验。


> 2026-11-01阶段五更新：原11失败/唯一Skip未变；无新增失败。实体手机软键盘和缺失image3参考未验，Streamlit DOM/桥接升级需复验。


> 2026-11-01阶段四更新：阶段四保留11旧失败/1 Skip；来源与最终逐ID对比见regression-comparison.json。旧历史和当前DB可不一致，中心显式禁写并要求再查询。真实API、全面滚动性能未验证；不可宣布全仓全绿。

| 优先级 | 问题/差异 | 证据与当前判断 |
|---|---|---|
| P0 | 最近指定完整回归11项失败 | 第6节完整报告；不能归为“测试全部过时”，也不能用历史全绿抵消 |
| P0 | Live既有实现与目标契约差异 | 用户已确认显式配置优先、按Provider/会话隔离费用；阶段1明确禁止改选择/授权逻辑，故百炼配置优先探测和旧checkbox等11失败仍在；本次仅补主问题/额外追问费用说明 |
| P0 | Qwen 历史/面板/导航及请求次数断言失败 | 涉及空历史提示、跨 Provider 展示与授权、集成中心切换和请求数；必须逐案分析，不能只更新文案断言 |
| 已补核（历史） | HEAD与工作区回归的对应关系 | 阶段0的505文件与旧回归曾完全一致；阶段1现有5个Web源码修改、2个新Python文件，已另建隔离源码清单和最终1098/11/1结果，不再把旧505一致性作为当前工作区状态 |
| P0 | 队长附件1102/8缺少原始证据 | 用户确认没有报告原件，旧E:路径不存在；其源码SHA、范围、失败项、skip和环境均无法核实，不接受“8项都是环境问题”或失败≤8验收 |
| 已解除（阶段1.2） | 浏览器条件 | 阶段1.1 已用 Edge 156 + Playwright 1.64.1 完成真实浏览器验收；阶段1.2 修复移动端侧栏/输入框后四规格 43/43 通过。原“MODULE_NOT_FOUND/未声明视觉验收”仅适用于阶段1.1前状态 |
| P1 | README/旧审计/说明存在过时表述 | README 仍写追问等“未提交”，Git 已有相关提交；旧不限额报告写 Live 只读、默认4工具，而较新说明和当前源码支持模拟八工具、默认8工具上限。不将旧说明套用于新路径 |
| P1 | RAG1000仍非完整验收 | 430来源/规则核验、570待语义复核；旧千题手册记误召回150/150，较新作品介绍及用户交接记121/150。批次/源码对应关系待核实，不覆写任一原值 |
| P1 | 历史全文忠实度不能标通过 | V3.5.2 DeepSeek/Qwen 两份审计均为 INDETERMINATE；指标数学无误不等于回答质量通过 |
| P1 | Live 修复缺少后续真实对照 | V3.6 报告记录 Qwen 取消未完成、跨轮审计及 RAG 订单绑定后置修复仅离线验证；不推断当前已解决 |
| P2 | P2 批次范围与交接简述不同 | 交接强调70候选/14响应；现场四批目录及 PoC 汇总记录280候选/56请求。70是其中一批，不覆盖原始证据；原始逐请求去重及全部原文哈希未重审 |

现场枚举部分 `artifacts/runtime` 临时目录返回拒绝访问；未尝试更改权限或清理，因此未完整清点全部运行目录。来源：现场读取错误及各行引用；没有发现必须马上修改代码才能建立本文档的阻塞。

## 6. 测试结果

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：本轮full-r6实际1356/11/1、199子测试，新增45全通过；原11/Skip ID逐项不变；阶段二40/三59/四45/五9/六60保持。Edge四规格120/120、32图；均隔离Mock/合成测试，非B正式、非真实API。

> 2026-11-01T20:08:10.337492+08:00 正式103恢复审查：本次未运行Agent/原始judge/pytest，正式有效计分0，103条NOT_RUN_BLOCKED；PASS/FAIL/SKIP未产生，不能当103 Skip。阶段六历史1311/11/1、199子测试及Edge60/60保持，未改成绩。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：新增离线完整结果：1311 passed / 11 failed / 1 skipped / 199 subtests，60新项全通过；阶段二40/三59/四45/五9保留。命令run_checks.py full-r10，证据artifacts/runtime/v37-phase6-baseline-override-20261101/full-r10/summary.json、junit.xml。四规格Edge60/60，28截图；不属于真实API/人工验收或103重新计分。


> 2026-11-01阶段五更新：阶段五最终离线full-r4：2026-11-01T06:52:07.471995+00:00至2026-11-01T06:54:16.750244+00:00，1251/11/1、199子测试；新9/原40+59+45通过；Edge DOM38、交互32、业务72，共142/142，72截图。均为隔离Mock/SQL/浏览器，非真实模型/API或人工验收。


> 2026-11-01阶段四更新：阶段四最终离线完整回归：2026-11-01T06:03:34.241635+00:00至2026-11-01T06:05:44.626761+00:00，1242 passed / 11 failed / 1 skipped / 199 subtests；新45、原支付40、原退改59全部通过。Mock Agent与AppTest/SQL/Edge均为隔离本地，非真实API/模型成绩；人工验收待用户。证据：artifacts/runtime/v37-phase4-user-features-20261101/full-r10/summary.json及JUnit；四规格72/72+24/24与40截图见browser/navigation JSON。

阶段1已在隔离副本实际执行测试，新增结果见本节后部；下表原历史结果保留。日期均按Asia/Shanghai；未记录的数量不补0，不同范围、源码、环境、子测试及历史批次不得相加。

| 类别/测试 | 执行时间 | 通过 | 失败 | 跳过 | 证据及限制 |
|---|---|---:|---:|---:|---|
| 离线：指定完整 pytest | 2026-10-31 21:24:29–21:26:33 | 1092 | 11 | 1 | `artifacts/runtime/commit-current-20261031-212140/regression-report.json`；197子测试通过、0子测试失败；A自测，非B正式成绩 |
| 离线：选择性代码范围回归 | 2026-10-31 21:28:32起 | 158 | 0 | 1 | 同目录 `selected-report.json`、`selected-verification/junit.xml`、`commit_current.py`；62子测试通过。JUnit总节点221含子项，不能写成221项通过；排除六个前端文件，非最终完整回归 |
| Mock：B历史双引擎快照 | 2026-10-20，具体时刻待核实 | Legacy 101/101；LangChain 100/100（历史说明） | 待核实 | 待核实 | 作品介绍文档及 `web/datasets/`；历史SHA `0af2712276258fee02573da33688a836738814c6`；103独立用例、201次执行，不是201不同用例；原报告本次未逐条重审 |
| 真实模型：八工具模拟业务 | 2026-10-28，具体时刻见原记录 | 不作总通过数 | 含政策忠实度失败 | 未汇总 | `docs/handoff/八工具Live模拟购票说明.md`、`artifacts/runtime/full-live-20261028/`；两模型完整流程有证据，DeepSeek政策轮 `rag_answer_inconsistent` 保留 |
| 真实模型：V3.6专项 | 2026-10-28阶段，精确时刻待核实 | 未统一汇总 | Qwen取消前置失败等 | 未汇总 | `docs/handoff/v36/A_V3.6_真实Live专项复验报告.md`、`artifacts/runtime/v36-stabilization/live/` |
| 真实API：V3.5.2模型/Embedding | 2026-10-26，逐请求见原账 | 9次HTTP200 | 非业务通过统计 | 不适用 | `docs/handoff/v352/V3.5.2_API预算与真实验证记录.md`；5次Embedding+4次生成，不能写9项质量通过 |
| 人工/浏览器验收 | 2026-10-28等历史记录 | 未汇总 | 未汇总 | 未汇总 | 八工具说明有本机浏览器操作记录；作品介绍含Mock截图。本次未打开浏览器复验，不代表最终人工验收通过 |

完整报告失败分布：`tests/test_deepseek_direct_send.py` 3项、`tests/test_followups_continuous.py` 1项、`tests/test_followups_mvp.py` 1项、`tests/test_qwen_langsmith_ui.py` 5项、`tests/test_unlimited_live_ui.py` 1项。

完整批次：status=failed；RAG附加步骤和性能步骤未执行；启动检查、原文件保护步骤报告通过；模型请求关闭、外部连接受阻断、拦截尝试0。报告源码指纹 `7991993de4b896e08e3c6cd29ee094e27117105ae515f224e74b08524e1c6491`，测试集指纹 `fdfc27d0cd78c32889042e4f39cc23838cf5711d4fb54a743ebdf52a168be0c5`。这些是原报告值，本次未重建指纹。

RAG历史：V3.5.2指标重算无数学错误，原值不改；DeepSeek完整回答审计6 supported/4 indeterminate，Qwen为7/3，最终均 INDETERMINATE。千题较新记录的无答案误召回仍121/150，不能称达标；真实Vector/Hybrid及千题回答质量未完整验证。来源：`docs/handoff/v352/audit/`、`docs/architecture/RAG千题评测手册.md`、作品介绍及用户交接。

阶段0补核（2026-10-31）：未执行新测试。原完整回归唯一skip为 `tests/test_p2_scenarios.py::test_no_approved_p2_scenarios`（无人类批准场景）。B manifest的7份文件哈希均匹配；读取原记录确认Legacy101通过/0失败、X17/X18不适用，LangChain100通过/0失败、X15/X16/T19不适用，均为历史快照，非当前重跑。七维度目录数：功能15/工具25/RAG15/多轮12/安全18/边界12/性能6。机器核查记录见 `artifacts/runtime/v37-phase0-20261031-review/audit.json`。

阶段1实测（2026-11-01；A离线自测，非B正式重跑）：

| 批次 | 通过/失败/跳过 | 子测试 | 证据（共同根artifacts/runtime/v37-phase1-20261101/） |
|---|---|---|---|
| 修改前首次完整 | 1056 / 47 / 1 | 197通过 | baseline/summary.json；36项因系统pytest临时目录权限在setup失败，原11失败保留 |
| 修改前隔离临时目录复跑 | 1092 / 11 / 1 | 197通过 | baseline/summary-r2.json；保留首轮，不改测试或系统目录 |
| 新阶段1专项首轮 | 5 / 1 / 0 | 2通过 | candidate-r1/summary.json；发现乘客列表显示为JSON后修正展示 |
| 修改后完整中间轮 | 1093 / 16 / 1 | 199通过 | candidate-r2/summary.json；5项新增展示兼容问题逐案修正，未改旧断言 |
| 最终完整，00:27:16–00:29:22 +08:00 | **1098 / 11 / 1** | **199通过、0失败** | candidate-r3/summary.json及snapshot/ticket-agent/artifacts/runtime/phase1-full/ |

最终新增6项通过；失败/skip完整ID集合与修改前r2完全相同，见comparison.json。阶段1测试6、LangSmith面板11、读取核验27、多轮授权12均通过，已包含在总数中；未执行真实API/浏览器验收。不以新总数覆盖旧基线或宣称全绿。

阶段二实测（2026-11-01，A隔离自测）：`artifacts/runtime/v37-phase2-payment-20261101/full-r4/`，1138 passed / 11 failed / 1 skipped / 199 subtests；新增40项全通过，原失败/skip逐ID一致、0移除测试。Edge四规格108/108通过；不替代B正式或真实支付验收。

阶段三实测：`artifacts/runtime/v37-phase3-refund-reschedule-20261101/full-r3/`，1197 passed / 11 failed / 1 skipped / 199 subtests；59新增全通过，阶段二40项保留通过，原失败/skip逐ID相同、0移除。四规格业务96/96，外部图标资源错误另列原始日志；不替代B成绩。

## 7. Git 提交记录

> 2026-11-01T23:04:35.523087+08:00 归档任务：用户明确授权提交并推送全部未提交代码；阶段五/六/七源码、固定Fixture、测试和交付文档一并归档，运行产物/数据库/账本不提交。准确SHA与远端回执见本节后续记录。

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：HEAD仍c889b082dd4bd07e3514038a69362b71dd21915c，原分支、暂存区空；阶段五/六/七工作未提交，不自动Push/Merge。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：本阶段Git HEAD仍c889b082dd4bd07e3514038a69362b71dd21915c、原分支，暂存区空，无Commit/Push/Merge；阶段五与阶段六改动均保留未提交。


> 2026-11-01阶段五更新：阶段一至四单个归档Commit c889b082dd4bd07e3514038a69362b71dd21915c，正常推送origin当前分支并核验远端同SHA；阶段五未提交/推送，暂存区空。


> 2026-11-01阶段四更新：阶段四无新Commit/Push/Merge；当前HEAD仍139cdbe2fca8c7249847f245cffef1ed0545dd36，branch仍feat/ticket-agent-v36-stabilization，暂存区空，阶段1至4修改保留工作区。

下列提交均在当前分支历史中；不等于每条提交当时都使用此分支名。推送状态以现场本地引用和历史回执为依据，未联网查询。

| Commit | 时间（+08:00） | 提交说明 | 推送证据 |
|---|---|---|---|
| `139cdbe2fca8c7249847f245cffef1ed0545dd36` | 2026-10-31 21:33:05 | docs: add competition introduction and real Mock screenshots | 历史推送回执确认此SHA；现场远端跟踪引用同SHA |
| `d7bfec68af43b80ee5772a821dd5c099fce9fb5a` | 2026-10-31 21:33:04 | feat: save workspace timelines and developer LangSmith panel | 属于上述HEAD祖先；远端实时状态未核验 |
| `e29fa099c3c7b3453e50116663f5b18b68fdc6ba` | 2026-10-31 21:33:03 | fix: validate QwenCloud key and endpoint configuration | 同上 |
| `f188716eed2f3a05bc45b107a6b0f9665d9291e7` | 2026-10-31 21:33:02 | feat: add P2 scenario generation and per-turn assertions | 同上 |
| `6b101a1ce7b72d78356545fee8f6aeebd9bba7ce` | 2026-10-31 01:52:52 | fix: correct Live authorization and RAG evidence validation | 当前祖先；旧完整ZIP基线及完整报告记录SHA |
| `d4f944a0f6671896408170766063dc71368d0130` | 2026-10-30 22:28:14 | feat: unify Agent execution traces and session replay | 当前祖先，实时远端未核验 |
| `ae87af2bde99fc00aa57804162770981ec006225` | 2026-10-30 12:50:47 | feat: save V3.7 workspaces, RAG evaluation and follow-ups | 当前祖先；README“未提交”文字须按历史语境阅读 |

历史回执：`artifacts/runtime/commit-current-20261031-212140/push-receipt.json`，核验时间2026-10-31 21:37:15 +08:00，local/remote均为当前SHA，未force push、未合并main、未推标签。本地跟踪分支为 `origin/feat/ticket-agent-v36-stabilization`。

现场标签：`handoff-a-20261012`、`handoff-a-v2-20261013`、`handoff-a-langchain-v3-20261013`，均须保护。本次只新增本文档，未暂存/提交/推送。来源：Git log/status/tag及上述回执。

## 8. 真实 API 与预算

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：本轮真实12306/模型/Embedding/LangSmith/交易请求0；仅本机测试连接，历史账本无变；不把替身或合成数据记作真实消耗，未知费用保持未知。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：本阶段模型/Embedding/LangSmith/12306/真实支付请求均0，SDK MockTransport不收费；未知Token/余额不补0。用户批准账本追加8249字节为当前259169字节基线，阶段内未变。


> 2026-11-01阶段五更新：本任务仅GitHub fetch/push/ls-remote联网；真实模型/Embedding/LangSmith/12306/交易请求0，无新增真实Token费用，无额度查询。账本获准追加仍保留，不作为本任务请求。


> 2026-11-01阶段四更新：阶段四模型/Embedding/LangSmith/12306/真实交易请求均0，无本阶段真实Token消耗；剩余额度未联网查询。用户确认保留账本开工前追加6890字节，原内容完整；以当前账本为保护基线，追加不计为阶段四调用。证据preflight-ledger-difference.json与用户明确答复；用量统计非阻断，不改变既有轮数/工具/超时/零重试/确认限制。

当前策略：累计Live请求预算已取消，为非阻断用量统计；不等于服务商余额无限，也不授权本次联网。历史额度用尽的文档是当时批次状态，不恢复为当前累计准入限制。

| Provider/历史范围 | 真实请求数 | 输入/输出Token | 费用/余额 | 证据 |
|---|---:|---|---|---|
| 本次状态文件建立 | 模型0、Embedding0、LangSmith0 | 无新增远端用量 | 本次无远端请求；账户余额未知 | 本次操作范围与工具记录 |
| V3.7阶段1实施/隔离回归 | 模型0、Embedding0、LangSmith0 | 仅离线替身记录，不算真实Token | 无本阶段远端请求；账户余额未知 | artifacts/runtime/v37-phase1-20261101/；清除凭据、关闭追踪、外部socket守卫 |
| DeepSeek，Live实验室批次 | 31 | 28632 / 3740 | 未知 | `docs/handoff/live_lab/真实API请求与Token用量报告.md` |
| 百炼，Live实验室批次 | 35 | 32124 / 4427 | 未知 | 同上；原证据 `docs/evidence/live_lab_20261027/` |
| DeepSeek，八工具批次 | 37 | 90641 / 3958 | 未知 | 八工具说明；`artifacts/runtime/full-live-20261028/usage/` |
| Qwen，八工具批次 | 20 | 48331 / 2180 | 未知 | 同上 |
| DeepSeek，V3.6批次 | 18 | 42727 / 1690 | 未知 | `docs/handoff/v36/V3.6_API真实请求与Token审计.md` |
| Qwen，V3.6批次 | 23 | 57096 / 2336 | 未知 | 同上；`artifacts/runtime/v36-stabilization/live/` |
| DeepSeek，P2四批生成 | 56（每批14） | 158832 / 48251 | 未知 | `artifacts/runtime/p2-poc-20261030/poc_report.json`、`artifacts/runtime/p2-gen/` |
| text-embedding-v4，V3.5.2批次 | 5 | 输入504；输出不适用 | 未知 | V3.5.2 API报告；1024维，另有两Provider各2次生成，见原报告 |

上述数字为已读取报告的批次值；未重新核对全部原始HTTP记录，批次重叠与共享日志尚未全局去重，**不提供项目累计总数**。服务商实际消耗、剩余金额及账户配额均待核实。原账、Trace和真实回复不重写。

统计入口：`target/api_usage.py`、`target/request_accounting.py`；默认 `artifacts/runtime/api-usage/<provider>/<namespace>/requests.jsonl`，可由 `TICKET_API_USAGE_DIR` 配置。必须按request_id去重并区分real_api/offline_stub/cache；未知Token/费用不能填0，HTTP200不等于业务成功。

执行保护仍存在：单轮模型轮数默认3、工具上限默认8、超时、安全区间、SDK零自动重试、身份及写操作确认。准确生效值取决于Provider/配置，不能为了取消累计预算删除这些保护。来源：当前runtime源码、`config.py`及不限额迁移报告。本文禁止保存API Key、密码或其他凭据。

阶段二用量补记：本阶段模型、Embedding、LangSmith、12306和真实支付请求均为0，无新增远端Token/模型费用；Provider账户余额仍未知。仅安装qrcode时访问包分发源，浏览器48次外部图标请求已拦截。证据见阶段二目录的安装回执、网络守卫与browser-verification.json。

阶段三用量：模型/Embedding/LangSmith/12306/真实支付退款请求均0，未新增依赖；账户余额未知。

## 9. 下一步开发计划

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：P0验收阶段七离线结果及提供B配套原件；Snapshot待用户提供合法真实原件/来源证明后再离线导入验收；Live需接口权利/网络范围及另行授权，默认禁用。不自动进入下一阶段或提交。

> 2026-11-01T20:08:10.337492+08:00 正式103恢复审查：P0：取得B当前103配套judge/cases原件、执行器Commit或交付包SHA、依赖锁/原命令，再验证trains_from_tools/C5及Baseline隔离后独立重计分；验收须有103逐项原断言证据，禁止A自行补写C5冒充B。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：P0：验收阶段六离线工程结果（标准：60新增项、失败/Skip集合不变、保护零差异）；独立处理11失败及B原始执行器取得后正式重计分。P1：用户明确授权后设计阶段七Fixture优先与来源边界，授权联网前不请求。P2：Live风格/远端追踪再验与既有RAG千题待复核，单独预算授权。


> 2026-11-01阶段五更新：P0：验收阶段五视觉/真实DOM数据及旧11失败；P1：明确是否归档阶段五，实体手机补验与DOM升级检查；P2：阶段六实时Override等须另行授权。


> 2026-11-01阶段四更新：P0：用户验收阶段四及现存11失败逐项产品契约。P1：获准后再做阶段五布局/固定输入框/移动端四规格验收。P2：开发者Override/真实数据源分别按后续授权执行；不改正式103用例或成绩基线。

当前阶段覆盖：P0等待用户验收阶段三及保留11失败的契约处理；P1仅在用户确认后设计阶段四；P2继续保留RAG/评测长期待验证项。下列旧计划是历史规划，不自动授权执行。

以下为建议待办，不构成自动开发、运行测试或联网授权。

| 优先级 | 目标 | 验收标准 |
|---|---|---|
| P0 | 明确默认模型、Live发送及历史会话交互契约 | 与用户确认预期，逐项映射11个失败；保留旧判据和新契约差异，不笼统宣布测试过时 |
| P0 | 按契约修复实际回归并建立最终源码证据 | 用户授权后实施；定向检查及必要完整离线回归使用全新目录、源码/测试指纹、结构化失败和原文件保护记录；实际结果如实更新本文 |
| P0 | 闭合当前HEAD与历史回归的源码对应关系 | 对照回归副本清单及提交回执，明确哪些源码被覆盖、哪些未覆盖；不能以37文件哈希一致替代完整证明 |
| P1 | 梳理版本、README及历史说明的适用范围 | 保留旧记录，标明3.7界面/V3.6分支差异、已提交状态、只读与八工具沙箱适用路径；文档调整须另获任务授权 |
| P1 | RAG质量及真实验证缺口清单 | 定位121/150原始批次；完成570条人工语义复核计划；Vector/Hybrid缺缓存时明确blocked，不自动生成向量；回答质量独立验收 |
| P1 | 规划Live修复后的最小复验 | 明确Provider、场景、请求范围、证据目录及验收判据；用户显式授权联网后才执行，区分工具/业务/回答结果 |
| P2 | P2具名审核及逐案失败归因 | 保护四批原始候选/响应/review；批准仅由具名人工完成，自动校验及沙箱通过不能替代批准 |
| P2 | 当前交付包与用量索引完善 | 新包关联明确SHA及证据范围；旧ZIP保留历史身份；用量先按请求去重，未知费用保持未知，不自动打包或上传 |

信息来源：第5、6、8节证据及用户交接建议；本节全部为未完成事项。

阶段0进展：上表“源码对应关系”已完成505文件哈希核对（0差异），原待办保留历史。当前按用户指定阶段0→1→2→3→4→5→6→7推进；本次仅交付阶段0报告，等待确认，不执行原计划中的修复。阶段1需限定真实数据尚未接入时的客户文案及费用交互；阶段6完成Baseline/Override隔离后才进入阶段7。详见改造前技术审查报告第10、13、14节。

阶段1进展：本次已按用户确认契约完成文案与信息分层及离线验收；下一步等待交付确认，讨论阶段2演示二维码的展示/确认语义及浏览器验证条件。未获准前不开始阶段2；旧11失败、模型优先级和授权行为不在本阶段修改范围。

## 10. 已知风险与注意事项

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：普通旧演示库保留会话日期/库存，严格Baseline/Test固定Fixture/时钟；Snapshot绝不回落/灌演示库存，新锁座建单改签等需切回Fixture重新查询。来源声明/格式/hash不等于真实采集证明。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：配置SHA是完整性旁证，不是账户认证；本地固定模拟身份不变。旧无sidecar历史不补造；新legacy_runtime不作为正式Baseline；待确认提案配置变更须取消重生成，禁止沿用旧费用/写确认。


> 2026-11-01阶段五更新：新增视口和旧iframe回调失效风险已复现并修复，透明工具栏遮挡已通过真实点击复验；仍依赖Streamlit1.65 DOM。历史业务/RAG/固定身份风险保留。


> 2026-11-01阶段四更新：阶段四：演示业务边界保持；历史快照不等于最新交易；无记录的支付方式/金额不补造；page支付审计非原支付事务组成部分，失败提示不可自动重付；离线图标错误原始记录保留。保护历史清单仅获准账本追加例外，其余零差异。

- 禁止reset、clean、stash、强制覆盖、擅自清理或回滚并行修改；编辑前查工作区。本次不修改无关代码。
- 保护 `docs/evidence/`、`web/datasets/`、`data/rag1000/`、原始Trace/真实回复、SQLite/Chroma、预算账本及用量日志；不原地打开冻结索引或覆盖历史报告。
- 保护B正式断言、P0复测包、原V3.6输入包、冻结RAG缓存、V1/V2/V3标签，以及P2原始70候选/14响应所在批次和其他已发现批次、review与approved；禁止自动批准。
- 公共十字段和工具五字段契约不擅改。模型提议、拦截、实际执行、工具成功、业务成功必须分别记录；stop不等于业务成功。
- Mock、离线HTTP替身、缓存重放、真实生成、真实Embedding、LangSmith及人工验收分开陈述；不能用历史1088/1097等通过数宣称当前全绿。
- 不限累计预算不取消防循环、超时、零重试和身份/写确认；超时可能已计费，未知Token不是0。统计日志非可靠完整账单。
- 最新代码仍有环境依赖行为，如配置影响默认模型；本次未读取密钥值，不确认本机凭据有效性。
- LangSmith展示/导出有独立授权边界；本地历史恢复不应重发模型请求，不补造旧事件或内部思维链。
- RAG指标数学审计、引用命中和全文忠实度是不同结论；430核验不等于1000全部人工审核，旧48题高分不代表千题通过。
- 旧完整ZIP `artifacts/deliverables/Ticket-Agent-当前完整版-20261031-020528-6b101a1.zip` 属6b101a1时期工作区，不是当前HEAD；存在性/内容本次未重新解包核验，不作为最新交付。
- 部分运行目录无权限，未完整清点全部历史；共享日志可能被并行进程追加，不能擅自归因或回滚。
- 未经用户批准不自动Commit/Push/Merge；真实API/联网/开发范围以新任务明确授权为准。本文只含非敏感元数据。

信息来源：用户安全与维护要求、现场检查、接口契约、当前源码及历史审计/迁移报告。上述保护要求长期保留。

阶段三进度：P0等待验收并保留11旧失败；P1用户确认后才设计阶段四；原计划保留历史，不自动授权。

## 11. 重要文件索引

> 2026-11-01T21:12:17.300021+08:00 阶段七更新：docs/reviews/Ticket-Agent-V3.7-Phase7-Train-Data-Source-Report.md；artifacts/runtime/v37-phase7-train-data-source-20261101/verification.json、source-inventory.json、fixture/snapshot/provenance/isolation-verification、regression-comparison、git-final-state、browser-verification及Skills/JUnit/原件/截图/停止记录。

> 2026-11-01T20:08:10.337492+08:00 正式103恢复审查：docs/reviews/Ticket-Agent-V3.7-Formal-103-Executor-Recovery-Report.md；artifacts/runtime/v37-formal-103-regrading-20261101/verification.json、inventory.json、provenance-audit.json、case-integrity.json、execution-gate.json、eval-audit-findings.json、environment.json及全部原始搜索stdout/stderr。

> 2026-11-01T18:21:44.283615+08:00 阶段六更新：阶段六索引：docs/reviews/Ticket-Agent-V3.7-Phase6-Baseline-Override-Report.md；artifacts/runtime/v37-phase6-baseline-override-20261101/verification.json、before-approved.json、protection-check.json、regression-comparison.json、skill-audit.json、code-eval-spec.json、skills-usage.json、browser-verification.json、四份*-config-evidence.json及browser-r8/server-stop.json。


> 2026-11-01阶段五更新：阶段五：web/user_layout.py/css、tests/test_phase5_layout.py；报告docs/reviews/Ticket-Agent-V3.7-Phase5-UI-Redesign-Report.md、Pre-Phase5-Git-Archive-Report.md；核验artifacts/runtime/v37-phase5-ui-redesign-20261101/verification.json。


> 2026-11-01阶段四更新：阶段四新增target/order_read_model.py、web/user_features.py、tests/test_user_features.py；报告docs/reviews/Ticket-Agent-V3.7-Phase4-User-Features-Report.md；核验artifacts/runtime/v37-phase4-user-features-20261101/verification.json及相关原始证据。

阶段二：`target/payment_qr.py`、`target/demo_payment.py`、`web/payment.py`、`tests/test_payment_qr.py`；报告`docs/reviews/Ticket-Agent-V3.7-Phase2-Payment-QR-Report.md`；证据`artifacts/runtime/v37-phase2-payment-20261101/`。

以下为相对项目根目录的路径，原件是证据权威来源。

| 类别 | 路径 |
|---|---|
| 状态与基础说明 | `PROJECT_STATUS.md`、`README.md`、`先读我_团队交接.md`、`启动说明.md`、`docs/contract.md` |
| V3.7阶段0技术审查 | `docs/reviews/Ticket-Agent-V3.7-改造前技术审查报告-20261031.md`；`artifacts/runtime/v37-phase0-20261031-review/` 内audit.json、protected-before.json、verification.json |
| V3.7阶段1实施 | `docs/reviews/Ticket-Agent-V3.7-Phase1-Implementation-Report.md`、`web/user_copy.py`、`tests/test_phase1_user_copy.py`、`artifacts/runtime/v37-phase1-20261101/` |
| 启动/依赖 | `启动_离线模式.cmd`、`启动_在线模式.cmd`、`scripts/Start-TicketAgent.ps1`、`requirements-v35-lock.txt`、`config.py`、`.env.example`（仅模板） |
| Agent/Provider | `target/agent.py`、`target/langchain_agent.py`、`target/deepseek_runtime.py`、`target/bailian_runtime.py` |
| 业务与授权 | `target/tools.py`、`target/write_authorization.py`、`target/business_state.py` |
| RAG与追问 | `target/rag_service.py`、`target/rag_faithfulness.py`、`target/rag_protection.py`、`target/embeddings.py`、`target/followups.py` |
| 审计/用量 | `target/run_events.py`、`target/api_usage.py`、`target/request_accounting.py`、`traces/` |
| Web | `web/app.py`、`web/runtime.py`、`web/conversation.py`、`web/developer_workspace.py`、`web/langsmith_panel.py`、`web/competition_view.py`、`web/evidence.py`、`web/session_store.py` |
| P2 | `target/p2_case.py`、`target/p2_executor.py`、`target/p2_review.py`、`scripts/p2_*.py`、`docs/architecture/P2_AI测试场景生成方案.md`、`artifacts/runtime/p2-gen/`、`data/p2_scenarios/approved/` |
| 千题 | `data/rag1000/v1.1.1/`、`docs/architecture/RAG千题评测手册.md`、`artifacts/runtime/rag1000-development/final-verification.json` |
| 当前回归入口/失败测试 | `scripts/regression_center.py`、第6节五个测试文件；P2与QwenCloud专项见 `tests/test_p2_*.py`、`tests/test_qwencloud_endpoint.py` |
| 本轮交接前提交与回归 | `artifacts/runtime/commit-current-20261031-212140/` 内 `regression-report.json`、`selected-report.json`、`commit-receipt.json`、`push-receipt.json` |
| 历史审计/交接 | `docs/handoff/v36/`、`docs/handoff/v352/audit/`、`docs/handoff/unlimited-live/`、`docs/audit/技术审计报告-20261030.md`、`docs/handoff/Ticket_Agent_作品介绍文档.md` |
| 受保护正式/历史材料 | `docs/evidence/`、`web/datasets/`、`data/rag1000/`、`artifacts/` 下原包/缓存/运行证据；不作全目录完整性已验证声明 |

实际一级目录：`target/`、`web/`、`tests/`、`scripts/`、`cases/`、`data/`、`docs/`、`traces/`、`artifacts/`；另有四个历史venv、`__pycache__/`、`_p0probe/`、`.dsh-vision-toolkit/`、`.git/`。`data/` 含policies、v37、rag1000、p2_scenarios；文档含architecture、handoff、evidence、audit、showcase。不是所有目录均受Git跟踪，不清理任何目录。

信息来源：现场目录枚举、文件路径检查与前述引用。根交接文件仅索引，未把所有历史文档逐篇重审。

阶段三索引：`target/order_refund.py`、`target/reschedule.py`、`web/order_actions.py`、三新测试文件；报告`docs/reviews/Ticket-Agent-V3.7-Phase3-Refund-Reschedule-Report.md`；证据`artifacts/runtime/v37-phase3-refund-reschedule-20261101/`。

## 12. 最近更新记录

### 2026-10-31：首次建立长期状态文件

- 完成：重新核对Git分支/HEAD/最近12条提交/工作区/本地远端引用/标签、一级目录、架构入口、依赖版本记录、README、相关交接/审计及现存测试报告。
- 完成：读取历史推送回执；提交回执列出的37个文件与当前文件SHA256一致（0差异），但没有扩大为完整源码/全部证据一致性证明。
- 完成：记录11项完整回归失败、选择性通过范围、版本/文档/P2/RAG证据差异，建立计划及长期维护规则。
- 修改文件：仅新增 `PROJECT_STATUS.md`；没有修改已有源码、测试、配置、原始报告或数据；未暂存/提交/推送。
- 测试：未运行任何测试；本次仅文档建立和只读核对。历史完整结果仍为1092通过、11失败、1跳过、197子测试通过。
- 待核实：统一发布版本；当前HEAD完整回归对应关系；11失败的产品契约与根因；实时远端；全局API去重用量/费用/余额；121/150原始批次；千题Vector/Hybrid和回答质量；570条人工复核；当前Live修复复验；全部历史文件完整性及最终人工验收。
- 后续：等待用户指定下一项工作。重要进展后增量更新本文12节，保留原始证据和必要历史，不因建立状态文件启动新功能开发。

信息来源：本次本地只读核对、用户要求及创建本文的文件变更；最终Git状态另在本次交付回复展示。

### 2026-10-31：V3.7改造阶段0技术审查

- 阶段：仅阶段0；报告交付后等待确认，未开始文案、二维码、业务、布局、Override或真实数据实现。
- 现场Git：仍为feat/ticket-agent-v36-stabilization / 139cdbe2fca8c7249847f245cffef1ed0545dd36；开始时仅已有未跟踪PROJECT_STATUS.md，不覆盖或提交它。
- 完成：读取两份外部需求附件，确认D:当前仓库、E:旧路径不存在；用户确认1102/8无原始报告，其“环境问题”归因不采信。
- 完成：原回归505文件SHA256与现场一致、0差异；B快照7份manifest哈希匹配；1892个正式数据/证据/测试/P2/工具/维度文件建立保护清单。范围不等于全部运行数据库完整性验证。
- 结论：固定Fixture优先、Baseline/Override隔离、Grid/Flex布局方向适用；不能简单替换查询源、保存JSON不更新执行器、或以局部height修补代替完整布局。
- 现状纠正：输入框已经在历史滚动容器之外；种子热点线路有意售罄；改签后不退是原P01/P02/P03约束；开发者配置当前只读；现有历史恢复只读，不恢复旧操作授权。
- 测试：本次未运行，仍引用历史1092通过/11失败/1跳过、197子测试通过。无新Trace；模型/Embedding/LangSmith请求均0；未联网/启动服务。
- 浏览器：Edge已安装、Streamlit1.65.0；Playwright项目解析/当前运行时加载未成功，未作依赖安装；实时DOM和1600×1100、390×844深浅四规格新截图未验证，不声明UI验收通过。
- 文件：新增阶段0技术审查报告与独立审查JSON产物，增量更新本文；源码/配置/测试/正式历史数据不修改；未Commit/Push/Merge。
- 遗留：默认模型/费用确认/客户来源文案/改签政策/两主空间与测试控制台关系需确认；B完整独立执行器入口、当前实时DOM/浏览器验证链、1102/8历史归属仍未闭合。后者因无原件不能补造。
- 下一步：用户确认报告与阶段1范围后才开工；UI验收前补齐隔离Playwright+Edge条件。详细证据、11项失败逐案分析和七个问题答复见报告。

### 2026-11-01：V3.7阶段1文案与技术信息分层

- 阶段：实现和隔离离线验收完成；浏览器视觉验收未完成；已停止，未进入阶段2。
- 修改：web/app.py、conversation.py、presentation.py、demo.py、developer_workspace.py；新增web/user_copy.py及tests/test_phase1_user_copy.py；更新本文、新增阶段1报告。原阶段0报告不改。
- 用户变化：主导航区分用户/开发者空间和独立测试控制台；模型设置收进高级折叠区；车票/订单/政策附近显示演示来源、非真实出票/扣款；确认参数为中文；政策/追问/错误原始诊断在开发者端查看。
- 保持：58个显式控件key、session_state名和内部路由不改；原核心Prompt、八工具Schema、Provider选择、授权、支付/退票/改签规则、CSS/滚动布局和LangSmith上传/GET实现不改。
- 测试：修改前隔离临时目录后1092/11/1；最终1098/11/1、199子测试通过。新增6项通过、2个通过子项，失败/skip集合不变。首轮临时目录权限错误及中间5项新增失败均留原证据，未改旧测试或增加skip/xfail。
- 保护：原103用例/B快照和1892保护文件不修改；核查见scope-checks.json及最终verification.json。清单不代表全盘历史库完整性证明。
- 证据：artifacts/runtime/v37-phase1-20261101/下各批source-manifest、summary、逐项结果、JUnit、日志；comparison.json比较失败ID；originals保存接手原件。
- 浏览器：本机Edge存在；Node项目环境无法解析playwright/playwright-core，未安装依赖、未生成截图，四规格及实际DOM/滚动行为均未验收。
- Git：仍为feat/ticket-agent-v36-stabilization / 139cdbe2fca8c7249847f245cffef1ed0545dd36；5个已有源码修改、2个新增Python文件及状态/报告保留工作区；未暂存、Commit、Push或Merge。
- 风险/下一步：当前全仓仍11旧失败，默认模型优先级/费用契约实际实现差异未修；原模型回复不重写。用户确认阶段1交付及未验收浏览器范围后，再明确阶段2演示二维码行为，不能把扫码当真实支付。

### 2026-11-01：V3.7 阶段1.1 浏览器视觉验收

- 阶段：仅浏览器视觉验收；未进入阶段2，未改产品代码。
- 环境：Microsoft Edge 156.0.4314.50；Playwright 1.64.1（本机 npm 缓存离线安装到 `artifacts/runtime/v37-phase1-browser-20261101/tools/`，不改项目依赖）；Node v24.15.0；Python 3.12.14；Streamlit 1.65.0；离线 Mock，端口 8513；真实模型/Embedding/LangSmith 请求 0。
- 启动：`TICKET_WEB_OFFLINE_ONLY=1`、`TICKET_DISABLE_LOCAL_SECRETS=1`、`AGENT_PROVIDER=mock`、`AGENT_ENGINE=legacy`；日志 `artifacts/runtime/v37-phase1-browser-20261101/app-start.log`。
- 结果：37 项浏览器检查，34 通过、3 失败。桌面 1600×1100 浅/深各 12/12；移动 390×844 浅/深各 9/12；主题 4/4；Console Error 0、PageError 0、请求失败 0（14 条 Chromium feature warnings，非项目异常）。
- 未通过：移动端首次加载侧栏 300px 展开遮挡聊天（`sidebar_default_covers_chat`/`fresh_chat_visible`）；移动端输入框初始 bottom=1124.47 > 844，需页面滚动才可见（`composer_in_viewport`）。输入框相对聊天容器位置稳定，桌面端固定通过。
- 功能差异：未发现独立“确认发送真实模型请求”费用授权勾选框；当前为费用提示+发送按钮，Embedding 联网仍有独立勾选框。阶段1若要求保留原费用授权控件，此项不满足，需确认。
- 证据：`artifacts/runtime/v37-phase1-browser-20261101/` 四规格截图、`verification.json`、`browser-info.json`、`dom-checks.json`、`input-metrics.json`、`console.json`、`function-summary.json`、`source-sha256.json`、`app-start.log`；报告 `docs/reviews/Ticket-Agent-V3.7-Phase1.1-Browser-Acceptance-Report.md`。
- 修改：仅新增验收目录、报告与本节；未改产品代码、测试、正式数据、历史 Trace/账本/B 快照/docs/evidence；未 Commit/Push/Merge。Git 仍为 `feat/ticket-agent-v36-stabilization` / `139cdbe2fca8c7249847f245cffef1ed0545dd36`，阶段1原有未提交修改保留。
- 结论：阶段1浏览器验收**未全部通过**；桌面端与主题通过，移动端两处布局问题需产品修复后再复验。未开始阶段2。

### 2026-11-01：V3.7 阶段1.2 移动端布局修复与授权核查

- 阶段：仅阶段1.2；完成移动端修复与复验；未进入阶段2，未开发二维码。
- 修改：`web/app.py` 将 `initial_sidebar_state` 改为 Streamlit 官方 `"auto"`（桌面展开、移动折叠）；`web/scroll_bridge.py` 增加 `scheduleFit()`，在首次挂载/resize 后延迟重算聊天可用高度；`web/conversation.py` 无净修改（SHA 与阶段1.1 一致）。
- 根因：侧栏被强制 `expanded`；聊天 bridge 的 `fit()` 在 Streamlit 布局完成前读取 `top=0`，写入 560px inline 高度，后续未重算。未新增固定高度，未改业务逻辑。
- 浏览器复验：Edge 156.0.4314.50 + Playwright 1.64.1，离线 Mock 8514；43/43 通过；桌面 12/12、移动 18/18、主题 4/4、功能 4/4、DOM 1/1、Console 4/4；Console Error/PageError/请求失败均为 0；真实模型/Embedding/LangSmith 请求 0。
- 移动实测：首次加载侧栏 x=-300/w=1；聊天 353.47/255.53；输入框 625–820（844 视口内）；历史滚动 top/mid/bottom 时输入框 y 恒 625；桌面输入框仍 830.69，布局未变。
- 授权核查：`6b101a1` 存在 Qwen 独立 checkbox；`d7bfec6` 已移除；阶段1 HEAD 无 checkbox，阶段1新增测试明确要求不增加额外 checkbox；旧 `test_qwen_still_requires_its_original_checkbox` 仍属保留的 11 失败。未恢复 checkbox，不修改测试，不伪造授权；风险与证据见 `authorization-contract.json`。
- 回归：`pytest tests` 得到 1098 passed / 11 failed / 1 skipped / 199 subtests；失败 ID 与阶段1.1 baseline 完全一致，新失败 0、已解决 0。首次从仓库根目录 pytest 误收集 artifacts 快照的 6941 collection error 已记录为范围错误，不认定为产品失败。
- 保护：未改 103 条正式用例、七维度、B 快照、1892 保护文件、历史 Trace/账本、原 11 失败记录、T04、批准用例 0；阶段1.1 报告与截图目录保留。
- 证据：`artifacts/runtime/v37-phase1-2-20261101/` 四规格截图、首次加载/侧栏/滚动截图、verification/browser/dom/input/console/layout/auth/regression/source SHA；报告 `docs/reviews/Ticket-Agent-V3.7-Phase1.2-Mobile-Fix-Report.md`。
- Git：`feat/ticket-agent-v36-stabilization` / `139cdbe...`；本阶段净改 app/scroll_bridge；阶段1原有未提交修改保留；未暂存/Commit/Push/Merge。
- 结论：阶段1移动端与输入框问题已修复，四种规格浏览器验收通过，可申请正式验收；等待用户确认后再进入阶段2。


### 2026-11-01T02:44:43+08:00：指定GitHub第三方Skills静态审计与项目级安装

- 范围：仅供应链/指令/适配性审计与PASS原版复制；不继续V3.7产品开发，当前版本及Phase1.2阶段结论保持。
- 来源：固定四仓库SHA；LangSmith d69a8fe41816c1faba25399e60301b79b747d147；Eval 80d5f7b0127c7572ed9e9339937adbfd7240ffeb；Anthropic ca45fc496a3436251f191354091d557da31c15b5；Playwright CLI 0a808078d96496cf2a8fa725143c870354f63cda。
- 结论：16个Skill为2 PASS、14 CONDITIONAL、0 REJECT；CLI另为CONDITIONAL，未安装。风险包括.env/云端上传与删除、非交互确认、远端安装、后台服务器、shell命令、索引重建和额外模型费用；不据此认定上游恶意。
- 实际安装：`.agents/skills/eval-audit/`、`.agents/skills/write-code-eval/`，均为上述Eval提交原版，4文件及原Apache-2.0 LICENSE共5文件哈希一致。无脚本/强制新依赖；原YAML隐式匹配设置保留，不扩大联网/写入/费用授权。
- 核验：1892保护文件0差异、103正式用例保持、7份B manifest及Phase1.2九份源码哈希通过；接手既有源码/测试/报告不改。本文仅追加；分支 `feat/ticket-agent-v36-stabilization` / HEAD `139cdbe2fca8c7249847f245cffef1ed0545dd36`、暂存区空；未Commit/Push/Merge。
- 验证命令：自写build_audit.py、install_pass_skills.py、finalize_audit.py（独立审计目录）；git diff --check。未执行第三方脚本、Skill功能、pytest或浏览器，本次功能测试计数不适用；保留历史1098/11/1、199子测试及43/43浏览器结果，未冒称新成绩。
- 网络/用量：仅公开GitHub元数据/固定源码和官方发现文档；无真实模型、Embedding、LangSmith业务、12306或支付调用，不配置API Key，不安装全局依赖。项目外下载仅独立临时目录。
- 证据：`docs/reviews/Ticket-Agent-GitHub-Skills-Security-Audit.md`；`artifacts/runtime/github-skill-security-audit/`七项JSON及静态扫描/源固定/安装尝试记录。首次复制在预检临时源ACL处失败、无安装写入；哈希核验后经审计暂存复制成功。
- 遗留：静态发现条件通过，宿主下一轮实际发现/调用未验证；第三方运行时/传递依赖/CVE未认证；CONDITIONAL项需另行明确数据/权限/费用范围再审。外部方法论不覆盖七维度、INDETERMINATE、A/B/Mock/Live与正式断言。
- 下一步：本任务完成即停止；继续产品阶段或启用暂缓Skill均等待用户明确任务。


### 2026-11-01T03:27:16+08:00：V3.7阶段二支付二维码与演示支付闭环

- 实现：方案B；qrcode/Pillow PNG显示在原订单卡片；扫码仅JSON识别，用户勾选后通过支付宝/微信/扫码确认三入口调用统一服务，均不真实扣款或出票。金额来自订单、单位元；无外部回调、token或新公开工具。
- 业务：原pay_order兼容旧调用；事务内核对预期金额/归属/状态，唯一demo_payments记录和paid状态一起提交；支付方式落库，重复/并发确认幂等；原orders列和退款/改签不改。
- 刷新：独立demo-payment-receipts.json用于只读展示，不重写公共Trace或Agent结果，不恢复旧操作授权；生成二维码/渲染/刷新/切换模型不会支付。
- 文件：新增target/payment_qr.py、target/demo_payment.py、web/payment.py、tests/test_payment_qr.py；改mock_core、web/runtime/conversation/presentation、两份requirements；更新本文和阶段二报告。保留阶段1/1.2其他修改与所有历史报告。
- 依赖：仅.venv-v35新增qrcode8.2（no-deps），Pillow12.3.0不升级；不安装浏览器/全局包。
- 命令：run_checks.py targeted-r1和full-r1/r2/r3/r4复用隔离机制，最终实际python -m pytest tests -q --tb=short；node browser_acceptance.js用既有Playwright+Edge离线验证。
- 测试：最终1138 passed / 11 failed / 1 skipped / 199 subtests，新增40项全通过；原11失败/唯一skip集合不变、无旧测试减少；前序29专项、1131/11/1、1133/11/1、1136/11/1全部保留。浏览器四规格各27/27，共108/108；PageError0；Console资源错误48/失败请求48均为被拦截的外部图标请求，未放行外网；20单DB回查一致。
- 保护：1892保护及3708接手历史产物0差异；103正式用例/B快照/七维度/SYSTEM_PROMPT/八工具Schema不改；A自测不混入正式成绩；支付不统计为真实业务成功。
- 证据：docs/reviews/Ticket-Agent-V3.7-Phase2-Payment-QR-Report.md；artifacts/runtime/v37-phase2-payment-20261101/含源码/原件、pytest原始报告、失败ID对比、四规格截图、像素二维码读取、DB回查与verification。前序验收脚本问题有原始记录，不作为产品失败或隐藏。
- Git：feat/ticket-agent-v36-stabilization / 139cdbe2fca8c7249847f245cffef1ed0545dd36，暂存区空；未Commit/Push/Merge，未reset/clean/stash。
- 用量/风险：模型/Embedding/LangSmith/12306/真实支付请求0；仅qrcode包安装联网。原11失败仍在，未实际手机扫描/真实支付，二维码无扫码通知，历史缺失支付方式不补造；非真实账户系统。只读刷新不授权写操作。
- 结论：阶段二完成待用户验收；停止，未开始阶段三。

### 2026-11-01T11:46:01+08:00：V3.7阶段三订单选择式退票与改签

- 完成：本人车次/日期/席别/乘客匹配、零/单/多候选、明确选择/费用预览/确认；明确车次聊天转入选择，不猜最近订单。Decimal退款明细持久化；改签卡片自动带ID，目标选择/差价预览/事务确认，P02已改签拒退。
- 安全：归属/状态/完整订单及目标库存快照复核，事务回滚/并发单次执行；页面操作source=page不伪造Agent Trace；独立只读刷新记录，不恢复授权。P01/P07打印记录保守拒退，交回流程未新增；保留退票48h=10%和改签48h跨日既有边界。
- Skills：完整读取并应用eval-audit的本地证据审计、write-code-eval的客观规则/正反边界测试；发现/采纳/未采纳见skill-audit.json、code-eval-spec.json与报告。未修改Skill或正式评分，不引入LLM Judge/MCP/依赖。
- 修改：mock_core、reschedule、conversation、presentation；新增order_refund、order_actions及三测试；更新本文、阶段三报告和独立产物。原阶段1/2未提交工作、支付机制与40测试不改。
- 测试：最终1197 passed / 11 failed / 1 skipped / 199 subtests，新增59全通过（27退款、17改签、15UI），原11失败/skip一致、无测试移除。前序targeted范围错误与提示关键词失败、1190/11/1和1194/11/1均保留。
- 浏览器：Edge四规格每项24/24，共96/96；12单来自UI操作，SQL订单/库存/明细与UI一致、Agent Trace哈希不变。PageError0，已拦截外部图标导致Console资源错误12/失败请求12；无新增业务浏览器错误，不冒称Console0。
- 保护：1892/3708和扩展4056历史文件0差异；正式103用例、B快照、七维度、政策/SYSTEM_PROMPT/八Schema不改；原测试、阶段二40项与历史报告截图保留。
- 证据：docs/reviews/Ticket-Agent-V3.7-Phase3-Refund-Reschedule-Report.md；artifacts/runtime/v37-phase3-refund-reschedule-20261101/含JUnit、源码/失败ID、Skills记录、四规格截图与DB回查、verification。
- Git：feat/ticket-agent-v36-stabilization / 139cdbe2fca8c7249847f245cffef1ed0545dd36，暂存区空，未Commit/Push/Merge或reset/clean/stash。模型/Embedding/LangSmith/12306/真实交易请求0，无依赖安装。
- 遗留：原11失败；P01/P07凭证交回未建模、固定模拟身份、原支付额与新票价独立记录；离线图标缺失。阶段三完成待验收，停止，未进入阶段四。

### 2026-11-01T14:09:24+08:00：V3.7阶段四四大功能面板与统一订单中心

- 完成：四独立面板、六右栏/四首屏入口、本人订单统一只读投影、支付/退改复用与状态差异禁写；查票/订单保留真实Agent工具Trace，政策保留原文来源与后续上下文。
- 修改：order_refund、conversation、presentation、payment、order_actions；新增order_read_model、user_features、test_user_features；更新本文、新增阶段四报告/独立运行证据。原业务服务、Prompt/Schema/七维度、正式103/B/所有旧测试不改；无新依赖。
- Skills：eval-audit先识别重复来源/假成功/权限/Trace/费率缺口；write-code-eval落实客观输入/预期/失败条件及SQL/Trace/UI证据。两原版哈希不变，未虚构API/运行器；未采用LLM Judge/新依赖/正式评分改造。
- 测试：full-r10隔离运行pytest tests -q --tb=short，1242 passed / 11 failed / 1 skipped / 199 subtests；新45、原支付40、原退改59全通过；失败/Skip集合不变、0旧测试移除。中间失败与定位尝试原始日志保留。
- 浏览器：Edge四规格业务72/72、导航/宽度24/24；40截图与SHA；8订单、8支付、4退款、4改签及16page事件回查，preview只读、reload不写。Console离线图标资源错误共20、业务PageError0；不宣称Console0。
- 保护：1892保护、103正式用例和7份B manifest保持；原3708/4056仅账本开工前获准追加6890字节，原前缀完整，获准后4056零差异。未覆盖旧报告/截图/Trace/数据库/账本。
- Git：feat/ticket-agent-v36-stabilization / 139cdbe2fca8c7249847f245cffef1ed0545dd36，暂存区空，未Commit/Push/Merge。8517自建测试进程已停止，其余用户服务不动。
- 证据：docs/reviews/Ticket-Agent-V3.7-Phase4-User-Features-Report.md；artifacts/runtime/v37-phase4-user-features-20261101/verification.json、技能记录、JUnit/源码/失败对比、浏览器/Agent/DB/截图与停止记录。
- 遗留：原11失败、真实服务未验、固定模拟身份/凭证交回未建模、历史与当前状态分层、图标离线缺失；页面跳动未量化，不替代阶段五验收。阶段四完成待验收，停止，未进入阶段五。

### 2026-11-01T14:31:08.986624+08:00：阶段一至四代码归档推送，启动阶段五

- 归档：39文件单个Commit c889b082dd4bd07e3514038a69362b71dd21915c，正常Push成功；远端SHA独立核验一致。无数据库/账本/运行产物、无阶段五代码；归档后工作区一度干净，暂存区空。
- 保护：103/B/1892/4056获准基线不变，阶段四1242/11/1、199子测试作为后续基线；本次归档未重复运行测试。
- 证据：docs/reviews/Ticket-Agent-V3.7-Pre-Phase5-Git-Archive-Report.md；artifacts/runtime/v37-pre-phase5-git-archive-20261101/。
- 阶段五：已获用户明确授权；按任务结构图实施，image3.png未提供。仅UI布局/呈现，业务、模型选择/费用授权、Prompt/工具/七维度和正式用例不变；完成后不自动提交或进入阶段六。

### 2026-11-01T14:58:06+08:00：阶段五用户端UI重做交付

- 前置归档：39文件Commit c889b082dd4bd07e3514038a69362b71dd21915c，正常Push且ls-remote一致；阶段五未混入。Push后报告及本阶段代码不自动提交。
- 完成：真正视口Grid/Flex、左历史与右栏独立滚动、聊天外底部输入、移动单栏展开、深浅主题、四快捷/六入口、客户化确认/折叠技术细节、原key单行Enter和可选多行Ctrl+Enter；原发送/确认/费用/Provider业务不变。
- 修复实测问题：三套高度冲突、欢迎跳底、顶栏key修改时机、旧iframe回调失效、展开图标/透明工具栏遮挡。未通过force点击或直接改被测scrollTop通过验收。
- 修改：app/conversation/design.css/scroll_bridge/user_features；新增user_layout.py/css及test_phase5_layout；本文/阶段五报告与Push后归档报告更新。target全保持、所有旧测试字节不改、无依赖变更。
- 实测：full-r4隔离pytest tests为1251 passed / 11 failed / 1 skipped / 199 subtests，新9全通过；原40+59+45通过，失败/Skip ID完全一致，0新增失败/旧测试减少。前序13失败与验收脚本错误原件保留。
- 浏览器：Edge四规格DOM38/38、交互32/32、业务72/72，72实际PNG；文档高/宽等于视口，chat scrollTop0→360、输入框y桌面963→963/手机655→655、page scrollTop0；动态650px、右栏、真实命中和输入/会话去重通过。76次实际离线Mock Agent调用，不是真实模型请求。
- Console：36条均为离线拦截的既有travel_explore SVG资源请求，PageError0/最终操作错误0，不伪造Console0。8518所有自建服务停止；其他用户服务不动。
- 保护：103/B/1892/4056获准基线零差异；不覆盖历史Trace/账本/库/报告。两个Skills原版方法用于实际审计/客观规则；不新增Judge/API/运行器或改七维度。
- 证据：docs/reviews/Ticket-Agent-V3.7-Phase5-UI-Redesign-Report.md；artifacts/runtime/v37-phase5-ui-redesign-20261101/verification.json与原始JUnit/DOM/交互/DB/Trace/截图/停止记录。
- Git/遗留：HEAD c889b082dd4bd07e3514038a69362b71dd21915c，阶段五未暂存/提交/推送；原11失败，缺image3/实体手机软键盘未验、DOM升级/既有业务/RAG风险保留。已停止，等待验收，不进入阶段六。


### 2026-11-01T18:21:44.283615+08:00：V3.7阶段六Baseline/Developer Override执行隔离

- 结论：PARTIAL（离线工程验收），实际运行配置生效并有旁证；正式103未执行B原断言，真实模型风格未验证，不宣称项目全绿。1892清单中1890文件字节不变；target/tools.py与web/evidence.py两项源码差异待用户批准。公开Schema/DIMENSIONS不变，原清单不改，不能宣称1892字节零差异。
- 修改：15个原源码文件增量、6个新配置/运行模块、2个新测试，更新本文与阶段六报告；具体清单/原因见报告第5节。阶段五原修改保留，六项布局文件及旧测试字节不变。
- 实测：full-r10，1311 passed / 11 failed / 1 skipped / 199 subtests；新增60全通过，旧失败/Skip逐ID一致，0旧测试减少；原40/59/45/9保持。四规格Edge60/60，28PNG、16次Mock运行，实际Prompt SHA/run/revision/工具/DB回查通过（含固定演示身份的显式脱敏还原核验；实际输入另有专项捕获）。Console20条中8资源拦截、12 JSON查看组件错误，后者未单独根因复验，不宣称Console0。
- 安全：统一dispatch与页面工具策略、双引擎deny/confirm、Provider/会话/revision费用重核、旧提案拒批可取消、新run冻结配置；正式固定Mock/fixture/政策/时钟/身份且不读Store，实验独立schema/报告。公共Trace/工具字段、SYSTEM_PROMPT、八Schema、七维度不改。
- 保护：1892清单中1890文件字节不变；target/tools.py与web/evidence.py两项源码差异待用户批准。公开Schema/DIMENSIONS不变，原清单不改，不能宣称1892字节零差异。 4056相对用户批准追加8249字节后的基线零差异；103/B/阶段五72图/报告/verification及历史Trace/库/账本不改。Skills原版两份SHA保持，使用发现审计/客观规则，无Judge/新依赖。
- 证据：docs/reviews/Ticket-Agent-V3.7-Phase6-Baseline-Override-Report.md；artifacts/runtime/v37-phase6-baseline-override-20261101/verification.json及JUnit/源码/浏览器/config/Skills/保护/停止记录。全部中间失败、启动/脚本问题及重跑原件保留。
- Git：HEAD c889b082dd4bd07e3514038a69362b71dd21915c，原分支、暂存区空、diff --check通过；未Commit/Push/Merge。8519自建服务停止，不动其他用户服务。真实模型/Embedding/LangSmith/12306/真实交易请求0。
- 遗留：原11失败、T04未重验/批准0、B原始执行器缺失、真实效果/实体软键盘未验、固定模拟身份及既有RAG问题。等待用户验收；不自动进入阶段七或提交推送。

### 2026-11-01T19:32:16.659908+08:00：阶段六保护例外批准闭环

- 用户明确批准：“批准这两处限定差异，保留原清单并如实记录”。仅涵盖target/tools.py执行前权限检查、web/evidence.py自定义实验过滤；两文件当前SHA绑定批准记录，不授权额外源码修改。
- 当前阶段状态：由PARTIAL更新为COMPLETE（离线工程验收，保护例外已批准），等待用户整体验收。原PARTIAL记录保留，原交付文档与JSON归档于approval-closeout-before/，不覆盖原1892清单/哈希或历史测试结论。
- 本次复核：已验收299项源码/配置/依赖清单无新增差异；其余1890保护文件与4056获准历史文件无变化，103/B、工具Schema、SYSTEM_PROMPT、DIMENSIONS、旧测试及阶段五72截图/报告/verification均保持。
- 测试：本次未重跑，沿用full-r10的1311 passed / 11 failed / 1 skipped / 199 subtests，新增60通过；Edge四规格60/60、28截图。原11失败、103断言未重跑、12条JSON组件Console错误及真实模型效果未验继续保留，不宣称项目全绿。
- 文件：本次仅更新本文、阶段六报告、verification/protection/final-git核验JSON并新增批准与闭环凭证；应用源码、测试及配置文件未修改。
- Git：HEAD仍c889b082dd4bd07e3514038a69362b71dd21915c，原分支，暂存区空；未Commit/Push/Merge，无真实API请求，不进入阶段七。
- 证据：artifacts/runtime/v37-phase6-baseline-override-20261101/protected-source-approval.json、approval-closeout-check.json及verification.json；报告docs/reviews/Ticket-Agent-V3.7-Phase6-Baseline-Override-Report.md。

### 2026-11-01T20:08:10.337492+08:00：正式103原始评测执行器恢复审查

- 状态：BLOCKED / BLOCKED_WAITING_FOR_ORIGINAL_B_EXECUTOR。阶段六离线工程COMPLETE及两处限定源码批准保留；本次未进入阶段七。
- 搜索：当前源码/数据/文档、ignored artifacts、36 ZIP目录、60本地引用/175提交/446 reflog，以及4989本地Git对象（含不可达）；同项目备份和旧E路径只读补查。部分临时目录仍读取受限，完整错误保存，未改ACL。
- 找到：11组历史b-rerun（5组101、6组103），六judge源码SHA相同且与8份历史提交清单匹配；清单JSON与Git一致，CRLF/LF字节差异明确记录。此前“未找到执行器”细化为“旧版有副本，当前正式103配套版本未恢复”，不覆盖旧审查结论的历史范围。
- 阻塞：旧103与当前有42条expect缺trains_from_tools，旧trace_assert不读取此字段；历史正式记录却有Legacy42+LC40共82条C5。不能修改/忽略字段或由A反推补写评分器，不能把旧版通用规则运行冒称当前正式103。
- 执行：未调用judge/Agent/pytest，无正式执行命令或新计分日志；103条仅哈希盘点，actual/assertion/time为null，NOT_RUN_BLOCKED，PASS/FAIL/SKIP未产生。历史1311/11/1与唯一Skip原件保持，无真实模型/Embedding/LangSmith/12306请求。
- 保护：1892按本任务当前获准基线零差异、4056历史零差异；103/B/旧测试/299源码和两处批准代码、Prompt/Schema/DIMENSIONS、阶段五/六报告/verification及截图不变。原1892旧哈希和批准记录保留，不偷换口径。
- 修改：仅本文与恢复报告；另增独立审查清单、哈希/来源/门禁/环境及搜索日志，不修改业务或配置源码，不Commit/Push/Merge。HEAD仍c889b082dd4bd07e3514038a69362b71dd21915c，分支feat/ticket-agent-v36-stabilization，暂存区空。
- 所需材料：B当前103配套judge/（含C5）、原cases/expect、执行器版本/包SHA、Python依赖锁/原命令/fixture与时钟说明；收到后再做身份与隔离准入，不索取密钥。
- 证据：docs/reviews/Ticket-Agent-V3.7-Formal-103-Executor-Recovery-Report.md；artifacts/runtime/v37-formal-103-regrading-20261101/verification.json、provenance-audit.json、case-integrity.json、execution-gate.json与原始搜索日志。任务停止，等待原B交付。

### 2026-11-01T21:12:17.300021+08:00：V3.7阶段七Fixture/快照/数据源隔离

- 状态：总体PARTIAL；Fixture COMPLETE，Snapshot PARTIAL（离线工程验证完成但无真实原件），Live BLOCKED / LIVE_SOURCE_BLOCKED_PENDING_AUTHORIZATION。103正式评测仍BLOCKED、未运行15或103原始断言。
- 实现：固定2026-10-20起7天2100行Fixture及SHA；Baseline/Test固定时钟并强制Fixture；旧用户演示会话日期/事务库保留。只读Snapshot、严格Schema/隐私/来源/时间/覆盖/unknown/SHA、原子不可覆盖导入；Live无网络实现。
- 隔离：Snapshot不建演示DB、不写库存/真实交易；禁止新候补/锁座/建单/改签，切回Fixture重新查询；原支付/取消/退款规则、阶段六权限/费用/Provider保持。换源冻结/锁定、旧提案及工具记忆隔离；实际来源/北京时间/状态在用户端附近与独立事件侧车记录。
- 实测：full-r6完整1356 passed / 11 failed / 1 skipped / 199 subtests，新45全通过；旧失败/Skip集合和全部旧测试不变，40/59/45/9/60保持。四规格Edge120/120、32截图、32次Mock运行，SQL库存/订单与源SHA/run回查通过；Console仍有原JSON组件/资源拦截问题，详见原日志，非Console0。
- 迭代原件：首次新增测试隔离路径3失败、首轮完整13失败的2项新Fixture定位问题、browser-r2输入上沿21px变化、full-r5费用文案2子断言失败（1356/13/1、197子测）均保留；修正新代码/测试后重验，不改旧判据或新增skip/xfail。
- 保护：1892当前获准基线、4056历史零差异，tools.py/evidence.py字节保持含阶段六已批改动；Prompt/八Schema/10/5/DIMENSIONS、原seed/政策、103/B/旧测试/P2/账本/库、阶段五/六报告verification和72+28图不改。全部新数据明确SYNTHETIC_TEST_FIXTURE，未向data/real导入合成数据。
- 修改：配置测试时钟、mock_core/provider/内部审计/改签来源guard及现有Web来源展示；新增train_source/train_snapshot、2 CLI、web/train_data、固定Fixture、1测试文件；本文/阶段七报告与独立产物，具体原因见报告第4节。不增加依赖，不重设计Grid/Flex。
- Git/用量：HEAD c889b082dd4bd07e3514038a69362b71dd21915c，原分支/暂存区空/diff --check通过；无Commit/Push/Merge。真实12306/模型/Embedding/LangSmith/交易请求0，8520自建服务停止，其他用户服务不动。
- 证据：docs/reviews/Ticket-Agent-V3.7-Phase7-Train-Data-Source-Report.md；artifacts/runtime/v37-phase7-train-data-source-20261101/verification.json及要求的8份结构化旁证、JUnit/源码/四规格/Skills/原始输入/快照/停止记录。
- 遗留与下一步：缺真实快照/独立采集证明、实时合法接口和授权、B C5执行器；原11失败、JSON组件Console、既有RAG/身份/实体软键盘边界保持。等待验收，不自动进入下一阶段或提交推送。

### 2026-11-01T23:04:35.523087+08:00：阶段五至七Git归档授权与开工核验
+
+- 用户明确要求提交并推送全部未提交代码；当前分支feat/ticket-agent-v36-stabilization，开工HEAD c889b082dd4bd07e3514038a69362b71dd21915c、暂存区空，48个候选文件。
+- 源码与最终full-r6清单完全一致，沿用1356 passed / 11 failed / 1 skipped / 199 subtests及四规格120/120，不重复运行完整测试；Fixture COMPLETE、Snapshot PARTIAL、Live BLOCKED、正式103 BLOCKED结论不变。
+- 密钥/敏感路径检查无命中；1892当前保护文件保持。两份用量账本在阶段七验收后分别追加5977/6036字节，原259169/463888字节前缀哈希完整；保留当前原件、不提交、不改写，本任务未发模型/Embedding/LangSmith/12306请求。
+- GitHub代理127.0.0.1不可达，仅本次Git进程直连成功，目标远端分支仍c889b082…；未修改全局代理或TLS设置，不强推、不切分支、不清理工作区。
+- 提交及推送尚待本次实际命令完成，后续追加准确回执。证据：artifacts/runtime/v37-phase5-7-git-archive-20261101/before.json；原阶段五/六/七及恢复报告、运行证据均保留。
+