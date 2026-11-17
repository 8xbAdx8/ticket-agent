# 只读质量修复后的最新说明（2026-10-16）

源码修复提交 `e216fdf57ec8f34b84134ba2b30b05e5d6ff5985`。请先看 [当前冻结交接](B_V3只读冻结测试交接_20261016.md)。两工具已有历史Live证据，其余六工具未开放；本轮102项A离线自测通过，新增API请求0，额度仍5/5。新提示词尚未联网回归；旧ZIP bff292cd是修复前版本。

下方保留前次审查/演示背景，其中“待修复话术”“过时标签”已由本轮离线修复，旧缺Key结论仅属于历史。

---

# 成员 B：正式测试交接（2026-10-16）

**当前可对接，真实 API 冻结。** 现有 5 次额度已用尽，本轮新增 0 次；不要运行在线检查、cli once/chat/batch 或网页发送来测试 DeepSeek，不得删除账本、换路径、增加上限。生产代码与 docs/contract.md 没改。

已有 Live 证据和审查见 [A 验证审查](A_DeepSeekLive验证审查_20261016.md)、[原始运行报告](../../evidence/deepseek/api-20261016-001224-2c3484/report.json)。仅 query_tickets、search_policy 各一个独立真实场景。形式上可以交 B，正式质量结论仍由 B 负责。

## 当前仓库和交接包实际有什么

- Agent、8 个模拟工具、SQLite/RAG、CLI/Web、正常契约，以及两个只读 DeepSeek 工具的既有实现。
- A 的 88 项离线自测、FakeTransport 协议测试、Mock 示例 cases/demo.json。它们不是 B 的 100 条正式用例。
- B_缺陷分析报告.md 和 B的总结_测试层.docx；报告所述历史 Mock 基线为 95/100、5 个已知缺陷，并记录 xfail/变异数据。此处只引用，不当成本轮实测。
- **没有** B 完整 judge/、100 条用例集、tests/test_all.py、正式 execution.jsonl。不能在当前仓库宣称已重跑完整 100 条，也不能替 B 重新编造用例或改判定器。
- 交接 ZIP 将提供源码、依赖锁、交接说明、已有真实证据/隔离库、审查和离线回归记录。PACKAGE_MANIFEST.json 标识源码提交及文件哈希；不含 .git、虚拟环境、密钥、真实预算 DB 或原业务数据库。

## 如何复用原来的 100 条 Mock 用例

先由 B 在自己的测试分支/测试工程保留原 judge、cases、assertions、metrics、execution 基线；对接本包的 target/config 与依赖，不覆盖 A 的 tests，不覆盖旧报告。确认 B 执行器实际支持的参数，不假设它已经有 provider 开关。

原接口仍为 `from target.agent import Agent; agent=Agent(); result=agent.chat(session_id,message)`。相同用例的多轮用同一 session，不同用例独立会话/子进程/数据库/Trace。日期占位符按实际用例时钟转换，保持 B 的原规则。

原 100 条输入、业务事实、工具 Schema 与 R1–R6 断言可作为复用基础，但先跑 **legacy Mock** 基线；原六变异只适用 legacy Mock。LangChain Mock all 是独立执行模式，其额外授权/调用顺序可能与规则剧本不同，不能直接拿一套总分混算。

| B 历史维度 | 报告所述数量 | 当前如何复用 |
|---|---:|---|
| 功能准确性 | 15 | Mock 保留原断言；Live 仅筛选只读意图，含下单/支付/取消成功的场景不适用 |
| 工具调用 | 25 | 复用实际工具名/参数/顺序/冗余/失控规则；按注册工具集解释 |
| RAG | 15 | 检查检索片段、doc_id 与回答事实；当前仅一个真实政策问句已跑 |
| 多轮 | 12 | 复用输入和会话隔离机制；真实条件继承、交通切换仍未验证 |
| 安全 | 15 | 区分只读拒绝写操作与完整业务授权；不是“工具没注册所以全部安全通过” |
| 边界 | 12 | 可复用缺参/空结果/工具异常意图；未知用量/网络错误会抛脱敏异常 |
| 性能 | 6 | 可复用计时方法；Mock 毫秒阈值不直接套到 Live，不混合分位 |

数量来自 B 的 DOCX/报告，原始用例内容未在此仓库逐条核对。最终可迁移的 Live 用例数未知，由 B 按原用例实际内容登记，不先假定“100 条都能测 Live”。

F03/M11（交通切换）、F14（无票）、F13（重复支付）、T25（政策路由）应由 B 复查原 xfail 标记。修复目标不等于新成绩；xfail、xpass、skipped 必须独立记录，不能把 95 passed + 5 xfailed 写成 100 passed。

本次政策问题与 T25 意图相关，但提示词明确要求检索，且 session/措辞不同，不能自动登记为“原 T25 已回归通过”。F13 的支付成功流程当前不适用于只读 Live。

## 当前允许的离线检查

