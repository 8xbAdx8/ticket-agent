# Trace、最终回复与质量判定一致性修复

日期：2026-10-27。检查起点：`957e5cb0fd7a8c07ea1cc2486e500ee5cf9254c4`。独立分支：`codex/fix-trace-quality-20261027`。代码及专项提交：`4eaddd0`；最终文档SHA以Git最新提交为准。

## 1. 结论与范围

已确认存在三处当前Bug：非票务引文触发数据校验、所有异常统一误报Token可能未知、错误判定fail却不保存失败原因。网页还把**未返回的异常占位记录**标为“Agent公开回答”，容易与模型原答混淆。本轮已做最小修复，并用历史原文和真实SDK的离线HTTP桩回归，不重写模型输出。

查票末尾非事实性追问的历史误判，在起点版本之前的 `22a1c75cffb96400a148ba83f73bbdfc00a7a690` 已修复。本轮确认其历史原因并增加冻结回归，**不把它冒充本轮新增修复**。

本轮模型生成、Embedding、LangSmith请求全部为0。虽然用户允许新增请求，这些问题可由已有响应和确定性桩复现，无须付费重跑。SDK桩测试不代表本轮真实模型质量通过。

## 2. 指定Trace逐层核查

Trace ID：`cbe8c088462046d99e49f322136c47d1`。

| 项目 | 原始证据 |
|---|---|
| 审计原件 | `artifacts/runtime/v33/user/web-aa088c032007/traces/audit_runs.jsonl` 第3行 |
| Provider旁证 | 同目录 `provider_runs.jsonl` 第3行 |
| 用户输入 | 妈妈 |
| 实际模型 | qwen3.8-flash |
| 当时代码SHA | 957e5cb0fd7a8c07ea1cc2486e500ee5cf9254c4 |
| 请求时间 | 2026-10-27 12:58:02.184460，北京时间 |
| HTTP | 200；request_id为`legacy-dbc4325ea7a9515b-14` |
| Token | 输入1412、输出81，合计1493；Provider旁证为complete |
| 工具调用 | 请求0次、执行0次，tool_execution_success=null；没有失败的工具调用 |
| 原异常 | reply_data_indeterminate，发生在模型返回之后的回答校验 |

模型完整原答：

```text
您发的“妈妈”我不太确定想问什么，方便补充一下吗？比如：

- 想查带儿童出行的**儿童票政策**（身高/年龄标准、购票规则）？
- 想为家人查询某天的车次余票？告诉我出发地、到达地和日期即可。

当前仅支持模拟查票和政策咨询，不能代为锁座或购票。
```

这段文字在邀请用户澄清，并没有声称查到班次、已经下单或执行工具。零工具调用符合该轮行为，不能据此推断工具失败。对一般语义是否最优仍由B判断，程序不自动给整个回答PASS。

| 层次 | 实际发生的行为 | 为什么看到不同文字 |
|---|---|---|
| 模型原始回复 | 上述澄清，保存在model_final与raw_model_reply | 模型正常HTTP返回 |
| 回答数据校验 | `indeterminate`，唯一未知项是`“妈妈” / unattributed_quotation` | 引文规则没有识别“您发的”，又对无票务事实的引号一律保守拦截 |
| Agent.chat | **抛出异常，未返回十字段结果** | `contract_returned=false`、`agent_completed=false`；不是返回了一句普通回答 |
| 审计中的public_trace | 包含“请求未完成；本轮真实 Token 用量可能未知。” | catch中调用trace.finish生成诊断占位；未写成正常契约返回 |
| 对话UI | 捕获异常，显示对应错误；不把失败轮追加为成功对话 | Conversation仅在Agent返回后append history；该输入没有匹配的正常traces.jsonl记录 |
| Trace工作台 | 原先把审计占位标题写为“Agent公开回答” | 标签未区分contract_returned=false，因此让占位看起来像真实返回 |
| 质量判定 | fail但failure_reasons为空 | verdict直接看error是否存在，原因列表却只收集失败的业务断言，两条正常断言均通过 |

