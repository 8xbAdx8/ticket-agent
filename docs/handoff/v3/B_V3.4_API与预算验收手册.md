# B · V3.4 API 与预算验收手册

日期：2026-10-25；分支feat/ticket-agent-v34-api-audit。A负责开发、自测，B独立制定正式断言、评级与成绩，本说明不替代B测试方案。

## 1. 当前边界

先阅读A同版本报告和docs/evidence/v34/api_audit_summary.json。两模型各2次真实请求，都完成query_tickets协议闭环；DeepSeek本次固定查询业务正确，百炼时刻错配业务失败。原始失败保留，后置保护仅离线通过。

共享**4/4**、各Provider**2/2**已耗尽，原正式账5/5未变。现在不要执行任何 --run、--run-models、--upload-langsmith、--readback-langsmith，或向Live网页发送消息；需要新的用户明确授权。不要删除账本/attempt文件或增额。仓库证据不代表另一台机器获得相同调用授权/Key。

## 2. 安装与无请求预检

已有.venv-deepseek直接复用；新机器才安装（下载依赖，不是模型请求）：

```powershell
py -3.12 -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt
```

实际版本在A报告，锁文件未改。仅本地配置/预算预检：

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider deepseek --profile v34
.\.venv-deepseek\Scripts\python.exe scripts/live_providers.py --provider bailian --profile v34
```

不带执行标志不调用模型；预检可能创建新账空schema，不创建付费请求、不写旧账。configured_unverified只是配置存在，非实时鉴权成功。缺Key明确失败、不回退Mock。fake-Key预检不证明账号/余额有效。

## 3. API Key 配置（不要发给A或聊天）

优先级：进程（含显式空）>项目内受保护.env>Windows用户变量。建议用户变量；修改后新开终端/重启服务。其他窗口的临时$env变量不传给既有进程。沙箱用户注册表视图可能不同，真实运行应在本人普通PowerShell检查，禁止打印Key排查。

隐藏输入后配置Windows用户级DeepSeek Key，不把字面量写进命令历史：

```powershell
$ticketSecureKey = Read-Host "DeepSeek API Key（隐藏输入）" -AsSecureString
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", [Net.NetworkCredential]::new("", $ticketSecureKey).Password, "User")
Remove-Variable ticketSecureKey
```

百炼换为DASHSCOPE_API_KEY，LangSmith换为LANGCHAIN_API_KEY。仅显示是否配置：

```powershell
"DEEPSEEK_API_KEY","DASHSCOPE_API_KEY","LANGCHAIN_API_KEY" | ForEach-Object {
  [pscustomobject]@{Name=$_; Configured= -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_,"User"))}
}
```

非敏感示例，百炼须匹配自己账号的地域/套餐/模型权限：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_MODEL","deepseek-flash","User")
[Environment]::SetEnvironmentVariable("DEEPSEEK_BASE_URL","https://api.deepseek.com","User")
[Environment]::SetEnvironmentVariable("DASHSCOPE_MODEL","qwen-plus","User")
[Environment]::SetEnvironmentVariable("DASHSCOPE_BASE_URL","https://dashscope.aliyuncs.com/compatible-mode/v1","User")
[Environment]::SetEnvironmentVariable("LANGCHAIN_PROJECT","ticket-agent-v33-review","User")
[Environment]::SetEnvironmentVariable("LANGCHAIN_ENDPOINT","https://api.smith.langchain.com","User")
[Environment]::SetEnvironmentVariable("LANGCHAIN_TRACING_V2","false","User")
```

也可按.env.example在本地.env填写；该真实文件被忽略，仍不得发送/打包。空Key行覆盖用户变量，不要留空却期待读用户Key。不要配置冲突的LANGCHAIN_*与LANGSMITH_*别名。启用LangSmith需用户同意过滤范围；普通模型调用关闭自动框架导出，不凭tracing=true宣称已上传。

## 4. 原Mock用例复用与分开统计

Legacy Mock仍为AGENT_PROVIDER=mock、AGENT_ENGINE=legacy；LangChain Mock为同provider、engine=langchain。沿用B自己现有100/101条等正式用例/断言，不把A281项当成B成绩。本仓库不假定judge模块已合并，使用B实际测试层入口，不复制/改写答案换通过。

完整离线回归会剥离真实Key并拦截外部Python网络，输出目录必须全新：

