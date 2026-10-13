"""从实际源码、Git 和 V3 验证附件生成交接文档；拒绝覆盖旧报告。"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from target.tools import TOOLS


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True,encoding="utf-8").strip()


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def main():
    folder = ROOT/"docs/handoff/v3"
    folder.mkdir(parents=True,exist_ok=True)
    names = ["A_V3开发完成报告.md","B_V3测试对接手册.md","C_V3验收与拍摄说明.md","V2_V3技术对照报告.md","V3最终交付清单.md"]
    if any((folder/n).exists() for n in names):
        raise FileExistsError("已有V3报告；先审查新的源码/证据，不能自动覆盖历史报告")
    evidence = read("docs/evidence/v3/final_framework/verification.json")
    baseline = read("docs/evidence/v3/v2_baseline/manifest.json")
    perf = read("docs/evidence/v3/mock_overhead/comparison.json")
    real = read("docs/evidence/v3/live_preflight/preflight.json")
    turns = read("docs/evidence/v3/final_framework/api_results.json")
    log = (ROOT/"docs/evidence/v3/final_legacy_smoke/unit.txt").read_text(encoding="utf-8")
    old_log = (ROOT/"docs/evidence/v3/original_environment_smoke/unit.txt").read_text(encoding="utf-8")
    count = int(re.search(r"Ran (\d+) tests",log)[1])
    skipped = int(re.search(r"skipped=(\d+)",old_log)[1])
    assert count == 56 and skipped == 28 and "\nOK\n" in log and "FAILED" not in log
    assert evidence["api_turns"]==11 and len(evidence["tools"])==8 and not real["real_model_tested"]
    for p,h in evidence["source_sha256"].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,"源码与验证附件不同: "+p
    for p,h in baseline["protected_sha256"].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,"旧文件变化: "+p
    branch,sha = git("branch","--show-current"),git("rev-parse","HEAD")
    assert branch == "feat/a-ticket-langchain-v3"
    for tag,h in baseline["tags"].items():
        assert git("rev-parse",tag+"^{commit}")==h
    commits = git("log","--reverse","--format=%H | %s",baseline["source_head"]+"..HEAD")
    common = f"""日期：2026-10-13（Asia/Shanghai）。分支 `{branch}`。

已验证核心源码与证据提交：`{sha}`；原型 `92efc2a739bd3712d2ff62910bf8944cd9ad81b9`，八工具 `950b0f2b62f41a6988cb28c306808baabebfab9b`。
这批报告会形成后续文档提交；最终交付提交以新标签 `handoff-a-langchain-v3-20261013` 解析，执行 `git rev-parse handoff-a-langchain-v3-20261013^{{commit}}` 获取完整 SHA。旧标签不移动。

**成员 A 开发交接状态：有条件交接。** 可供 B 正式测试和 C 拍摄离线 Mock；真实大模型尚未联网实测，正式成绩与人工验收待 B/C 提供。所有数字是成员 A 的实际自测结果，不是正式比赛评分。
"""
    versions = "、".join(f"{n} {v}" for n,v in evidence["versions"].items())
    tools_table = "| 工具 | 必填参数 | 可选参数 |\n|---|---|---|\n" + "\n".join(
        f"| `{t['function']['name']}` | {', '.join(t['function']['parameters'].get('required',[])) or '无'} | {', '.join(k for k in t['function']['parameters']['properties'] if k not in t['function']['parameters'].get('required',[])) or '无'} |" for t in TOOLS)
    setup = r'''```powershell
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
'''
    verify = r'''```powershell
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
'''
    results = f"""| 实际验证 | 结果 | 证据 |
