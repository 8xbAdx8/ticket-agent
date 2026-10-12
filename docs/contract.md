# 接口契约（开工第一天先定死，三人并行不互相阻塞）

> 本文件由成员 A 维护，任何字段变更必须在群里同步。
> 成员 B 的断言脚本、成员 C 的看板**只依赖本文档**，不依赖 A 的内部实现。

## 1. 唯一对外入口

```python
from target.agent import Agent
agent = Agent()
result = agent.chat(session_id, message)      # 多轮用同一个 session_id
```

## 2. 返回值结构（严格按此格式）

```json
{
  "session_id": "S1",
  "provider": "mock",
  "model": "glm-4-flash",
  "user_msg": "帮我查下周三北京到上海的高铁",
  "steps": [
    {"step": 1, "calls": [
      {"tool": "query_tickets",
       "args": {"from_city": "北京", "to_city": "上海", "date": "2026-10-21", "seat_type": "二等座"},
       "ok": true,
       "latency_ms": 12,
       "result_preview": "{\"trains\": [...], \"count\": 12}"}
    ]}
  ],
  "tool_sequence": ["query_tickets"],
  "reply": "为您查到以下车次：G101 ...",
  "finish_reason": "stop",
  "tokens": {"prompt": 0, "completion": 0},
  "total_latency_ms": 15
}
```

字段说明（成员 B 写断言、成员 C 画看板都认这些字段）：

| 字段 | 含义 | 备注 |
|---|---|---|
| `session_id` | 会话 ID | 多轮对话必须一致 |
| `steps[].calls[]` | 每一轮的一次工具调用 | **断言的核心数据来源** |
| `tool` | 工具名 | 用于判定"该调没调 / 调错工具" |
| `args` | 模型传的参数 | 用于判定参数值与格式 |
| `ok` | 调用是否成功 | false 表示返回了 error 或抛异常 |
| `latency_ms` | 单次调用耗时 | 性能维度 |
| `tool_sequence` | 工具调用顺序（扁平） | 用于判定顺序与重复调用 |
| `finish_reason` | `stop` / `max_steps_exceeded` | 后者即"疑似死循环" |
| `total_latency_ms` | 整轮耗时 | 性能维度 |

## 3. 工具清单（8 个，参数见 `target/tools.py` 的 TOOLS schema）

| 工具 | 必填参数 | 说明 |
|---|---|---|
| `query_tickets` | from_city, to_city, date | 查车次余票，date 必须 YYYY-MM-DD |
| `monitor_seat` | train_no, date, seat_type | 无票时订阅候补监控 |
| `lock_seat` | train_no, date, seat_type, passengers | 锁座，返回 lock_id |
| `create_order` | lock_id, passenger_ids, contact | 幂等：同 lock_id 只生成一个订单 |
| `pay_order` | order_id | 仅改状态，不接真实支付 |
| `cancel_order` | order_id | 按政策 P01 阶梯算手续费 |
| `query_order` | order_id 或 phone | 默认只返回本人订单 |
| `search_policy` | question | RAG 检索，回答须带 doc_id |

## 4. 业务约束（成员 B 据此写顺序断言）

1. `create_order` 前必须先 `lock_seat`；
2. 余票为 0 时只能 `monitor_seat`，不得声称有票；
3. 规则类问题（退改签/儿童票/行李/报销）应走 `search_policy`，不是 `query_tickets`；
4. 不得查询其他用户订单（`phone` 只能是本人）。

## 5. 执行记录落盘

每次 `chat()` 追加一行 JSONL 到 `traces/traces.jsonl`，字段名与第 2 节完全一致。
**这个文件就是提交给评委的"测试执行记录"原始素材**，不要删。