以下两个审查命令仅用于 A 原机：依赖接手保护文件、真实账本及三套既有虚拟环境。需要新输出目录，不覆盖本次已提交证据。无需 API Key，不发生成请求：

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv-deepseek\Scripts\python.exe scripts/audit_deepseek_live.py --out docs/evidence/deepseek/review-20261016/B-audit-new
# 输出目录必须是新目录；运行器移除真实模型密钥并限制网络。
.\.venv-deepseek\Scripts\python.exe scripts/run_deepseek_review_offline.py --out docs/evidence/deepseek/review-20261016/B-offline-new
```

审查脚本只读打开隔离库存和账本，验证已有 report/trace/tool ID/参数/结果/用量，不重新推理。费用账本不随 ZIP 传递；B 在新机器可读取 budget_snapshot.json 的历史快照。缺少原账本时不能用新空账本冒充预算已复核，可直接核对报告/公共 Trace，或由 A 提供原机审查结果。

在 B 的新机器或解压包中，原业务库、真实账本和虚拟环境均不随包传递，因此上述完整审查运行器不适用；直接读取包内已保存的审查/预算快照。安装锁定依赖后，可在清除实际模型密钥、设置 AGENT_PROVIDER=mock / AGENT_ENGINE=legacy、配置独立 DB/Trace 的进程中运行 `python -m unittest discover -s tests -v`（A 的离线自测），或按 START_B_交接说明.md 的网络阻断脚本运行。不要把缺失历史原件当成审查失败后自行补造文件。

原 100 条 Mock 的正式执行命令仍由 B 工程提供（报告曾给出 `python -m judge.executor` / `python -m judge.metrics`），本仓库没有对应模块，本次没有执行这些命令。Mock 执行也应关闭真实 LLM 裁判、清除相关密钥或使用网络限制，避免 judge/llm_judge 在后台额外计费。

## 未来如何测试 DeepSeek（当前不执行）

只有人明确解除冻结、批准新增请求预算后，再确认账户、账本与运行范围。不要现在重跑 `scripts/check_deepseek_api.py --run`；当前 5/5 不会因为换 session 而重置。

届时配置 `AGENT_PROVIDER=deepseek`、`AGENT_ENGINE=langchain`、`AGENT_MODEL=deepseek-flash`、官方 URL、`AGENT_LC_TOOLSET=read_only`、`DEEPSEEK_THINKING=disabled`。密钥只在本地环境提供，不进入测试记录；业务 DB/Trace 各用新目录，费用账本不擅自另建。每个用户轮次可多次请求模型；100 用例不等于 100 次 API 请求，LLM 裁判请求还需另计预算。

按场景独立记录 model、provider、toolset、thinking、版本/commit、输入、状态、实际调用/参数、回复、tokens、latency、request_count、judge 类型。多轮失败/调用异常也应保留，不能自动再试后只保留最好结果。

`steps[].calls[]` 与 `tool_sequence` 继续复用契约。`deepseek_runs.jsonl` 提供实际 model_response.tool_calls 和 tool_end 完整结果；契约 result_preview 仍截断，不能只解析它判断全部班次。实际模型名看 response_model，不用别名推断供应商内部版本。stop 不是业务成功。

真实模型回复非确定：对工具和业务事实作确定性断言，对自然语言用语义/事实检查；不要为了 Live 通过率回改 Mock 标准答案。必须改变规则时由 B 新建 Live 规则版本并保留旧版。引用应来自本轮命中文档，车次/库存/价格应对应本轮工具结果。

DeepSeek 请求失败或 usage 未取得时抛 `DeepSeekError`，旁路失败 tokens=null；正常 JSON 的 10 顶层/5 call 字段不变。CLI 的 error JSON 是诊断对象，不能当正常契约。若 B 判定器要求所有错误也返回正常 JSON，需团队先确认未知用量的表示，本轮不改接口。

## 成绩与费用必须分别统计

| 分组 | 当前可以写什么 | 不可以写什么 |
|---|---|---|
| B 历史 Mock | 报告所述旧版本 95/100 | 本次 V3 正式 95/100 或 100/100 |
| A 离线回归 | 新环境 88 项通过，另有旧环境跳过 | B 的 100 条用例通过 |
| 本次 Live 只读 | 已保存的 2 个基础闭环事实审查通过 | 全部八工具、全部100条或完整安全质量通过 |
| Live 多轮/异常/安全 | 尚未执行或待 B 评估 | 因工具未开放、被跳过而记 PASS |

每组分别列计划/执行/通过/失败/跳过/不适用/阻塞/xfail/xpass，说明分母；不要混合模型或执行模式的成功率、延迟和费用。当前 Live 两个场景可据此核对事实，但正式评价仍为待 B。

用量已知：输入 4,796、输出 563（含 Hello）。两个 Agent Trace 合计输入 4,788、输出 562，另 Hello 8/1；不可漏算或重复算。实际费用未知，无供应商账单。当前已使用额度 5，剩余 0。本次审查新增 0 次，不重新查余额。

优先确认 LIVE-REVIEW-01（只读回复仍邀请订票）、错误契约、模式/历史回放标签、真实多轮/越权与幻觉。测试结论、严重级别、正式规则和评分由 B 决定；A 本轮未代替 B 修改或执行完整正式测试层。
