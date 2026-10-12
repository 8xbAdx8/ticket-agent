# 成员 B 测试对接手册

报告日期：2026-10-12（Asia/Shanghai）。运行证据时间：2026-10-12T20:11:38.809590+08:00。

核验实现版本：`e719956d7c82bd6392c25916d3c193be7e4b452e`；分支 `feat/a-ticket-handoff`。报告最后文档提交可用 `git rev-parse handoff-a-20261012` 取得（Git 提交不能把自身 SHA 写进自身内容；最终 SHA 另在交付回复中给出）。

数据来源：当前源码、`docs/contract.md`、Git 提交、`docs/evidence/verification.json` 及对应实际日志。所有运行结果均为 Mock 或本地模拟响应，未联网测试真实模型。

## 1. 对接职责与准备

| 成员 | 责任与交付边界 |
|---|---|
| A（本人，非队长） | Agent 主循环、模型 Provider、模拟高铁/机票、8 个工具与 Function Calling、RAG、CLI、Streamlit、Trace 与契约接口，以及本人模块基本自测。 |
| B（测试负责人） | 根据被测 Agent 与契约设计/执行工具、功能、RAG、多轮、安全、边界、性能测试；记录缺陷、独立给出正式测试结论与成绩。 |
| C（持续跟进与最终交付负责人） | 开发期了解进度、协调和记录问题；最终组织验收、作品介绍、正式报告、截图与视频制作；正式测试数据由 B 提供。 |

A 的 `tests/` 与 `scripts/smoke.py` 只验证自身实现及运行条件，不替 B 完成正式测试方案、评分系统或缺陷评估，也未改动 B/C 的代码。

本手册只交付被测 Agent 的运行方式、稳定接口及可复现条件。B 自己确定正式测试方案、断言、缺陷评级、覆盖率与成绩。A 的基本自测可作实现参考，不能当 B 的正式结果。接口权威来源是原 `docs/contract.md`，本次未修改；文件 SHA256 `bfe2f8ebf1ec02b831765286652e50344d1cfcc24d5179bd8ffd78fe6e8c0381`。

环境实际验证版本：Python 3.12.14；openai 3.29.0；streamlit 1.65.0；fastapi 0.143.0；uvicorn 0.54.0；pandas 3.0.6；pytest 9.1.1。完整传递依赖见 `requirements-lock.txt`。

## 2. 安装与运行

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

若在无依赖机器只跑 Mock + CLI，不需要安装 requirements；若运行 A 的完整 `tests/`（含 Web 和真实适配器自测），需安装锁定依赖。`pytest` 被安装但本次实际测试命令是 unittest，不能写成“pytest 全部通过”。

验证入口：`python -m unittest discover -s tests -v` 为成员 A 12 个基本自测；`python scripts/smoke.py` 创建新的隔离目录、捕获实际命令和本地服务证据（会更新 docs/evidence，本次交付前的证据请先另存）。进程运行前设置配置，import 后修改 os.environ 不会改变已导入 config。

## 3. Python 入口（已经实际执行）

```python
from target.agent import Agent
agent = Agent()  # 默认 mock；一组多轮用同一个实例
r1 = agent.chat("S1", "查明天上海到杭州的高铁")
r2 = agent.chat("S1", "我要买一张")
r3 = agent.chat("S1", "支付")
r4 = agent.chat("S1", "帮我退掉")
print(r1["tool_sequence"])
print(r2["tool_sequence"])
print(r3["finish_reason"])
```

同一组语句已通过 `scripts/handoff_example.py` 和多轮自测执行。观测序列依次为 query_tickets；query_tickets→lock_seat→create_order；pay_order；cancel_order，工具 ok 均为 true，finish_reason 都为 stop。不得每轮新建 Agent 后还期望记忆存在；`Agent().chat(session_id,message)` 是单次入口表达方式，多轮需保留实例。

实际第一轮完整返回（直接从 `docs/evidence/python_examples.json` 读取，不是手写伪造模板；日期/订单/耗时随重跑变化）：

