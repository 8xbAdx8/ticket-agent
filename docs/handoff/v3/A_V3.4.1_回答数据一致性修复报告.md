# A · V3.4.1 回答数据一致性修复报告

日期：2026-10-25。结论：**有条件交接，可供B独立离线质量验收；修复后Live尚未验证**。

## 1. 实际基线与保护

基线feat/ticket-agent-v34-api-audit，提交e7831d3dce401653e8da8fc3911b574415015ba6；原工作区仅docs/showcase/v3展示.zip未跟踪。新分支codex/ticket-agent-v341-answer-integrity，不重置工作区、改main或标签。初始3590文件哈希保护包含原数据库、历史Trace、旧账、V3.4证据、契约与用户ZIP；全部未变。

本轮真实模型请求**0**，LangSmith请求**0**；新Token/费用不产生。V3.4共享4/4及原正式DeepSeek5/5不变，没有新建可调用的Live预算、重置旧账或使用不限额配置。历史模型费用仍未知。

## 2. 四处原始错误全部复现

模型qwen-plus，Trace ID `7f83f6a0165a46fd8791e74ff7f84558`。用户输入、参数、完整query_tickets结果和原模型回复逐字见[V3.4.1历史证据对照表](V3.4.1_DeepSeek与百炼历史证据对照表.md)，机器证据见docs/evidence/v341/historical_comparison.json；原件不改。

| 车次 | 字段 | 错误值 | 正确值 | 错误类型 |
|---|---|---|---|---|
| G7303 | depart | 06:00 | 12:34 | departure_time_mismatch |
| G7303 | arrive | 07:00 | 13:34 | arrival_time_mismatch |
| G7301 | depart | 12:34 | 06:00 | departure_time_mismatch |
| G7301 | arrive | 13:34 | 07:00 | arrival_time_mismatch |

实际查询上海→杭州、2026-10-26、高铁二等座。G7303票价73/库存51、G7302 09:17→10:17/73/47、G7301 73/35；时刻错位不是工具失败。本轮旧检测器和新检测器都检出四处，证明同一历史问题被保留复现；没有重新调用百炼。

DeepSeek历史Trace `4effd0cdd8ae4d60a386b5e86f7f3996`，实际模型deepseek-flash；本次已检字段一致。每Provider只有一个旧查询，不能宣称整体准确率或新模型成绩。

## 3. 检测器如何工作

target/reply_consistency.py为纯Python函数check(reply,events)，不调用API。以成功query_tickets的tool_end.result.trains为依据；明确executed=false、ok=false、工具错误、无完整结果的public result_preview不作为权威。旧事件未记录executed时兼容读取，来源保留event_index/call_id/args；无法证明更强的独立数据库事实。

1. 解析有明确标签的中文/英文字段、Markdown表格及逐车次多行文本，提取train_no、from_city、to_city、date、depart、arrive、seat_type、price、seats_left。
2. 先匹配车次，再用日期/路线/席别等明确身份筛选候选；同车次不同日期或席别不互相覆盖。只有候选业务数据相同或可唯一识别时逐字段比较，不按工具数组位置配对。
3. 找不到车次报unreturned_train；明确字段不相等分类为时刻、价格、库存、日期、路线、席别错误。身份组合不存在且无法确定是哪一个身份字段错时保存record_identity_mismatch，避免武断归因。多个日期/席别未指定，或同一身份多次工具快照相冲突，标indeterminate。
4. 统一时间/绝对日期/精确金额表示，金额用Decimal。库存“有票”只检>0，售罄检=0，不造具体张数；“充足”“大约”“73元起”等不确定表达不当作精确值。明确全量有票摘要仅在单查询可核验范围检查。
5. 区分用户引用/原话、否定句、假设/问句和模型主动陈述。用户引用不算查票成功；模型说“查询结果为‘G9999…’”仍检查。引号归属不明、复合多车次声明无法归属、格式不支持时标indeterminate，不凭关键词推断成功。
6. 每处错误保存字段、claimed、tool_value/tool_values、error_type、原文/行号与权威来源；检查不修改reply、工具结果或历史文件。

状态兼容：status=failed代表已发现错配；status=indeterminate代表存在明确但无法可靠核验的内容；checked_fields_match只说明已检查字段一致；无事实声明保留旧not_verified且verdict=indeterminate。checked_fields计非车次身份字段以兼容旧时刻计数，identity_checks另计。**这不是通用自然语言事实审计器，也不承诺完整语义正确。**

## 4. 共用防护与安全降级

