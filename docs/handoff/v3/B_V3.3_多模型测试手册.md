# B：V3.3 多模型测试接入手册

日期：2026-10-25。本轮 A 完成适配器与离线自测，没有真实请求或远端上报；B 继续独立维护正式断言与成绩。不要将新增 256 项 A 自测写成 B 的正式用例数。

## 安装与安全配置

沿用 Python 3.12 和 `requirements-deepseek-lock.txt`，本轮未升级依赖。已安装者不重装。

```powershell
cd D:\codexproject\ticket-agent
py -3.12 -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt
```

使用 PowerShell 当前终端环境，不把 Key 粘贴到命令历史或发给别人。隐藏输入方式（仅手动执行，不会在赋值时输出 Key）：

```powershell
$env:DASHSCOPE_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host '百炼 API Key（隐藏）' -AsSecureString)).Password
# 以下是北京按量兼容服务的官方示例；必须与自己的 Key 地域/工作空间/套餐一致。
$env:DASHSCOPE_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
$env:DASHSCOPE_MODEL = 'qwen-plus'
# DeepSeek 使用独立变量；需要测试它时才配置。
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'DeepSeek API Key（隐藏）' -AsSecureString)).Password
```

地址和模型没有默认值。qwen-plus 只是官方兼容示例，并不保证账号权限；其他地域/工作空间请按官方控制台配置。Coding Plan / Token Plan 地址不适用于此后端接入。百炼当前通过 OpenAI 兼容 Chat Completions；Qwen 请求关闭思考，其他模型的额外协议须另行验证。

禁止 `echo`、`Get-ChildItem Env:` 全量输出或截图 Key。Key 只在环境/SDK 服务端内存使用，不放 Widget、用例、JSON、日志、Git 或 .env 提交。关闭终端即不保留本次进程变量；可手动 `Remove-Item Env:DASHSCOPE_API_KEY`。

## 零请求预检与 localhost

```powershell
# 没有 --run/--serve：仅本地配置预检，不验证 Key 有效性、余额或模型权限。
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider bailian
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider deepseek

# 启动 localhost，不自动生成；发送仍需页面费用确认。
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider bailian --serve --port 8503
```

缺 Key 明确报错并停止，不回退 Mock。页面左侧可选 Legacy Mock、LangChain Mock、DeepSeek Live、Bailian Live；另一个 Live Provider 也须完整配置，切模型新建隔离会话。只切页/主题/模型/查看历史不消耗 API。

Mock 继续双击 `启动_离线模式.cmd`。旧在线启动器仍可启动 DeepSeek，默认关闭外传；要启用 LangSmith，请用本节新命令，保留明确的启用配置。拉取代码后重启 Python 服务，不只刷新浏览器。

## 初次真实验证：合计最多三次

**本文命令由用户手动选择执行；A 本轮没有运行。** 一次聊天不等于一次模型生成，查票闭环通常需两次，复杂情况可能更多。三个账本固定保留：

- `artifacts/runtime/v33-live-providers/deepseek/requests.db`：该 Provider 预算。
- `artifacts/runtime/v33-live-providers/bailian/requests.db`：该 Provider 预算。
- `artifacts/runtime/v33-live-providers/initial-total.db`：两者合计初次三次上限。

原正式 DeepSeek 5/5 与旧手动账本不改。超时/崩溃的预留不退款，不能据此计算实际扣款。达到上限即停止，禁止删账本、换路径绕限或修改代码增加额度；需要用户重新明确授权。

建议优先选择**百炼查票闭环**：

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider bailian --run --scenario tickets --case-id BL-ticket-01 --out artifacts/runtime/v33-live-providers/bl-ticket-01
```

预检显示还有额度时，可以手动选择 DeepSeek 基础文本（通常 1 次）：

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider deepseek --run --scenario text --case-id DS-text-01 --out artifacts/runtime/v33-live-providers/ds-text-01
```

不要一次执行全部示例，不保证所有模型均按预期轮数结束。`--scenario policy` 适用于真实政策检索，但通常还需两次，不在额度不足时尝试。两模型同一查票用例通常合计至少四次，初次三次不足，不能声称完成双模型查票对照。

