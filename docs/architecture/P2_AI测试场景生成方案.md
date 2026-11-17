# P2：AI 自动化测试场景生成系统 —— 技术方案与可行性审查

- 日期：2026-10-30
- 状态：**方案评审稿**（只读审查，本轮未写任何源码、未调用任何真实 API、未改 103 条用例与 RAG 1000 题库）
- 目标：在现有 Ticket Agent 上增加一条“**真实大模型生成 → 确定性校验 → 人工审核 → Regression Center 执行**”的场景生产线，能证明题目确实由 AI 生成，且不会污染正式成绩。

---

## 0. 结论摘要（先给答案）

| 问题 | 结论 |
|---|---|
| P2 最小可行实现 | 一条 CLI 流水线：`p2_generate`（调真实模型，7 维各 10 条）→ `p2_validate`（Schema/接地/去重/可执行）→ 人工 `review.jsonl` → `p2_run`（离线 Mock 执行）→ 结果并入 Regression Center。 |
| 可复用 | Agent 执行链、DeepSeek/Qwen Provider、`request_accounting` 计费、`run_events` 事件链、`rag_store.documents` 证据、RAG case schema、103 条 `expect` 断言 DSL、`web/evidence.py` 结果适配。 |
| 必须新增 | 证据包构造、生成器、场景 Schema、校验器、批次存储、执行器（现有 103 条**没有执行器**）、审核与隔离门禁。 |
| DeepSeek / Qwen 分工 | DeepSeek 主生成（本仓库已验证 `response_format=json_object`）；Qwen 做**小样本复核与双生成对照**，不假设其结构化能力一致，先探针后使用。 |
| 70 条 PoC 验收 | 生成成功 ≥95%、Schema ≥95%、重复 ≤5%、接地 ≥90%、可执行 ≥90%、人工采纳 ≥60%（每维 ≥50%）、正式池污染 0。 |
| 如何证明 AI 生成 | 请求回执（request_id + token usage）+ 原始响应落盘与哈希 + Prompt 哈希 + 与规则模板的 n-gram 背离度 + 可重放校验。 |
| 如何防污染 | 物理隔离目录 + `P2-` 前缀 + 双状态（candidate/approved）+ 人工签字 + 加载器拒绝 `rag1000` 来源 + 未批准用例不进入任何成绩。 |

---

## 1. 审查基线与约束

### 1.1 与 P2 直接相关的现状（全部核实过）

| 资产 | 位置 | 事实 |
|---|---|---|
| 七维度定义 | `web/competition_view.py:10-17` | 功能准确性 / 工具调用 / RAG / 多轮 / 安全 / 边界 / 性能 |
| **103 条正式用例** | `web/datasets/b_v32_20261020/case_catalog.json` | 103 条，字段 `id/dimension/name/session_id/message/expect`；维度分布：工具调用 25、安全 18、功能准确性 15、RAG 15、边界 12、多轮 12、性能 6 |
| 断言 DSL | 同上 `expect` | `raises / must_call / args / reply_contains / reply_not_contains / finish_reason / trains_from_tools / max_latency_ms / require_citation` |
| **执行器** | —— | **不存在**。`case_catalog` 只被 `web/evidence.py:48-49` 读来展示；B 的执行结果是历史快照 `execution.jsonl`，不是可执行测试 |
| Regression Center | `scripts/regression_center.py` | 只跑 pytest 节点（`must start with tests/`，`:70`），做隔离副本、保护目录、指纹与报告 |
| Agent 契约 | `target/agent.py:232` | `Agent.chat(session_id, message)` 返回十字段；`steps[].calls[]` 五字段 |
| Provider | `target/deepseek_runtime.py`（`Settings`: timeout 20、max_output_tokens 512、turn_token_budget 12000、max_model_calls 3）、`target/bailian_runtime.py`、`target/api_config.py:53,74` | 统一 `make_model(settings)`；DeepSeek 已在 `target/followups.py:175-205` 验证过 JSON 模式 |
| 计费/回执 | `target/request_accounting.py:27 capture`、`UsageLog` | 每次 HTTP 事件、request_id、token 用量 |
| 事件链 | `target/run_events.py:10 capture / :22 emit` | `event_id / previous_event_id / session_id / run_id / provider / model` |
| RAG 证据 | `target/rag_store.py:20 documents()` | 57 篇 chunk、`chunk_id = Pxx-0000-<sha12>`、可回指 |
| RAG case schema | `data/rag1000/v1.1.1/schema.json` | 23 个必填字段，含 `required_evidence.quote`、`expected_behavior` 枚举 |
| 离线执行方式 | `tests/test_agent.py:16-24` | patch `config.DB_PATH`/`TRACE_DIR` 到临时目录，`Agent(MockProvider())` |
| 业务状态机 | `target/business_state.py` | `locked / lock_expired / order_pending / paid / payment_failed / cancelled` |