|---|---|---|
| V3环境 unittest（由smoke执行） | {count}项通过，0 skip：旧28+框架原型13+订单13+Live SDK桩2 | docs/evidence/v3/final_legacy_smoke/unit.txt |
| 原V2环境 unittest | 旧28通过，框架28 skip（没有安装LangChain） | docs/evidence/v3/original_environment_smoke/unit.txt |
| 两套环境入口冒烟 | 每套10项检查成功、32条legacy Mock Trace | final_legacy_smoke/verification.json、original_environment_smoke/verification.json |
| LangChain Mock API | 11轮对话覆盖8工具，交通切换/日期/政策/订单流程成功 | final_framework/api_results.json、framework_events.json |
| LangChain CLI/Web | CLI once/chat、AppTest消息/工具表/JSON/回放成功 | final_framework/verification.json |
| 六种预设变异 | legacy 的六变异自测通过；LC初始化主动拒绝变异 | test_agent.test_six_injected_mutations、自测日志 |
| 原始成果保护 | {len(baseline['protected_sha256'])}个原文件SHA256相同；V1/V2标签相同 | v2_baseline/manifest.json |
| Live接入 | ChatOpenAI/SDK边界桩2项通过，无Key预检；远端调用0 | live_sdk_stub.txt、live_preflight/preflight.json |

以上证据路径相对于 `docs/evidence/v3/`（第一条已写完整路径）。`scripts/smoke.py` 的历史 version_scope 字符串仍写 V2 A self-validation，实际分支和V3扩展测试以本表与日志为准。

原型首次CLI验证断言错误以及订单自测初次失败都保留，见 prototype_check_failure.txt、orders_unit_utf8.txt；没有删改失败证据或B判定规则。原型12项、订单初始12项是阶段记录，最终分别为13项，不把重复运行累计成“更多测试用例”。
"""
    statuses = """| 功能 | 状态 | 边界 |
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
"""
    limitations = """- 默认引擎仍 legacy；`AGENT_ENGINE=langchain` 才进入框架。默认 LC 工具集 read_only，仅两个工具；all 才开放完整流程。
- LangChain Mock 复用V2规则决策，不能证明真实模型自主规划、复杂推理或抗幻觉能力。model字段仍是配置名称，Mock显示glm-4-flash不表示调用了这个模型。
- InMemorySaver不跨进程/重启持久化，未做历史压缩；长对话/多session内存增长，Mock测试消息留存也会占内存。Agent互斥锁串行化调用；没有正式并发压力结果。
- 写授权为保守中文语法，问题/否定/引用/假设和复杂表达可能拒绝；不是生产身份认证。一次请求最多一个成功锁，不支持跨轮旧锁直接下单、多路线一轮多订单；拒绝也会计入真实工具尝试。
- DB固定一个模拟当前用户，不同session只隔离消息状态，不隔离订单/库存。独立用例应独立DB，不可仅换session来清业务数据。
- 候补仅模拟返回监控凭据，无后台持续抢票。没有真实改签执行、身份证核验、折扣计算或支付渠道。库只覆盖生成日起7天，旧库不自动刷新；用新隔离库复现。
- 真实模型仍可能不调用工具、选错工具、生成不可靠回复，Prompt不能保证完全没有幻觉；需Key后由A接入验证、B独立评估。stop只是循环结束，必须同时检查ok、工具结果和业务状态。
- 向量RAG和LangChain模式HTTP业务链未单独实测；共同HTTP工具/legacy链已由smoke实测。未测部署到公网、负载、重启恢复、远端端点兼容性。
"""
    guide = """| 顺序 | 同一会话输入 | 应观察到 | 证据/成功依据 |
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
"""
    files = "\n".join("- `"+p.relative_to(ROOT).as_posix()+"`" for p in sorted(ROOT.rglob("*.py"))
                      if not any(x in p.parts for x in (".venv",".venv-v3","artifacts",".git","__pycache__")))
    reports = {}
    reports[names[0]] = "# 成员 A：V3 开发完成报告\n\n"+common+f"""
## 实际现状与开发范围

V2最新接手HEAD为 `{baseline['source_head']}`，不同于V2标签提交 `{baseline['tags']['handoff-a-v2-20261013']}`；已经含Web等待动画。旧环境未安装或使用LangChain/LangGraph，Agent原生Python循环。现在额外创建独立 `.venv-v3`，依赖 {versions}；Python3.12.14，pip check无冲突。原环境和旧锁定依赖未覆盖。

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

{tools_table}

八工具实际用途/返回结构见B手册。默认read_only保留可运行最小原型；all为完整模拟流程。写授权在工具执行前检查当前用户原文，失败返回原error结构并真实记录Trace，不执行后端。成功调用仍由LangChain调度，业务状态/幂等仍由原SQLite函数管理。

