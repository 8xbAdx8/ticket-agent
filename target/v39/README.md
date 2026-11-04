# V3.9 本地铁路模拟模块

这是现有 Ticket Agent 的可关闭扩展，不是新的真实票务系统。

## 当前边界

- 只读使用阶段八固定 SHA 的 SQLite；不修改原型、GTFS、旧订单数据库或 Fixture。
- 默认 `RAILWAY_SIMULATION_ENABLED=0`。Baseline 永远保留旧八工具。
- 新增 11 个 `railway_*` 工具；模型只能读取、报价、生成提案，不能确认交易。
- 单个确认 Worker，SQLite 单活租约与 boot epoch；原始确认秘密只在该进程内存。
- 铁路对话当前使用明确标注的确定性离线演示 Provider。Legacy/LangChain 共用服务和注册表；不调用真实模型。
- D9 未批准：产品默认拒绝退款、改签及已支付订单取消。测试中显式注入的 A/B 政策不构成产品批准。

## 离线启动

在项目根目录启动独立的演示进程：

```powershell
$env:RAILWAY_SIMULATION_ENABLED='1'
$env:TICKET_DISABLE_LOCAL_SECRETS='1'
$env:TICKET_WEB_OFFLINE_ONLY='1'
$env:AGENT_PROVIDER='mock'
$env:AGENT_ENGINE='legacy'
.\.venv-v35\Scripts\python.exe -m streamlit run web/app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

用户工作空间选择“全国铁路模拟出行”。初次进入按需建立 `data/v39/simulation.sqlite`。可以用 `RAILWAY_SIM_DB_PATH` 指向 `data/v39/` 或本轮 `artifacts/runtime/v39-implementation-*` 下的全新路径；服务拒绝旧数据库、阶段八数据库和保护目录。

先查找车站并明确选择编号，查询静态车次，再选择模拟席别和乘客、生成报价、生成确认卡。勾选确认卡后才能锁座建单，模拟支付也需新的确认卡。查询与模型提案不代表出票、锁定真实座位或真实扣款。

开发者工作台可以选择 `rail-...` 会话调整原有 Mock 配置、Prompt 后缀与写权限。配置变化使旧提案失效。切换 Baseline 或在线 Provider 会关闭铁路执行入口，不会触发真实模型请求。退款/改签默认入口显示待批准，不能通过修改 Prompt 绕过。

## 测试

```powershell
.\.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v39-implementation-本地新批次/tests
```

输出目录必须全新。运行器使用独立临时数据库、清除子进程凭据环境并禁止外部 socket，允许本机测试 RPC；保存源码哈希、JUnit、原始日志及逐项结果。它不执行 B 方正式 103 条评分。

原始 V1.2.2 T046 将 K5165 终到时间写为次日 23:53，固定原件实际是次日 06:51。执行器保留原预期，因此当前套件有该失败，不承诺全绿；实际原件与 `47:53` 时间换算另有独立测试。

## 数据库与回滚

`store.py` 在新文件中逐条执行 `schema.sql` 和 `hardening.sql`；先启用 WAL、验证每条连接的外键，再 `BEGIN IMMEDIATE`。初始化中途失败，DDL 全部回滚，失败新文件保留供诊断。不要覆盖或自动修复该文件，改用独立新路径。已存在数据库必须匹配完整迁移 checksum；不会静默升级不匹配的文件。

本轮不是对旧数据库的迁移。回滚应用入口：停止演示进程，令 `RAILWAY_SIMULATION_ENABLED=0` 后重启；保留所有 V3.9 数据库、回执和日志，不删除数据。旧八工具和工作空间继续运行。演示“重置”通过新建独立 scenario 完成，不删除旧库存、订单和账本。

源码、数据库文件和确认 Worker 必须作为同一部署单元管理。不能用复制 raw secret、第二 Worker 或恢复旧 token 的方式绕过单活和重启失效规则。进程重启后旧确认卡需重新生成。

完整结果与限制见 `docs/reviews/Ticket-Agent-V3.9-Implementation-Report.md`。当前为 **PARTIAL**，不是正式发布或独立验收通过。