### 1.2 关键判断

1. **103 条用例不能直接跑**：P2 无论做不做生成，都躲不开一个执行器。P2 顺便把这层补上，但**不改动 103 条本身**。
2. **RAG 1000 是规则拼装**：`scripts/build_rag_benchmark.py` + `scripts/rag_benchmark_banks.py` 是模板库，不能拿来充当 AI 生成证据。P2 必须新开命名空间。
3. **结构化输出能力按 Provider 分别处理**：DeepSeek 的 `response_format={"type":"json_object"}` 在本仓库有成功先例；Qwen 走 OpenAI 兼容层，不能假设行为完全一致。

---

## 2. 现有架构复用清单

| 能力 | 复用对象 | 复用方式 | 需要改动 |
|---|---|---|---|
| 模型调用 | `deepseek_runtime.make_model` / `bailian_runtime.make_model` | 直接调用，**新建独立 Settings**（`max_output_tokens=1024`、`timeout=30`、`max_model_calls=1`） | 无（不改原文件） |
| 请求回执/预算 | `request_accounting.capture` + `UsageLog` | 生成批次内 `capture(events, generator_id, 'gen:<dim>')` | 无 |
| 事件链 | `run_events.capture/emit` | 使用**独立文件** `generation_events.jsonl`，schema 不变 | 无 |
| 证据 | `rag_store.documents()` | 构造证据包，引用真实 `doc_id/chunk_id/version/quote` | 无 |
| 用例 Schema | `data/rag1000/v1.1.1/schema.json` | 作为 P2 Schema 的父集，新增字段不删旧字段 | 无 |
| 断言 DSL | 103 条 `expect` | P2 场景编译成同一 DSL，执行器共享 | 无 |
| 执行环境 | `tests/test_agent.py` 的临时 DB/TRACE 模式 | 每个场景独立临时目录 | 无 |
| 结果展示 | `web/evidence.py` 的 row 形状（`id/dimension/status`） | P2 结果输出同形状，未来可接 P0 | 无（MVP 不接 UI） |
| 回归执行 | `scripts/regression_center.py` | 新增 pytest 文件即可被现有流程跑到 | **不改** regression_center |
| 业务状态 | `target/business_state.detect/actions` | 生成“操作型场景”的依据 | 无 |

**结论：不需要重构任何现有模块。** P2 是“旁挂一条生产线 + 一个数据驱动测试文件”。

---

## 3. 七维度覆盖设计

| 维度 | 场景族 | 证据来源 | 断言（编译为 `expect`） | 执行方式 | PoC |
|---|---|---|---|---|---|
| 功能准确性 | 单轮问答、政策解释、订单查询 | 政策 chunk / 工具 Schema | `must_call`、`reply_contains`、`finish_reason` | Mock Agent | 10 |
| 工具调用 | 正确工具/正确参数/不该调用时拒绝 | 工具 Schema 参数表 | `must_call`、`args`、`reply_not_contains` | Mock Agent | 10 |
| RAG | 有答案/无答案/多文档/版本冲突 | `documents()` + 真 `quote` | `must_call=["search_policy"]`、`require_citation`、`reply_contains=["Pxx"]` | keyword 模式（离线） | 10 |
| 多轮 | 2–4 轮：补全条件、切换意图、确认流程 | 对话状态 + 业务状态 | 逐轮 `turn_expects`（`must_call`/`reply_contains`） | Mock Agent | 10 |
| 安全 | 越权查询、注入指令、诱导付费、套取密钥 | 工具 Schema + 安全基线 | `reply_not_contains`、`must_call` 缺失、`raises` | Mock Agent | 10 |
| 边界 | 空输入、超长输入、非法参数、工具异常、售罄 | 工具校验规则（如 `tools.py:196` 1..1440） | `raises`、`reply_contains`、`max_tool_calls` | Mock Agent | 10 |
| 性能 | 步数上限、工具调用上限、payload 上限 | `Settings` 预算字段 | `max_steps`、`max_tool_calls`、`max_payload_bytes` | Mock Agent（结构合规） | 10 |

> **性能维度必须说清楚**：离线 Mock 不能测“真实并发响应速度”。P2 的“性能”只覆盖**资源与步数护栏**（是否越界、是否死循环）。真实延迟/并发仍是 `scripts/v37_performance.py` 的独立轨道，不能混为一谈，也不能把 Mock 的毫秒数写成性能成绩。

---

## 4. 新增模块设计

