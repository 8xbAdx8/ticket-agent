# 成员 A 任务书：被测层「出行服务智能助手」+ CLI + Web 前端

> 赛事：第九届传智杯 · AI赋能智能测试创新挑战赛（团队赛，1-3 人）
> 交付截止：校赛前（以指导老师通知为准，通常早于 11-18）
> 编制日期：2026-10-12　　v1.0

---

## 0. 你负责什么（一句话）

**搭一个"会被别人测试"的抢票智能体**，再给它配一个命令行入口和一个网页控制台。
你是"造病人"的人，不是"造体检设备"的人（那是成员 B）。

- 场景：**高铁为主 + 机票少量**（虚构数据）
- 模型：**暂无 key，先用 Mock 模式**离线跑通，拿到 key 后改一行配置切换真实模型
- 后端：**纯 Python 函数核心 + 可选 FastAPI 外壳**（两种形态共用一份逻辑）

---

## 1. 接口契约（第一天先定死，B 和 C 都依赖它）

完整版见 `ticket-agent/docs/contract.md`，核心就这一条：

```python
from target.agent import Agent
result = Agent().chat(session_id, message)
# result = {"reply": str, "tool_sequence": [...], "steps": [...],
#           "finish_reason": "stop"|"max_steps_exceeded", "total_latency_ms": int, ...}
```

**你的所有实现必须保证 `chat()` 返回这个结构**（字段含义见契约文档）。
`steps[].calls[]` 里的 `tool / args / ok / latency_ms` 是 B 写断言的唯一数据来源，
`tool_sequence` 与 `finish_reason` 是 C 画看板的唯一数据来源。

traces 每次对话自动追加到 `traces/traces.jsonl`，**不要删**，那是评委要看的执行记录。

---

## 2. 交付物清单

| # | 交付物 | 说明 | 状态 |
|---|---|---|---|
| A1 | 模拟票务后端 | 高铁 6 条线 + 机票 3 条线，7 天余票；支持故障注入 | 骨架已给 |
| A2 | 8 个工具 + schema | `target/tools.py`，schema 描述要写清楚 | 骨架已给 |
| A3 | Agent 主循环 | function calling 循环 + trace 记录 | 骨架已给 |
| A4 | RAG 政策检索 | 10 条政策，关键词检索（零依赖），可升级向量 | 骨架已给 |
| A5 | Mock 模型提供者 | 离线跑通全部场景，支持注入 6 种缺陷 | 骨架已给 |
| A6 | **Python CLI** | `cli.py`：交互式 / 单条 / 批量三种模式 | 骨架已给 |
| A7 | **Web 前端** | `web/app.py`：Streamlit 控制台 + 离线回放 | 骨架已给 |
| A8 | 数据自测 | 自己跑一遍 6 条示例对话，确认链路完整 | 待你做 |

骨架代码已在 `ticket-agent/` 下，**你需要做的是理解、跑通、补全、调优**，不是从零写。

---

## 3. 目录结构（每个文件的职责）

```
ticket-agent/
├─ config.py              换模型只改这里（PROVIDER / MODEL / BASE_URL / API_KEY）
├─ run_demo.py            零依赖演示，第一条命令就跑这个
├─ cli.py                 Python CLI 入口
├─ requirements.txt       最小依赖为空，进阶功能才需要装
├─ data/
│  ├─ seed.py             生成 SQLite（504 条余票记录）
│  ├─ policies.md         RAG 语料，10 条政策，按 [P0x] 分块
│  └─ tickets.db          运行后自动生成
├─ target/                ← 你主要改这里
│  ├─ mock_core.py        模拟票务业务核心（纯函数）：查票/锁座/下单/支付/退票
│  ├─ mock_api.py         FastAPI 外壳（可选，演示更像真实系统）
│  ├─ tools.py            8 个工具的 OpenAI schema + dispatch 分发
│  ├─ rag.py              政策检索：关键词兜底，可开关升级向量检索
│  ├─ providers.py        MockProvider（离线剧本） / OpenAIProvider（真实模型）
│  ├─ agent.py            主循环 + chat() 对外接口  ← 契约出口
│  └─ trace.py            trace 记录与落盘  ← 契约核心
├─ web/app.py             Streamlit 控制台（对话 + trace + 离线回放 + 变异开关）
├─ cases/demo.json        批量用例样例
├─ traces/traces.jsonl    执行记录（自动追加，别删）
└─ docs/contract.md       接口契约（B、C 都看这个）
```

---

## 4. 环境搭建（10 分钟）

```bash
cd ticket-agent
python run_demo.py                      # 零依赖，不需要 pip install 任何包
python cli.py once "帮我查明天上海到杭州的高铁"
python cli.py chat                      # 交互式对话
python cli.py batch cases/demo.json
```

