# 成员 B：V2 测试对接说明

生成日期：2026-10-13（Asia/Shanghai）。分支：`feat/a-ticket-v2`。
经过回归的源码提交：`1804518c9a312ec0d4ab8cb000124e37ee551887`；本手册是该源码之上的文档提交。
最终交付提交用 `git rev-parse HEAD` 确认；交付标签计划为 `handoff-a-v2-20261013`，仅在检查通过后建立，解析标签可得到最终 SHA，避免文档声称包含自身的提交哈希。
V1 标签保留：`handoff-a-20261012` → `e719956d7c82bd6392c25916d3c193be7e4b452e`。
所有运行结果均为 A 自测；业务虚构。成员 B 报告的 V1 95/100 是其提供的结论，A 未获得完整 judge/用例/原始 execution.jsonl，不能宣称 V2 正式 100/100。


## 获取、安装与隔离启动

V2 使用独立分支 `feat/a-ticket-v2`，不要把它覆盖到 V1 标签。仓库协作者获取已发布的 V2 分支后，先确认 `git log -1` 与交付标签；已有本地修改时先自行保留，再切换。测试层是否与此分支组合由 B 决定，A 没有复制 judge 或改正式断言。

私有仓库需要协作者权限；权限由团队协调，不共享访问令牌。新机器可运行 `git clone --branch feat/a-ticket-v2 https://github.com/8xbAdx8/ticket-agent.git` 后进入 ticket-agent。已有 checkout 可以 `git fetch origin --tags`、`git switch feat/a-ticket-v2`；已有同名本地分支时先检查差异，不能直接 reset 覆盖队友修改。最终交付标识用 `git rev-parse handoff-a-v2-20261013` 确认。

```powershell
# 在项目根目录执行；新机器先建立环境并安装冻结依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$v2Run = "v2-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0,6)
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\$v2Run\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\$v2Run\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe cli.py chat
```

已有虚拟环境时跳过前两条；系统 python 若打开商店，改用已安装 Python 3.12 的实际可执行文件建立环境。`seed.py` 遇到已有库拒绝覆盖，新目录无需 --reset。每次全新独立用例换新运行目录，环境变量在导入 config 或启动程序前设置。


CLI `once` 每次是新 Agent；多轮请用 `cli.py chat` 或同一个 Python Agent 实例与 session_id。CLI `batch cases/demo.json` 是已有演示用例，不是 B 的 100 用例。网页用 `.venv\Scripts\python.exe -m streamlit run web/app.py`。

## 已运行的 Python 入口与真实 JSON

直接执行 `scripts/v2_api_example.py --output-dir <新的证据目录>`。已运行版本在 `docs/evidence/v2/api_example/`，四轮序列为订票 query→lock→create、政策 search_policy、pay_order、重复 pay_order。
核心调用如下（先按上面的环境初始化独立库）：

```python
from target.agent import Agent
agent = Agent()
for message in ["订明天上海到杭州的高铁", "锁座后多久必须完成支付？", "支付我刚才的订单。", "支付"]:
    result = agent.chat("v2-api-example", message)
    print(result["tool_sequence"], result["reply"])
```

以下为该示例实际政策轮返回，未改字段或数值；运行时间及模型字段只是本机 Mock 记录：

```json
{
  "session_id": "v2-api-example",
  "provider": "mock",
  "model": "glm-4-flash",
  "user_msg": "锁座后多久必须完成支付？",
  "steps": [
    {
      "step": 1,
      "calls": [
        {
          "tool": "search_policy",
          "args": {
            "question": "锁座后多久必须完成支付？"
          },
          "ok": true,
          "latency_ms": 0,
          "result_preview": "{\"question\": \"锁座后多久必须完成支付？\", \"hits\": [{\"doc_id\": \"P11\", \"source\": \"data/policies.md#P11\", \"title\": \"锁座与支付有效期\", \"content\": \"模拟锁座有效期 15 分钟，过期未支付自动释放库存；下单必须提供与锁座一致的乘客列表。重复支付不重复扣减库存。\", \"score\": 1.8708}, {..."
        }
      ]
    }
  ],
  "tool_sequence": [
    "search_policy"
  ],
  "reply": "模拟锁座有效期 15 分钟，过期未支付自动释放库存；下单必须提供与锁座一致的乘客列表。重复支付不重复扣减库存。 未支付订单取消不收取手续费，释放已占库存；已退款或已取消订单不得再次释放库存，取消后的订单不可支付。（依据 P11, P12）",
  "finish_reason": "stop",
  "tokens": {
    "prompt": 0,
    "completion": 0
  },
  "total_latency_ms": 0
}
```

## 契约字段与判定注意

