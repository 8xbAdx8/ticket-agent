# A · V3.4 API 全量适配审计报告

日期：2026-10-25；分支：`feat/ticket-agent-v34-api-audit`。结论：**有条件交接**。B可以独立离线回归并复核真实证据；不能宣布两个模型业务均通过，不能声称后置修复已经Live复验。

## 1. 版本与证据边界

| 用途 | Git SHA |
|---|---|
| V3.3恢复点 | `b4a7fa02126a12991caacc99702cc5ccf242dded` |
| 本轮实际模型请求源码 | `dc1e2895d8303f2df84ed9e0e16d77982797dbd9` |
| 后置修复最终离线验收源码 | `af2a2d54824f91ed901ee8b9eec49816f567727f` |

最终交付提交在上述源码之后，仅整理文档和证据，用 `git rev-parse HEAD` 获取。不能把文档提交SHA说成实际发生模型请求的源码。V1/V2标签、原始数据、历史证据及用户未跟踪ZIP保留。原分支没有重写历史，不合并main。

机器可读汇总：`docs/evidence/v34/api_audit_summary.json`；持续开发记录：`docs/v34_development_log.md`。旧V3.3、B原测试和本轮A自测分开统计。

## 2. 三个服务实际状态

| 服务 | 实际配置 | 连接/模型响应 | 工具协议闭环 | 业务/远端核验 |
|---|---|---|---|---|
| DeepSeek | `deepseek-flash`；`https://api.deepseek.com` | 已验证 | query_tickets已验证 | 本次固定查询与工具一致 |
| 百炼 | `qwen-plus`；`https://dashscope.aliyuncs.com/compatible-mode/v1` | 已验证 | query_tickets已验证 | **时刻错配，业务失败** |
| LangSmith | `https://api.smith.langchain.com`；项目ticket-agent-v33-review | 合成记录可回读 | 不适用 | **合成过滤上传已验证** |

三类Key在本机已配置，但不会随仓库交付。预检只检查配置，不联网认证，仍显示configured_unverified；验证事实以带版本和Trace ID的证据为准。没有单独发送Hello请求，模型响应与连接依据真实工具闭环。LangSmith不是全模型对话上传。

Live继续只开放query_tickets、search_policy；代码白名单禁止lock_seat、create_order、pay_order、cancel_order、query_order、monitor_seat。没有调用真实铁路/航空/支付系统。

## 3. 真实问题与修复原理

### 预算缺失关联与结算

旧总账3条均reserved_outcome_unknown，Provider账有DeepSeek2条HTTP200、百炼1条HTTP200。代码证实共享总账原先独立reserve而未可靠settle，Provider拒绝时可能遗留单边预留。旧schema没有共享request ID，条数相同不证明逐条关联。

新增target/request_accounting.py：新账同一UUID，以SQLite ATTACH同一事务成对预留/结算；固定持久化上限、幂等回写、发送前守卫、请求/Trace/步骤关联。记录预留、发送开始、响应、结算与未知结果。已收到的HTTP状态不被后续解析/工具/第二轮失败覆盖。中断保留身份与消耗，不猜测退款。原子路径仅接受DELETE/TRUNCATE/PERSIST journal mode，拒绝不满足恢复条件的配置。

旧账没有迁移、猜测补写或释放；新机制只用于新授权账本。

### 配置与错误事实

新增target/api_config.py：进程环境（含显式空）>项目内受保护.env>Windows用户变量，只读取白名单，不执行shell，不允许项目外.env路径。统一模型/Endpoint摘要，Key、前缀、认证头不输出；把Key误填成模型名时也脱敏。离线守卫禁止发现真实本地秘密。.env.example不是实际配置，空值会覆盖后备来源。

HTTP事件真实关联框架模型步骤与Trace。Token完整、部分已知、未知分开；未知用null，非伪造0。已知全部用量时业务失败仍保留完整Token。原单账本超时category保持旧reserved_outcome_unknown以兼容原断言，新双账细分阶段；异常细节在旁证中保存。