```json
{
  "session_id": "handoff-normal",
  "provider": "mock",
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
            "date": "2026-10-13",
            "kind": "高铁",
            "seat_type": "二等座"
          },
          "ok": true,
          "latency_ms": 1,
          "result_preview": "{\"trains\": [{\"kind\": \"高铁\", \"train_no\": \"G7303\", \"from_city\": \"上海\", \"to_city\": \"杭州\", \"date\": \"2026-10-13\", \"depart\": \"12:34\", \"arrive\": \"13:34\", \"seat_type\": \"二等座\", \"price\": 73.0, \"seats_left\": 50}, {\"..."
        }
      ]
    }
  ],
  "tool_sequence": [
    "query_tickets"
  ],
  "reply": "为您查到以下车次：G7303 上海→杭州 12:34 开，二等座 ¥73.0，余票 50；G7302 上海→杭州 09:17 开，二等座 ¥73.0，余票 47；G7301 上海→杭州 06:00 开，二等座 ¥73.0，余票 35。",
  "finish_reason": "stop",
  "tokens": {
    "prompt": 0,
    "completion": 0
  },
  "total_latency_ms": 1
}
```

也可直接运行 `python scripts/handoff_example.py`，输出包含正常多轮、候补和六变异的 label/result 包装；其中 result 才是原契约 JSON。全部内容与保存 Trace 的相应行一致。

## 4. 完整返回 JSON 字段

| 字段 | 类型 | 含义与限制 |
|---|---|---|
| session_id | string | 调用传入非空 sid；同实例同 sid 延续 messages。不是登录身份。 |
| provider | string | 实际 Provider.name，通常 mock/openai。 |
| model | string | config.MODEL_NAME；Mock 中仅配置名，不代表联网用了该模型。 |
| user_msg | string | 本轮用户原文，不是整段历史。 |
| steps | array | 有工具的模型轮次列表，每项有 step（1 起）和 calls。最终无工具回答不新增一步，无工具时为空。 |
| tool_sequence | array[string] | 按 steps/calls 展开后的工具名顺序，包含失败调用与重复调用。 |
| reply | string | 最终文字答复，包括错误提示；不是业务成功标志。 |
| finish_reason | string | stop 或 max_steps_exceeded，见下文判定。 |
| tokens | object | prompt/completion 两个整数，真实 Provider 各轮 usage 累加；SDK 没有 usage 时为 0，Mock 始终 0。 |
| total_latency_ms | integer | 一轮实际时间（毫秒截断），冻结后返回/保存相同。 |

上表共 10 个顶层字段。未新增 timestamp、mutation、trace 嵌套字段。变异名在旁路包装文件 label 里，或由 B 在自己的运行元数据中保存。

### steps[].calls[]

| 字段 | 类型 | 意义 |
|---|---|---|
| tool | string | Provider 请求的工具名称；可记录未知名称的失败，不应以此证明工具存在。 |
| args | 通常 object | 模型传参原样；正常 schema 参数为 object。真实模型返回坏 JSON 时可能记录原始字符串，dispatch 拒绝；B 可作为异常输入证据，不应假设每次都可 args['date']。 |
| ok | boolean | result 字典含 error 或工具执行抛异常时 false；成功执行为 true，不表示模型语义/参数意图一定正确。 |
| latency_ms | integer | dispatch 中校验、执行和异常处理的实际耗时；HTTP 模式包含请求往返。 |
| result_preview | string | JSON 序列化的前 200 字符；过长再加 `...`，最多 203 字符，截断后可能不是合法 JSON。 |

实际调用记录：

```json
{
  "tool": "query_tickets",
  "args": {
    "from_city": "上海",
    "to_city": "杭州",
    "date": "2026-10-13",
    "kind": "高铁",
    "seat_type": "二等座"
  },
  "ok": true,
  "latency_ms": 1,
  "result_preview": "{\"trains\": [{\"kind\": \"高铁\", \"train_no\": \"G7303\", \"from_city\": \"上海\", \"to_city\": \"杭州\", \"date\": \"2026-10-13\", \"depart\": \"12:34\", \"arrive\": \"13:34\", \"seat_type\": \"二等座\", \"price\": 73.0, \"seats_left\": 50}, {\"..."
}
```

`step` 按 Provider 回合计，一步可以有两次或更多 tool_calls。Python 当前逐个执行，不是并发；repeat_call 的两次 query 在同一步。`tool_sequence = [c['tool'] for s in steps for c in s['calls']]` 是字段含义说明，不是 B 的正式评分代码。

### finish_reason 与耗时