```
scripts/p2_generate.py  ── 调模型、落盘候选
        │
        ▼
target/p2_packets.py  → 证据包（确定性，无模型）
target/p2_generator.py → Prompt 构造 + 调用 + 解析/修复
target/p2_store.py     → 批次目录、manifest、append-only JSONL、哈希
        │
        ▼
scripts/p2_validate.py（target/p2_validate.py）→ 7 项检查
        │
        ▼
data/p2_scenarios/review/<batch>.review.jsonl（人工）
        │  approved
        ▼
data/p2_scenarios/approved/<batch>.jsonl
        │
        ▼
target/p2_executor.py → 执行 + 断言 DSL
        │
        ▼
tests/test_p2_scenarios.py（pytest 参数化）→ Regression Center
```

| 新增文件 | 职责 | 依赖 |
|---|---|---|
| `target/p2_case.py` | 场景 Schema（jsonschema 4.26 已装）、维度枚举、`compile_expect()`、`validate_static()` | `jsonschema` |
| `target/p2_packets.py` | `build_packets(dimension, corpus, tools, states, seed)`，确定性、可复算 | `rag_store.documents`、`tools.TOOLS`、`business_state` |
| `target/p2_generator.py` | `build_prompt()`、`generate(provider, settings, batch)`、`parse_json()`（原生/宽松）、`normalize()` | `deepseek_runtime`/`bailian_runtime`、`request_accounting` |
| `target/p2_store.py` | `BatchWriter`（manifest、`candidates.jsonl`、`raw/`、`generation_events.jsonl`）、`load_approved()` | `run_events` |
| `target/p2_validate.py` | 7 项检查，输出 `validation.json` + 可直接给人看的 `validation.md` | `p2_case`、`p2_packets` |
| `target/p2_executor.py` | `run_case(agent, case)`，实现 `expect` DSL 全部键 | `target/agent.py` |
| `scripts/p2_generate.py` / `p2_validate.py` / `p2_run.py` | CLI 包装，参数校验，退出码 | 上述模块 |
| `tests/test_p2_scenarios.py` | 读 `approved/`，无则 skip；每案独立临时 DB/TRACE | `pytest` |
| `tests/test_p2_*.py` | Schema/生成/去重/接地的离线单测（假 transport） | `unittest` |

---

## 5. 数据结构与接口

### 5.1 证据包（`evidence/<packet_id>.json`，确定性生成）

```json
{
  "schema": "ticket-p2-packet/1",
  "packet_id": "ev-rag-0007",
  "dimension": "RAG",
  "docs": [{"doc_id": "P01", "title": "退票手续费阶梯", "chunk_id": "P01-0000-<sha12>",
            "version": "645904208717fad9", "quote": "开车前 48 小时以上退票，收取票价 5% 手续费"}],
  "tools": [{"name": "query_tickets", "required": ["from_city", "to_city", "date"],
             "enums": {"kind": ["高铁", "机票"], "seat_type": ["二等座", "一等座", "商务座", "经济舱", "公务舱"]}}],
  "business_state": null,
  "allowed_entities": ["P01", "P02", "G7303"],
  "notes": "只能使用本包内的事实；引用必须逐字出现在 quote 中"
}
```

### 5.2 候选场景（`candidates.jsonl` 每行一条）

```json
{
  "schema": "ticket-p2-scenario/1",
  "case_id": "P2-RAG-0007",
  "dimension": "RAG",
  "title": "退票手续费阶梯：48 小时以上",
  "turns": ["开车前三天退票，手续费怎么算？"],
  "expected_behavior": "answer",
  "expect": {
    "must_call": ["search_policy"],
    "reply_contains": ["5%"],
    "require_citation": true,
    "finish_reason": "stop"
  },
  "expected_doc_ids": ["P01"],
  "required_evidence": [{"doc_id": "P01", "version": "645904208717fad9",
                         "quote": "开车前 48 小时以上退票，收取票价 5% 手续费"}],
  "forbidden_claims": ["真实退款已到账"],
  "difficulty": "easy",
  "packet_id": "ev-rag-0007",
  "provenance": {
    "origin": "ai_generated",
    "batch_id": "p2-20261101-120000-abc123",
    "provider": "deepseek", "model": "deepseek-flash",
    "prompt_sha256": "…", "response_sha256": "…", "request_id": "…",
    "generated_utc": "2026-11-01T04:00:00Z",
    "review_status": "candidate"
  }
}
```

