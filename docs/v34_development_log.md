# V3.4 API 生命周期审计记录

## 2026-10-25 基线、现场与保护

- 实际恢复点 `b4a7fa02126a12991caacc99702cc5ccf242dded`，建立 `feat/ticket-agent-v34-api-audit`。原未跟踪 `docs/showcase/v3展示.zip` 保留。
- 检查 contract、Provider/Agent/工具、模型/依赖/配置、启动器、Trace 与旧预算。952 文件建立哈希保护，旧账本使用 SQLite backup 保留修复前一致快照，均在隔离工作目录，不覆盖原件。
- 旧总账3条均 reserved_outcome_unknown，Provider账 DeepSeek2条HTTP200、百炼1条HTTP200；总计数相同不证明逐请求可关联，旧 schema 没有共享请求ID。代码证实总预算只 reserve 不 settle；若Provider再拒绝，可留下总账单边预留。无法对旧记录确定一一关联，不释放旧额度，不伪造结算。
- 当前进程仅DeepSeek Key可见；百炼、LangSmith均不在进程/Windows用户环境。用户将自行配置用户变量，不接收聊天中的Key。官方文档只读核对，无模型请求。

## 2026-10-25 原子预算与配置

- 新增 `target/request_accounting.py`：同一 request_id，SQLite ATTACH + 单事务成对预留和结算，固定上限元数据、重复回写幂等、响应事实不可被后续异常覆盖、未知/超时保留消耗和身份。旧无ID账本只读拒绝续用，必须新授权账本。
- DeepSeek/百炼 HTTP 客户端接入共同记账，保留代理/证书默认行为和零重试；真实请求/响应事件关联框架 model_step 与 Trace ID。SDK解析/工具/下一轮失败不抹掉已收到的响应。
- 新增 `target/api_config.py`：进程（含显式空）优先于受保护项目.env，再到Windows用户变量；离线守卫禁止发现真实本地Key。统一模型配置和安全Endpoint摘要，提供.env.example，忽略真实env/密钥文件。
- `provider_runs.jsonl` 区分完整Token与observed partial；接口十字段/五字段不改。LangSmith synthetic记录明确命名，自动框架Tracing保持关闭。
- 首轮14项测试出现旧简化schema缺status及测试SQLite连接未关闭两个错误；修正只读兼容和测试closing，原失败日志保留。第三轮14/14通过；原DeepSeek运行时测试11/11通过。命令：`python -m unittest discover -s tests -p test_v34_api_audit.py -v`、`-p test_deepseek_runtime.py`，全部离线。
- 正式账本5/5、旧共享与Provider账本均未修改。实现提交与后续验收见git log和最终报告。

## 2026-10-25 固定授权验收入口

- 预算/配置模块提交 `6d46a93`。新增 `scripts/verify_v34_live.py`，固定新授权目录；DeepSeek2、百炼2、总4，Provider每轮最多2个模型步骤，失败/中断后attempt标记禁止重跑。执行前必须有匹配当前冻结源码SHA的完整离线报告。
- 预检仅本地检查与初始化新账本空schema；合成LangSmith预览和上传分成两个动作，必须用已检查payload摘要，另有一次上传标记。没有借用模型请求来验证LangSmith。
- 用户自行设置用户环境后，在实际用户权限下只读布尔检查均已配置。受限沙箱HKCU视图不同；在线验收使用已授权的实际用户环境，依旧不打印Key或前缀。
- 原始请求账本快照和哈希保留。16项新增确定性测试通过后，执行全量离线回归，随后才允许实际受控验收。

## 2026-10-25 全回归发现的兼容问题

- 首轮完整离线报告 `artifacts/runtime/v34-offline-20261025` 为failed：272项中原DeepSeek两项子断言要求单账本超时保留 `reserved_outcome_unknown`，新客户端把它细分成timeout/network类别，导致同样运行原单测的smoke失败。未修改原断言。
- 修复为旧单账本保留原类别；新的关联双账本才记录细分状态，旁证始终保留具体错误。旧未知记录不被重写。额外加固预检所有输出的秘密脱敏，防止用户误把Key填进模型名时打印；新增确定性断言。
- 真实请求仍0，在线门禁因离线failed保持阻止。修复并提交后将重跑全量，不借用首轮局部通过来开启联网。

## 2026-10-25 真实验收与新增发现

- `dc1e289` 冻结后全量离线273/273通过，V3跳过59、V2跳过141，均0失败；Mock smoke与原八变异25/8通过。952个历史文件哈希不变。实际用户权限预检DeepSeek/百炼均ready，新账本0/4、各0/2；密钥值未输出。
- 执行 `scripts/verify_v34_live.py --run-models --offline-report artifacts/runtime/v34-offline-final-20261025/report.json`：DeepSeek2次、百炼2次，均完成真实query_tickets工具闭环；没有自动重试，额度全部使用。DeepSeek输入1942/输出304，百炼输入1756/输出288。无可靠账单/实际价格，费用未知。
- DeepSeek Trace `4effd0cdd8ae4d60a386b5e86f7f3996`，3818ms，回复字段与工具三条结果一致。百炼 Trace `7f83f6a0165a46fd8791e74ff7f84558`，8415ms；协议闭环成功，但G7303/G7301的出发/到达时间对调，业务核验失败，不能把HTTP200/stop记为业务成功。原始回复和结果不改。
- LangSmith合成预览摘要 `5b06cbc1e4b13a9bde21efd1a46292173e165541bde15cc46f2bbe8ce46bb698` 已实际查看，无秘密/身份/订单/思维链。1次POST返回202、立即GET404，远端ID `52006b2b-acb1-4b8f-bfb1-51cea7ac409b`；当时未验证。不重传，额外GET已另行询问用户授权，未当作默认自动重试。
- 真实SDK提示socket options会替换HTTP transport并禁用代理自动发现；本轮网络成功，但此行为不应静默影响用户代理。显式 `http_socket_options=()` 保留原client transport/mounts，构造器离线断言通过；没有追加模型请求验证这个连接选项。
- 新增 `target/reply_consistency.py`：只对明确单车次发/到时间及有表头的表格做保守检查；错配抛reply_tool_mismatch，保留原模型文字，绝不替换成成功回复。无可检查字段保持未验证，不宣称通用语义检测。对捕获百炼回复离线复现4项错配，DeepSeek原表格通过。
- 修复新sidecar的Token完整性：已知全部HTTP用量在业务失败时仍完整保留；第二次超时则保留partial；未知usage不再生成observed 0。新增独立GET回读接口只在明确授权后调用，绝不POST；每次固定授权最多一次。
- 新增测试累计25项通过，原断言不改。源代码更新后将再次离线回归；本轮模型额度4/4已用尽，不再联网生成。后置一致性/代理修复只离线验证，不借用原Live结果宣称复验通过。

- 后置修复首轮完整回归281项出现1个旧事件顺序断言错误（DEF-06/07原测试用last_events[-2]查看原始政策回复），smoke因此失败。将一致性结果附于原model_final事件，保留原事件顺序和原始文本；不修改原断言。失败报告保留 `artifacts/runtime/v34-post-live-offline-20261025`，修复后另建目录复验。