| 字段 | 原语义（V2 保持） |
|---|---|
| session_id / user_msg | 调用方 ID / 本轮原始输入 |
| provider / model | 提供者名称 / 配置模型名；Mock 默认模型名不证明真实调用 |
| steps | 模型工具步骤；step 从 1 起；无工具回复可为空 |
| steps[].calls[] | 每次调用的 **5 个字段**：tool、args、ok、latency_ms、result_preview |
| tool_sequence | 按 steps/calls 顺序扁平化的工具名列表，真实重复调用仍保留 |
| reply | 最终回复或错误说明；不能只看关键词/stop 判业务成功 |
| finish_reason | 无后续工具调用或模型错误处理时 stop；用完 MAX_STEPS 时 max_steps_exceeded |
| tokens | prompt/completion 累计；Mock=0，SDK 桩仅验证累加逻辑 |
| total_latency_ms | 进入 Trace 到 finish/abort 的 perf_counter 差值整毫秒，含模型/工具执行，不含保存 JSONL；不是工具耗时相加 |

calls.ok=false 表示 error/异常；模型返回错误仍可能 stop。result_preview 超过 200 字符会截断并加 ...，不能当作完整 JSON 解析。顶层仍是 10 个字段，无新 trace 嵌套，无新增 duplicate_pay 契约字段；重复标记来自已有 pay_order 后端结果。参数 Schema 与 V1 全部相同，仅 kind/seat 错配现在得到校验错误。
`Agent.reset` 清会话、不重置 SQLite；`清空会话` 不恢复库存/订单。不同测试独立 Agent+session_id+数据库+Trace目录；改变环境后重启或导入前设置 config；并行进程共享库仍会相互影响。

读取当前目录 JSONL 的例子：

```python
import json
from pathlib import Path
import config
for line in (Path(config.TRACE_DIR) / "traces.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        print(row["session_id"], row["tool_sequence"], row["finish_reason"])
```

原路径默认 traces/traces.jsonl，新测试应使用 AGENT_TRACE_DIR。出现坏行保存原文件并记录行号，不删除失败记录。

## 工具 Schema 与返回

| 工具 | 必填 | 可选 | 主要返回/语义 |
|---|---|---|---|
| `query_tickets` | from_city, to_city, date | seat_type, kind | trains/count；行含 kind、seat_type、seats_left、价格/路线/班次；本次 HTTP 实际字段：trains, count |
| `monitor_seat` | train_no, date, seat_type | duration_min | task_id/status/duration_min 等监控凭据（无后台监控守护进程）；本次 HTTP 实际字段：task_id, train_no, date, seat_type, duration_min, current_seats, status |
| `lock_seat` | train_no, date, seat_type, passengers | 无 | lock_id/expire_at/ttl_seconds；unit_price/count 和锁座信息；本次 HTTP 实际字段：lock_id, train_no, date, seat_type, passengers, unit_price, count, expire_at, ttl_seconds |
| `create_order` | lock_id, passenger_ids, contact | 无 | order_id/status/amount/train_no/date；重复创建标记可能返回；本次 HTTP 实际字段：order_id, phone, train_no, date, seat_type, passengers, amount, status, created_at, lock_id, idempotent_hit |
| `pay_order` | order_id | pay_type | order_id/status；重复支付另有 duplicate_pay=true；本次 HTTP 实际字段：order_id, status, pay_type, amount, duplicate_pay |
| `cancel_order` | order_id | reason | status；已支付退款含 fee/fee_rate/refund/policy_ref，未支付直接取消；本次 HTTP 实际字段：order_id, status, amount, fee, refund, fee_rate, policy_ref |
| `query_order` | 无 | order_id, phone | 指定 ID 返回单个订单；按本人查询返回 orders 列表；本次 HTTP 实际字段：order_id, phone, train_no, date, seat_type, passengers, amount, status, created_at, lock_id |
| `search_policy` | question | 无 | hits；每条含 doc_id/content/score；本次 HTTP 实际字段：question, hits, count |

成功返回随业务分支略有不同，以 tools.py、mock_core.py 和 regression/http.json 的真实响应为准；失败原结构 error 不变。席别与交通方式必须一致，日期 YYYY-MM-DD；订单只允许模拟本人，未对接真实支付。

## 六变异开关与恢复

推荐用实例级字典，不污染其他用例：

```python
from target.agent import Agent
from target.providers import MockProvider, clear_mutations
clear_mutations()
agent = Agent(MockProvider(mutations={"date_offset": 1}))
result = agent.chat("isolated-offset", "查明天上海到杭州的高铁")
# 恢复时新建正常实例，同时换全新库/Trace，不能沿用刚才错误日期的历史
normal = Agent(MockProvider(mutations={}))
```

既有全局方式 `set_mutation(name, True)` / `clear_mutations()` 保留，date_offset 使用值 1；clear_mutations 只清全局字典，实例自带字典需清空或换新实例。Web 开关仅本浏览器会话，“恢复正常模式”后“清空会话”，写业务测试还要换隔离库并重启。