字段约束：
- `case_id` 必须 `P2-<DIM>-<4位序号>`，**与 103 条（E/F/M/P/R/T/X）和 RAG（RAG-xxxx）不重叠**。
- `expect` 只允许出现 9 个已知键（见 §1.1），未知键 → 拒绝。
- `required_evidence.quote` 必须能在 `docs[].content` 中**逐字找到**（NFKC + 去空白后比较）。
- `expected_doc_ids` 必须是生产语料中的真实 `doc_id`，且 ⊆ 该 packet 的 `docs`。
- `turns` 长度 1–4；超过 4 轮不生成（上下文成本与判定复杂度）。

### 5.3 批次 manifest（`artifacts/runtime/p2-gen/<batch_id>/batch.json`）

```json
{
  "schema": "ticket-p2-batch/1",
  "batch_id": "p2-20261101-120000-abc123",
  "created_utc": "…",
  "provider": "deepseek", "model": "deepseek-flash",
  "structured_mode": "native_json | lenient_parse",
  "prompt_version": "p2-gen/1", "prompt_sha256": "…",
  "settings": {"max_output_tokens": 1024, "timeout": 30},
  "requested": 70, "generated": 70, "failed": 0,
  "real_api_requests": 7, "tokens": {"prompt": 0, "completion": 0},
  "request_ids": ["…"],
  "status": "candidates | validated | reviewed | approved | rejected",
  "validation": {"schema_pass": 0, "grounding_pass": 0, "duplicate": 0, "executable": 0}
}
```

### 5.4 审核记录（`review.jsonl`）

```json
{"case_id": "P2-RAG-0007", "decision": "approve|reject|edit", "reason": "依据充分",
 "edited_fields": {}, "reviewer": "B", "reviewed_utc": "…", "batch_id": "…"}
```

### 5.5 执行结果（`results.jsonl`，与 `web/evidence.py` 的 row 同形）

```json
{"id": "P2-RAG-0007", "dimension": "RAG", "status": "passed|failed|error|skipped",
 "detail": "require_citation: 未引用 P01", "latency_ms": 42,
 "actual": {"tool_sequence": ["search_policy"], "reply": "…"},
 "run_id": "…", "batch_id": "…", "engine": "mock"}
```

### 5.6 CLI 契约

```text
python scripts/p2_generate.py --dimension all --count 10 --provider deepseek \
    --batch p2-<ts> [--dry-run]            # dry-run 只打印 prompt 与估计 token，不调 API
python scripts/p2_validate.py --batch p2-<ts>
python scripts/p2_run.py --batch p2-<ts> --engine legacy|langchain
```

退出码：`0` 全通过；`2` 校验未达标；`3` 配置缺失/未授权（BLOCKED，不静默降级）。

---

## 6. 生成流程

1. **构造证据包**（无模型）：按维度从 `documents()`、`TOOLS`、`business_state` 抽取；每个包 1–3 篇文档或 2–4 个工具；包内 `quote` 是原文切片。
2. **组装 Prompt**：系统提示固定为“只使用 packets 中的事实；每条必须给 `packet_id` 与逐字 `quote`；`expect` 只可用 9 个键；禁止真实世界承诺”。用户载荷只放 packet JSON + 目标条数 + 已有题目标题（用于避免重复）。
3. **调用模型**：
   - DeepSeek：`model.bind(response_format={"type":"json_object"}, max_tokens=1024).invoke(...)`（与 `followups._invoke` 同法）。
   - Qwen：先用 1 条探针判断是否接受 `response_format`；不接受则退化为“要求只输出 JSON + fenced 解析”，并在 manifest 记 `structured_mode=lenient_parse`。
4. **解析**：严格 `json.loads` → 失败时提取首个 `{...}` → 再失败记 `parse_failed`（**最多重试 1 次**，重试也失败即记失败，不无限循环）。
5. **归一化**：补 `case_id`（维度内自增）、`schema`、`provenance`（从回执取 model/request_id/tokens）。
6. **落盘**：`candidates.jsonl` 追加、`raw/<dim>.json` 存原始响应、事件写 `generation_events.jsonl`。
7. **断点续跑**：以 `(batch_id, dimension)` 为键，已存在且 `status=ok` 的维度跳过；`--force` 才覆盖（新目录，不覆盖旧批次）。

**缓存**：`cache = sha256(prompt_version + prompt_sha256 + provider + model + params)`；命中直接复用候选并标注 `cache_hit=true`，不产生 API 请求。

---

## 7. 自动质量审核（7 项）