Mock复用V2规则决定下一条AIMessage，其实际ToolMessage来自框架工具执行；Live由ChatOpenAI接收真实模型响应，尚未联网。原Prompt在target/agent.py SYSTEM_PROMPT，框架补充日期/授权说明在langchain_agent.py；没有内部思维链日志。

## 多轮、RAG与Trace

同一Agent+session保留消息，不同session隔离；reset删除框架线程。InMemorySaver非持久化。RAG复用原中文字符/英文词重叠打分（不是BM25），按政策段检索TOP_K=3，模型得到带doc_id/source的工具结果后回复；没有迁移为LangChain向量链。

Trace直接记录wrap_tool_call真实请求/结果；详细event只在独立验证附件，公开JSON不加字段。step是本轮模型调用索引，工具表按实际请求顺序；工具耗时包含框架/业务/授权/序列化，total_latency_ms是原Trace起止perf_counter的整数毫秒，不含落盘，异常分支末尾checkpoint收尾在finish之后。模型无工具的最后回复轮不强造调用。tokens从AIMessage.usage_metadata累计，Mock为0；未成功返回的模型调用不能估算token。MAX_STEPS限制模型实际调用次数，耗尽仍返回max_steps_exceeded；stop不代表业务成功。

## 已实现与待完成

{statuses}

## 启动与实际验证

{setup}
{verify}
{results}

## Git与保护

```
{commits}
```

V1/V2标签和99原文件已逐一hash核对；V2核心快照保存为.py.txt，避免混入Python源码。V1→V2五缺陷和原始失败证据保持在旧文档/证据，V3不替换它们。最终文档提交/新标签为后续交接快照，仅推送V3独立分支和新标签，不合并main。

## 已知限制与后续建议

{limitations}

优先获得有效Key验证真实端点，然后由B正式回归；再根据实际结果决定是否加入持久化Checkpointer、历史裁剪、框架专属变异、授权澄清UI。不要把LangChain库存在等同于真实模型能力提升已经验证。

## 当前Python源文件清单

{files}

报告由generate_v3_handoff读取Git、实际Schema、验证JSON/日志和源码hash生成。生成时间为本批文档日期，不随既有文件自动更新；源码改变后需重新验证和审查。
"""
    reports[names[1]] = "# 成员 B：V3 测试对接手册\n\n"+common+rf"""
## 安装、启动和接口

{setup}

Python入口仍为 `from target.agent import Agent; agent=Agent(); result=agent.chat(session_id,message)`，同一进程设置环境变量应在import config前完成，配置改变需重新启动。可显式 `Agent(engine="langchain")`，工具集仍由配置决定。完整可运行示例已真实执行：

```powershell
$env:PYTHONIOENCODING="utf-8"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
.\.venv-v3\Scripts\python.exe scripts/v3_api_example.py --output-dir "artifacts/runtime/v3-api-$stamp"
```

脚本在独立DB/Trace中明确patch Mock/all，7轮覆盖8工具，结果保存results.json。核心调用如下（前面已按启动配置初始化新DB）：

```python
from target.agent import Agent
agent = Agent()
result = agent.chat("B-case-001", "订明天上海到杭州的高铁")
print(result["tool_sequence"])
result = agent.chat("B-case-001", "支付我刚才的订单。")
agent.reset("B-case-001")
```

这段调用方式已由verify_v3与v3_api_example实际执行，模拟订票应query_tickets→lock_seat→create_order，后续支付为pay_order。独立Python示例文件包含完整隔离初始化，避免复制片段时使用默认旧库。

## 原返回字段与映射

| 字段 | 说明 |
|---|---|
| session_id | 原输入会话标识，同一Agent中用于thread_id |
| provider | legacy为mock/openai；框架为langchain_mock/langchain_live，无新增顶层字段 |
| model | 配置AGENT_MODEL，Mock只是名称，不代表实际联网 |
| user_msg | 本轮原输入 |
| steps | step从1开始，对应本轮模型调用轮数；calls数组内记录实际工具尝试 |
| tool_sequence | 按steps/calls顺序展平，包含失败/授权拒绝调用，不能由reply猜测 |
| reply | 实际模型/Mock最终文字，或安全异常/上限提示 |
| finish_reason | stop或max_steps_exceeded；stop只表示结束，检查ok/结果/订单后才能判成功 |
| tokens | prompt/completion；框架从usage_metadata累计，Mock为0，SDK桩是假定计数 |
| total_latency_ms | Trace创建至finish/abort的perf_counter整数毫秒；不含保存JSONL，异常checkpoint收尾也不计入 |