进阶（拿到 key 或要做前端/服务时再装）：

```bash
pip install -r requirements.txt        # openai / fastapi / uvicorn / streamlit
uvicorn target.mock_api:app --port 8000          # 起 HTTP 外壳（可选）
streamlit run web/app.py                         # 起 Web 前端
```

切换到真实模型（拿到 key 后，三选一）：

```bash
# Windows PowerShell
$env:AGENT_PROVIDER="openai"
$env:AGENT_API_KEY="你的key"
$env:AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"   # 智谱 GLM-Flash
$env:AGENT_MODEL="glm-4-flash"
python cli.py chat
```

**代码零改动**，只靠环境变量切换——这是设计好的，不要破坏它。

---

## 5. 第一周里程碑（建议节奏）

| 天 | 任务 | 完成标志 |
|---|---|---|
| D1 | 跑通 `run_demo.py`，读懂 8 个文件 | 能给别人讲清"模型说→代码做"的循环 |
| D2 | 补全工具 schema 的 description，核对参数类型 | 8 个工具全部能单独调用成功 |
| D3 | 造数据：把车次扩到 30 条线，加机票 5 条；补齐政策到 15 条 | 数据库有票/无票场景都能覆盖 |
| D4 | 调通 CLI 三种模式 + Web 前端 | `streamlit run web/app.py` 能演示一轮完整下单 |
| D5 | 自测 6 条示例对话 + 6 种变异开关 | `traces.jsonl` 有完整记录，变异能被触发 |
| D6 | 交一版给 B：`chat()` 契约 + 10 条示例 trace | B 可以开始写断言 |

---

## 6. 变异开关（B 要用，你必须保证能触发）

在 `providers.py` 里已经实现，B 通过 `providers.set_mutation(name)` 打开：

| 开关 | 注入的缺陷 | 期望被 B 的哪条规则捕获 |
|---|---|---|
| `date_offset=1` | 日期解析偏移一天 | R3 参数错 |
| `skip_lock` | 跳过 lock_seat 直接下单 | R4 顺序错 |
| `repeat_call` | 同一请求重复调用 | R5 冗余 |
| `infinite_loop` | 无票时反复监控不退出 | R6 失控（finish_reason=max_steps_exceeded） |
| `route_error` | 规则问题错走 query_tickets | R2 误调用 |
| `no_citation` | 政策回答不给出处 | RAG 引用检查 |

**已验证**：`infinite_loop` 能正确触发 8 步后 `max_steps_exceeded`。其余请你逐个跑一遍确认。

---

## 7. 验收标准（自测清单，全打勾才算完成）

- [ ] `python run_demo.py` 无报错，6 条场景都能给出合理回复
- [ ] 完整链路能跑通：查票 → 锁座 → 下单 → 支付 → 退票，每步 trace 都记录
- [ ] 无票场景正确走候补（不会编造有票）
- [ ] 规则类问题走 RAG 且**回答带 doc_id 出处**
- [ ] `traces/traces.jsonl` 每条记录字段齐全（对照 `docs/contract.md`）
- [ ] CLI 三种模式都能用；Web 前端能演示并回放
- [ ] 6 个变异开关都能触发对应缺陷
- [ ] 换成真实模型时**只改环境变量，不改代码**

---

## 8. 注意事项

1. **合规红线**：全部使用自建虚构数据，不对接 12306 / 航司 / 任何真实票务与支付接口；不实现针对真实平台的抢票脚本。作品性质是"智能体质量保障研究"，README 与文档首屏要写明。
2. **Git 提交粒度**：官网会核查原创性与开发过程可复现性，**禁止一次性提交全部功能**。每个工具、每个模块单独提交，commit message 写清楚做了什么。
3. **不要替 B 写测试**：你只保证 `chat()` 契约稳定、trace 字段齐全；断言逻辑是 B 的活，写了会重复且容易冲突。
4. **改动契约必须通知**：`trace.py` 与 `docs/contract.md` 的任何字段变更，先在群里说一声。
5. **性能数据要真实**：`latency_ms` 来自真实计时，不要写死；B 的性能维度依赖它。
6. **有阻塞就问**：卡住超过半天直接提出来，别自己憋。

---

## 9. 你现在就可以做的三件事

1. `python run_demo.py` —— 先看到东西跑起来
2. 读 `target/agent.py` 的 `chat()` —— 理解契约出口
3. 读 `target/providers.py` 的 `MockProvider` —— 理解"模型说→代码做"的循环

有疑问在群里问，不要自己猜测改契约。