| # | 检查 | 算法 | 阈值 | 不通过 |
|---|---|---|---|---|
| 1 | JSON Schema | `jsonschema` 校验 `p2_case.SCENARIO_SCHEMA` | 100% 字段合法 | 拒绝 |
| 2 | 语义重复 | 归一化问题 + 字符 bigram Jaccard ≥0.85；与 103 条、RAG 1000、同批其它候选三向比较 | ≤5% | 拒绝 |
| 3 | 测试依据 | `quote` ⊆ 对应 doc 内容（逐字）；`expected_doc_ids` ⊆ packet docs 且存在于生产语料 | 100% | 拒绝 |
| 4 | 预期合理性 | `answer` 必须有 `expected_doc_ids` 或 `must_call`；`clarify` 必须带 `clarification_fields`；`refuse` 必须有 `forbidden_claims`；`no_answer` 不得有 `expected_doc_ids` | 100% | 拒绝 |
| 5 | 工具合法性 | `must_call` ⊆ `TOOL_NAMES`；`args` 的键 ⊆ 工具 Schema；枚举值合法 | 100% | 拒绝 |
| 6 | 与 103/RAG 隔离 | `case_id` 前缀、`dataset_version` 非 `rag1000*`、写入路径不在 `data/rag1000` | 100% | 拒绝 |
| 7 | 可执行性 | 编译后 `expect` 能在执行器里全部识别；`turns ≤4`；无自相矛盾（同一断言 `contains` 与 `not_contains` 同值） | ≥95% | 标记 `unexecutable` |

**人工门槛（硬性）**：`candidate → validated → approved` 必须有一条 `review.jsonl` 的 `approve` 记录，带 reviewer 与时间。**没有 approve 的用例不进入 `approved/`，也不进入任何成绩。**

---

## 8. 防幻觉与防污染

### 8.1 防幻觉

1. **证据闭包**：模型只能看到 packet；每条用例必须回填 `packet_id`；校验器要求 `quote` 逐字命中，**不允许改写**。
2. **期望枚举化**：`expected_behavior` 只能取 6 个枚举值（复用 RAG schema），不允许模型写“应该回答得更好”这类不可判定描述。
3. **断言 DSL 化**：9 个键全部机器可判；模型不能发明断言类型。
4. **数值来源限制**：`reply_contains` 里出现的数字必须能在 `quote` 中找到（或由 `quote` 内数字按显式 `±1` 规则推导，规则写在用例的 `derivation` 字段，校验器复算）。
5. **禁止现实承诺**：`forbidden_claims` 必填至少 1 条（如“真实扣款成功”“真实 12306 出票”）。
6. **交叉复核（可选，低成本）**：抽 20% 用例让 Qwen 做“证据是否支持该期望”的判断题；不一致 → `needs_review`。Qwen 只做**审核者**，不做主生成。

### 8.2 防污染

- **物理隔离**：候选在 `artifacts/runtime/p2-gen/`，批准后在 `data/p2_scenarios/approved/`；**任何写操作都不碰 `data/rag1000/`、`web/datasets/b_v32_20261020/`、`tests/` 里的既有用例。**
- **命名隔离**：`P2-<DIM>-<seq>`；执行结果 `id` 同前缀；报表单独成批，不并入 103 条与 RAG 1000 的任何汇总。
- **双状态机**：`candidate → validated → approved → executed`；只有 `approved` 可执行；`rejected` 永久保留证据但不执行。
- **加载器门禁**：`load_approved()` 拒绝任何 `dataset_version` 以 `rag1000` 开头、或 `case_id` 不以 `P2-` 开头的记录。
- **默认关闭**：`tests/test_p2_scenarios.py` 在 `approved/` 为空时 `skip`，不会让 CI 凭空多出“通过”。

---

## 9. 生成证据链与可追溯

### 9.1 批次级

`batch.json` 记录：`batch_id / provider / model / structured_mode / prompt_version / prompt_sha256 / settings / requested / generated / failed / real_api_requests / tokens / request_ids / status / validation`。

### 9.2 用例级

`provenance`：`origin(ai_generated|rule_generated|human) / batch_id / provider / model / prompt_sha256 / response_sha256 / request_id / generated_utc / review_status`。

### 9.3 与 P1 Trace 的关系

- **生成**不是 Agent 运行，不写 `run_events.jsonl`（避免污染线上 Trace）。生成用同 schema 的 `generation_events.jsonl`，事件类型 `p2_gen_started / p2_gen_completed / p2_gen_failed / p2_validate_completed / p2_review_recorded`。
- **执行**走现有 `Agent.chat`，自然产生 `traces.jsonl` 与 `run_events.jsonl`；结果行带 `run_id`，所以每条用例都能从“生成”追到“执行 Trace”。

### 9.4 如何证明“确实是 AI 生成”

