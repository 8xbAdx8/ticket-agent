# DeepSeek Live localhost 完整闭环验证

日期：2026-10-17。分支：codex/minimal-deepseek-20261017。
实际执行源码HEAD：c6def7111cf4cebaabfa4c068417849b7077480b。
原恢复点2a8da2f867e2356f623816a4d08e4fb9bbc3d37e及其恢复分支保留。

**DeepSeek Live localhost 完整闭环 PASS。** 本轮只有一个真实用户回合、两次DeepSeek生成请求，未重试、未追加第三次请求。
这个结论仅针对下面这个模拟查票场景，不代表全部Live功能或成员B的正式质量评价。

## A/B：实际修改与原因

没有修改任何生产源码、Prompt、工具、业务状态机、Mock、六Mutation、授权/只读/预算守卫，也没有新增Provider层。

旧冒烟使用全新临时账本但额度1。第一次请求返回tool_calls后，本地工具执行成功；工具结果回传模型所需的第二次请求在发送前被预算守卫拒绝。

本轮最小调整是使用**另一个全新隔离账本**，额度2、使用数从0开始。没有将旧1/1账本改成1/2，没有修改正式5/5账本。本轮实际设置：

```text
AGENT_PROVIDER=deepseek
AGENT_ENGINE=langchain
AGENT_LC_TOOLSET=read_only
AGENT_MODEL=deepseek-flash
AGENT_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=<configured>
DEEPSEEK_BUDGET_PATH=<本轮隔离目录>/budget.db
DEEPSEEK_MAX_REQUESTS=2
DEEPSEEK_MAX_MODEL_CALLS=2
DEEPSEEK_MAX_TOOL_CALLS=1
DEEPSEEK_THINKING=disabled
```

SDK继续使用原代码的max_retries=0、超时20秒、输出上限512 Token。以上仅记录本轮已执行配置，不是重新授权，不要照此另建账本继续调用。

## C：先行离线回归

复用当前仓库原有回归入口，在新目录执行；凭据移除、外网阻断，SDK测试使用MockTransport。

| 范围 | 本轮实际结果 |
|---|---|
| 原DeepSeek SDK环境完整自测 | 122通过、0跳过，含原DeepSeek离线测试 |
| DEF-06 / DEF-07 | 原12个定向方法继续通过 |
| 原V3环境完整自测 | 90通过、32依赖跳过 |
| 原环境完整自测 | 42通过、80依赖跳过 |
| legacy Mock原判据 | 101/101 |
| Mutation原判据 | 55/55检出 |
| 原legacy pytest | 101 passed |
| 旧新增代码专项 | 37通过、0失败、3 N/A |
| LangChain Mock旧B判据 | 98/100，仍为X15/X16；T19 N/A |

X15/X16与当前HEAD已保存基线一致，没有新增失败。两项仍保留FAIL，没有改断言、跳过或计作通过，完整旧判据汇总仍为failed。它们分别要求拒绝锁座时调用lock_seat，以及只接受旧成功/未授权文案，与DEF-06澄清语义冲突。此次使用16个文件哈希已验证的B旧判据副本，不替代B的最新独立评估。

另以MockTransport验证临时limit=2时前两个假请求到达假传输、第三个在传输前被预算守卫拒绝；这个专项产生真实API请求0次。

## D/E/F：两次实际DeepSeek请求

唯一输入：

> 查明天上海到杭州的高铁二等座，请查询工具结果后列出有余票的车次。

| 请求 | HTTP | finish_reason | 输入Token | 输出Token | 结果 |
|---|---|---|---|---|---|
| #1 | 200 | tool_calls | 776 | 113 | 模型自主选择query_tickets |
| #2 | 200 | stop | 1164 | 218 | 模型生成非空最终自然语言回复，无新工具调用 |

本轮真实生成请求总数2；输入1940、输出331、合计2271 Token。实际费用未知，没有额外查询余额/账单。Agent总耗时4544ms，工具耗时2ms；没有单独测量两次HTTP请求各自延迟。

## G：模型实际最终回复

以下原样取自本轮model_final、正常Trace及localhost页面；三者一致，没有拼接替代成功回复：

已按 2026-10-18（明天）查询上海 → 杭州的高铁二等座，以下车次均有余票：

