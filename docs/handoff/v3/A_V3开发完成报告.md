# 成员 A：V3 开发完成报告

日期：2026-10-13（Asia/Shanghai）。分支 `feat/a-ticket-langchain-v3`。

已验证核心源码与证据提交：`595dc0af157e89613597946934f343a76216976b`；原型 `92efc2a739bd3712d2ff62910bf8944cd9ad81b9`，八工具 `950b0f2b62f41a6988cb28c306808baabebfab9b`。
这批报告会形成后续文档提交；最终交付提交以新标签 `handoff-a-langchain-v3-20261013` 解析，执行 `git rev-parse handoff-a-langchain-v3-20261013^{commit}` 获取完整 SHA。旧标签不移动。

**成员 A 开发交接状态：有条件交接。** 可供 B 正式测试和 C 拍摄离线 Mock；真实大模型尚未联网实测，正式成绩与人工验收待 B/C 提供。所有数字是成员 A 的实际自测结果，不是正式比赛评分。

## 实际现状与开发范围

V2最新接手HEAD为 `f8b493ad13bcbf7d4814d798d2ef2f223373b1ac`，不同于V2标签提交 `6ef683a50f60970dbd4ded1678a818d026afcbde`；已经含Web等待动画。旧环境未安装或使用LangChain/LangGraph，Agent原生Python循环。现在额外创建独立 `.venv-v3`，依赖 langchain 1.4.5、langchain-core 1.6.10、langchain-openai 1.7.1、langgraph 1.2.15、streamlit 1.65.0、openai 3.29.0；Python3.12.14，pip check无冲突。原环境和旧锁定依赖未覆盖。

A负责目标Agent、模型/工具/RAG/业务/CLI/Web/Trace及本模块自测；B负责正式测试断言、七维度评估/指标与缺陷；C负责跟进、最终验收、作品报告/截图/视频。仓库有B缺陷报告和DOCX总结，但没有judge完整测试层或V2/V3正式执行结果。95/100是B报告所述V1基线，不是本次实测成绩。

## 架构和实际API

`Agent.chat → LangChainAgent → create_agent → 标准模型 → AIMessage.tool_calls → StructuredTool/tools.dispatch → mock_core或rag → ToolMessage → 下一轮模型 → Trace`。

LangChain 1.x `create_agent` 管理循环和工具节点（底层依赖LangGraph）；没有把旧Agent._chat包装进节点。`BaseChatModel`/`ChatResult`/`AIMessage`用于离线Mock适配，`ChatOpenAI`用于Live；`StructuredTool.from_function`完整复用八工具JSON Schema；`AgentMiddleware.wrap_model_call/wrap_tool_call`记录真实事件和执行授权；`InMemorySaver`按thread_id=session_id隔离状态，delete_thread实现reset。未自建复杂状态图。

## 代码位置与职责

| 文件 | 职责 |
|---|---|
| target/agent.py | 兼容旧入口，选择legacy/langchain，RLock串行 |
| target/langchain_agent.py | 真正create_agent、会话、Trace中间件、MAX_STEPS、工具适配、Live初始化 |
| target/langchain_model.py | 标准离线模型，把框架消息转给Mock规则；不执行工具或循环 |
| target/write_authorization.py | 独立检查写授权、订单引用、成功锁与重复占座 |
| target/providers.py | 原legacy Mock/Live及六变异；Mock规则复用 |
| target/tools.py / mock_core.py | 既有8工具校验/分发、SQLite状态/库存/幂等，无本次修改 |
| target/rag.py / data/policies.md | 既有15条政策检索，无本次修改 |
| target/trace.py | 既有10字段JSONL，保持字节不变 |
| config.py / cli.py / web/app.py | 新引擎与工具集配置、模式展示，旧页面功能保留 |
| requirements-v3.txt / requirements-v3-lock.txt | 框架依赖及实际冻结，旧依赖保留 |
| tests/test_langchain_agent.py / tests/test_langchain_orders.py / tests/test_langchain_live_adapter.py | 13+13+2项新自测 |
| scripts/snapshot_v3_baseline.py / verify_v3.py | V2基线/99文件保护，框架API/CLI/Web证据 |
| scripts/validate_langchain_live.py / compare_v3_modes.py | 独立真实端点验证入口、Mock小样本对照 |
| scripts/v3_api_example.py / generate_v3_handoff.py | 可运行交接示例、源码/证据自动汇编报告 |
| docs/v3_development_log.md / v3_tool_migration_assessment.md | 持续记录与剩余6工具风险评估 |

