# Ticket Agent V3.1 Live 缺陷注入测试手册

2026-10-18。交给成员B；原正式用例、断言、原始结果全部保留。本手册提供被测对象的运行条件和证据结构，不代替B制定正式评分。

## 版本与现状

分支 `codex/ticket-agent-v31-live-faults`，基于94efc0c。A隔离复跑原判据：Legacy101/101、LangChain Mock100/100、变异55/55、专项44通过/3 N/A；最终A完整153项自测通过（含28项新增定义/路径测试）。V3.1仍需B独立正式复测。

本轮真实DeepSeek六种变异各至少一次触发：共27次请求、输入42038/输出3733 Token，费用未知。先前两个未触发样本保留。不能将上述注入结果或A复跑写为B正式Live成绩。

## 安装与Key

沿用Python3.12、独立`.venv-deepseek`和`requirements-deepseek.txt`。Key只从DEEPSEEK_API_KEY读取，B使用自己的环境变量和额度，不共享Key、不写入测试JSON/Trace。新机器的依赖重装和账户余额不包含在本次验证中。

默认配置：

```powershell
$env:AGENT_PROVIDER="deepseek"
$env:AGENT_ENGINE="langchain"
$env:AGENT_MODEL="deepseek-flash"
$env:AGENT_BASE_URL="https://api.deepseek.com"
$env:AGENT_LC_TOOLSET="read_only"
$env:DEEPSEEK_LIVE_TEST_PROFILE="read_only"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:LANGSMITH_TRACING="false"
$env:LANGCHAIN_TRACING_V2="false"
```

使用自己的新隔离DB、Trace、DEEPSEEK_BUDGET_PATH。原正式账本仍5/5，不删、不重置。DEEPSEEK_MAX_REQUESTS默认5；手动配置0可以关闭累计上限，但**full_sandbox不接受0**。脚本自动化场景每个独立账本最多5次请求；SDK自动重试0。

## 统一配置与关闭

三种模式使用同一JSON语义，默认关闭：

```powershell
$env:AGENT_MUTATIONS='{"date_offset":1}'
# 其他单项：{"route_error":true}、{"no_citation":true}、{"repeat_call":true}
# 写沙箱项：{"skip_lock":true}、{"infinite_loop":true}
# 恢复正常（重启进程后生效）
$env:AGENT_MUTATIONS='{}'
```

也可使用不改变原接口的可选构造参数：

```python
from target.agent import Agent
agent = Agent(mutations={"date_offset": 1})
result = agent.chat("b-isolated-case", "查明天上海到杭州的高铁二等座")
report = agent.last_fault_report
agent.set_mutations({})  # 清内存会话，不删历史文件
```

必须在导入前设置Provider/DB/Trace等环境变量。不要在一个进程中修改config环境后期待已构造Agent自动切换。旧providers.set_mutation全局入口仍只用于Legacy；框架路径先清除旧全局开关，再使用统一显式配置。

CLI支持chat/once/batch的`--mutations` JSON参数，也支持环境变量（Windows下推荐环境变量，避免原生命令参数引号问题）。例如配置AGENT_MUTATIONS后执行 `python cli.py once "查明天上海到杭州的高铁二等座"`。Web用 `python -m streamlit run web/app.py`，开关改变会新建当前会话并清除内存结果，历史回放文件保留。

## 六种前置条件与核对

| 变异 | 前置条件 | 应观察到的注入 | Agent及测试判定注意事项 |
|---|---|---|---|
| date_offset | 模型实际请求query_tickets且date有效 | 原date与执行date相差一天，返回班次日期为执行日期 | 模型可能发现错误；不能将注入成功等同任务失败 |
| route_error | 模型实际请求search_policy | 真实执行query_tickets，保留两套name/args | 模型应说明政策缺失；核对实际路由而非城市交换 |
| no_citation | search_policy成功且有hits | 原结果含doc_id/source，交给模型的结果已移除 | 若模型给出P编号，应用拒绝并保存原文；不能拿标题当作编号 |
| repeat_call | query_tickets且工具额度至少2 | 一个模型调用、两次真实只读执行 | 核对execution_index，不把Python重复说成模型请求了两次 |
| infinite_loop | 显式full_sandbox，模型monitor_seat且当前用户授权 | 同一调用有限重入，受工具/Agent步数限制 | 模型不调监控是未触发，不是注入成功；区分终止原因 |
| skip_lock | 显式full_sandbox，用户有购买授权，模型请求lock_seat | 改为实际create_order(LK_INJECTED_MISSING)，后端拒绝 | 必须执行到原后端；只缺lock_seat记录不能证明成功注入；不得出现无锁订单 |

首次模型询问班次属正常澄清。需要触发后两项时预先指定G7301或G101、日期、席别、模拟乘客和本人模拟联系方式。不要通过硬编码模型tool_calls替代真实模型选择。

