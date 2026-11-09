# Ticket Agent 最新版必要运行包

日期：2026-11-05。此前3.74GB包包含大量历史归档，不适合作为用户要求的运行交付。本包改为单ZIP，仅打包最新版程序、运行环境及必要数据；此前完整归档和本机原文件保留。

- 文件：`artifacts/deliverables/Ticket-Agent-最新版运行包-Windows-x64-20261105.zip`。
- 约342MB，比此前缩小约91%；解压约1.47GB，建议至少3GB空闲空间，Windows 10/11 x64。
- 当前分支 `feat/ticket-agent-v36-stabilization`，HEAD `c1620cb4e9e8df094494fc77ef3f0d07ef9928c3`。包含当前未提交的乘客提案修复和暂停模拟时钟。无Commit/Push。

保留：当前源码、原离线/在线CMD、便携Python3.12.14及依赖、未修改的阶段八static.sqlite、2100 Fixture、政策/Chroma索引、原三工作空间、小型正式测试数据及源码、页面实际读取的固定旁证、数据许可和署名。静态DB源SHA不变；GTFS版本/来源/授权风险附于 DATA_SOURCES。

不随运行包转交：原始GTFS下载ZIP和评估库、历史审查ZIP、测试运行目录、旧订单DB及WAL/SHM、旧会话、Trace、费用账本、密钥、浏览器配置/缓存、旧工程副本、Git管理目录。保护资产不删除、不修改，全部原件仍在原工程和之前的完整归档；本包不宣称包含1892/4056/5538整套历史归档。首次启动使用新建演示数据库，旧订单不迁移。原始GTFS/历史审计输入并非应用启动依赖，执行某些历史专项回归须取回原件。

直接完整解压到短路径，例如 `D:\TicketAgent`，进入 Ticket-Agent，双击 `启动_离线模式.cmd`。不需要外置解压脚本或另装Python。不在ZIP内运行。在线模式按 `.env.example` 配自己的Key和端点；本包不带Key、不自动发请求。

## 独立解压验证

证据：`artifacts/deliverables/latest-runtime-only-20261105/`。

- 使用包内Python且断开外部网络进行实际验证，模块及base_prefix均在新解压ROOT，未借用原环境。
- 完整初次解压：15663清单文件SHA256零差异，9.48秒；最终补入状态说明后再全包CRC/SHA核验，见 final-validation.json。
- 原离线CMD预检和实际启动：PASS，独立端口8741。在线CMD无Key：预期missing_key/退出2，真实请求0。
- 原Conversation Mock调用本地GTFS查询、示例政策检索、Registry库存/报价、用户确认建单/支付/退款：PASS，最终CANCELLED，账本守恒、库存held/sold归零、外键完整、PAYMENT只一笔。
- Chroma基线本地状态ready，B正式快照SHA全匹配，Baseline八工具身份通过。
- 验证驱动首次在没有配置Embedding端点时按现有规则得到invalid_endpoint，原日志保留；第二次仅给测试进程提供 `.env.example` 中已有兼容端点，网络仍禁止，索引本地完整性通过。没有修改产品逻辑、没有调用Embedding。纯离线政策走关键词检索。
- 原离线CMD页面Edge四规格（1600×1100/390×844，浅/深）：36/36，8张截图。查车/选车/报价建单/时间推进/超时释放/刷新/新会话/横向溢出均通过。PageError0；Console16、Network16为主动阻断fonts.gstatic.com图标资源，未记为零。
- 本次未重跑完整回归；此前387/0/0与旧1441/11/1+199子测试仅作历史参考。正式103仍BLOCKED，没有重新计分。未调用真实模型、铁路或支付；未在另一台物理电脑实测；未替代外部独立审查和用户验收。

本轮源码零修改；只新增打包产物及本报告、增量更新PROJECT_STATUS.md。当前工作区原有未提交成果保留。