| 开关 | 已观察行为 | 可检测缺陷维度 |
|---|---|---|
| date_offset=1 | 查询日期比正常值 +1 天 | 相对日期与参数准确性 |
| skip_lock | query→create，创建失败且没有 lock | 业务顺序/前置条件 |
| repeat_call | query_tickets 连续 2 次 | 重复调用/效率 |
| infinite_loop | query 后连续 monitor，8 步 max_steps_exceeded | 循环/最大步数 |
| route_error | 政策咨询改调用 query_tickets | 意图工具路由 |
| no_citation | search_policy 存在但回复无 doc_id | RAG 引用可检查性 |

这只是 A 提供可复现条件，不是 B 的正式判定规则/变异分数。六项实际证据见 regression/python_examples.json 与 audit_first.json。
重置业务时优先换新目录；若要清空自己已有隔离库，先停 CLI/Web/HTTP 并确认 AGENT_DB_PATH 指向该测试库，再 `data/seed.py --reset`。不要指向 V1 原始库。日期过期时也用新库；初始化覆盖当天和后六天。

## 回归入口与 B 下一步

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke.py
# 输出目录必须不存在；时间后缀避免覆盖历史
$v2Evidence = "artifacts/runtime/v2-proof-" + [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts/reproduce_v2_defects.py --output-dir "$v2Evidence/defects" --label "v2-local-rerun"
.\.venv\Scripts\python.exe scripts/v2_api_example.py --output-dir "$v2Evidence/api"
.\.venv\Scripts\python.exe scripts/validate_real_provider.py --output-dir "$v2Evidence/real-preflight"
```


本仓库不存在 judge/ 或 B 原始 execution.jsonl。`python -m judge.executor` / `python -m judge.metrics` 没在 A 仓库执行；B 在自己的完整测试层中按原配置执行并保留新的结果目录。不要用 A 的 28 自测或 5 个观察目标替换正式 100 用例。

请重点重新确认 F03/M11/F14/F13/T25，连带多轮省略日期/路线/席别、含糊澄清、否定支付、取消咨询、复合订票支付、正常退票和所有六变异。**原五个 xfail 由 B 重新处理**：若修复已确认，应取消或更新预期失败条件，并检查 XPASS/strict 设置，避免把已修复成功用例统计为失败或漏算。不由 A 修改断言换通过率。
DEF-03 仅建议其他席别，明确尚未查询其库存；如果正式用例要求实际查出其他席别，需先对齐额外调用口径。本轮保持单次查询与原工具序列。

## 真实模式与限制

当前没有 API Key。`preflight.json` 明确 api_key_present=false、real_model_tested=false、real_trace_count=0：**真实模型待验证**。

已实现 OpenAI 风格 Chat Completions 适配器，SDK 测试桩检查调用 ID/工具结果回传、错误和最大步数，不能算模型自主决策测试。Prompt 已增加 V2 规则，第三方端点是否支持全部协议需实测。

有合法有效 Key 时，由使用者通过安全环境注入 `AGENT_API_KEY`，不要写入源码、文档、录屏或聊天。配置 `AGENT_PROVIDER=openai`、服务方提供的 `AGENT_BASE_URL` 和支持工具调用的 `AGENT_MODEL` 后，重启进程并显式运行：

```powershell
$v2Real = "artifacts/runtime/real-" + [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts/validate_real_provider.py --output-dir $v2Real --run
```

这是实际远端 API 调用，可能产生服务方费用。没有 --run / 没有 Key / provider 不是 openai 时仅预检。8 个独立场景覆盖单轮、多轮交通切换、工具回传、查锁下单、RAG、工具故障、正常停止、强制 MAX_STEPS=1；每个场景使用临时虚构库。上限场景是人为缩小步数的验证，不能据此称模型自然死循环。
每个 result.json 保存输入、完整消息（含工具参数/结果和服务器 call_id）、实际回复/Trace、耗时、调用错误与“完成情况待确认”；finish_reason=stop 不保证业务成功。模型认证/网络失败也会保存失败回复，不能当作成功。Mock 与真实附件放在不同目录，不与 V1 Trace 混用。
协议参考：[OpenAI Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。本次未迁移 API 或新增契约字段。


A 可交付稳定 Mock V2 和证据。正式通过率/覆盖率/缺陷关闭/耗时统计由 B 提供；目前全量正式 V2 成绩待确认。
字节 SHA256 审计用于 A 原始工作区的保护与证据绑定；换行转换会改变文件字节。跨机器先按 Git 提交/标签确认源码，再把新机器的运行证据另存，不能把换行造成的哈希差异当作 Agent 缺陷。