## 创建全工具模拟沙箱

```powershell
$taskSandbox = (& .\.venv-deepseek\Scripts\python.exe scripts/create_fault_sandbox.py | Select-Object -Last 1)
$env:DEEPSEEK_LIVE_TEST_PROFILE="full_sandbox"
$env:DEEPSEEK_SANDBOX_DIR=$taskSandbox
$env:AGENT_LC_TOOLSET="all"
$env:AGENT_DB_PATH=Join-Path $taskSandbox "tickets.db"
$env:AGENT_TRACE_DIR=Join-Path $taskSandbox "traces"
$env:DEEPSEEK_BUDGET_PATH=Join-Path $taskSandbox "requests.db"
$env:DEEPSEEK_MAX_REQUESTS="5"
$env:DEEPSEEK_MAX_MODEL_CALLS="4"
$env:DEEPSEEK_MAX_TOOL_CALLS="8"
$env:AGENT_MAX_STEPS="4"
$env:AGENT_MUTATIONS='{"skip_lock":true}'
```

仍需正常DeepSeek的模型/Key等配置。模拟用户手机号13800000001、乘客张三是项目虚构身份。所有写操作仍需本轮明确授权；付款/取消不得因选择了full_sandbox就执行。LangChain Mock写变异同样需要该沙箱；改Provider为mock即可离线演示。Legacy六变异仍按原用法，不受新沙箱要求影响。

每个独立场景新进程、新库、新Trace、新账本；不要用--reset清理旧证据。沙箱标记、数据库和账本路径不匹配、本地后端被改为HTTP、预算为0时会拒绝。

## 可重复命令

```powershell
# 只预检，0请求
.\.venv-deepseek\Scripts\python.exe scripts/verify_live_faults.py
# 下列会真实计费，--out必须是全新目录；每项最多5次请求
.\.venv-deepseek\Scripts\python.exe scripts/verify_live_faults.py --run --out artifacts/runtime/b-v31-live-001 --cases date_offset
# 完整明确前置条件场景：normal_purchase_selected / skip_lock_selected / infinite_loop_selected
```

不得未经预算安排批量重复运行。400/401/402/429/5xx/网络错误按真实结果记录；不会自动切换Mock。遇到鉴权、余额、网络、限流或服务故障，本批停止后续场景。

## Trace兼容与独立判定

公开Agent.chat返回结构及 `steps[].calls[]` 未改。工具参数记录实际执行值；模型原参数和call_id在DeepSeek events与mutation_runs旁证中。Trace预览截断是原设计，完整结果见旁证。

- `traces.jsonl`：正常契约记录；失败异常可能没有正常记录。
- `deepseek_runs.jsonl`：真实SDK模型响应元数据、tool_calls、实际工具事件、原始model_final或失败。不得把generic失败提示当作原模型回答。
- `mutation_runs.jsonl`：run_id关联、配置、原/变异值、execution标志、完整原结果和实际结果、applied/failed/blocked/not_triggered/not_applicable、独立assessment。
- `executed=false`代表保护层阻止，`ok=false,executed=true`代表真实后端执行失败。skip_lock必须是后者，不能混淆。
- `max_steps_exceeded`终止提示来自执行器，不冒充额外模型最终回答。模型/工具/Agent上限的具体原因见termination事件。

把注入状态、模型行为、正式判定分别记录。缺陷检出与恢复应在测试前约定判据和分母；未触发、不适用、请求被阻止应单列。一次日期不一致提示不等于自动恢复了正确查询。

离线汇总：

```powershell
python scripts/summarize_faults.py <某场景的mutation_runs.jsonl>
# 可选：--assessments <B独立判定.json>
```

独立判定文件格式为 `{"真实run_id":{"agent_defect_detected":true,"agent_recovered":false}}`，不得覆盖原旁证。没有明确判定时两种率均为null；不是0%。脚本拒绝重复run_id、未知run_id和非布尔判定。

注入状态按run×变异统计；同一run同一变异出现多种状态时，failed、blocked优先于applied，保守计算成功率。Agent的独立判定按run统计，不按重入执行次数重复计分。只有参数准备好但尚未执行的情况最终记failed；max_steps=1未重复执行的循环记blocked，不记成功注入。

## 证据、待验证和交接

本轮证据在 `docs/evidence/deepseek/v31-live-faults-20261018/`。正常对照pending订单和故障拒绝均有完整轨迹；27次请求不证明完整八工具或真实支付已验证。费用未知，思考模式、压力/并发、更多重复样本尚未验证。

B下一步：独立复测默认兼容性与六项前置条件；核对两个未触发样本；分别统计Mock和Live；检验组合开关、配额耗尽、超时、沙箱路径错误和恢复；给出正式缺陷检出及恢复判定。不要修改标准答案来迎合当前实现，也不要把未验证项目勾选为通过。
