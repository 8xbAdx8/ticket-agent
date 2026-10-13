# Ticket Agent V3 持续开发记录

日期按 Asia/Shanghai；所有验证为 A 自测，B/C 正式结论单独确认。

## 2026-10-13 审查与 V2 基线保护

- 读取 V3 用户任务书、README、依赖、config、contract、Agent/Provider/8 工具/Trace/RAG 与 V2 五份手册和证据。接手 HEAD f8b493ad13bcbf7d4814d798d2ef2f223373b1ac，工作区原来干净，包含标签之后的 Web 增强。
- V1 标签 e719956d7c82bd6392c25916d3c193be7e4b452e；V2 标签 6ef683a50f60970dbd4ded1678a818d026afcbde，均不移动。当前 Agent 为自研循环，项目 .venv 无 LangChain/LangGraph；B judge 与正式 V2 execution.jsonl 不存在，真实 API Key 未配置。
- 从最新 V2 建立 feat/a-ticket-langchain-v3。V2 核心文本和 99 个原文件 SHA256 保存至 docs/evidence/v3/v2_baseline/；原 DB/Trace/失败证据/旧手册不改写。
- 新增 scripts/snapshot_v3_baseline.py；实际运行 .venv/Scripts/python.exe scripts/snapshot_v3_baseline.py 成功。
- pip index 实际查询稳定版本：langchain 1.4.5、langchain-openai 1.7.1；对照官方 create_agent/middleware/checkpointer 文档。新增 requirements-v3.txt 和单独 .venv-v3，原 .venv 与 requirements-lock.txt 保留。
- B/C 影响：新增 engine 模式将保持旧返回字段，legacy 继续默认；最小原型先只接 query_tickets/search_policy，不把 V2 原循环包成框架节点。
- 官方资料：https://docs.langchain.com/oss/python/langchain/agents 、middleware/custom 、short-term-memory 。安装与原型验证结果在后续条目登记。
- 本阶段 SHA 在下一阶段登记。

基线准备提交：87abfaf5560ecf182f9fe65e998aadd35cc3d729。

## 2026-10-13 真正的两个工具 LangChain 原型

- 新增 target/langchain_agent.py：create_agent 管理模型/工具循环；StructuredTool 复用原 tools.dispatch/schema；wrap_model_call 与 wrap_tool_call 把实际事件记入原 Trace；InMemorySaver 按 session_id 保存框架会话，reset 删除该线程。
- 新增 target/langchain_model.py：标准 BaseChatModel，复用 V2 Mock 决策规则产生 AIMessage；它不执行工具，也不执行原 Agent 循环。LangChain 的 ToolMessage 实际反馈给模型。模型接入代码使用 ChatOpenAI，无 Key 条件立即拒绝 Live，网络未调用。
- 修改 config/Agent：AGENT_ENGINE=legacy|langchain（默认 legacy），延迟导入框架；公开 chat 字段不变。新增模型调用轮数上限，与 V2 MAX_STEPS 保持口径，而非套用图节点计数。单次工具顺序执行，默认禁用外部 LangSmith 上传。
- CLI 增加 engine/provider 提示；Web 标出 LangChain Mock/Live，六变异按钮仅 legacy 可用；原动画、工具表、JSON/回放保持。smoke 明确在 legacy 环境检查原链路。
- 实际安装 langchain 1.4.5、langchain-core 1.6.10、langchain-openai 1.7.1、langgraph 1.2.15；.venv-v3 pip check 无冲突，独立冻结 requirements-v3-lock.txt。原 V2 .venv/锁定文件保留。
- 新增 tests/test_langchain_agent.py 12 项必要自测：查询/政策引用、框架真实调用与反馈、交通日期席别继承、session 隔离/reset、参数/schema、工具异常、模型异常、MAX_STEPS/恢复、Trace、legacy 变异和无 Key。
- 实际命令 `.venv-v3/Scripts/python.exe scripts/run_v2_selftests.py --log docs/evidence/v3/prototype_unit.txt --pattern test_langchain_agent.py`：12 项通过；既有 `scripts/smoke.py --output-dir docs/evidence/v3/prototype_legacy_smoke`：40 自测（旧28+新12）、10 入口/服务检查、32 legacy Mock Trace 全部通过。
- 新增 scripts/verify_v3.py；首次 CLI 自测因错误假定 stdout 有 provider 而 AssertionError，原结果和失败说明保留。改为检查真实 JSONL；`--output-dir docs/evidence/v3/prototype_retry` 实际 5 轮框架 API、CLI once/chat、Web AppTest 成功；99 原文件保护通过。沒有修改 B 规则。
- B/C 影响：新 provider 值 langchain_mock/langchain_live 用于明确模式；contract 原 provider 字段没有枚举限制，未新增字段。step 为本轮实际模型调用轮，工具耗时包含框架工具执行/序列化，total 为 Trace 起止；框架模型无工具轮不强造工具步骤。
- 限制：第一轮只开放 query_tickets/search_policy；其余六工具等待业务授权/重放风险评估。InMemorySaver 只在当前 Agent/进程内保留，未实现跨重启持久化；六故意变异仅 legacy，不外推为 LangChain 模型能力。真实大模型尚未联网实测。
- 本模块源码 SHA 在下一阶段登记。

