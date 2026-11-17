# 成员 C：V3 验收与拍摄说明

日期：2026-10-13（Asia/Shanghai）。分支 `feat/a-ticket-langchain-v3`。

已验证核心源码与证据提交：`595dc0af157e89613597946934f343a76216976b`；原型 `92efc2a739bd3712d2ff62910bf8944cd9ad81b9`，八工具 `950b0f2b62f41a6988cb28c306808baabebfab9b`。
这批报告会形成后续文档提交；最终交付提交以新标签 `handoff-a-langchain-v3-20261013` 解析，执行 `git rev-parse handoff-a-langchain-v3-20261013^{commit}` 获取完整 SHA。旧标签不移动。

**成员 A 开发交接状态：有条件交接。** 可供 B 正式测试和 C 拍摄离线 Mock；真实大模型尚未联网实测，正式成绩与人工验收待 B/C 提供。所有数字是成员 A 的实际自测结果，不是正式比赛评分。

## 用容易理解的语言介绍项目

项目用虚构高铁/航班/政策搭建可测试的出行助手，让团队检查“理解请求→调用工具→遵守业务规则→给出有来源的回复”是否正确。普通聊天机器人可以直接回答，Ticket Agent需查模拟数据库、锁座/下单、检查订单状态和引用政策；因此便于比赛按工具调用、功能、记忆、安全、边界和性能等维度测量。

V2由自己写的Python循环安排步骤；V3把“模型回答要调用哪个工具、执行工具、把结果交回模型、继续到结束”交给真正的LangChain框架。模拟业务、政策、Web和对外JSON沿用。LangGraph在这里是框架底层依赖，并没有额外自建复杂图。

LangChain Mock仍是规则模拟模型，展示框架工程流程，不能讲成真实AI自主规划。LangChain Live的真实模型负责理解、工具选择与组织回复，但目前没有密钥，尚未联网实测。可讲已完成接入代码，不可展示为实测模型成绩。

## 环境和从零部署

已验证Windows PowerShell、Python3.12.14；依赖 langchain 1.4.5、langchain-core 1.6.10、langchain-openai 1.7.1、langgraph 1.2.15、streamlit 1.65.0、openai 3.29.0。如果没有Python，先安装Python3.12并确认 `py -3.12 --version`；下载/克隆仓库后在仓库根目录执行。已有本机环境不要重建。

```powershell
# 在仓库根目录，建议 Python 3.12；已有 .venv 可直接用于创建独立V3环境
.\.venv\Scripts\python.exe -m venv .venv-v3
.\.venv-v3\Scripts\python.exe -m pip install -r requirements-v3-lock.txt
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_ENGINE="langchain"
$env:AGENT_PROVIDER="mock"
$env:AGENT_LC_TOOLSET="all"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\v3-$runId\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\v3-$runId\langchain_mock"
.\.venv-v3\Scripts\python.exe data/seed.py
.\.venv-v3\Scripts\python.exe cli.py once "查明天上海到杭州的高铁"
.\.venv-v3\Scripts\python.exe cli.py chat
# 输入 q 退出 CLI 后再启动 Web
.\.venv-v3\Scripts\python.exe -m streamlit run web/app.py
```

首次从零部署时先在项目根目录运行 `py -3.12 -m venv .venv`，再按上述创建 `.venv-v3`；不要对已有环境重复执行创建命令。锁定依赖是本次实际安装版本，更新依赖需要重新验证。Web 地址以控制台打印的本机 URL 为准，默认 http://localhost:8501；首次 Streamlit 要求 Email 可留空按回车。CLI 和 Web 分别创建 Agent，不共享内存会话。


默认引擎legacy；展示V3务必使用AGENT_ENGINE=langchain，完整订单演示用all。只读演示用read_only，仅支持查询与政策。改环境变量后停止旧服务重启；新PowerShell窗口不会自动继承另一个窗口临时变量。

## 验收步骤

| 顺序 | 同一会话输入 | 应观察到 | 证据/成功依据 |
|---|---|---|---|
| 1 | 查明天上海到杭州的高铁 | query_tickets和有票班次 | args日期为明天，kind高铁，席别二等座，ok=true |
| 2 | 那机票呢 | 交通切换到机票 | 继承路线/日期，经济舱；该模拟路线没有航班时如实空结果 |
| 3 | 还是高铁吧 | 切回高铁 | kind高铁，旧经济舱不能继承 |
| 4 | 后天呢 | 日期改变、路线仍保留 | query_tickets.date为后天 |
| 5 | 锁座后多久必须完成支付？ | search_policy，P11来源 | 不出现pay_order；工具原始hits含source |
| 6 | 订明天上海到杭州的高铁 | query_tickets→lock_seat→create_order | pending订单、成功lock_id，不自动支付 |
| 7 | 支付我刚才的订单。 | pay_order | 同一订单paid |
| 8 | 支付 | 再次pay_order | duplicate_pay=true，提示没有重复扣款 |
| 9 | 帮我退掉 | cancel_order | refunded与政策引用，库存释放一次 |
| 10 | 查我的订单 | query_order | 本人订单与最终状态 |
| 11 | 抢明天北京到上海的票 | query_tickets→monitor_seat | 原种子售罄路线，返回模拟候补任务，不声称已买到 |