1. Provider 本轮无工具请求，即以 stop 完成；工具报错后 Mock 给出解释也会 stop。
2. Provider 抛异常/返回错误消息格式，Agent 安全回复并 stop。契约没有 provider_error 状态，因此 B 要同时检查 reply 和 calls.ok。
3. 连续 MAX_STEPS 回合都要求工具，耗尽 for 循环为 max_steps_exceeded；最后工具可以成功，依然表示循环未得到最终无工具回答。
4. 请求 sid/message 非字符串或空白时入口直接抛 ValueError，不生成 Trace。初始化缺 Key/依赖错误也可能在 chat 前抛出。磁盘追加失败会抛异常，没有声称已落盘。

单次 latency 和 total 使用单调 perf_counter 真计时，非固定数。total 起点在本轮 Trace 初始化，终点是 finish，包含模型/工具循环；不包含最后写盘时间。模型时间及整数截断意味着 total 不应直接等于所有调用 latency 之和，0ms 不是伪造。

## 5. 读取 Trace（不会覆盖历史）

```python
import json
from pathlib import Path
import config
path = config.TRACE_DIR / "traces.jsonl"
with path.open(encoding="utf-8") as f:
    for line_no, line in enumerate(f, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print("不完整行：", line_no)  # 保留原文件，复制证据排查
            continue
        print(record["session_id"], record["tool_sequence"], record["finish_reason"])
```

JSONL 是每次 chat 一行，而不是整个会话只一行；同 sid 多轮会重复出现。默认 `traces/traces.jsonl`，设置 AGENT_TRACE_DIR 后读取对应位置。本次已实际逐行解析 `docs/evidence/mock_traces.jsonl` 32 条；返回与保存完全一致的验证在 test_agent 中。不要解析 result_preview 来取完整工具数据；需要工具完整返回可单独 dispatch，或由 B 在自己平台保留数据，不改 A 契约。

## 6. 工具参数及返回

以下参数表自动取自当前 TOOLS schema。query_order 无 required，order_id/phone 都可省略，省略返回本人列表；指定 order_id 走单订单分支。契约表虽写“order_id 或 phone”，现有 schema/实现允许默认本人查询，未擅改契约。

| 工具 | 状态 | 用途 | 参数（`*` 必填） |
|---|---|---|---|
| `query_tickets` | 【已实现并验证】Mock/本地 HTTP | 查询指定出发地、到达地、日期的车次与余票数量。date 必须是 YYYY-MM-DD 格式，当用户说'下周三''明天'等相对时间时必须先换算成具体日期。 | `from_city*`: string；`to_city*`: string；`date*`: string；`seat_type`: string（二等座/一等座/商务座/经济舱/公务舱）；`kind`: string（高铁/机票） |
| `monitor_seat` | 【已实现并验证】Mock/本地 HTTP | 当目标车次无余票时，订阅该车次的余票监控（候补），返回监控任务 ID。 | `train_no*`: string；`date*`: string；`seat_type*`: string；`duration_min`: integer |
| `lock_seat` | 【已实现并验证】Mock/本地 HTTP | 锁定座位，占住库存并返回有时效的 lock_id。下单前必须先调用本工具。 | `train_no*`: string；`date*`: string；`seat_type*`: string；`passengers*`: array |
| `create_order` | 【已实现并验证】Mock/本地 HTTP | 凭有效的 lock_id 创建订单。同一 lock_id 重复调用只会生成一个订单（幂等）。 | `lock_id*`: string；`passenger_ids*`: array；`contact*`: string |
| `pay_order` | 【已实现并验证】Mock/本地 HTTP | 支付订单。仅修改订单状态，不涉及任何真实支付渠道。 | `order_id*`: string；`pay_type`: string（alipay/wechat/card） |
| `cancel_order` | 【已实现并验证】Mock/本地 HTTP | 退票。手续费按知识库政策 P01 的阶梯规则计算并引用出处。 | `order_id*`: string；`reason`: string |
| `query_order` | 【已实现并验证】Mock/本地 HTTP | 查询订单。不传 phone 时只返回当前登录用户的订单；不得返回其他用户的订单信息。 | `order_id`: string；`phone`: string |
| `search_policy` | 【已实现并验证】Mock/本地 HTTP | 检索退改签、儿童票、行李、报销凭证等政策知识库。当用户询问规则类问题而非购票操作时使用本工具，回答必须带 doc_id 出处。 | `question*`: string |