四重证据，缺一不可：
1. **HTTP 回执**：`request_accounting` 捕获的 `request_id` + token 用量，与 provider 返回的 `usage` 对得上。
2. **原始响应落盘**：`raw/<dim>.json` 保存完整响应体，计算 `response_sha256`；用例里的 `response_sha256` 必须与之一致（可重放校验）。
3. **Prompt 指纹**：`prompt_sha256` + `prompt_version`，同批次所有用例共享。
4. **模板背离度**：把生成题与 `scripts/rag_benchmark_banks.py` 的规则模板做 bigram 相似度，**≥0.9 的占比必须 <5%**，否则说明只是换皮拼装。

补充：`scripts/p2_verify.py --batch` 重算上述哈希并输出 `verify.json`；人工可在报告里贴 `request_id` 与 provider 控制台对账。

---

## 10. 成本与预算

### 10.1 Provider 分工

| | DeepSeek | Qwen (DashScope 兼容) |
|---|---|---|
| 本仓库已验证 | `followups._invoke` 的 `response_format=json_object` 成功 | 仅通用调用，未验证 JSON 模式 |
| 角色 | **主生成**（7 维 × 10） | **复核/对照**（20% 抽样 + 14 条双生成） |
| 结构化处理 | native JSON | 先探针；失败走 lenient 解析并单独标注 |
| 预算 | 7 次请求 | ≤3 次请求（1 探针 + 2 复核批次） |

### 10.2 预算上限（单批次，硬性）

| 项 | 上限 | 触发动作 |
|---|---|---|
| 请求数 | 10 | 停止并报 `budget_exhausted` |
| 输入 token | 20,000 | 同上 |
| 输出 token | 20,000 | 同上 |
| 单请求重试 | 1 | 第二次失败记 `gen_failed` |
| 单批总时长 | 10 min | 中断并保留已完成部分 |

估算（7 维 × 10 条）：输入 ≈ 7×1.5k=10.5k tokens，输出 ≈ 7×1.2k=8.4k tokens。**单价不在仓库内，报告只记录实测 tokens，不编造金额**；如需费用，按 Provider 官价 × 实测 tokens 另算。

### 10.3 断点续跑与缓存

- 维度级断点：`(batch_id, dimension)` 已完成则跳过。
- Prompt 级缓存：命中不调 API，`cache_hit=true`，不重复计费。
- 批次目录只追加，不覆盖；重跑生成新 `batch_id`。

---

## 11. 70 条 PoC 验收

| 指标 | 定义 | 阈值 |
|---|---|---|
| 生成成功率 | 可解析出 JSON 的条数 / 请求条数 | ≥95%（≥67/70） |
| Schema 合格率 | 通过 jsonschema / 生成成功 | ≥95% |
| 重复率 | 与 103、RAG1000、批内重复 / 生成成功 | ≤5% |
| 有效依据率 | `quote` 逐字命中且 doc 存在 / 生成成功 | ≥90% |
| 可执行率 | 编译后可被执行器识别 / 生成成功 | ≥90% |
| 人工采纳率 | approve / 提交审核 | ≥60%（≥42/70），**每维 ≥50%** |
| 污染 | 未经 approve 进入 `approved/` 或成绩的条数 | **0** |
| 证据完整性 | 有 batch_id + prompt_sha + request_id（或显式 unknown） | 100% |

输出：`poc_report.json` + `poc_report.md`（逐维表格 + 失败样本 + Provider 对照）。**报告标题必须写“PoC 试验，不是正式验收成绩”。**

---

## 12. 风险清单

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| 模型编造看似合理的期望 | 高 | 高 | 证据闭包 + 引用逐字校验 + 人工审核 |
| 引用存在但不支持结论 | 中 | 高 | 数字来源规则 + Qwen 复核抽样 + 人工 |
| 去重漏掉改写题 | 中 | 中 | bigram + 人工抽查；后续可加 embedding（本轮不做） |
| Qwen JSON 模式不兼容 | 中 | 中 | 探针 + lenient 解析 + 单独统计，不混入主批 |
| 成本超预算 | 低 | 中 | 硬上限 + 缓存 + 维度断点 |
| 生成题污染正式池 | 低 | **极高** | 目录隔离 + 状态机 + 加载器门禁 + 人工签字 |
| 性能维度被误读为真实性能 | 中 | 中 | 只测护栏；报告显著标注“Mock 结构合规” |
| 七维覆盖靠数量堆砌 | 中 | 中 | 每维族配额 + 覆盖矩阵，不以条数宣称覆盖 |

---

## 13. 分阶段实施计划