第二条相同输入的独立历史记录 `2a8a65c47f604739a0547e1323ba7c23` 也复现了这个问题：引文为“妈妈”及“下周三北京到上海的高铁”的示例问法。输入759、输出85，Provider同样保存complete；不是另一次网络错误。

## 3. 查票历史Trace的确切原因

Trace ID：`6ed4d02f56244449ba992e803c86f200`。原件：`artifacts/runtime/v33/user/web-f9d4cb6b05d6/traces/audit_runs.jsonl` 第1行及同目录Provider旁证第1行。当时SHA为 `5e13a0b85cf9b42fd262b923046e2972f47e2758`。

用户输入：“查明天上海到杭州的高铁二等座”。请求发生在北京时间2026-10-26 22:28，传参日期2026-10-27与当时“明天”一致。DeepSeek实际调用query_tickets，工具执行ok=true，模型输入1916、输出299，Token已完整记录。

| 车次 | 工具出发/到达 | 模型出发/到达 | 工具/模型票价 | 工具/模型余票 |
|---|---|---|---|---|
| G7301 | 06:00 / 07:00 | 06:00 / 07:00 | 73 / 73 | 35 / 35 |
| G7302 | 09:17 / 10:17 | 09:17 / 10:17 | 73 / 73 | 47 / 47 |
| G7303 | 12:34 / 13:34 | 12:34 / 13:34 | 73 / 73 | 51 / 51 |

工具按7303、7302、7301返回，模型按7301、7302、7303展示；检测器按身份匹配，因此这不是行位置错配。原审计保存25个非车次字段检查、3个车次身份检查，全部一致，无finding。

**唯一导致indeterminate的原句：**“如果您需要改查其他席别或返程车次，可以告诉我”。其中“席别”被当作待提取字段，“如果”又触发不确定事实规则。它实际上只是邀请下一轮输入，并未声称具体数据。

当前起点源码已有`non_factual_follow_up`排除规则，直接用该原答和原事件离线复核得到 `checked_fields_match`，25字段及3身份仍一致。本轮保留专项，防止回退；原历史失败判定不改。**字段一致不等于全文语义准确率100%。** 相同输入的其他正常JSONL行不能据输入相同就关联到这次失败run，应使用Trace ID及旁证哈希。

## 4. 实际代码修复

| 文件 | 最小修改与边界 |
|---|---|
| `target/reply_consistency.py` | 识别“您发的/输入的”等用户引文、无票务事实的引号及明确的示例查询；后续“查询结果为”优先作为模型主动断言检查。未知车次、时刻、价格等引文仍需核验，不因有引号就豁免 |
| `target/live_evidence.py` | 抽取已有Token汇总为共享函数；只看实际model_response和已尝试HTTP数量，区分complete/partial/unknown，业务失败不改变已知Token |
| `target/deepseek_runtime.py` | 旧deepseek_runs旁证也使用同一汇总，避免与Provider旁证、审计不一致 |
| `target/langchain_agent.py` | catch保留具体错误类别、异常类型和发生阶段；校验类占位明确说明校验问题。仅在实际用量缺失/部分时提示Token未知/部分，继续抛原类别，不把错误当成功返回 |
| `target/diagnostics.py` | 判定检查原模型回复，避免占位掩盖幻觉；运行异常/工具失败都记录原因。`reply_data_indeterminate`归入未知原因，不单凭它认定明确业务错误；已证实的字段/工具错误仍fail |
| `web/trace_view.py` | 分开展示模型原答、数据校验、异常、已返回回复/未返回占位 |
| `web/audit_view.py` | 展示异常、未知原因、contract_returned=false；旧fail空原因记录提示缺失，不补造历史原因或重写原判定 |
| `tests/test_trace_quality_consistency.py`及冻结fixture | 新增A自测；从3条历史记录提取白名单原文和事件，附原文件哈希与行号；不读取密钥，不拷贝认证头或内部推理 |