每轮看右侧工具表、完整JSON与页面底部回放；本轮的tool_sequence与表格一致。Mock很快，处理动画可能一闪而过，不应人为标成模型内部思考。清空会话清记忆，不重置库存/订单或删除JSONL。


另开一个新的浏览器会话/Agent输入“后天呢”，应要求先给路线，证明消息隔离；清空原会话后输入同样省略问法，应不沿用旧路线。其他会话共享同一模拟身份订单/库存，这是当前设计，不能演示成多账户数据隔离。

失败时保留：输入文本、会话ID、模式/工具集、右侧工具表和完整JSON截图、对应JSONL最后一行；说明预期与实际。不要覆盖旧库或删Trace。截图不要包含Key、私人路径/用户信息；日志导出前检查配置摘要。会员成绩由B确认后加入报告。

## 演示与5—10分钟分镜建议

| 时长建议 | 操作/讲解 | 拍摄画面与事实 |
|---|---|---|
| 0—1分钟 | 项目目标、A/B/C分工、虚构业务 | 首页标题与“模拟数据/Mock”提示 |
| 1—2分钟 | V2→V3架构变化 | A报告架构和create_agent源码，说明框架管理循环 |
| 2—3分钟 | 查询→机票→高铁→后天 | 左侧输入、右侧参数变化，不声称无数据路线有票 |
| 3—4分钟 | 支付时限政策 | search_policy、P11来源与回复，强调没有支付操作 |
| 4—6分钟 | 有票订票→支付→重复支付→退票 | query→lock→create工具链、订单ID、duplicate_pay提示和政策 |
| 6—7分钟 | 无票候补 | 售罄结果与monitor_seat，说明只模拟监控任务 |
| 7—8分钟 | 执行轨迹与离线回放 | 工具顺序/参数/ok/耗时、完整JSON与历史列表；无内部思维链 |
| 8—9分钟 | legacy故意变异演示 | 停服务切AGENT_ENGINE=legacy，重启新会话后勾date_offset，对比真实工具日期 |
| 9—10分钟 | 自测证据、边界、后续工作 | 本次A56项自测与Key待验证；B成绩由B单独提供 |

演示变异可以准备第二个PowerShell、不同DB/Trace/端口来展示legacy；两个服务不能共用同一会话对象，LC开关禁用属于正常行为。结束恢复正常模式并新建会话。推荐报告截图：V3模式标题、交通席别切换工具参数、P11来源、三步下单链、重复支付、候补、离线回放、A实际测试日志。不要拍摄SDK桩输出冒充真实模型。

## 技术资料与常见问题

- Prompt：target/agent.py SYSTEM_PROMPT与target/langchain_agent.py补充规则；框架入口create_agent与中间件同文件。工具Schema/业务：target/tools.py、mock_core.py；RAG：target/rag.py和data/policies.md；Mock标准模型：target/langchain_model.py。
- 模型消息/工具结果的实际交互：docs/evidence/v3/final_framework/framework_events.json；公开JSON见api_results.json。Trace是可检查的执行记录，不是模型思维链。
- B只依赖Agent.chat契约做正式断言，A提供可复现Agent；C用真实B结果做最终报告。当前没有B正式V3成绩，不写覆盖率/成功率/缺陷数。
- ModuleNotFoundError：确认使用.venv-v3并安装requirements-v3-lock.txt；原.venv没有框架是正常的。页面仍写legacy：环境变量后重启服务。8501占用：确认旧服务，或加--server.port 8502。Streamlit Email留空回车。
- 无Key：使用Mock；Live需要有效Key和端点支持工具调用，按B手册先预检。不要向队友发含Key配置。
- 明天查询无班次：旧库7天窗口过时，换新隔离库seed；机票路线仅5条，并非高铁所有路线都有机票。
- 写操作被拒绝：用表中明确命令，在同会话先创建本人订单；复杂或含问号请求可能触发保守授权。保存JSON交A/B，不修改判定结论。
- 动画很短：本地Mock毫秒级响应，等待期间通用图标正常，无法靠它证明真实模型思考或细粒度阶段。

## 实际状态与材料