DeepSeek与百炼在同一LangChain只读路径调用check，没有按Provider放宽规则。failed抛reply_tool_mismatch，indeterminate抛reply_data_indeterminate。失败不能返回正常成功JSON；公共十字段/工具五字段结构未改。原model_final.text及事件顺序保留，检查摘要嵌于该事件，失败旁证仍落盘。Web显示中文明确拦截原因；CLI为两个Provider提供脱敏失败输出。不会悄悄将原回答改成正确答案，也不发送纠错请求。

本轮采用明确停止的降级，没有增加结构化结果展示流程或偷偷继续工具链；已有工具卡片/JSON/历史回放保持原路径。六个写/订单工具仍禁止；Mock不启用新Live后置保护。

重要边界：若M7故意篡改模型可见的工具数据，回答可以与篡改后的工具数据一致；原独立数据库审计仍负责检出假车次。不能把“与工具一致”升级成“与数据库绝对真实一致”，不能为保留Mutation而给某个变异加豁免。

## 5. 文件与提交

| 文件 | 作用 |
|---|---|
| target/reply_consistency.py | 九字段核验、身份匹配、无法判定和证据 |
| target/langchain_agent.py | 两Provider共用检查与停止 |
| web/conversation.py、cli.py | 中文安全降级/百炼CLI脱敏错误 |
| tests/test_v341_reply_consistency.py、tests/fixtures/v341_reply_cases.json | A自测与64组完整用例 |
| scripts/verify_v341_offline.py | 纯离线全回归、字段证据与历史对照导出 |
| docs/v341_development_log.md | 连续过程、失败与修复 |
| docs/evidence/v341/、本组交接文档 | 可审查证据与交接/复验计划 |
| .gitattributes、README.md | 新证据换行保护、当前状态 |

未修改原契约、B断言/报告、原Mock/八变异、后端、Provider预算与请求机制、依赖版本。沿用V3.4环境，无新增包。

| 提交 | 作用 |
|---|---|
| 8bd3822 | 第一版字段保护与72项专项（当时62组字段用例） |
| 68e17ad | 离线验收与证据导出入口 |
| 9bd3c29049bb6de920e80283e3a9a4e361155470 | 正库存谓词兼容，最终74项专项、64组用例；完整回归实际源码 |

之后仅文档/证据交付提交，以git rev-parse HEAD取得交付SHA；不能说文档提交已做过Live。分支推送状态由最终终端结果确认，不合并main。

## 6. 实际验证结果

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/verify_v341_offline.py --out artifacts/runtime/v341-release-20261025
```

目录已存在，不要复用。复测换全新runtime子目录，脚本剥离真实Key并拦截外部Python网络，自动执行专项及原verify_v33_offline.py。公开报告docs/evidence/v341/report.json：

| 范围 | 收集 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|---:|
| 新专项（包含SDK离线桩） | 74 | 74 | 0 | 0 |
| 完整依赖全回归 | 355 | 355 | 0 | 0 |
| V3环境全回归 | 355 | 290 | 0 | 65 |
| V2环境全回归 | 355 | 204 | 0 | 151 |

新增74项=64组字段用例+4项属性/原错误验证+6项跨Provider真实SDK离线桩；完整355已包含它们，不再相加。原281项全部保持通过，原Mock smoke、八变异25记录/8标注、审计/历史回放/并发/幻觉/DEF/契约均通过。V3/V2跳过原因保留日志。不是B的新正式成绩。

每字段用例有输入、权威事件、输出、预期断言、实际判定与assertion_passed；检测器按预期判failed不是单测失败。两次历史重放明确标historical_live_replay_not_new_live。

首轮全回归353项有1个原M7子场景失败，smoke同步失败；修改有票语义为真实正库存谓词，原9项审计定向通过，再于全新目录重跑355项通过。保留所有失败证据，不改旧failed报告。专项扩展期的1个误报也保留development-attempts/。生产/历史保护哈希未变化，网络拦截尝试0。

## 7. 未完成与下一步

【已实现并离线验证】九字段保守检查、字段证据、共用拦截、安全提示、历史原错误复现、64组证据和完整回归。

【尚未验证】修复后真实模型再生成的表现、其他自由文本/JSON/英文复杂语句、多轮历史冲突的更精细消歧、跨日时区的相对日期推理、B独立质量评级、C最终人工验收。受限格式和含糊语言可能产生安全停止；B需独立评估误报/漏检，不将已检字段一致当成全部字段已覆盖。

独立在线计划见V3.4.1_真实复验计划.md：先建议百炼2请求，用户明确授权后才建立独立新账。没有执行、没有自动申请或增加额度。

**成员A开发交接状态：有条件交接。** 四处错误均复现并被新保护检出，原回归恢复通过；仅能交付已验证的离线能力，不能宣称修复后Live质量已验收。
