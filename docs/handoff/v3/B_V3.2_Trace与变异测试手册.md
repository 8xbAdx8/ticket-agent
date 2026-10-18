# B：V3.2 Trace 与变异测试手册

2026-10-18。本手册交付运行接口和可复现条件；正式断言、指标评价与缺陷结论仍由成员 B 决定。本轮没有修改 B 原文件。

## 安全启动：不需要 API Key

在项目根目录打开 PowerShell。已有 `.venv-deepseek` 可直接使用；新机器安装时使用 Python 3.12 和 requirements-deepseek-lock.txt，安装依赖需要普通包下载网络，不会自行调用模型。

```powershell
cd D:\codexproject\ticket-agent
# 新机器才执行下面两行；已有环境跳过
py -3.12 -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt

$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_ENGINE="langchain"
$env:AGENT_LC_TOOLSET="all"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MUTATIONS="{}"
$runId=[guid]::NewGuid().ToString("N")
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\b-v32-$runId\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\b-v32-$runId\traces"
.\.venv-deepseek\Scripts\python.exe data/seed.py
.\.venv-deepseek\Scripts\python.exe -m streamlit run web/app.py
```

访问 http://localhost:8501。不要 seed 原库；以上库为新路径。每个测试进程用新 DB、TRACE_DIR、session_id，关闭变异并新建 Agent 清除模型上下文；清会话不会恢复库存。Web 并发按钮自建临时库，不动此库。重置某组模拟业务时应另建一组新路径，不删除历史数据。

本轮依赖实测：Python 3.12.14，LangChain 1.4.5，core 1.6.10，langchain-deepseek 1.1.1，LangGraph 1.2.15，httpx 0.28.1，Streamlit 1.65.0，pytest 9.1.1。未升级依赖。

## 一键复现新增八种证据

```powershell
$evidence="artifacts/runtime/b-v32-"+[guid]::NewGuid().ToString("N")
.\.venv-deepseek\Scripts\python.exe scripts/verify_v32_offline.py --out $evidence
```

该脚本在导入 SDK 前移除真实凭据并禁止非回环连接，只有 httpx.MockTransport 响应；会生成 25 条实际 Agent/后端记录和 8 条独立检测器样本。不接受 --run，不产生真实 API 请求，也不读写正式预算。路径必须全新，拒绝覆盖已有目录。

预期 status=passed、real_api_requests=0、failures=[]。检查 report.json 的 case_verdicts；预期缺陷成功检出可以 test_verdict=pass，但 quality_verdict=fail。不得据此宣称 Agent 八种缺陷全部自动恢复。

专项自测（全离线桩，A 测试，不替代正式测试）：

```powershell
$env:AGENT_ENGINE="legacy"
.\.venv-deepseek\Scripts\python.exe -m unittest tests.test_diagnostics tests.test_v32_audit tests.test_concurrency_probe tests.test_web -v
.\.venv-deepseek\Scripts\python.exe -m unittest discover -s tests -v
```

第二条运行完整 A 自测，前提是保持 mock/legacy、AGENT_MUTATIONS={}；DeepSeek 专项使用测试中注入的假密钥和 MockTransport。需强制网络阻断的跨环境留证脚本 `run_deepseek_review_offline.py` 依赖 A 旧工作区的历史账本、原数据及三套虚拟环境；新机器未拥有这些保护基线时不要为了运行它创建/伪造正式账本。新机器优先使用上面的独立八变异 runner 和完整 unittest。原完整测试数及跳过数见交付证据 offline/verification.json，正式 B 成绩应独立运行后命名保存。

## Agent 接口、开关与对照

```python
from target.agent import Agent

agent = Agent(mutations={})
normal = agent.chat("b-baseline", "查今天上海到杭州高铁二等座")
baseline = agent.last_audit_report
agent.set_mutations({"hallucinated_train": True})
mutant = agent.chat("b-mutant", "查今天上海到杭州高铁二等座")
evidence = agent.last_audit_report
assert "G9999" not in evidence["authority"]["trains"]
assert evidence["judgement"]["dimensions"]["platform_defect_detected"] is True
agent.set_mutations({})  # 清上下文，不能沿用污染结果
restored = agent.chat("b-restored", "查今天上海到杭州高铁二等座")
```

本示例已由专项测试及证据 runner 实际执行。运行前采用上述隔离环境，勿对原业务库直接测试。也可通过 AGENT_MUTATIONS JSON 设定；date_offset 值必须整数 1，其余是 true/false。显式 Agent(mutations={}) 优先用于确定关闭。

原 providers.set_mutation 六项及旧测试行为保留；M7/M8 使用显式 Agent 配置或新八开关，不塞入旧全局注册表。DeepSeek 默认仍是 read_only，只有 query_tickets、search_policy；skip_lock/infinite_loop 在未开放对应工具时 not_applicable。LangChain Mock 写变异也要求现有 full_sandbox，推荐一键离线 runner 自动创建；不要手工改正式账本或放宽守卫。