## 工具、授权与执行方式

| 工具 | 必填参数 | 可选参数 |
|---|---|---|
| `query_tickets` | from_city, to_city, date | seat_type, kind |
| `monitor_seat` | train_no, date, seat_type | duration_min |
| `lock_seat` | train_no, date, seat_type, passengers | 无 |
| `create_order` | lock_id, passenger_ids, contact | 无 |
| `pay_order` | order_id | pay_type |
| `cancel_order` | order_id | reason |
| `query_order` | 无 | order_id, phone |
| `search_policy` | question | 无 |

八工具实际用途/返回结构见B手册。默认read_only保留可运行最小原型；all为完整模拟流程。写授权在工具执行前检查当前用户原文，失败返回原error结构并真实记录Trace，不执行后端。成功调用仍由LangChain调度，业务状态/幂等仍由原SQLite函数管理。

Mock复用V2规则决定下一条AIMessage，其实际ToolMessage来自框架工具执行；Live由ChatOpenAI接收真实模型响应，尚未联网。原Prompt在target/agent.py SYSTEM_PROMPT，框架补充日期/授权说明在langchain_agent.py；没有内部思维链日志。

## 多轮、RAG与Trace

同一Agent+session保留消息，不同session隔离；reset删除框架线程。InMemorySaver非持久化。RAG复用原中文字符/英文词重叠打分（不是BM25），按政策段检索TOP_K=3，模型得到带doc_id/source的工具结果后回复；没有迁移为LangChain向量链。

Trace直接记录wrap_tool_call真实请求/结果；详细event只在独立验证附件，公开JSON不加字段。step是本轮模型调用索引，工具表按实际请求顺序；工具耗时包含框架/业务/授权/序列化，total_latency_ms是原Trace起止perf_counter的整数毫秒，不含落盘，异常分支末尾checkpoint收尾在finish之后。模型无工具的最后回复轮不强造调用。tokens从AIMessage.usage_metadata累计，Mock为0；未成功返回的模型调用不能估算token。MAX_STEPS限制模型实际调用次数，耗尽仍返回max_steps_exceeded；stop不代表业务成功。

## 已实现与待完成

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