`steps[].calls[]`严格5字段：tool（实际请求名）、args（实际参数对象）、ok（无error且ToolMessage非error）、latency_ms（框架工具执行/授权/序列化耗时）、result_preview（原Trace字符串摘要，最多200字符后加...，可能不是可解析JSON）。详细结果和服务器call_id在验证framework_events.json，未塞入契约字段。

实际查询JSON（从final_framework/api_results.json原样提取，日期/耗时为当次运行）：

```json
{json.dumps(turns[0],ensure_ascii=False,indent=2)}
```

不能硬编码当次订单ID、日期或耗时。`provider=langchain_live`表示适配器路径，不足以证明远端请求；本次SDK桩测试也走该适配器，正式真实模型证据必须同时检查preflight/verification的real_api_attempted和原始远端响应。

## 八工具参数与返回

{tools_table}

| 工具 | 用途和后端真实返回 |
|---|---|
| query_tickets | trains/count（kind/train_no/路线/date/depart/arrive/seat_type/price/seats_left）；售罄行与无班次区别保留 |
| monitor_seat | 模拟task_id、train_no/date/seat_type/duration_min/current_seats/status；非后台持续监控 |
| lock_seat | lock_id、班次/日期/席别/passengers/unit_price/count/expire_at/ttl_seconds；占库存 |
| create_order | 订单信息order_id/phone/train_no/date/seat_type/passengers/amount/status/created_at/lock_id，idempotent_hit |
| pay_order | order_id/status，首次pay_type/amount/duplicate_pay=false；重复duplicate_pay=true，无再次扣款 |
| cancel_order | order_id/status/amount/fee/refund/fee_rate/policy_ref；pending取消与paid退款不同 |
| query_order | 指定order_id返回本人订单对象，否则orders/count/queried_phone |
| search_policy | question/hits/count，hits含doc_id/source/title/content/score |

参数校验与状态错误返回error对象，Trace ok=false。Schema直接复用target/tools.py（additionalProperties=false）；核心结果也复用原mock_core/rag，未改变契约。字段详细原始示例见final_framework/framework_events.json，不从截断preview恢复完整对象。

## 写授权、变异与用例隔离

LangChain写授权检查见v3_tool_migration_assessment.md。被拒绝调用仍出现在Trace；不能据“出现pay_order”断言扣款，应看ok/后端状态。一次请求最多一个成功锁；创建必须用本轮成功锁；明确支付/退票须有订单引用；问题/否定/引用/假设拒绝。复杂中文、英文及跨轮直接消费旧锁是已知限制，需B评审。

六变异继续仅legacy：date_offset=1（日期偏移）、skip_lock（跳过锁）、repeat_call（重复调用）、infinite_loop（持续调用）、route_error（政策错路由）、no_citation（缺引用）。开启示例：

```python
from target import providers
from target.agent import Agent
providers.set_mutation("date_offset", 1)
agent = Agent(engine="legacy")
# 运行用例后恢复；已有会话可能已含错参数，重新建Agent
providers.clear_mutations()
agent = Agent(engine="legacy")
```

Web切legacy后启用开关；恢复正常模式再清空会话。LC按钮禁用且初始化发现非空变异报ValueError；当前没有LC专属变异集，不能直接把legacy变异覆盖率外推过去。

每个测试用例独立AGENT_DB_PATH、AGENT_TRACE_DIR与session，固定模拟身份不会按session自动隔离库存。Agent.reset只清消息，不清数据库/Trace。手动重置仅作用于明确配置的测试库：停止占用它的CLI/Web/HTTP后 `python data/seed.py --reset`；换新Trace路径保留既有证据。使用--output-dir脚本会拒绝现有目录。

JSONL每行一个返回值，读取方式：

```python
import json
from pathlib import Path
import config
records = [json.loads(line) for line in (config.TRACE_DIR / "traces.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
```

## A已跑验证与B后续工作

{verify}
{results}