正常澄清修复后的契约reply就是模型原文，`tool_sequence=[]`、`finish_reason=stop`。票务一致性为not_verified表示没有适用票务事实，并不表示工具调用失败。独立业务质量保留indeterminate、business_correct=null，不编造整体PASS。

真正的API鉴权/超时/预算/Token缺失、工具执行失败、明确数据矛盾依旧失败；无法可靠核验的具体数据依旧拦截、记indeterminate及具体原因。十个公开字段、工具调用五字段、只读白名单、预算、业务后端和变异逻辑均保持兼容。

## 5. 验证与复验

首批相关专项121通过；最终新增专项27通过、0失败、0跳过，另2个子测试通过。覆盖两Provider SDK、网页send与渲染、零工具澄清、真实错误分类、无重试、已知/部分/未知Token、原答与占位分离、幽灵车次仍被拦截、3条历史原文重放。

最终完整离线pytest **622通过、0失败、0跳过，另96子测试通过**。完整依赖环境unittest收集622项无跳过；旧DeepSeek/V3/V2环境分别收集622项，跳过24/112/247项（依赖不同），均无失败。Mock冒烟10命令、32条Trace通过，原八变异矩阵、八RAG变异、48题Keyword/Vector/Hybrid复验通过。自建快照13133个原文件无变化；发布回归另核对3933个原文件和62份V3.5.2证据，均无变化。原Chroma、历史失败Trace、原预算和B资料均保留。

首次专项中两个网页测试因测试夹具将Web目录放到系统临时目录而被正常路径守卫拒绝，已将**新增夹具**改为项目runtime隔离目录，不改安全守卫；首次失败记录保留。首轮全量因测试启动时额外设置TICKET_LANGSMITH_EXPORT_ENABLED=false，导致8项原LangSmith桩测试被强制关闭。移除该子进程启动环境干扰后重跑，不修改原测试或标准答案。最终完整回归与兼容环境结果以 [最终摘要](../../evidence/trace-quality-20261027/summary.json) 为准，首轮失败证据一并保存。

在新PowerShell中进行纯离线复验（输出目录必须全新）：

```powershell
$env:PYTHONIOENCODING='utf-8'
Remove-Item Env:TICKET_LANGSMITH_EXPORT_ENABLED -ErrorAction SilentlyContinue
.\.venv-v35\Scripts\python.exe scripts/verify_v352_offline.py --current-only --out artifacts/runtime/my-trace-quality-review
```

脚本自动清除子进程真实Key、阻断非回环Python网络、复制原RAG索引；无需`--run`。省略`--current-only`可执行已安装的旧环境矩阵与冒烟。不要因为此命令去清除用户持久化Key或旧预算。

历史逐项证据与当前离线重判：[historical-comparison.json](../../evidence/trace-quality-20261027/historical-comparison.json)。它是新报告，不替换旧审计。代码修复后需停止旧在线窗口再重新启动；已有会话可能仍持有旧Python Agent实例，新建/刷新页面不能保证完全重载模块。

## 6. B后续独立确认

1. 同样输入“妈妈”及引用示例的澄清：原文可返回、零工具、不误报网络/Token问题。
2. 不把零工具澄清当作调用失败，也不把没有业务事实的对话自动记成业务PASS。
3. 后置校验失败但响应有完整用量时，审计/Provider/DeepSeek旁证一致报告已知用量；缺失和部分仍未知。
4. 鉴权、预算、超时、工具失败、数据不确定、确定错配分别验收；fail必须有原因，未知必须列未知原因。
5. Trace页区分原模型输出与未返回占位；旧Trace只读回放，空原因不得自动推断PASS。
6. 真实账户最新模型的后续表现由独立Live测试确认；本轮SDK桩不替代正式质量结论。此前交接ZIP对应957e5cb0，未自动改写或覆盖，使用本修复分支时须核对新SHA。