| 工具 | 成功返回结构及注意事项 |
|---|---|
| query_tickets | `trains: list, count: int`；trains 每项包含 kind/train_no/from_city/to_city/date/depart/arrive/seat_type/price/seats_left。最多 20 条，按余票降序、发车时间升序；0 票与空列表不同。 |
| monitor_seat | task_id/train_no/date/seat_type/duration_min/current_seats/status（monitoring）；仅凭据，无后台线程、不兑现、不扣款。 |
| lock_seat | lock_id/train_no/date/seat_type/passengers/unit_price/count/expire_at/ttl_seconds；锁座有效期 900 秒，创建时扣库存。 |
| create_order | order_id/phone/train_no/date/seat_type/passengers/amount/status/created_at/lock_id/idempotent_hit；passengers 是 SQLite 兼容的 JSON 字符串，非列表。重复相同 lock_id 返回同一订单。 |
| pay_order | 首次返回 order_id/status/pay_type/amount/duplicate_pay=false；重复已支付返回 order_id/status/duplicate_pay=true（不保证 pay_type/amount 在重复分支存在）。 |
| cancel_order | order_id/status/amount/fee/refund/fee_rate/policy_ref；paid→refunded，pending→cancelled（fee=0, refund=0，因为没有真实扣款）。已退款/取消/过期不可重复释放库存。 |
| query_order | 不指定订单号返回 orders/count/queried_phone；指定 order_id 返回单个订单原始字典（不包装 orders）。只可查询本人；状态 pending/paid/refunded/cancelled/expired。 |
| search_policy | question/hits/count；每个 hit 有 doc_id/source/title/content/score；source 为项目内文件片段标识。空检索返回 hits=[]。 |

业务/参数失败返回 `{"error": "原因"}`，某些分支另含 status 或 seats_left。`dispatch(name,args)` 返回 `(result, ok, latency_ms)`；以字典是否含 error 判定 ok。工具结果保留在内存对话中，Trace 只保存预览，不保证预览包含以上全部字段。

默认参数：monitor duration_min=30，pay pay_type=alipay，cancel reason=""，search top_k=config.TOP_K=3。seat_type 与 kind 可省略，底层查所有匹配席别/方式；Mock 通常主动传 kind/默认席别。enum 以 schema 为准，监控/锁座 seat_type 字符串仍需对应库存。date 必须精确 YYYY-MM-DD 且真实日历日期；未定义参数、空字符串、数组重复/为空、布尔替代 integer 都被拒绝。duration_min 范围 1..1440。

完整 HTTP 实际工具返回见 `docs/evidence/http.json`，不把随机 task/order/lock ID 当固定预期。

单独调用示例（已由自测和 HTTP 验证同一路径）：

```python
from datetime import timedelta
import config
from target.tools import dispatch
day = (config.today() + timedelta(days=1)).isoformat()
result, ok, latency_ms = dispatch("query_tickets", {
    "from_city": "上海", "to_city": "杭州", "date": day, "seat_type": "二等座"
})
print(ok, latency_ms, result["count"])
```

## 7. 六种变异与恢复

```python
from target import providers
from target.agent import Agent
providers.clear_mutations()
providers.set_mutation("skip_lock")
try:
    result = Agent().chat("case-skip", "订明天上海到杭州的高铁")
finally:
    providers.clear_mutations()
```

date_offset 用 `providers.set_mutation("date_offset", 1)`；布尔开关用 set_mutation(name)，关闭单项可 set_mutation(name,False)，全部关闭用 clear_mutations。全局字典对同进程默认 MockProvider 实例生效，B 串行测试使用；独立字典可 `Agent(provider=providers.MockProvider({"skip_lock": True}))`，不受全局 clear_mutations 控制，须清空该字典或新建正常 provider。Web 的开关正是每个浏览器独立字典，不使用全局 MUTATIONS。

| 开关 | 单独启用后的复现输入 | 已观察到的行为 | 用于检查的缺陷类别 |
|---|---|---|---|
| date_offset=1 | 查明天上海到杭州的高铁 | query_tickets 日期比正常解析晚 1 天 | 日期参数偏差（任务书 R3） |
| skip_lock | 订明天上海到杭州的高铁 | query_tickets→create_order，缺 lock_seat；不存在的锁被后端拒绝，ok=false | 调用顺序（R4） |
| repeat_call | 查明天上海到杭州的高铁 | 同一步两次 query_tickets，同参数 | 冗余重复（R5） |
| infinite_loop | 抢明天北京到上海的票 | query_tickets 后连续 7 次 monitor_seat，总 8 步后 max_steps_exceeded | 失控与步数上限（R6） |
| route_error | 退票手续费怎么算 | query_tickets 代替 search_policy | 意图路由（R2） |
| no_citation | 退票手续费怎么算 | 调用 search_policy，但回复省略 P01/P02 等引用 | RAG 引用缺失 |

