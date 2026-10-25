# B · V3.4.1 真实模型准确性测试手册

日期：2026-10-25。当前只有**历史Live证据重放与修复后的离线SDK桩**，没有修复后真实Live复验。B独立制定正式断言、误报/漏检评价及成绩；A新增自测不替代B正式100/101条等用例。

## 1. 安装、版本与零费用回归

使用原.venv-deepseek及requirements-deepseek-lock.txt，不需新依赖。开发分支codex/ticket-agent-v341-answer-integrity；基线e7831d3，最终运行源码9bd3c29049bb6de920e80283e3a9a4e361155470；用git rev-parse HEAD获取最后文档交付SHA。

```powershell
$env:PYTHONIOENCODING="utf-8"
$ticketReview = Get-Date -Format "yyyyMMdd-HHmmss"
.\.venv-deepseek\Scripts\python.exe scripts/verify_v341_offline.py --out "artifacts/runtime/b-v341-$ticketReview"
```

该命令已实际执行，会运行新74项专项、原三环境回归、smoke与八变异。剥离真实Key、禁用本地秘密发现并阻止外部Python网络，输出目录必须全新。新74项包含于完整355项，不能重复计数；V3为290通过65跳过，V2为204通过151跳过，完整环境355通过0跳过，均0失败。原281项维持通过；B正式测试层未改，不假设judge目录已经合并。

需要只跑专项时，在离线守卫环境使用unittest discover -s tests -p test_v341_reply_consistency.py -v。完整入口已包含此命令与网络守卫，优先使用完整入口。

## 2. 读取每项输入、权威与判定

静态测试定义：tests/fixtures/v341_reply_cases.json。公开执行证据：docs/evidence/v341/cases/<case_id>.json，64组；每组包括user_input、authority_events、model_output、assertion、actual、assertion_passed。62组为合成确定性输入、2组为历史真实回复重放。不是64次真实模型请求。

assertion_passed=true表示检测器结果符合该测试预期；actual.status=failed可能正是成功检出错误，不能把它统计成A单测失败。反之checked_fields_match不表示模型整体回答正确。

不联网的单例回放示例（已实际执行）：

```python
import json
from pathlib import Path
from target.reply_consistency import check

case = json.loads(Path("docs/evidence/v341/cases/history_bailian.json").read_text(encoding="utf-8"))
result = check(case["model_output"], case["authority_events"])
assert result["status"] == "failed"
assert len(result["findings"]) == 4
print([(f["train_no"], f["field"], f["claimed"], f["tool_value"]) for f in result["findings"]])
```

expected字段是A自测预期，B可建立自己的独立评价，不修改原B答案换通过。本轮新增原始用例从未写回历史Trace或V3.4证据。

## 3. 判定语义

| 字段 | 含义 |
|---|---|
| status=failed / verdict=inconsistent | 有明确字段或身份组合错误，Live停止 |
| status=indeterminate | 有事实内容但身份/格式/语义不能可靠核验，Live停止 |
| status=checked_fields_match | 仅已检字段相符，仍需B判断覆盖和业务结果 |
| status=not_verified / verdict=indeterminate | 无可核验事实，不当作通过或业务成功 |
| findings[] | 错误字段、claimed、tool_value(s)、error_type、行号/原文、权威来源 |
| field_checks[] | 逐字段依据与匹配结果，包含身份和comparison |
| indeterminate[] | 无法判定的具体原因，不转换为0错误成功率 |
| ignored[] | 用户引用、否定等语义范围，不能冒充模型肯定陈述 |
| checked_fields / identity_checks | 非车次身份字段计数 / 车次身份计数；不是测试覆盖率 |

字段分类：departure_time_mismatch、arrival_time_mismatch、price_mismatch、inventory_mismatch、date_mismatch、route_mismatch、seat_type_mismatch；未返回车次为unreturned_train，无法唯一归因的身份组合为record_identity_mismatch。具体枚举依据实际报告，不把所有错误简单写成幻觉。

业务身份依据train_no及明确date/from_city/to_city/seat_type等筛选，不依赖行序。同车次多日/多席别未指定或相同身份多快照冲突，必须无法判定；不能挑一个恰好匹配的票价。旧完整tool_end缺executed可兼容，公开result_preview不足以成为权威。

票价按Decimal精确值比较，时间/日期标准化；“有余票”检库存>0，不推测张数，“充足/大约/起价”等不能假定精确值。表格支持明确列名，中文标签支持逐车次/多行；复杂自由文本、未标记引用、关系跨多车次、相对日期等仍可能安全停止或漏检。B应特别探索这些范围，不能把本项目描述为通用语义验证器。

## 4. Agent、Web、CLI与Trace兼容

入口Agent().chat(session_id,message)不变，正常结果十字段、calls五字段、finish_reason语义不变；stop不是业务正确。两个Live Provider走同一检测器，不按模型设置不同答案。Mock路径及八变异原样保留。

明确错配抛reply_tool_mismatch，无法可靠核验抛reply_data_indeterminate；Web显示明确中文停止原因，CLI两Provider均脱敏退出。失败可能没有正常traces.jsonl行，应读取provider_runs.jsonl与审计旁证中的model_final.text及reply_consistency，原模型文字保持原样。原工具执行结果和第一次HTTP成功不会因后置拦截变成“未调用模型”。也不能把错误提示当成模型已经纠正原回复。

六项SDK桩集成覆盖两Provider的正常/错误/无法判定，真实LangChain+实际隔离SQLite+httpx.MockTransport，不是实际远端API。桩请求仅写临时测试账，绝不计为新增付费请求。

M7会故意把假车次加入工具可见结果，字段一致性可能显示相符；原独立SQLite审计仍须检出权威库不存在。不要为通过测试而修改M7、原断言或关闭保护。首轮兼容失败和修复记录在development-attempts/，最终原9项审计回归和完整smoke通过。

## 5. 历史对照与B独立项目

历史DeepSeek真实工具调用成功、单例A核验正确；百炼真实工具成功但4处时刻错配。原model_final均无本轮保护，不写成“当时已拦截”。输入/输出Token分别1942/304、1756/288，延迟3818/8415ms，仅旧任务观测；费用未知。详见V3.4.1_DeepSeek与百炼历史证据对照表.md和historical_comparison.json。

B优先独立验证：九字段边界及错误分类；同车次多日/多席别、重复/冲突快照与行序；假车次/空结果；用户引用与主动引用、否定+肯定混句；金额/库存表达的误报漏检；两Provider相同规则；失败Trace保留原文和工具来源；Mock/八变异/DEF/契约。原xfail继续由B根据正式复测处理。

## 6. 未来Live与密钥

当前V3.4共享4/4、正式旧5/5不变，本轮不允许真实请求。不要设置不限额、不删账、不修改状态，不执行在线启动后的发送。API Key本地隐藏配置方法见B_V3.4_API与预算验收手册.md；不发Key给A，不写进用例、日志或报告。LangSmith也不自动上传。

独立计划见V3.4.1_真实复验计划.md，建议先百炼2次生成。B需分开统计：模型协议、工具执行、模型原回复准确性、保护层拦截、整体业务完成。模型仍答错而保护成功应记“模型错误/保护成功/任务安全停止”，不能改成模型业务成功。新授权后再做Live，当前不宣称已经完成。