真实SDK警告默认socket options会重建HTTP transport，影响代理发现。后置显式http_socket_options=()保留原transport/mounts；构造和协议离线验证通过，**没有额外联网复验此修改**。

### 百炼时刻错配

原模型确实选择query_tickets、Python成功执行、结果按同一call ID回传，但最终把G7303/G7301的出发与到达时刻互换。新增target/reply_consistency.py：对明确单车次时间声明及带表头表格保守核对，实际四处错误离线检出；新Live路径报reply_tool_mismatch，原文字保留在model_final事件。

没有把错误回答替换成成功回复，没有掩盖失败调用。检查仅涵盖明确发到时刻，不是通用业务语义检测；无可检查字段保持未验证。结果附在原model_final事件内，原事件顺序不变，兼容DEF-06/07原断言。原Live失败保留，后置保护未Live复验。

### LangSmith远端回执

默认禁止未经筛选的框架自动导出。一次合成POST202、立即GET404，当时不能标verified。用户另行明确授权最多一次额外只读GET，返回200且远端ID/输入/输出/预览摘要匹配，没有重传或自动轮询。不能仅凭延后可见断言首次404的具体原因。

## 4. 文件职责与实际环境

| 文件 | 修改用途 |
|---|---|
| target/api_config.py、config.py、.env.example、.gitignore | 统一安全配置与忽略规则 |
| target/request_accounting.py | 新双账原子预留/结算与HTTP审计 |
| target/deepseek_runtime.py、target/bailian_runtime.py | 复用上述记账、原白名单和零重试 |
| target/live_providers.py、scripts/live_providers.py | 保留V3.3，显式新增V3.4固定授权profile |
| scripts/verify_v34_live.py | 固定2+2/总4、一次attempt、匹配离线门禁、合成上传/独立回读 |
| target/langchain_agent.py、target/live_evidence.py | 请求关联、原始事件、用量完整性 |
| target/reply_consistency.py | 明确车次时刻核验 |
| target/observability.py | 严格单次GET核验、合成范围 |
| tests/test_v34_api_audit.py | 新增A确定性自测25项 |
| docs/v34_development_log.md、交接文档、docs/evidence/v34/ | 开发过程、原始结果副本、对账和验证证据 |
| README.md、启动说明.md | 当前状态、入口与预算说明 |
| .gitattributes | 仅对新V3.4证据关闭Git换行转换，保证索引SHA256可跨平台复核 |

原docs/contract.md、业务工具、Mock主逻辑、变异实现、B正式断言与报告、依赖锁未改。完整差异见git diff b4a7fa0..HEAD --stat。

实际Python3.12.14；langchain1.4.5、langchain-core1.6.10、langchain-deepseek1.1.1、langchain-openai1.7.1、langgraph1.2.15、openai3.29.0、httpx0.28.1、langsmith0.14.8、streamlit1.65.0。复用.venv-deepseek，未统一升级包。

模型负责理解、选择工具和文字；LangChain执行模型返回的tool_calls并按call ID回传结果；原Python工具/SQLite负责虚构票务数据。Trace源于框架与实际HTTP事件，不从最后文字推测。一次真实模型生成请求可能计费，一轮对话本次各需2次；预检/打开网页不生成。

## 5. 本轮真实证据、Token与费用

输入：查明天上海到杭州的高铁二等座，请列出有余票的车次；以工具结果为依据。

实际参数：from_city上海、to_city杭州、date2026-10-26、kind高铁、seat_type二等座。工具结果：G7303 12:34→13:34/51张，G7302 09:17→10:17/47张，G7301 06:00→07:00/35张；模拟单价均73元。

| Provider | Trace ID | 请求 | 输入Token | 输出Token | 整轮ms |
|---|---|---:|---:|---:|---:|
| DeepSeek | 4effd0cdd8ae4d60a386b5e86f7f3996 | 2 | 1942 | 304 | 3818 |
| 百炼 | 7f83f6a0165a46fd8791e74ff7f84558 | 2 | 1756 | 288 | 8415 |

合计输入3698、输出592、总4290 Token；**实际费用未知**，无账单/账户实际计价依据，不把未知写成免费。各一次任务不能当作平均性能或通过率。自动重试0，写工具0。