B需在独立分支/测试层分别评估legacy与LC：返回契约/provider、工具选择/参数/同轮多调用、会话/reset、循环预算、RAG来源、写授权/否定/省略/提示注入、库存及幂等、异常、长会话/并发/框架开销；有效Key后另测真实模型幻觉与端点兼容。正式测试断言不得仅据Mock回复固定措辞；具体规则由B制定。

原五缺陷V1证据与V2修复对照仍见旧手册。请B检查原五个xfail，修复后重新处理标记防止统计错误；95/100仅V1报告基线，未运行B完整层不能宣称100/100。当前仓库没有judge.executor/metrics，所以不执行不存在的命令、不复制改写B断言。

## Live准备与限制

设置AGENT_ENGINE=langchain、AGENT_PROVIDER=openai以及合法支持工具调用的AGENT_MODEL/AGENT_BASE_URL；Key从个人环境安全注入，不放进源码/截图/日志。`validate_langchain_live.py --output-dir 新目录`先预检；有效配置后才使用--run（有远端费用）。它按场景隔离库/记录，业务成功仍待人工检查。此次real_trace_count=0、API Key未配置。

{limitations}
"""
    reports[names[2]] = "# 成员 C：V3 验收与拍摄说明\n\n"+common+f"""
## 用容易理解的语言介绍项目

项目用虚构高铁/航班/政策搭建可测试的出行助手，让团队检查“理解请求→调用工具→遵守业务规则→给出有来源的回复”是否正确。普通聊天机器人可以直接回答，Ticket Agent需查模拟数据库、锁座/下单、检查订单状态和引用政策；因此便于比赛按工具调用、功能、记忆、安全、边界和性能等维度测量。

V2由自己写的Python循环安排步骤；V3把“模型回答要调用哪个工具、执行工具、把结果交回模型、继续到结束”交给真正的LangChain框架。模拟业务、政策、Web和对外JSON沿用。LangGraph在这里是框架底层依赖，并没有额外自建复杂图。

LangChain Mock仍是规则模拟模型，展示框架工程流程，不能讲成真实AI自主规划。LangChain Live的真实模型负责理解、工具选择与组织回复，但目前没有密钥，尚未联网实测。可讲已完成接入代码，不可展示为实测模型成绩。

## 环境和从零部署

已验证Windows PowerShell、Python3.12.14；依赖 {versions}。如果没有Python，先安装Python3.12并确认 `py -3.12 --version`；下载/克隆仓库后在仓库根目录执行。已有本机环境不要重建。

{setup}

默认引擎legacy；展示V3务必使用AGENT_ENGINE=langchain，完整订单演示用all。只读演示用read_only，仅支持查询与政策。改环境变量后停止旧服务重启；新PowerShell窗口不会自动继承另一个窗口临时变量。

## 验收步骤

{guide}

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

{statuses}
{results}

{limitations}
"""
    a,b = perf["summaries"]["legacy"],perf["summaries"]["langchain"]
    reports[names[3]] = "# V2 / V3 技术对照报告\n\n"+common+f"""
## 以实际基线对照

V2对照采用最新接手HEAD `{baseline['source_head']}`，含标签之后的Web动画；旧标签仍为 `{baseline['tags']['handoff-a-v2-20261013']}`。没有把旧V2报告中数字改为本次V3数据。