以上全部是人为注入 Mock 变异，不是实际大模型自然产生的缺陷。不应同时打开多个开关作单一变异结论（组合可能相互遮盖）。默认 MAX_STEPS=8；如更改步数，循环次数随之改变。

恢复正常的完整条件：清空变异、`mock_core.clear_faults()`、`agent.reset()` 或新建 Agent、新建/重置隔离业务库、新 Trace 目录。只 reset(sid) 不恢复库存；只 clear_mutations 不删除会话历史；只重启 Web 不一定改变原库订单。真实模型不读取这些 Mock 变异，不应靠 set_mutation 推断真实模型缺陷。

## 8. 重置数据与防用例污染

推荐每个独立场景新进程 + 新库 + 新 Trace 目录；一组连续购付退款步骤属于同一场景，故意共享同实例/sid/库。不同 sid 隔离记忆，不隔离固定模拟用户的订单/库存。

```powershell
# 使用自己准备的新场景名，运行前设定；不要对 data/tickets.db 执行重置。
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\case-001\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\case-001\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe cli.py once "帮我查明天上海到杭州的高铁"
# 如明确复用并重置这个隔离库，先停止关联 Web/HTTP/CLI，再运行：
.\.venv\Scripts\python.exe data/seed.py --reset
```

不会清除/覆盖 traces.jsonl，换新目录保留历史。建库日期会更新，订单与锁会归零，库存由种子恢复。默认原库不会自动升级为扩展线路；跨日/过久未重建库会出现日期过期或空结果，应作为测试前置条件记录。锁 TTL 以 config.now 为准，访问时回收，等待期间没有后台更新。

backend 故障注入是额外调试入口，与六变异不同：`mock_core.set_fault('query_tickets','timeout'/'error')` 抛立即模拟异常，不是真正等待超时；query_tickets 的 empty 返回空结果。clear_faults 恢复。HTTP 服务器是另一进程，客户端设置 FAULTS 不会同步到服务器。

## 9. HTTP 方式（本次已验证）

第一个终端先设置相同隔离路径并启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn target.mock_api:app --host 127.0.0.1 --port 8000
```

客户端第二终端同样配置库/Trace，再设 `$env:AGENT_USE_HTTP="1"` 和 `$env:AGENT_MOCK_URL="http://127.0.0.1:8000"`，运行 CLI。POST `/tool/query_tickets` 请求体是 `{"args":{"from_city":"上海","to_city":"杭州","date":"YYYY-MM-DD"}}`，不要直接裸传参数字典。GET `/health` 返回 status/tools；GET `/inventory` 需 from_city/to_city/date 都有值。HTTP 错误常作为 JSON error 且 HTTP 200，必须检查 body；结构性请求错误 FastAPI 可返回 422。tools.dispatch 捕获网络异常为 ok=false，HTTP 客户端 timeout=10 秒。服务器仅本地模拟，不能用于生产暴露。

## 10. 真实模式与已知接口限制

真实模型配置均在**新进程启动前**通过环境变量提供：

```powershell
$env:AGENT_PROVIDER="openai"
# 由安全配置注入 AGENT_API_KEY，勿输入到对话/文档/录屏；下面只示范非秘密配置。
$env:AGENT_BASE_URL="<支持 Chat Completions 和 tools 的端点>"
$env:AGENT_MODEL="<端点支持的模型名>"
.\.venv\Scripts\python.exe cli.py chat
```

不要直接运行含尖括号的占位配置，需按团队获批的模型服务填写。原默认模型名是 glm-4-flash、默认 URL 在 config.py；它们不证明该端点当前可用。Key 缺失时 Agent 初始化抛配置 ValueError，Web 显示初始化错误；运行中的网络/模型异常返回安全提示并以 stop 收尾。各端点兼容性、模型权限与余额、真实能力由获 Key 后的实测确认。本次未访问真实模型或外部票务/支付服务。切回 Mock 后重启进程即可。

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

交接建议：当前可开始 B 的 Mock 正式测试；真实模型测试需队长协调服务与 Key。B 生成自己的原始证据、测试结论，C 再据此形成报告。最后核对 `git rev-parse HEAD`/交付标签，源码版本 `e719956d7c82bd6392c25916d3c193be7e4b452e`，分支 `feat/a-ticket-handoff`。
