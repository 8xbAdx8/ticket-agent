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