| 车次 | 出发 | 到达 | 席别 | 票价 | 余票 |
|---|---|---|---|---|---|
| G7301 | 06:00 | 07:00 | 二等座 | ¥73.0 | 35 张 |
| G7302 | 09:17 | 10:17 | 二等座 | ¥73.0 | 47 张 |
| G7303 | 12:34 | 13:34 | 二等座 | ¥73.0 | 51 张 |

共 3 个车次，二等座均有余票。以上为当前查询到的结果，余票会变动，请以实际为准。

另外说明一下我的能力边界：当前仅支持模拟查票和政策咨询，不能为您锁座、候补、下单或支付。如需了解退改签、儿童票等规则，可以帮您检索政策。

## H：真实工具执行与一致性

```json
{"from_city":"上海","to_city":"杭州","date":"2026-10-18","seat_type":"二等座","kind":"高铁"}
```

第一次真实响应的tool_call_id与实际工具执行事件call_id一致。query_tickets只执行一次，ok=true；tool_sequence=[query_tickets]。工具返回G7303/G7302/G7301，余票51/47/35，价格均73元。最终回复按车次重新排序后，出发/到达、席别、价格和余票均逐项匹配工具结果，没有多报班次。

LangChain沿用现有模型→工具→模型循环，第二次真实响应结束原回合。只读白名单query_tickets/search_policy保持启用。没有出现越权工具，lock_seat/create_order/pay_order/cancel_order/query_order/monitor_seat均未调用。隔离业务库库存2100条、锁座0条、订单0条。

正常Agent.chat契约字段不变，本轮生成一条正常traces.jsonl和一条deepseek_runs.jsonl旁证，reply/finish_reason/tokens一致；error=null。没有保存内部推理内容或Authorization请求头。

## I/J/K：预算与安全

- 正式预算5/5，文件SHA256不变；上限及记录均未修改。
- 本轮隔离预算从0/2用到2/2，已耗尽，不再发送。
- 上轮1次冒烟目录、历史Trace、763个原件和16个B判据文件哈希不变。
- Mock、Mutation及所有生产源码没有修改；离线Mock成绩与本轮Live分开记录。
- Key从当前进程DEEPSEEK_API_KEY读取，启动前仅从已配置的Windows用户环境变量继承，不读取秘密文件、不输出Key。
- 本轮日志、Trace、JSON、截图及将交付的证据检查未发现完整Key；公开配置仅为<configured>。没有将Key写入源码、报告或Git。

## L：localhost与清理

本轮使用现有Streamlit入口web/app.py，监听127.0.0.1:61081，健康检查ok、Agent初始化成功。
通过真实浏览器打开localhost，输入上述问题，仅点击发送一次。页面显示最终回复、3个班次卡片、query_tickets成功、stop和真实Token。

完成后关闭本轮Streamlit PID 29372，确认进程已结束；与本轮目录/端口相关的Python/Node/Java残留进程为0。没有终止其他用户程序或重新启动服务。

## M/N：Git与下一阶段

只新增本报告及脱敏证据，不改旧文件；同一独立证据提交。完整提交SHA见最终回复或git log -1 --format=%H -- docs/handoff/v3/DeepSeek_Live完整闭环验证_20261017.md。未合并main、未打Tag、未创建Release、未推送。

可以进入成员B的后续只读Live测试准备、成员C的真实证据演示准备；进一步在线测试需要新的明确请求预算授权。本次PASS不是八工具Live通过、不是正式比赛验收，也不授权继续调用。到此停止，不继续开发或重复测试。

## 证据索引

- [完整结构化核验](../../evidence/deepseek/live-complete-20261017-01/result.json)
- [实际两次HTTP结果与用量](../../evidence/deepseek/live-complete-20261017-01/requests.json)
- [框架实际模型/工具事件](../../evidence/deepseek/live-complete-20261017-01/traces/deepseek_runs.jsonl)
- [正常契约Trace](../../evidence/deepseek/live-complete-20261017-01/traces/traces.jsonl)
- [localhost页面截图](../../evidence/deepseek/live-complete-20261017-01/result.png)
- [页面可见内容](../../evidence/deepseek/live-complete-20261017-01/page-result.txt)
- [离线原始汇总（保留X15/X16失败）](../../evidence/deepseek/live-complete-20261017-01/offline/verification.json)
- [进程清理](../../evidence/deepseek/live-complete-20261017-01/process_cleanup.json)

**DeepSeek Live localhost 完整闭环 PASS。**