| 阶段 | 内容 | 产出 | 退出条件 | 估时 |
|---|---|---|---|---|
| P0 | Schema + 证据包 + 存储 + 校验器骨架 | `target/p2_case.py`、`p2_packets.py`、`p2_store.py`、单测 | 70 条假数据全量校验跑通，0 真实 API | 0.5 天 |
| P1 | 生成器 + 单维 PoC（功能准确性 10 条） | `p2_generator.py`、`scripts/p2_generate.py`、fake transport 单测 | 离线可复现，Schema 通过率 ≥95% | 1 天 |
| P2 | 七维 70 条真实生成（需授权） | 批次目录 + `validation.md` | 六项指标达标或明确记录未达标 | 0.5 天 |
| P3 | 人工审核 70 条 | `review.jsonl` + 采纳率 | 每维 ≥50% | 0.5 天 |
| P4 | 执行器 + pytest 接入 | `p2_executor.py`、`tests/test_p2_scenarios.py`、Regression Center 跑通 | 已批准用例可执行，未批准不执行 | 1 天 |
| P5（可选） | Qwen 复核 + 报告页 | `p2_verify.py`、UI 区块 | 证据链可一键复算 | 1 天 |

---

## 14. Codex 实施任务拆分

| # | 任务 | 文件 | 验收 |
|---|---|---|---|
| T1 | 场景 Schema 与维度常量 | `target/p2_case.py` | `SCENARIO_SCHEMA` 通过 jsonschema；维度常量与 `web/competition_view.REQUIREMENTS` 一致（单测断言） |
| T2 | 证据包构造 | `target/p2_packets.py` | 同一 seed 两次构造哈希一致；每包 quote 均逐字命中 |
| T3 | 生成器（含 JSON 原生/宽松解析） | `target/p2_generator.py` | 假 transport 单测覆盖：正常/围栏/坏 JSON/超时；重试 ≤1 |
| T4 | 批次存储与 manifest | `target/p2_store.py` | append-only；`batch.json` 字段齐全；哈希可复算 |
| T5 | 校验器 7 项 | `target/p2_validate.py` | 每项至少 2 个正例 + 2 个反例；输出 `validation.json` |
| T6 | CLI 生成/校验 | `scripts/p2_generate.py`、`p2_validate.py` | `--dry-run` 不产生请求；未授权退出码 3 |
| T7 | 执行器（`expect` DSL） | `target/p2_executor.py` | 9 个键全覆盖；每条断言可单测 |
| T8 | pytest 接入 | `tests/test_p2_scenarios.py` | 无 approved → skip；有 approved → 独立临时 DB/TRACE |
| T9 | 证据链校验脚本 | `scripts/p2_verify.py` | 重算 response/prompt 哈希；不一致退出码 2 |
| T10 | 文档与样例批次 | `docs/architecture/P2_AI测试场景生成方案.md`、`artifacts/runtime/p2-gen/sample/` | 读者可按文档复跑 |

**不要动**：`scripts/regression_center.py`、`web/datasets/b_v32_20261020/`、`data/rag1000/`、`tests/` 下既有用例、`artifacts/runtime/v35-rag/index`。

---

## 15. 不建议做的事

1. 不要让模型直接写“预期答案文本”当判定依据——只能写枚举行为 + 机器断言 + 逐字引用。
2. 不要自动 approve；不要用“模型自评”替代人工签字。
3. 不要把生成结果写进 `data/rag1000/` 或 103 条目录，哪怕只是测试。
4. 不要为了凑 70 条而放宽校验；宁可 `generated<70` 并如实报告。
5. 不要用 Mock 延迟当性能成绩；性能维度只测护栏。
6. 不要改 Regression Center 去适配 P2；用新增 pytest 文件接入。
7. 不要把 Qwen 的宽松解析结果与 DeepSeek 原生 JSON 混在同一通过率里。

---

## 16. 七个问题直答

1. **P2 最小可行实现**：`p2_generate`（DeepSeek 原生 JSON，7 维各 10 条）→ `p2_validate`（7 项检查）→ 人工 `review.jsonl` → `p2_run`（离线 Mock 执行 `expect` DSL）→ `tests/test_p2_scenarios.py` 被 Regression Center 跑到。新增 6 个模块 + 1 个测试文件，不改任何现有模块。
2. **可复用**：Agent/Conversation 执行链、DeepSeek/Qwen Provider、`request_accounting`、`run_events`、`rag_store.documents`、RAG case schema、103 条的 `expect` DSL、`web/evidence.py` 结果形状。
3. **必须新增**：证据包、生成器、场景 Schema、校验器、批次存储、**执行器**（现有 103 条没有）、审核门禁与隔离。
4. **DeepSeek / Qwen 分工**：DeepSeek 主生成（本仓库已验证 JSON 模式）；Qwen 先探针、再做 20% 抽样复核与 14 条双生成对照，宽松解析单独统计。不假设两家结构化能力相同。
5. **70 条 PoC 验收**：六项指标 + 污染为 0 + 证据完整率 100%，逐维 ≥50% 采纳；输出 `poc_report.json/md`，标题写明“试验，非正式成绩”。
6. **如何证明 AI 生成**：HTTP 回执（request_id + usage）、原始响应与 `response_sha256`、`prompt_sha256`、与规则模板的 n-gram 背离度 <5%、`p2_verify.py` 可重放复算。
7. **防污染**：物理目录隔离（`artifacts/runtime/p2-gen` → `data/p2_scenarios/approved`）、`P2-` 前缀、`candidate→validated→approved→executed` 状态机、人工签字、加载器拒绝 `rag1000` 来源、未批准不执行不计分。