两个工具原型提交：92efc2a739bd3712d2ff62910bf8944cd9ad81b9。

## 2026-10-13 八工具与独立写操作授权

- 先完成 docs/v3_tool_migration_assessment.md 的六工具成本/状态/重放风险评估，再接入。
- 修改 target/langchain_agent.py：read_only/all 两种工具集；仍由 create_agent 执行原工具。新增 target/write_authorization.py：当前用户独立授权检查、订单引用核验、本轮成功锁限定、一轮最多一次成功锁座。被拒绝调用真实记入 Trace，不调用后端。
- 新增 tests/test_langchain_orders.py（最终13项）；原型 tests/test_langchain_agent.py 增加未知工具与多调用模型桩支持（最终13项）。查询、监控、锁座、创建、支付、重复支付、退款、订单查询及安全阻断均实际运行。
- 初次运行漏设 PYTHONIOENCODING，日志采集器不能按 UTF-8 解码，未生成日志；设置后保留 orders_unit_utf8.txt 的实际失败（A 自测连接关闭和预期回复措辞），修正自测后 orders_unit_passed.txt 12项全过。后来新增同模型轮重复写探针，在最终56项自测中通过。
- 实际 `.venv-v3/Scripts/python.exe scripts/verify_v3.py --toolset all --output-dir docs/evidence/v3/full_tools` 和 final_framework：11轮 API、CLI once/chat、Web AppTest 通过，覆盖8工具；保护99原文件通过。
- B/C 影响：默认只读原型不变；all 才开放完整模拟流程。新的拒绝信息在原 result_preview/error 内，不新增契约字段。必须对授权规则适用范围和写操作工具序列做独立回归。六变异保留 legacy。
- 已知限制：中文保守命令识别，跨轮使用旧锁、多路线一轮多订单未支持；模拟固定身份不等同真实登录系统。没有真实模型结果。
- 本模块 commit SHA 在下一阶段登记。

八工具授权模块提交：950b0f2b62f41a6988cb28c306808baabebfab9b。

## 2026-10-13 Live 接入准备、扩展回归和开销对照

- 新增 scripts/validate_langchain_live.py：默认只预检；--run 且 openai/有效 Key 才尝试远端。每场景独立临时 DB/Trace，记录实际框架事件、模型消息、调用参数/call_id/结果回传与耗时，错误与业务完成情况单独确认；不会写入旧 Trace。
- 新增 tests/test_langchain_live_adapter.py：实际 ChatOpenAI/SDK 转换链上的2项无网络桩验证，覆盖工具Schema、服务器call_id、ToolMessage、token累计、异常/下一轮恢复。SDK 边界已替换，不能把这些结果当真实模型结果。
- 实际 live_sdk_stub.txt 2项通过；live_preflight/preflight.json：无 Key、未调用远端、0真实Trace，状态“真实大模型尚未联网实测”。配置使用既有 AGENT_PROVIDER/MODEL/API_KEY/BASE_URL，无秘密提交。
- 最终 `.venv-v3/Scripts/python.exe scripts/smoke.py --output-dir docs/evidence/v3/final_legacy_smoke`：56项自测全通过（原28+框架原型13+订单13+Live SDK桩2），10入口/服务检查、32 legacy Mock Trace。原 `.venv/Scripts/python.exe scripts/smoke.py --output-dir docs/evidence/v3/original_environment_smoke`：原28通过、新框架28明确skip；10入口/服务检查、32 legacy Mock Trace。六变异仍通过 test_six_injected_mutations。
- 最终 verify_v3 --toolset all --output-dir docs/evidence/v3/final_framework：11轮框架API覆盖8工具、CLI/Web成功、99保护文件相同。B正式judge未在仓库，未执行或改写正式断言，不声称100/100。
- 新增 scripts/compare_v3_modes.py，实际 --output-dir docs/evidence/v3/mock_overhead；同环境每模式3组5轮（15轮）Mock，保存原始耗时，不形成正式性能指标。首次框架初始化包含懒导入，调用中位数见 comparison.json。pip check再次确认无依赖冲突。
- B/C 影响：需要区分legacy Mock/LangChain Mock/Live SDK桩/真实模型；stop不等于业务成功。新provider值虽不改变字段，B如果自行枚举provider需审查；最终测试成绩须B提供。
- 未完成：真实远端Function Calling、跨重启会话持久化、LangChain六变异、正式压力/模型幻觉评估、C人工验收与录屏。只交付准备/可复现A自测。
- 本阶段源码 SHA 在交接文档登记。
