# 成员 C：已经验证的 DeepSeek 证据如何演示（2026-10-16）

**当前演示是“回放真实 Live 历史记录”，不是实时调用。** 已经用完 5 次额度，现在禁止任何新的 API 请求，不演示在线发送、下单、支付或退款。

## 已有真实材料

- [原始运行报告](../../evidence/deepseek/api-20261016-001224-2c3484/report.json)：Hello、余额状态、两个真实只读工具场景、模型回复和事件。
- [公共 Trace（2条）](../../evidence/deepseek/api-20261016-001224-2c3484/traces/traces.jsonl) 与 [完整工具事件](../../evidence/deepseek/api-20261016-001224-2c3484/traces/deepseek_runs.jsonl)。不含内部思维链或认证头。
- [离线复核结果](../../evidence/deepseek/review-20261016/audit.json)、[预算快照](../../evidence/deepseek/review-20261016/budget_snapshot.json)。

北京时间 10 月 16 日 00:12 的这次运行，请求与返回名称均为 deepseek-flash。已验证的是 query_tickets、search_policy；其他 6 个工具并未开放 Live。所有业务数据始终虚构。

## 最容易演示的方法：打开文件

1. 在编辑器打开 report.json，先展示 `status=passed`、两个 verified=true 和生成请求数 5。
2. 打开 query_tickets 场景：用户问明天上海到杭州；模型传入 2026-10-17、高铁、二等座；工具返回 3 条车次。最终回复的价格 73 元及余票 35/47/51 与工具结果一致。
3. 展示 `model_response.tool_calls.id → tool_start.call_id → tool_end.call_id` 的一致性，说明这是实际工具轨迹，不是从文字猜出来的。
4. 展示 search_policy：返回 P12/P11/P13，最终引用 P11/P12，说明 15 分钟有效期和未支付取消规则。没有执行付款。
5. 展示 Token：输入 4,796、输出 563，共 5,359。费用写“未知，待供应商账单”，不能写本次 0 元。

可使用 CLI 只读显示最后一条真实历史 Trace；这里不创建 DeepSeek Agent，也不发请求：

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_ENGINE="legacy"
$env:DEEPSEEK_API_KEY=""
$env:AGENT_API_KEY=""
$env:AGENT_TRACE_DIR="$PWD\docs\evidence\deepseek\api-20261016-001224-2c3484\traces"
.\.venv-deepseek\Scripts\python.exe cli.py trace
```

终端返回对象的 provider=deepseek_live 指的是这条历史记录的来源；不是刚才进行了一次新的推理。该命令已在本次离线审查中运行核对。

## 用现有 Streamlit 展示历史记录

只复制 Trace 到新演示目录，保护原证据。页面当前模型配置是 Mock，仅在“历史记录回放”里看真实 Live 记录；**不要点击发送**。当前模式标签与历史来源不是一回事，镜头/字幕明确写“真实 Live 历史证据离线回放”。旧页面的“真实模型未验证”提示属于过时通用文案，本次未改生产界面，不把它当事实说明。

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_ENGINE="legacy"
$env:DEEPSEEK_API_KEY=""
$env:AGENT_API_KEY=""
$demoRun = Get-Date -Format "yyyyMMdd-HHmmss-ffff"
$demoDir = "$PWD\artifacts\runtime\recorded-live-$demoRun"
New-Item -ItemType Directory -Path $demoDir | Out-Null
Copy-Item -LiteralPath "docs\evidence\deepseek\api-20261016-001224-2c3484\traces\traces.jsonl" -Destination "$demoDir\traces.jsonl"
$env:AGENT_TRACE_DIR=$demoDir
$env:AGENT_DB_PATH="$demoDir\unused-demo.db"
.\.venv-deepseek\Scripts\python.exe -m streamlit run web/app.py
```

打开本机页面后选“历史记录回放”，分别选择两个 session，展开 JSON。这里只显示原始 Trace，不重新生成工具卡片，不触发真实模型。若误点 Mock 发送，新增内容只会进入副本，但不应混入展示中的 Live 记录。

## 3–5 分钟讲解顺序

| 时间 | 画面 | 可准确讲的内容 |
|---|---|---|
| 0:00–0:40 | 当前说明和报告概要 | 接入了真实 DeepSeek，当前演示回放已保存记录 |
| 0:40–1:50 | 查票 tool_calls、入参、结果、最终表格 | 模型选工具，LangChain 调度，Python 查虚构库存 |
| 1:50–2:50 | 政策调用与 P11/P12 | 模型依据检索结果回答，出处可以检查 |
| 2:50–3:30 | Token、预算、费用记录 | 5次生成请求已用完；本次回放新增0；实际费用未知 |
| 3:30–4:30 | 审查风险与交接 | 两个只读场景已证实，多轮/其他工具/正式评分待B |

查票回复末尾询问是否“办理订票”是已记录的能力话术风险，不以这句话证明真实下单可用。动画本身不是调用证据；Mock 的完整订票演示如另拍，必须单独标 Mock，不与这两个 Live 场景混剪成“八工具实测”。

不得展示密钥、环境变量值、认证头或内部推理。最终测试成绩由 B 提供，当前没有正式 Live 成功率/覆盖率/缺陷数量。需要实时新演示时，先由人解除冻结并授权新预算，本说明不构成新增请求授权。