## 启动与实际验证

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

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_ENGINE="legacy"
$env:AGENT_PROVIDER="mock"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
.\.venv-v3\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-v3\Scripts\python.exe scripts/smoke.py --output-dir "artifacts/runtime/v3-smoke-$stamp"
.\.venv-v3\Scripts\python.exe scripts/verify_v3.py --toolset all --output-dir "artifacts/runtime/v3-framework-$stamp"
.\.venv-v3\Scripts\python.exe scripts/v3_api_example.py --output-dir "artifacts/runtime/v3-example-$stamp"
```

smoke 显式检测 legacy 入口；框架测试单独创建 LangChain Agent。unittest 推荐在上面的 legacy 环境发现全部测试，单项框架测试内部显式切换。验证脚本使用临时/新库，输出目录必须不存在，重复执行换新的后缀。框架 verify 内部显式设置 Mock；不会读取 Key 调用真实模型。

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


## Git与保护

```
87abfaf5560ecf182f9fe65e998aadd35cc3d729 | chore(v3): preserve latest V2 baseline and isolate LangChain dependencies
92efc2a739bd3712d2ff62910bf8944cd9ad81b9 | feat(v3): run real LangChain agent with two tools and contract-compatible traces
950b0f2b62f41a6988cb28c306808baabebfab9b | feat(v3): integrate all eight tools with independent write authorization
595dc0af157e89613597946934f343a76216976b | test(v3): validate Live adapter offline and preserve full compatibility evidence
```

V1/V2标签和99原文件已逐一hash核对；V2核心快照保存为.py.txt，避免混入Python源码。V1→V2五缺陷和原始失败证据保持在旧文档/证据，V3不替换它们。最终文档提交/新标签为后续交接快照，仅推送V3独立分支和新标签，不合并main。

## 已知限制与后续建议

- 默认引擎仍 legacy；`AGENT_ENGINE=langchain` 才进入框架。默认 LC 工具集 read_only，仅两个工具；all 才开放完整流程。
- LangChain Mock 复用V2规则决策，不能证明真实模型自主规划、复杂推理或抗幻觉能力。model字段仍是配置名称，Mock显示glm-4-flash不表示调用了这个模型。
- InMemorySaver不跨进程/重启持久化，未做历史压缩；长对话/多session内存增长，Mock测试消息留存也会占内存。Agent互斥锁串行化调用；没有正式并发压力结果。
- 写授权为保守中文语法，问题/否定/引用/假设和复杂表达可能拒绝；不是生产身份认证。一次请求最多一个成功锁，不支持跨轮旧锁直接下单、多路线一轮多订单；拒绝也会计入真实工具尝试。
- DB固定一个模拟当前用户，不同session只隔离消息状态，不隔离订单/库存。独立用例应独立DB，不可仅换session来清业务数据。
- 候补仅模拟返回监控凭据，无后台持续抢票。没有真实改签执行、身份证核验、折扣计算或支付渠道。库只覆盖生成日起7天，旧库不自动刷新；用新隔离库复现。
- 真实模型仍可能不调用工具、选错工具、生成不可靠回复，Prompt不能保证完全没有幻觉；需Key后由A接入验证、B独立评估。stop只是循环结束，必须同时检查ok、工具结果和业务状态。
- 向量RAG和LangChain模式HTTP业务链未单独实测；共同HTTP工具/legacy链已由smoke实测。未测部署到公网、负载、重启恢复、远端端点兼容性。


优先获得有效Key验证真实端点，然后由B正式回归；再根据实际结果决定是否加入持久化Checkpointer、历史裁剪、框架专属变异、授权澄清UI。不要把LangChain库存在等同于真实模型能力提升已经验证。

## 当前Python源文件清单

- `cli.py`
- `config.py`
- `data/seed.py`
- `run_demo.py`
- `scripts/audit_v2_evidence.py`
- `scripts/check_v2_handoff.py`
- `scripts/compare_v3_modes.py`
- `scripts/check_v3_handoff.py`
- `scripts/generate_handoff.py`
- `scripts/generate_v2_handoff.py`
- `scripts/generate_v3_handoff.py`
- `scripts/handoff_example.py`
- `scripts/read_legacy_doc.py`
- `scripts/reproduce_v2_defects.py`
- `scripts/run_v2_selftests.py`
- `scripts/smoke.py`
- `scripts/snapshot_v3_baseline.py`
- `scripts/v2_api_example.py`
- `scripts/v3_api_example.py`
- `scripts/validate_langchain_live.py`
- `scripts/validate_real_provider.py`
- `scripts/verify_v3.py`
- `target/__init__.py`
- `target/agent.py`
- `target/langchain_agent.py`
- `target/langchain_model.py`
- `target/mock_api.py`
- `target/mock_core.py`
- `target/providers.py`
- `target/rag.py`
- `target/tools.py`
- `target/trace.py`
- `target/write_authorization.py`
- `tests/test_agent.py`
- `tests/test_core.py`
- `tests/test_langchain_agent.py`
- `tests/test_langchain_live_adapter.py`
- `tests/test_langchain_orders.py`
- `tests/test_provider.py`
- `tests/test_v2_defects.py`
- `tests/test_v2_provider.py`
- `tests/test_web.py`
- `web/app.py`

报告由generate_v3_handoff读取Git、实际Schema、验证JSON/日志和源码hash生成。生成时间为本批文档日期，不随既有文件自动更新；源码改变后需重新验证和审查。
