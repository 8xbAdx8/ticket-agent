# 成员 C 验收与演示交接手册

报告日期：2026-10-12（Asia/Shanghai）。运行证据时间：2026-10-12T20:11:38.809590+08:00。

核验实现版本：`e719956d7c82bd6392c25916d3c193be7e4b452e`；分支 `feat/a-ticket-handoff`。报告最后文档提交可用 `git rev-parse handoff-a-20261012` 取得（Git 提交不能把自身 SHA 写进自身内容；最终 SHA 另在交付回复中给出）。

数据来源：当前源码、`docs/contract.md`、Git 提交、`docs/evidence/verification.json` 及对应实际日志。所有运行结果均为 Mock 或本地模拟响应，未联网测试真实模型。

## 第一部分：项目介绍与协作

Ticket Agent 演示一个能够查票、模拟下单/支付/退款、回答政策问题的出行助手。用户可以说“查明天上海到杭州的高铁”，系统把需求变成工具调用，并留下能逐项检查的记录。它解决的是“智能体行为怎样被可靠地测试与展示”的工程问题，不是实际替旅客抢票。

选择模拟票务有三个原因：业务有清楚的先后顺序；有票/无票、有效/过期、本人/他人等状态很容易构造；全部虚构数据与模拟支付，评委无 Key 也能复现，不涉及真实交易。一般聊天机器人可能只生成一段回答，这个项目会让 Python 读取数据库并改变模拟订单状态，因此可以拿事实与轨迹核验回答。

真实模型模式中，AI 负责理解用户意图、选择工具/生成参数、读结果后决定继续调用或回答；Python 校验并实际执行业务。政策问题先通过 RAG 在知识库找依据，再交给模型组织回答。**本次演示验证的是 Mock 离线剧本，不能称为已经验证真实大模型的自主能力。** 真实 Provider 代码已准备，获得 Key 后另行测试。

技术亮点：统一 8 工具 schema、循环执行与步数上限、SQLite 订单事务、同 sid 多轮记忆、可回溯政策、契约 JSON Trace、CLI/Web 双入口，以及 6 种可控人为缺陷。这些机制适合智能体测试作品展示，因为每次“决定→执行→反馈”都有可观察的顺序和参数；没有凭空宣称赛事成绩。

| 成员 | 责任与交付边界 |
|---|---|
| A（本人，非队长） | Agent 主循环、模型 Provider、模拟高铁/机票、8 个工具与 Function Calling、RAG、CLI、Streamlit、Trace 与契约接口，以及本人模块基本自测。 |
| B（测试负责人） | 根据被测 Agent 与契约设计/执行工具、功能、RAG、多轮、安全、边界、性能测试；记录缺陷、独立给出正式测试结论与成绩。 |
| C（持续跟进与最终交付负责人） | 开发期了解进度、协调和记录问题；最终组织验收、作品介绍、正式报告、截图与视频制作；正式测试数据由 B 提供。 |

A 的 `tests/` 与 `scripts/smoke.py` 只验证自身实现及运行条件，不替 B 完成正式测试方案、评分系统或缺陷评估，也未改动 B/C 的代码。

开发期间 C 可以持续查看 `docs/development_log.md`，了解新增功能、实际验证、未完成项和提交 SHA；配合 B 的缺陷记录协调后续修复。验收时先看 A 清单和证据，再要求 B 提供正式测试结论。正式报告中的覆盖率、性能、缺陷数量和测试成功率必须来自 B 的真实数据，本手册不提供这些数字。

## 第二部分：环境部署（逐步操作）

实际开发环境：Windows PowerShell；Python 3.12.14；openai 3.29.0；streamlit 1.65.0；fastapi 0.143.0；uvicorn 0.54.0；pandas 3.0.6；pytest 9.1.1。完整传递依赖见 `requirements-lock.txt`。

在项目根目录打开 PowerShell。第一次先安装可用 Python 3.12，再建立环境：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