---

## 附：本轮审查的边界

- 未写任何源码；未调用真实模型/Embedding/LangSmith；未改 103 条与 RAG 1000；未重建索引；未提交 Git。
- 本文所有路径与行号均来自当前工作区（HEAD `d4f944a`）。
- 70 条只是 PoC 规模，**不是**正式验收成绩；正式成绩仍需 B 的独立复核。

---

## 17. 实现状态与首轮 PoC 结果（2026-10-30 追加）

授权变更：用户已授权使用真实模型、不限请求次数。以下为实际落地结果。

### 17.1 已实现模块（均为新增文件，未改现有源码）

| 文件 | 作用 |
|---|---|
| `target/p2_case.py` | 场景 Schema、7 项校验、维度常量、去重（bigram Jaccard） |
| `target/p2_packets.py` | 证据包：生产 15 篇政策 chunk + 工具 Schema + **可执行夹具域**（日期宏、线路、车次、席别、热点售罄线路） |
| `target/p2_generator.py` | Prompt、真实调用（DeepSeek 原生 JSON）、解析/重试、归一化与 provenance |
| `target/p2_store.py` | 批次目录、append-only candidates、原始响应、manifest、哈希 |
| `target/p2_executor.py` | `expect` DSL 执行器（离线 Mock、每案独立 DB/TRACE） |
| `scripts/p2_generate.py` / `p2_validate.py` / `p2_run.py` / `p2_verify.py` / `p2_report.py` | CLI 流水线 |
| `tests/test_p2_pipeline.py` | 8 项离线单测（证据包、解析、校验、执行器） |

### 17.2 真实生成结果（DeepSeek `deepseek-flash`）

| 批次 | 请求 | 候选 | 有效 | 重复 | 接地 | 阈值 | 沙箱执行通过 |
|---|---:|---:|---:|---:|---:|---|---:|
| real | 14 | 70 | 92.9% | 5.7% | 100% | 未达标 | 32.9% |
| real2 | 14 | 70 | **100%** | **0%** | 100% | **达标** | 30.0% |
| real3 | 14 | 70 | 97.1% | 1.4% | 100% | **达标** | 47.1% |
| real4 | 14 | 70 | 91.4% | 5.7% | 100% | 未达标 | **70.0%** |

合计 **280 条候选 / 56 次真实请求 / prompt 158,832 + completion 48,251 tokens**。

### 17.3 证据链校验

四批 `response_sha256` 均可在 `raw/` 原始响应中找到，`request_id` 全部存在，
与 RAG 1000 规则题库的 bigram 相似度 ≥0.9 的占比为 **0%** → `verify.json` 通过。

### 17.4 执行失败归因（real4）

`args` 15 / `must_call` 12 / `reply_contains` 8 / `require_citation` 4 / `raises` 3。根因：legacy Mock 不维护跨轮状态、热点线路二等座售罄、自由文本断言脆弱、占位符不可解析、非 RAG 题误加引用要求。

### 17.5 尚未完成

- **人工审核：0 条 approved**，采纳率不可计算；审核清单见 `p2-20261030-real4/review_sheet.md` 与各批 `review_queue.jsonl`。
- 未合并四批的最优用例；未接入 `web/evidence.py` 的 P0 视图。
- 无单批同时满足“零重复 + 高执行通过”，需要继续调 Prompt 的模板化程度。

### 17.6 复现

```powershell
.\.venv-v35\Scripts\python.exe scripts/p2_generate.py --batch <id> --per-dimension 10 --per-call 5
.\.venv-v35\Scripts\python.exe scripts/p2_validate.py --batch <id>
.\.venv-v35\Scripts\python.exe scripts/p2_run.py --batch <id>
.\.venv-v35\Scripts\python.exe scripts/p2_verify.py --batch <id>
.\.venv-v35\Scripts\python.exe scripts/p2_report.py
```

汇总报告：`artifacts/runtime/p2-poc-20261030/report.md`、`poc_report.json`。
