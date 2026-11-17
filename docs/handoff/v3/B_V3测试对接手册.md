# 成员 B：V3 测试对接手册

日期：2026-10-13（Asia/Shanghai）。分支 `feat/a-ticket-langchain-v3`。

已验证核心源码与证据提交：`595dc0af157e89613597946934f343a76216976b`；原型 `92efc2a739bd3712d2ff62910bf8944cd9ad81b9`，八工具 `950b0f2b62f41a6988cb28c306808baabebfab9b`。
这批报告会形成后续文档提交；最终交付提交以新标签 `handoff-a-langchain-v3-20261013` 解析，执行 `git rev-parse handoff-a-langchain-v3-20261013^{commit}` 获取完整 SHA。旧标签不移动。

**成员 A 开发交接状态：有条件交接。** 可供 B 正式测试和 C 拍摄离线 Mock；真实大模型尚未联网实测，正式成绩与人工验收待 B/C 提供。所有数字是成员 A 的实际自测结果，不是正式比赛评分。

## 安装、启动和接口

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
{
  "session_id": "v3-demo",
  "provider": "langchain_mock",
  "model": "glm-4-flash",
  "user_msg": "查明天上海到杭州的高铁",
  "steps": [
    {
      "step": 1,
      "calls": [
        {
          "tool": "query_tickets",
          "args": {
            "from_city": "上海",
            "to_city": "杭州",
            "date": "2026-10-14",
            "kind": "高铁",
            "seat_type": "二等座"
          },
          "ok": true,
          "latency_ms": 1,
          "result_preview": "{\"trains\": [{\"kind\": \"高铁\", \"train_no\": \"G7303\", \"from_city\": \"上海\", \"to_city\": \"杭州\", \"date\": \"2026-10-14\", \"depart\": \"12:34\", \"arrive\": \"13:34\", \"seat_type\": \"二等座\", \"price\": 73.0, \"seats_left\": 51}, {\"..."
        }
      ]
    }
  ],
  "tool_sequence": [
    "query_tickets"
  ],
  "reply": "为您查到以下有余票的班次：G7303 上海→杭州 12:34 开，二等座 ¥73.0，余票 51；G7302 上海→杭州 09:17 开，二等座 ¥73.0，余票 47；G7301 上海→杭州 06:00 开，二等座 ¥73.0，余票 35。",
  "finish_reason": "stop",
  "tokens": {
    "prompt": 0,
    "completion": 0
  },
  "total_latency_ms": 9
}
```

不能硬编码当次订单ID、日期或耗时。`provider=langchain_live`表示适配器路径，不足以证明远端请求；本次SDK桩测试也走该适配器，正式真实模型证据必须同时检查preflight/verification的real_api_attempted和原始远端响应。

## 八工具参数与返回

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


B需在独立分支/测试层分别评估legacy与LC：返回契约/provider、工具选择/参数/同轮多调用、会话/reset、循环预算、RAG来源、写授权/否定/省略/提示注入、库存及幂等、异常、长会话/并发/框架开销；有效Key后另测真实模型幻觉与端点兼容。正式测试断言不得仅据Mock回复固定措辞；具体规则由B制定。

原五缺陷V1证据与V2修复对照仍见旧手册。请B检查原五个xfail，修复后重新处理标记防止统计错误；95/100仅V1报告基线，未运行B完整层不能宣称100/100。当前仓库没有judge.executor/metrics，所以不执行不存在的命令、不复制改写B断言。

## Live准备与限制

设置AGENT_ENGINE=langchain、AGENT_PROVIDER=openai以及合法支持工具调用的AGENT_MODEL/AGENT_BASE_URL；Key从个人环境安全注入，不放进源码/截图/日志。`validate_langchain_live.py --output-dir 新目录`先预检；有效配置后才使用--run（有远端费用）。它按场景隔离库/记录，业务成功仍待人工检查。此次real_trace_count=0、API Key未配置。

- 默认引擎仍 legacy；`AGENT_ENGINE=langchain` 才进入框架。默认 LC 工具集 read_only，仅两个工具；all 才开放完整流程。
- LangChain Mock 复用V2规则决策，不能证明真实模型自主规划、复杂推理或抗幻觉能力。model字段仍是配置名称，Mock显示glm-4-flash不表示调用了这个模型。
- InMemorySaver不跨进程/重启持久化，未做历史压缩；长对话/多session内存增长，Mock测试消息留存也会占内存。Agent互斥锁串行化调用；没有正式并发压力结果。
- 写授权为保守中文语法，问题/否定/引用/假设和复杂表达可能拒绝；不是生产身份认证。一次请求最多一个成功锁，不支持跨轮旧锁直接下单、多路线一轮多订单；拒绝也会计入真实工具尝试。
- DB固定一个模拟当前用户，不同session只隔离消息状态，不隔离订单/库存。独立用例应独立DB，不可仅换session来清业务数据。
- 候补仅模拟返回监控凭据，无后台持续抢票。没有真实改签执行、身份证核验、折扣计算或支付渠道。库只覆盖生成日起7天，旧库不自动刷新；用新隔离库复现。
- 真实模型仍可能不调用工具、选错工具、生成不可靠回复，Prompt不能保证完全没有幻觉；需Key后由A接入验证、B独立评估。stop只是循环结束，必须同时检查ok、工具结果和业务状态。
- 向量RAG和LangChain模式HTTP业务链未单独实测；共同HTTP工具/legacy链已由smoke实测。未测部署到公网、负载、重启恢复、远端端点兼容性。