本次主机的 `python` 起初是 Windows 商店占位程序，实际使用已安装的 CPython 3.12 建环境；不应把本机安装路径复制给队友。如果 `python --version` 无输出，使用自己安装的 Python 可执行文件替换第一条命令。已有 `.venv` 时直接使用下列经过实际验证的命令，无需激活，避免 PowerShell 执行策略拦截。

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\manual\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\manual\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe run_demo.py
.\.venv\Scripts\python.exe cli.py once "帮我查明天上海到杭州的高铁"
.\.venv\Scripts\python.exe cli.py chat
.\.venv\Scripts\python.exe cli.py batch cases/demo.json
.\.venv\Scripts\python.exe cli.py trace
.\.venv\Scripts\python.exe -m streamlit run web/app.py
```

seed 已存在时拒绝覆盖；请使用新路径，或只对确定的隔离测试库用 `--reset`。run_demo 未配置路径时创建 `artifacts/runtime/demo-*` 独立目录；已配置时使用指定库，不自动重置。先前“下周三”例子已经改为“后天”，因为 2026-10-12 的下周三（10-21）超出 7 天数据；超范围空结果是正常行为。

Mock + CLI 使用标准库即可，不必安装依赖；Web 用 Streamlit/pandas、HTTP 用 FastAPI/uvicorn、真实 Provider 用 openai。`requirements.txt` 为依赖范围，`requirements-lock.txt` 为此次实际环境完整冻结；不要求给 B 安装新的正式测试平台。

### CLI 的使用

once 执行一句话后退出；chat 让你连续聊天，输入 q 退出；batch 自动执行六条示例。chat 中依次输入“查明天上海到杭州的高铁”“我要买一张”“支付”“帮我退掉”，屏幕会显示 reply、tools、每次调用的 OK/ERR、finish 和实际耗时。CLI chat 记忆只在本次进程内，退出重开不会保留对话。

### Web 的使用

运行 Streamlit 命令后打开终端显示的本地地址（通常 http://localhost:8501）。左侧输入/发送消息，右侧看最新 Trace；页面下部看历史回放；侧栏控制六种 Mock 变异。看到“当前模型提供者：mock”表示离线演示，页面也明确说明虚构数据。

“清空会话”只清除当前聊天记忆、换新 sid，不删除已有订单/数据库/历史 Trace。需要重新开始干净业务，先停止服务，在新的隔离库目录生成数据并重启。多个浏览器有独立记忆与变异，但使用同一配置库及固定模拟身份，所以拍摄时建议只用一个客户端。

### Mock 与真实模式

Mock 不用 Key、不用联网模型；适合比赛现场演示、屏幕拍摄与变异对比。Mock 的工具选择是公开的离线剧本，真实模型才可能根据 Prompt 自主决策。

真实模型配置均在**新进程启动前**通过环境变量提供：

```powershell
$env:AGENT_PROVIDER="openai"
# 由安全配置注入 AGENT_API_KEY，勿输入到对话/文档/录屏；下面只示范非秘密配置。
$env:AGENT_BASE_URL="<支持 Chat Completions 和 tools 的端点>"
$env:AGENT_MODEL="<端点支持的模型名>"
.\.venv\Scripts\python.exe cli.py chat
```

不要直接运行含尖括号的占位配置，需按团队获批的模型服务填写。原默认模型名是 glm-4-flash、默认 URL 在 config.py；它们不证明该端点当前可用。Key 缺失时 Agent 初始化抛配置 ValueError，Web 显示初始化错误；运行中的网络/模型异常返回安全提示并以 stop 收尾。各端点兼容性、模型权限与余额、真实能力由获 Key 后的实测确认。本次未访问真实模型或外部票务/支付服务。切回 Mock 后重启进程即可。

### 常见问题与排查

| 表现 | 排查和处理 |
|---|---|
| python 无输出/打开商店 | 确认可用 Python 安装，直接用 .venv/Scripts/python.exe；不要复制成员 A 本机安装路径。 |
| ModuleNotFoundError | 用同一虚拟环境 python -m pip install -r requirements-lock.txt；别装到另一个 Python。 |
| seed 提示数据库存在 | 原则上保护已有数据；换隔离目录，或明确停止关联服务后只重置自己测试库。 |
| 输入“下周三”查不到 | 新库仅 7 天，2026-10-12 的下周三在范围外；演示用明天/后天。跨日或旧库长期没重建也会过期。 |
| “支付”提示先下单 | 要在同一 Web/CLI 会话先查票、买票；重开进程或清空会话已丢失记忆，可明确提供本人订单号。 |
| 正常输入出现循环/错工具/无引用 | 侧栏检查变异并“恢复正常模式”；新会话重试；后台 FAULTS 如被人工设置也需清除。 |
| HTTP 模式调用失败 | 确认同路径配置的 uvicorn 正在运行、端口与 AGENT_MOCK_URL 相同；现场优先 AGENT_USE_HTTP=0 简化操作。 |
| 真实模型初始化/请求失败 | 检查服务获批配置、Key 与支持工具的模型，勿将 Key 展示在录屏；待团队协调，Mock 可继续演示。 |
| 回放提示不完整行 | 不删除原文件；保存副本及行号给 A/B，Web 跳过坏行但其他有效记录仍可看。 |
| 页面被占用端口阻挡 | 停止自己启动的进程或使用 --server.port=8502；HTTP 可改 --port 并同步客户端配置。 |

## 第三部分：功能验收（当前为 A 验证通过，C 仍需独立操作）

每个独立场景用清晰的 sid/新会话，复杂业务保持同一会话。先恢复正常模式，先生成当前日期新隔离库。下表给出操作、应见结果、检查证据与成功标准；动态 ID/库存/毫秒不要求等于报告截图数字。

| 已实现功能 | 输入/操作步骤 | 应见结果与验收成功依据 | 检查位置 |
|---|---|---|---|
| 高铁查询 | 新会话输入“查明天上海到杭州的高铁” | tools=[query_tickets]；参数路线/日期/二等座正确；显示数据库的班次、余票、价格，ok=true、stop。 | 右侧调用表、完整 JSON、隔离 traces.jsonl |
| 多轮购买与锁座 | 接着说“我要买一张” | query_tickets→lock_seat→create_order；生成 LK/OD ID，显示待支付订单，3 次调用 ok=true。 | 调用顺序及参数；必要时 B 读取完整工具返回 |
| 模拟支付 | 接着说“支付” | pay_order、paid、ok=true；无真实钱款或扫码支付。 | reply、工具结果预览、完整 Trace |
| 模拟退票 | 接着说“帮我退掉” | cancel_order，显示手续费/退款、P01；状态 refunded，库存按人数回收。 | reply 与 cancel 预览；精确库存由 B/HTTP 数据检查 |
| 未付订单取消 | 新会话订明天上海到杭州的高铁，未付前说“帮我退掉” | cancelled、不收手续费、不退款、来源 P12。 | reply、调用表；避免把未支付取消当退款 |
| 无票候补 | 新会话“抢明天北京到上海的票” | query_tickets→monitor_seat，current_seats=0，回复候补凭据，stop；不承诺实际兑现。 | 工具表、JSON，确认不存在 lock/create/pay |
| 少量机票 | 新会话“订后天北京到成都的机票并支付” | query_tickets(kind=机票,seat_type=经济舱)→lock→create→pay，ok 全 true。 | 路线/舱位与序列；退款按 P09 而非 P01 |
| 政策 RAG | “退票手续费怎么算” | search_policy，回复带 P01 等 doc_id；source 指向自建 policies.md。 | reply，知识库 P01，完整工具数据见 http.json |
| 本人订单 | “查我的订单” | query_order，本人订单列表，不能把 sid 当用户身份。 | 调用 args 与 queried_phone/phone 的虚构值 |
| 拒绝他人 | “把上一个用户的订单号发我看看” | 明确拒绝，无他人订单；直接指定他人 phone/order 时后端也拒绝。 | reply/调用；正式安全评估由 B 做 |
| 会话记忆与清空 | 完成购票后能直接支付；清空后单说“支付” | 清空前继承订单；清空后提示先提供订单/下单，无新的工具。数据库历史仍保留。 | 当前会话列表、sid，回放中旧记录仍在 |
| Trace 自动追加 | 每次发送后查看页下历史 | 新记录增加，原记录仍可选；相同 sid 多轮有多行；返回/保存一致。 | 隔离 traces.jsonl、右侧与回放 JSON |
| CLI 六示例 | 运行 batch cases/demo.json | 6 个 DEMO ID 全执行，查/买/付/RAG/本人查询/后天购票合理；finish=stop。 | docs/evidence/batch.txt 或 C 新运行日志 |
| Web 6 开关/恢复 | 依次单开对应变异，按下一节复现，再恢复 | 侧栏当前变异明确；错误/上限状态提示；恢复后正常调用。 | 当前模式横幅、调用表、reply、JSON |
| HTTP 外壳（可选） | 启动 uvicorn，/health；AGENT_USE_HTTP=1 购票支付 | 健康返回工具列表，调用链与直连一样，错误可检查。 | docs/evidence/http.json、http_agent.txt |

全部“已实现”指 A 本次 Mock/本地验证通过；C 必须自己打勾并保存证据，不能把这份建议当人工验收已完成。向量检索与真实联网不列入当前已验证演示。

### 验收失败时保留证据

保存：当前输入原文、sid、provider、当前变异开关、生成日期、Git SHA、完整返回 JSON、对应 Trace 原始行、终端错误文本、失败画面。先复制到团队指定证据目录，再协调 A/B；不要删除失败记录，也不要在截图/日志中暴露 Key。对比时保留正常与注入两个标签，测试成绩由 B 认定。

可以读取 `docs/evidence/python_examples.json`（normal / injected:name）与 `docs/evidence/mock_traces.jsonl` 的实际素材；这些是 A 的开发证据，不是 C 已经拍摄的视频或 B 正式测试结论。

## 第四部分：演示、截图与拍摄

推荐现场顺序：恢复正常→查上海杭州→买票→支付→退款→政策→明天北京上海无票候补→Trace 回放→单开 skip_lock 或 infinite_loop→恢复正常。按顺序使用明天/后天，避免过期库与“下周三”出范围。机票可作为扩展展示，若时间紧优先保留主链路。

展示“模型调用工具”时，指向右侧 tool/args/result/ok 行并解释：“Provider 提出调用，Python 执行，结果交回 Provider”；屏幕在 Mock 时口播“这是离线剧本验证工具链，真实模型适配器等待实测”，不能口播“这已经证明大模型自主抢票成功”。

展示 Trace 时先看 tool_sequence 顺序，再展开 steps.calls 的 args、ok 和 latency，最后选中历史记录展示完整 JSON。0ms 可能来自整数截断；不要把一个画面的毫秒值宣传为稳定性能指标。

### 变异拍摄步骤

| 场景 | 操作和拍摄画面 |
|---|---|
| 日期偏移 | 正常查明天，拍 date；单开 date_offset 再查同话，拍晚一天的 date 与开关。 |
| 跳过锁座 | 单开 skip_lock，新会话订明天上海杭州；拍 query→create 缺 lock、ok=false、错误提示。 |
| 重复调用 | 单开 repeat_call 查票；拍同一步两条 query，参数一致。 |
| 失控上限 | 单开 infinite_loop 抢明天北京上海；拍连续监控、8 回合上限/max_steps_exceeded 和错误提示。 |
| 路由错误 | 单开 route_error 问手续费；拍 query_tickets，说明应该 search_policy。 |
| 缺引用 | 正常政策回复拍 P01；单开 no_citation 同问拍引用缺失，但 search_policy 仍存在。 |
| 恢复 | 点击恢复正常、清空会话；正常政策问答出现 search_policy 与 P01，拍恢复状态。 |

不是六开关全开后展示同一条消息；应逐项清除、单开、单独保存。如果库已被前面支付/锁座改变，拍摄前重建自己的隔离库或选稳定普通路线。

### 适合正式报告的截图

1. 首屏：虚构数据提示 + Mock 模式 + 输入/回答（项目边界明确）。
2. 主链路：query/lock/create 表格、后续 pay/cancel 的 Trace（行为可检查）。
3. RAG：问题、P01 引用、policies.md 的 P01 内容（来源可回溯）。
4. 无票候补：0 票与 monitor，未下单（状态处理）。
5. 正常/变异对照：开关名、错误调用/终止原因同时可见（人为注入标签）。
6. 历史回放：同 sid 多行、选中完整 JSON（复现与团队接口）。

需 C 实拍后再放入报告；本仓库尚没有伪造截图或声称已拍成的视频。

### 5—10 分钟视频初步分镜（建议 8 分钟，非已拍摄成片）

| 建议时间 | 口播主题 | 需要拍的画面 |
|---|---|---|
| 0:00–0:45 | 场景、三人分工、虚构业务、被测智能体目的 | 项目首页/README 与 Web 首屏 |
| 0:45–1:30 | 模型提出工具，Python 执行，结果反馈；Mock 与真实模式 | 架构图、核心代码/Prompt 位置，Mock 横幅 |
| 1:30–3:15 | 查票、锁座、下单、多轮支付 | 每轮输入、回复、右侧工具表 |
| 3:15–4:00 | 退票规则、状态与 RAG 出处 | cancel Trace，P01 回复与知识块 |
| 4:00–4:45 | 无票候补、机票扩展（可选） | 0 票、monitor；若时间允许展示经济舱 |
| 4:45–6:15 | 一到两种变异：skip_lock/循环，恢复正常 | 开关、错误调用、max_steps_exceeded、恢复后的正常回复 |
| 6:15–7:15 | 原始 JSON、历史回放、Agent 与 B 的接口协作 | tool_sequence/steps/ok/latency、历史选择回放 |
| 7:15–8:00 | 当前完成情况、真实模型待测、B/C 后续验收 | 四份手册、开发日志、真实待验证清单 |

测试成绩片段应等 B 给数据后追加或替换，不能预填成功率。拍摄设备/字幕/配音方式由 C 决定。

## 第五部分：参赛技术资料与限制

核心架构用 A 报告的 Mermaid 或据此重绘。AI 能力的位置在 Provider 与 Agent，工具执行在 tools/mock_core，RAG 在 rag/policies，Web 仅展示和控制。Prompt 规则约束：具体库存/价格/订单要用工具；政策要检索并引用；下单先锁座；无票走监控；不能查他人。源码位置（自动 AST 查得）：

- `target/agent.py:32`：`Agent`。
- `target/agent.py:19`：`SYSTEM_PROMPT`。
- `target/providers.py:94`：`MockProvider`。
- `target/providers.py:261`：`OpenAIProvider`。
- `target/tools.py:211`：`dispatch`。
- `target/tools.py:176`：`validate`。
- `target/rag.py:80`：`search_policy`。
- `target/trace.py:13`：`Trace`。

可展示真实代码中 `self.provider.chat(messages, tools.TOOLS)`、`tools.dispatch`、`trace.record_call`、role=tool 消息追加。B 调用同一个 `Agent().chat` 并使用既有契约数据，C 据返回/JSONL 拍摄和组织材料，不依赖 A 私有内部实现。

当前 A 的实测：12 个实现自测、10 条运行/服务检查、32 条 Mock Trace；这些仅是开发验证记录，不是比赛测试数量、覆盖率或性能成绩。详细日志见 `docs/evidence/` 与 A 报告。

| 项目 | 状态与限制 |
|---|---|
| 真实模型联网 | 【已实现但未验证】适配器代码在，SDK 模拟响应验证成功；无 Key，联网结果待验证。 |
| 向量 RAG | 【已实现但未验证】代码存在，未安装/下载 sentence-transformers/faiss 模型。失败回退关键词；向量质量与首次下载待验证。 |
| 任意自然语言理解 | 【部分实现】Mock 是关键词/正则剧本，有限城市/意图、默认乘客张三、默认明天；仅支持明确“乘客张三、李四”列表格式，复杂表述可能误解。 |
| 会话记忆 | 【部分实现】同一个 Agent 实例同 sid 内存保存，进程重启丢失；不同 sid 记忆隔离，但票务库/固定身份共享。无跨进程持久化、无长期上下文压缩。 |
| 身份与安全 | 【部分实现】固定虚构演示身份，工具拒绝他人手机号/订单号；无真实登录、多租户、完整提示注入防护或生产权限认证。 |
| 真实改签/儿童学生票/身份证实名 | 【尚未实现】只有政策检索，未建立改签动作、折扣、报销凭证状态、折扣机票或 P10 一证一票核验。 |
| 候补后台兑现 | 【尚未实现】monitor_seat 仅返回无票班次监控凭据；不轮询/排队/自动抢票兑现，不承诺成功。 |
| 库存更新与旧库升级 | 【部分实现】新库 2100 条、7 天；已有原库原样保留，没有自动 schema/数据迁移或每日滚动刷新。 |
| 并发与性能 | 【部分实现】SQLite 事务避免该实现的扣库/状态竞态；未做压力、负载/高并发或性能基准，Trace 计时不能当比赛性能结论。 |
| RAG 相关性与引用 | 【部分实现】关键词重叠而非 BM25/语义推理，可能召回不相关片段；真实模型引用仅由 Prompt 约束，未增加强制引用校验器。 |
| 错误与 Trace | 【部分实现】模型异常安全回复、工具异常 ok=false；契约只有两种 finish_reason，因此 stop 可包含失败。预览 200 字符可能截断、不是完整 JSON。Trace 不记录模型原始响应、变异 label 或时间戳，标签在证据包装中。 |
| Web/Trace 大规模使用 | 【部分实现】AppTest 与本地服务通过；历史文件全文读取，没分页/日志轮转/跨进程写锁；人工浏览器外观、多人共享及大量回放待验证。 |
| 正式参赛结论 | 【尚未实现】由 B 给正式测试结果，C 完成验收、截图视频与正式报告；A 没有提供覆盖率、性能评分、缺陷数量或成功率。 |

未声称这些未完成项已经通过。无已知阻塞 Mock 冒烟链路的代码 Bug；上述限制仍可能导致未覆盖输入失败，应由 B 的独立测试确认。

成员 C 当前可以开始 Mock 验收与拍摄准备；最终正式报告待 B 提供真实测试结论，并由 C 确认截图/成片和完整项目验收。