每次 `--out` 必须新目录；只有证据隔离，不会重置共同请求预算。零自动重试。命令报告 passed 仅针对模型/工具协议闭环，语义正确、政策忠实度与业务成功仍待 B 判定。

## 原接口、原测试与证据

```python
from target.agent import Agent
agent = Agent()
result = agent.chat('b-independent-session', '查明天上海到杭州的高铁')
```

使用前先在进程启动前配置 AGENT_PROVIDER/ENGINE 等；bailian 默认 langchain，工具集必须 read_only。直接 Python 测试仍须显式配置独立 DB/Trace/预算；推荐上述命令自动隔离。不要把已有库存/订单文件当新用例基线。

十字段和 calls 五字段见未修改的 `docs/contract.md`。Live 未知 Token/HTTP 错误按原策略抛安全异常；异常不是成功 JSON，详情在 sidecar。`finish_reason=stop` 不等于业务成功。

| 文件 | 用途 |
|---|---|
| `traces/traces.jsonl` | 成功返回的十字段公共契约 |
| `traces/audit_runs.jsonl` | 原版本化审计、权威库快照与独立规则 |
| `traces/provider_runs.jsonl` | 本轮 Provider/实际模型/case/SHA/时间/Token/真实事件与错误；未知用量 null |
| `traces/deepseek_runs.jsonl` | DeepSeek 原格式证据，仅 DeepSeek 写入 |
| `traces/langsmith_exports.jsonl` | 独立远端回执，不改变公共 Trace |
| `report.json` | 显式验证命令的单次范围/预算/结果；不等于正式测试评价 |

用真实 model_response.tool_calls 对照 tool_end 参数、ok、executed、result；随后模型必须收到 ToolMessage 并给出最终回答。不能从最终文本猜调用，更不能把普通文本算 Function Calling。reply_data_consistency/policy_grounding/business_success 未正式评估时保持未知。

B 原 101/101、100/100、69/69 等是不同历史批次。本轮没有重写 B 正式用例。可复用已有用例的输入、参数约束和业务不变量，但 Mock / DeepSeek / Bailian 分开统计，Live 自然语言采用事实/引用/参数检查，不能全部逐字匹配。跨模型还需相同输入/日期/工具集、隔离会话与库，独立保存原件。

## LangSmith：单独授权与核验

```powershell
$env:LANGCHAIN_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'LangSmith Key（隐藏）' -AsSecureString)).Password
$env:LANGCHAIN_TRACING_V2 = 'true'
$env:LANGCHAIN_PROJECT = 'ticket-agent-v33-review'
$env:LANGCHAIN_ENDPOINT = 'https://api.smith.langchain.com'
```

上述为官方默认服务；其他部署/区域由用户明确配置。可选 LANGCHAIN_WORKSPACE_ID。兼容 LANGSMITH_* 同义变量，但两套冲突会拒绝；不要保留另一套不同 Key/开关。

环境开关不会让 Agent 自动全量上传。页面须预览并勾选明确范围，再点“导出本轮并验证远端”。CLI 只有添加 `--upload-langsmith --confirm-upload` 才在同次模型运行之后导出：上传范围为本轮过滤后的输入/只读系统提示部分、最终回复、只读参数/结果及关联元数据，不含完整对话、订单、原始思维链或旁证全文。

不要为了上传再次生成模型请求；已有页面本轮结果可直接导出。每次导出最多 POST + GET 两次 LangSmith HTTP，模型生成数不增加；若 GET 因索引延迟/权限失败，标未验证/失败，不自动重试。核对 local Trace ID、remote ID、payload 摘要、POST/GET 状态、remote_verified 和 verification_origin。离线 fixture 的 verified 只是桩协议测试，不能当远端收到。

本地成功/失败与远端成功/失败分别判断。远端失败不得改原结果；未知用量不填 0。脱敏有范围，任意自由文本姓名不能保证自动识别，预览发现敏感内容应取消上传。

## 离线回归与待验证

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/verify_v33_offline.py --out artifacts/runtime/v33-providers-b-review
```

A 最终完整环境 256 通过、0 失败；V3 197 通过/59 跳过；V2 118 通过/138 跳过。原 smoke、八变异 25/8 通过。API/远端上报均 0。B 仍需独立验证真实账户/Tool Calling、多轮、RAG、异常/授权、预算及当前 UI，原 T04/脚本统计风险保持记录。