```powershell
$ticketReview = Get-Date -Format "yyyyMMdd-HHmmss"
.\.venv-deepseek\Scripts\python.exe scripts/verify_v33_offline.py --out "artifacts/runtime/b-v34-$ticketReview"
```

最终实际结果：完整281通过0跳过；V3为222通过59跳过；V2为136通过145跳过，均0失败。另有smoke、八变异25条运行/8标注、审计/回放/并发/幻觉/契约/DEF回归。跳过原因在offline/final/日志，不累加三环境分母。此脚本不调用模型或LangSmith。

日后获新授权的Live测试需独立Provider、case_id、session_id、库、Trace和预算，不直接把全部Mock用例跑到真实API。先估算模型请求数：一轮对话不等于一次HTTP。Mock成绩、Live协议、Live业务、A自测分别统计。自然语言不宜逐字匹配；B独立确定参数、真实工具事实和政策来源的断言。

## 5. 接口、错误与账本

入口仍为Agent().chat(session_id,message)，公共十字段、calls五字段、docs/contract.md原样保留。tool_sequence只是执行工具顺序，calls[].ok是工具结果，stop不是业务通过。Live未知usage不能当Mock数值0；旁证provider_runs.jsonl的token_usage_status区分complete/partial/unknown，tokens及observed_tokens可为null。

API/预算/工具/安全错误可能抛脱敏类型异常，不保证所有失败都正常返回JSON；B应捕获并核对已保存的执行/审计旁证。初始化失败可能没有Trace。新账phase/category/status区分预留、发送后未知、响应与结算。前一次HTTP200必须保留，后一次失败不能抹掉。超时不退款、不重试；未知不能推断免费。

traces.jsonl保存公共结果，provider_runs.jsonl保存实际模型/HTTP事件，audit_runs.jsonl保存独立审计；HTTP request_id与tool_call_id不同，各用于请求对账与工具消息协议。总账/Provider账按request_id连接，不以自增id或相近时间猜测对应。

只开放query_tickets、search_policy；lock_seat、create_order、pay_order、cancel_order、query_order、monitor_seat继续由代码白名单阻止。只读场景不得邀请或执行付费/下单。Mock原业务和八变异保留，不为DeepSeek改正式断言。

## 6. 本次真实证据离线复核

DeepSeek目录docs/evidence/v34/live-20261025/deepseek/，Trace4effd0cdd8ae4d60a386b5e86f7f3996；百炼对应bailian/，Trace7f83f6a0165a46fd8791e74ff7f84558。

original_result.json保留原模型tool_calls、call ID、工具结果与回复；authority_and_review.json给出实际只读数据库对照；traces/为公开Trace与旁证。budgets/current_reconciliation.json四条同UUID镜像，HTTP200且settled。历史快照与未知说明另存，未释放旧额度。

以下示例只读已保存JSON，不创建Agent、不请求模型；已实际执行。DeepSeek应checked_fields_match且6项，百炼failed且4处错配：

```python
import json
from pathlib import Path
from target.reply_consistency import check

for provider in ("deepseek", "bailian"):
    base = Path("docs/evidence/v34/live-20261025") / provider
    original = json.loads((base / "original_result.json").read_text(encoding="utf-8"))
    print(provider, check(original["public_trace"]["reply"], original["live_record"]["events"]))
```

检查只针对明确每车次时刻，不是完整语义通过。保护遇确定错配报reply_tool_mismatch、保留原model_final，不能把错误提示冒充模型已纠正。真实请求源码dc1e289，最终离线源码af2a2d5；后置保护未Live复验。

## 7. LangSmith、费用与后续

langsmith/保留预览、首次202/404和另行授权后的200回读。远端ID52006b2b-acb1-4b8f-bfb1-51cea7ac409b，只有合成数据，不是完整模型对话；不能重写首次未验证receipt。累计1上传+2GET，与模型4请求分开统计。模型输入3698/输出592 Token，实际费用未知，不填0。

B下一步：独立复测Mock/八变异/契约/DEF-06/07、预算幂等与异常，确认百炼错配保护的漏检/误报边界，复核原五xfail状态。新授权后再安排后置Live复验、政策RAG、多轮和异常矩阵。目前可冻结供有条件回归，不能签署百炼完整业务通过或全量Live验收完成。