| 功能 | 状态 | 边界 |
|---|---|---|
| 真正create_agent模型/工具循环 | 【已实现并验证】 | 实际LangChain Mock/SDK桩；没有调用旧Agent._chat |
| query_tickets/search_policy原型 | 【已实现并验证】 | 单轮/多轮/政策P11引用/异常 |
| all模式八工具与写授权 | 【已实现并验证】 | 虚构订单/模拟支付；授权中文命令保守 |
| Checkpointer会话隔离/reset | 【已实现并验证】 | InMemorySaver，当前Agent实例内 |
| 跨重启会话持久化 | 【未实现】 | 未接数据库Checkpointer |
| 原团队Trace字段兼容 | 【已实现并验证】 | 字段不变；provider新值/框架开销请B评审 |
| legacy V2及六变异 | 【已实现并验证】 | 原环境28项、入口服务、六变异仍可用 |
| LangChain六变异 | 【未实现】 | 不静默接受，开关只在legacy可用 |
| CLI/Web与处理动画 | 【已实现并验证】 | AppTest/服务启动；动画为通用等待，人工视觉验收待C |
| 关键词RAG | 【已实现并验证】 | 15条虚构政策；原算法与语料未修改 |
| 可选向量RAG | 【已实现但未验证】 | 旧可选分支保留；不属于本次框架迁移成果 |
| ChatOpenAI真实模型接入 | 【部分实现】 | 代码/无网络SDK桩已验证；远端模型待有效Key |
| 真实大模型自主Function Calling | 【已实现但未验证】 | 接入路径存在，真实大模型尚未联网实测 |
| 正式B测试层与V3成绩 | 【未实现】 | judge/完整断言未在当前仓库，不是A开发职责 |
| C正式验收、截图视频 | 【未实现】 | 由C根据Mock及后续B真实成绩完成 |

| 实际验证 | 结果 | 证据 |
|---|---|---|
| V3环境 unittest（由smoke执行） | 56项通过，0 skip：旧28+框架原型13+订单13+Live SDK桩2 | docs/evidence/v3/final_legacy_smoke/unit.txt |
| 原V2环境 unittest | 旧28通过，框架28 skip（没有安装LangChain） | docs/evidence/v3/original_environment_smoke/unit.txt |
| 两套环境入口冒烟 | 每套10项检查成功、32条legacy Mock Trace | final_legacy_smoke/verification.json、original_environment_smoke/verification.json |
| LangChain Mock API | 11轮对话覆盖8工具，交通切换/日期/政策/订单流程成功 | final_framework/api_results.json、framework_events.json |
| LangChain CLI/Web | CLI once/chat、AppTest消息/工具表/JSON/回放成功 | final_framework/verification.json |
| 六种预设变异 | legacy 的六变异自测通过；LC初始化主动拒绝变异 | test_agent.test_six_injected_mutations、自测日志 |
| 原始成果保护 | 99个原文件SHA256相同；V1/V2标签相同 | v2_baseline/manifest.json |
| Live接入 | ChatOpenAI/SDK边界桩2项通过，无Key预检；远端调用0 | live_sdk_stub.txt、live_preflight/preflight.json |

以上证据路径相对于 `docs/evidence/v3/`（第一条已写完整路径）。`scripts/smoke.py` 的历史 version_scope 字符串仍写 V2 A self-validation，实际分支和V3扩展测试以本表与日志为准。

原型首次CLI验证断言错误以及订单自测初次失败都保留，见 prototype_check_failure.txt、orders_unit_utf8.txt；没有删改失败证据或B判定规则。原型12项、订单初始12项是阶段记录，最终分别为13项，不把重复运行累计成“更多测试用例”。


- 默认引擎仍 legacy；`AGENT_ENGINE=langchain` 才进入框架。默认 LC 工具集 read_only，仅两个工具；all 才开放完整流程。
- LangChain Mock 复用V2规则决策，不能证明真实模型自主规划、复杂推理或抗幻觉能力。model字段仍是配置名称，Mock显示glm-4-flash不表示调用了这个模型。
- InMemorySaver不跨进程/重启持久化，未做历史压缩；长对话/多session内存增长，Mock测试消息留存也会占内存。Agent互斥锁串行化调用；没有正式并发压力结果。
- 写授权为保守中文语法，问题/否定/引用/假设和复杂表达可能拒绝；不是生产身份认证。一次请求最多一个成功锁，不支持跨轮旧锁直接下单、多路线一轮多订单；拒绝也会计入真实工具尝试。
- DB固定一个模拟当前用户，不同session只隔离消息状态，不隔离订单/库存。独立用例应独立DB，不可仅换session来清业务数据。
- 候补仅模拟返回监控凭据，无后台持续抢票。没有真实改签执行、身份证核验、折扣计算或支付渠道。库只覆盖生成日起7天，旧库不自动刷新；用新隔离库复现。
- 真实模型仍可能不调用工具、选错工具、生成不可靠回复，Prompt不能保证完全没有幻觉；需Key后由A接入验证、B独立评估。stop只是循环结束，必须同时检查ok、工具结果和业务状态。
- 向量RAG和LangChain模式HTTP业务链未单独实测；共同HTTP工具/legacy链已由smoke实测。未测部署到公网、负载、重启恢复、远端端点兼容性。