docs/evidence/v34/live-20261025/{deepseek,bailian}/中original_result.json保留原始回复、tool_calls与事件；traces/为公共及Provider旁证；authority_and_review.json为实际只读库结果与A核验。两Provider库/会话隔离，各orders0、locks0。

LangSmith远端ID：52006b2b-acb1-4b8f-bfb1-51cea7ac409b；项目ticket-agent-v33-review；预览SHA：5b06cbc1e4b13a9bde21efd1a46292173e165541bde15cc46f2bbe8ce46bb698。langsmith/result.json保留首次202/404未验证结果；readback-result.json为另行授权后的200。累计**1上传、2GET、3次HTTP**，与模型生成分别统计；仅合成数据，不上传完整真实对话/原始推理。

## 6. 对账与保护

新账根artifacts/runtime/v34-api-audit/authorization-20261025/：共享4/4、DeepSeek2/2、百炼2/2，四条均HTTP200/settled，逐UUID匹配，无新未知。公开budgets/current_reconciliation.json可独立检查，不删除账本/attempt或增额。

原正式DeepSeek5/5、旧V3.3账本和原件均未改。旧SQLite一致backup保存在隔离工作目录；公开budgets/before/为脱敏结构快照和原件SHA。historical_reconciliation.json说明旧3条未知无法逐条关联，释放0。原始952文件保护范围（含原库、历史Trace、契约、用户ZIP）哈希全部不变。最终回归另有982文件保护范围全部不变；范围不同，不能解释成新增历史文件。

没有自动恢复库、覆盖历史Trace或删除用户文件。最终敏感检查见security_review.json；只公布类别与通过状态，不公布任何秘密值/前缀。

## 7. 已执行测试与提交

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/verify_v33_offline.py --out artifacts/runtime/v34-release-offline-20261025
```

以上目录已存在不可重用；复测选全新目录。最终公开offline/final/report.json，源码af2a2d5：

| 环境 | 收集 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|---:|
| 完整依赖、全部离线桩 | 281 | 281 | 0 | 0 |
| V3环境 | 281 | 222 | 0 | 59 |
| V2环境 | 281 | 136 | 0 | 145 |

另有smoke、八变异25运行/8标注、审计/回放/幻觉/并发/契约/DEF回归通过。剥离真实Key并阻断非本机Python网络；尝试0、真实生成0。跳过原因在各日志；三个环境不累计；不是B正式100条或100%成绩。

初轮全回归因原超时分类失败，后置首轮因事件顺序失败；早期新增自测曾有最小schema/连接关闭问题。全部保留development-attempts/日志，修复实现而未改原断言。

| 提交 | 模块 |
|---|---|
| 6d46a93 | 原子预算与统一配置 |
| 011b9c3 | 固定授权验收入口 |
| dc1e289 | 旧超时兼容、预检脱敏；随后真实模型验收 |
| b1bd1a8 | 时刻保护、Token完整性、代理保持、额外授权GET路径 |
| af2a2d5 | 保留原事件顺序；随后最终全离线通过 |

## 8. 未完成与交接依据

- 【真实API已验证】两模型query_tickets协议；DeepSeek本次单查询业务；LangSmith单条合成记录。
- 【LangChain Mock/离线桩已验证】完整281项、新25项A自测与八变异；原接口兼容。
- 【仅代码及离线验证】后置时刻保护、代理选项保持、Token修复，未Live复验。
- 【尚未验证】本轮Live政策RAG、多轮、异常矩阵、跨区域/套餐、思考模式、最终后置代码在线表现、B正式V3.4评价、C人工验收。
- 【存在问题】原百炼四处时刻错配；保护范围有限；旧3条未知无法恢复关联；新预算4/4耗尽。超时不确定是否收费，不自动重试/退预算。

**成员A开发交接状态：有条件交接。** B可离线独立回归与证据审查；C可如实展示已有记录。任何新增在线验收须用户明确授权新独立额度，不能删改旧账。后续优先确认百炼错误保护边界并在授权后Live复验，再验证RAG/多轮。