M8 在 Agent.chat 中不适用。直接运行真正的后端对照：

```python
from target.concurrency_probe import probe, SCENARIOS

baseline = probe("same_lock_two")
mutant = probe("same_lock_two", mutant=True)
assert baseline["judgement"]["actual_behavior"]["orders"] == 1
assert mutant["judgement"]["actual_behavior"]["orders"] == 2
assert mutant["judgement"]["dimensions"]["platform_defect_detected"] is True
assert mutant["resources_cleaned"]
```

支持 2—8 线程；默认两线程，same_lock_many 默认四线程。七正常场景：same_lock_two、same_lock_many、same_request_retry、different_locks、expired_lock、worker_failure、query_after_retry。正常同锁座返回相同订单；不同锁座各有独立订单；过期锁不创建；预设失败线程不部分写入。mutant 不用于 expired_lock/worker_failure；不同锁座变异为 not_applicable，不能统计为成功注入。

## 如何读证据

```python
from pathlib import Path
from target.diagnostics import read_audits, metrics

records = read_audits(Path("docs/evidence/v32/20261018-negation-fix/cases/sdk-date_offset"))
audit = records[0]
print(audit["trace_id"])
print(audit["mutation_events"])
print(audit["fault_report"]["model_requests"])
print(audit["fault_report"]["executions"])
print(audit["judgement"])
print(metrics(records))
```

- 公开 traces.jsonl：原十字段、原 calls 五字段；tool_sequence 是契约中记录的工具顺序，不能单凭重复名称推断真的执行两次。
- 新 audit_runs.jsonl：唯一 trace_id、权威快照、原始模型调用、参数校验、实际执行和判断。用 read_audits 自动校验/加载 blobs，不要只读 JSONL 封套就认定没有原始结果。
- executions.executed=true 是派发观察器确认进入后端；false 是拦截/拒绝；null 是无法确认。ok 另表业务返回成功与否。result 与 original_result 不能混用。
- mutation_events 的 before/after 必须对应实际字段；applied 才表示已注入；开关 enabled 不等于 applied。
- raw_model_reply 是模型公开输出，不是内部思维链；错误时也尽量保留，不用友好错误回复盖掉原文。
- contract_returned=false 表示原入口抛出错误，没有正常返回；读取 error、token_usage_evidence 和历史 deepseek_runs。未知/部分用量不能当 0 费用。
- finish_reason=stop 仅循环结束；max_steps_exceeded 表示受到上限约束。total_latency_ms 沿用 finish 时计时，额外旁证保存耗时需用外层墙钟另外测量。
- 旧 Trace 没有旁证时不能补造；Web 会明确提示缺失。相同内容的多条记录需按 ID 选择。

## 六个判断维度与分母

注入、平台检出、Agent 识别、Agent 恢复、安全停止、业务结果分别判断。unknown/null 独立列出；检出与识别/恢复率只计实际成功注入且对应结果可判定的记录。不触发与不适用不能混入成功样本。有限规则无法证明广义模型语义识别，交付集合该分母为 0、rate=null。

幻觉检测器的肯定句与否定/引用/假设有独立样本，6 条可判定加 2 条排除；需要 B 继续补人工标注集。不能用 6/6 描述真实模型幻觉准确率。

并发统计必须核对 requests、authority.orders、锁座 used/status、followup_query、并发屏障信息。不同锁座测试证明无应用级全局互斥且数据独立；SQLite 原生串行提交不属于新增全局应用锁。

## 与现有 100 条测试的关系、Live 边界

A 已隔离复制 B 的原判据运行，原文件字节不变；Legacy 101、LangChain Mock 100、原变异 55 继续独立统计。新增八种审计专项不改旧分母，不把 Mock、SDK 桩、后端并发、历史 Live 混成一个总通过率。B 请使用自己的原工作流，再追加 V3.2 专项；不要为了通过调整标准答案或 xfail。

本轮不配置 Key、不运行任何 --run。若将来另获在线授权，仍只通过 DEEPSEEK_API_KEY、AGENT_PROVIDER=deepseek、AGENT_ENGINE=langchain、AGENT_LC_TOOLSET=read_only，独立新 DB/Trace/预算路径并经预算守卫。当前默认两个只读工具，不能宣称八工具 Live 全通过。M7 新在线表现待验证，M8 不需要真实模型。真实模型自然语言不适合逐字匹配；确定性字段、来源、执行事实和业务不变量应独立断言。

问题提交时保留：分支/源码 SHA、环境摘要（无 Key）、trace_id、public Trace、audit/blob 原文件、断言名、原输入和失败原因；不要覆盖原失败证据。