| 维度 | V2 legacy | V3 LangChain | 状态/兼容限制 |
|---|---|---|---|
| 执行循环 | Agent._chat手工循环 | create_agent框架模型/工具节点循环 | 【已实现并验证】禁止旧_chat参与的探针通过 |
| 模型适配 | MockProvider、OpenAI SDK | 标准BaseChatModel Mock、ChatOpenAI | Mock/SDK桩已验证，真实端点待验证 |
| 工具调度 | Python遍历tool_calls→dispatch | AIMessage→StructuredTool→ToolMessage→框架下一轮 | 【已实现并验证】8Schema复用，max_concurrency=1 |
| 状态 | sessions的字典消息列表 | InMemorySaver，thread_id=session_id | 【已实现并验证】隔离/reset；两者均非跨重启持久化 |
| RAG | 中文字符/英文词打分，15政策 | 同一个search_policy工具与语料 | 【已实现并验证】没换向量框架，不虚报算法升级 |
| Trace | 循环直接record_call | middleware记录实际请求/响应，再调用原Trace | 【已实现并验证】10顶层/5calls字段不改 |
| provider | mock/openai | langchain_mock/langchain_live | 字段兼容，新值需B检查自己的枚举假设 |
| 步数 | 最多MAX_STEPS次模型调用 | 中间件限制实际模型调用次数 | 不用框架图节点数冒充模型轮数 |
| 敏感模拟写 | Mock识别/Prompt+后端状态权限 | 加独立当前消息授权与订单引用/锁校验 | 【已实现并验证】更保守，可能新增拒绝表达 |
| 六变异 | 原6开关 | 仅legacy开放；LC明确拒绝 | legacy已验证，LC专属变异【未实现】 |
| CLI/Web | 原命令、动画、轨迹、回放 | 同入口，加引擎/工具集提示 | 【已实现并验证】CLI/AppTest/legacy服务检查 |
| 可测试性 | legacy Mock规则+业务/SDK自测 | 框架消息探针、授权拦截、预算/隔离与SDK边界桩 | 新28项A自测；不能外推为B覆盖率 |
| 依赖 | 原requirements-lock、.venv | 独立requirements-v3-lock、.venv-v3 | LangChain1.4.5/LangGraph1.2.15真实安装；lazy import保旧入口 |

## Mock运行开销的实际小样本

`scripts/compare_v3_modes.py --output-dir docs/evidence/v3/mock_overhead`，同一V3环境每模式3组5轮，相同查询/交通切换/日期/政策输入、各自新DB和Agent，直接mock_core，无网络/向量。顺序每组legacy先运行，再langchain，未随机化。

| 实测口径 | legacy Mock | LangChain Mock |
|---|---|---|
| 轮数 | {a['turns']} | {b['turns']} |
| chat调用墙钟中位数ms（含落盘） | {a['chat_wall_median_ms']:.3f} | {b['chat_wall_median_ms']:.3f} |
| chat范围ms | {a['chat_wall_min_ms']:.3f}—{a['chat_wall_max_ms']:.3f} | {b['chat_wall_min_ms']:.3f}—{b['chat_wall_max_ms']:.3f} |
| 三次初始化ms | {', '.join(f'{v:.3f}' for v in a['init_ms'])} | {', '.join(f'{v:.3f}' for v in b['init_ms'])} |

本次小样本显示框架有额外本地调度/检查点开销，首次初始化含延迟导入。墙钟包含Trace写盘，和契约total_latency_ms口径不同；不要拿整数0ms说“无耗时”。没有内存/并发/长对话、远端模型响应时间或统计置信度，不形成比赛性能优劣结论。

## 已验证与尚未验证

{statuses}
{results}

V2五修复继续保留：方式切换席别一致性、机票回高铁、售罄/无班次区别、重复支付幂等提示、支付政策走P11。LangChain Mock复用同一规则，额外经过实际框架消息/工具链；这不代表真实模型也会全对。原五缺陷证据与对照见docs/handoff/V1_V2缺陷修复对照.md，不覆写。

## 迁移收益和兼容风险

实际收益：标准模型/工具接口、框架管理循环和会话、真实ToolMessage反馈、中间件可独立插入授权/Trace，后续可选持久化与模型替换。并未凭安装框架证明订票准确率提高。

风险：依赖和端点变化；框架包体/初始化/状态开销；provider新值、失败调用和同轮工具排序断言；授权更保守带来的拒绝；LangChain的图递归限制与模型预算不能混同；旧测试需要区分当前引擎；记忆不是账户隔离。B正式回归待完成，C描述这些真实技术变化，不预先写正式测试成绩。

{limitations}
"""
    reports[names[4]] = "# V3 最终交付清单\n\n"+common+f"""
## 共同确认

- [x] 【已实现并验证】V3独立分支，从最新V2创建；V1/V2标签及99原文件保护。
- [x] 【已实现并验证】真实LangChain1.x create_agent，不包装旧Agent循环。
- [x] 【已实现并验证】两个工具原型先验证提交，再扩到八工具。
- [x] 【已实现并验证】独立写授权、成功锁约束、一次占座、订单引用；旧后端权限/状态/幂等复用。
- [x] 【已实现并验证】Agent.chat、10顶层字段与5calls字段、两个finish_reason值兼容；contract未改。
- [x] 【已实现并验证】Checkpointer会话隔离/reset；模型调用预算、工具错误、异常与Trace落盘。
- [x] 【已实现并验证】LangChain Mock、本地RAG政策引用、8工具流程、CLI/Web/JSON/回放。
- [x] 【已实现并验证】legacy正常模式、六变异、原V2环境28项自测通过。
- [x] 【已实现并验证】V3环境56项A自测、10项入口检查、11轮LC API、CLI/Web，证据保留。
- [x] 【已实现并验证】独立依赖、pip check、新脚本、持续开发记录与六工具评估。
- [x] 【已实现并验证】Live配置/初始化/SDK桩/无Key预检部分；原真实Provider路径保留。
- [ ] 【已实现但未验证】有效Key下真实模型自主工具选择、联网结果、端点兼容与异常场景。
- [ ] 【已实现但未验证】旧可选向量检索；未纳入本次升级的验证成绩。
- [ ] 【未实现】跨重启持久化、历史压缩、LC专属六变异和正式并发性能验证。
- [ ] 【未实现】成员B完整正式V3回归/判定/指标；原五xfail需B处理。
- [ ] 【未实现】成员C人工视觉验收、截图、正式参赛报告与视频。

## 关键命令与证据

{setup}
{verify}
{results}

## Git和实际文件交付

核心与证据SHA `{sha}`。最终报告源码列表、工具参数从本仓库生成；文档最终提交由新标签解析，不使用自身提交SHA循环写文档。不要移动旧标签或未经协调合并main。

```
{commits}
```

必须交付：target/agent.py、langchain_agent.py、langchain_model.py、write_authorization.py、原providers/tools/mock_core/rag/trace/mock_api、config.py、cli.py、web/app.py、data/seed.py、policies.md、原cases/tests、三份新框架自测、requirements-v3.txt/lock、scripts中验证/示例/生成脚本、docs/contract.md、原V1/V2手册和证据、新docs/evidence/v3及五份本目录报告。完整Python路径清单见A报告。

运行环境目录.venv/.venv-v3、个人Key、临时库与运行日志不应作为源码提交。源码仓库中的原数据库/Trace按历史保护原则保留，队友复现使用新隔离路径seed，不在旧库上正式回归。

## 给B和C的材料

B：B_V3测试对接手册.md、原contract、tool schema、新分支/交付标签、A自测源码和新证据、六工具迁移风险；请分别测legacy/LC，并审查provider/耗时、拒绝语法、reset、同轮多工具、重放/库存/幂等、真实模型。B未合并完整层时不要运行虚构judge命令。

C：C_V3验收与拍摄说明.md、A架构/Prompt代码、V2_V3技术对照报告.md、V1_V2原缺陷修复对照、实际Mock JSON与事件/回放、可演示流程与分镜。报告测试成绩等待B提供；LangChain Mock字幕需始终明确。

## 已知问题与人工确认

{limitations}

有条件交接依据：框架/8工具/兼容接口/本地入口与A自测已实跑、原成果保护已核验；缺少真实Key实测、B正式回归、C人工验收。没有凭计划勾选完成项，没有把100/100当实际成绩。
"""
    for name,body in reports.items():
        # 报告不能泄露本机账户路径或Key；命令只含仓库相对路径和环境变量名。
        assert str(Path.home()) not in body and str(ROOT) not in body
        (folder/name).write_text(body,encoding="utf-8")
    facts = {"generated_date":"2026-10-13","branch":branch,"verified_source_commit":sha,
             "reports":["docs/handoff/v3/"+n for n in names],"unit_tests":count,"legacy_passed":count-skipped,
             "legacy_skipped":skipped,"api_turns":evidence["api_turns"],"tools":evidence["tools"],
             "real_model_tested":False,"protected_files":len(baseline["protected_sha256"]),
             "source_sha256":evidence["source_sha256"],"report_sha256":{n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in names}}
    (ROOT/"docs/evidence/v3/handoff_facts.json").write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"reports":len(reports),"unit_tests":count,"protected":facts["protected_files"]},ensure_ascii=False))


if __name__ == "__main__":
    main()
