# Ticket Agent 最新完整运行包交付报告

日期：2026-11-05（Asia/Shanghai）。本次仅制作运行包、隔离验证和更新交付文档，无产品源码修改，无 Commit / Push。

## 归档来源与范围

- 分支：`feat/ticket-agent-v36-stabilization`。
- HEAD：`c1620cb4e9e8df094494fc77ef3f0d07ef9928c3`。
- 归档来自实际工作区，包含 HEAD 之外已有的乘客提案修复和独立模拟时钟代码、测试、报告；不是仅导出 Git 已提交文件。
- 发布目录：`artifacts/deliverables/Ticket-Agent-Portable-20261105-110446/`。
- ZIP：`Ticket-Agent-最新完整便携版-Windows-x64-20261105-110446.zip`，精确大小和 SHA256 以同目录最终校验文件为准。
- 逐文件 SHA256、空目录、来源、排除原因：包内 `Ticket-Agent/PORTABLE/manifest.json`。

用户明确选择“完整运行包：排除重复旧工程副本，并附排除清单”。保留最新工程、必要数据、报告和原始保护证据；原项目未删除任何文件。排除243个重复旧工程目录、旧虚拟环境、Git管理目录、node_modules、缓存及既有交付包。1081个旧测试临时目录无法正常遍历，逐项记录为 unreadable_directory，没有修改 ACL；其中保护清单指定的104份日志通过逐文件读取补齐。最终1892、4056、5538三组保护文件全部收录，并与本轮实际源文件逐项 SHA256 匹配。此结论不表示改写或消除了历史基线早已存在的差异。

另移除7组 Chromium 测试配置目录及其 Cookie、登录/同步缓存；保留截图、原始运行日志和报告。不携带本机 .env、API Key 或用户凭据；已扫描已知配置密钥和常见高置信度 Token 格式，以及25441个嵌套ZIP/Office成员。扫描不包含图片OCR，嵌套大文件/更深层归档存在扫描范围限制，不声称完成对所有历史内容的绝对安全证明。

## 便携运行设计

目标：Windows 10/11 x64，建议解压前至少保留20GB空闲空间。内置可重定位 Python 3.12.14、原环境依赖及对应许可证，无需在另一台电脑复制失效的 venv 或先联网 pip 安装。Streamlit 1.65.0、SQLite 3.53.1，以及 pandas、Chroma、LangChain、DeepSeek/Qwen SDK 均使用包内运行时通过导入验证。

随包提供独立解压CMD和PowerShell助手，先检查整包SHA256，再用包内Python解压并逐文件验SHA256；支持中文、空格和Windows长路径，拒绝覆盖非空目标目录。不要在ZIP内直接启动，也不要用不支持长路径的解压程序忽略失败项。

解压后仍使用原 `启动_离线模式.cmd` / `启动_在线模式.cmd`。仅在包内两CMD增加启动前的 `PORTABLE/prepare.py` 调用：迁移副本中可变会话索引的绝对路径，原索引留存在 `PORTABLE/original_indexes/`。不改原项目CMD、业务数据库、原始Trace。第一次迁移85份索引；再次启动为0份，重复搬迁场景亦有隔离验证。

在线模式需使用新电脑自己配置的有效 Qwen/DeepSeek Key 和对应地址。本包没有密钥；密钥缺失时预检明确返回 missing_key，不自动发起真实请求。

## 必要数据核验

- GTFS ZIP：`artifacts/runtime/railway-dataset-preparation-20261102-gtfs/output_gtfs.zip`。
- GTFS SHA256：`3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`。
- 阶段八静态SQLite：`artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite`，原件只读且哈希未变。
- 实际查询统计：3169站、11588有效班次、107669有效经停；`trip_quarantine`表188行。历史“187异常班次”不是本轮测得表行数，不以硬编码替代实际统计，本轮未更改数据。
- 保留Fixture、RAG/Chroma、`docs/evidence`、`web/datasets`、正式103、B快照、历史账本、原Trace、报告及独立审查证据。
- 保留 `data/tickets.db` 和 `data/v39/` 数据库及其 WAL/SHM 原件。来源冲突的 `simulation-v391.sqlite` 只进行字节哈希和复制，没有连接、迁移、重置或修改。验证使用新建隔离库。

## 实际验证

验证目录：`artifacts/deliverables/latest-portable-20261105-110446/`。实际解压目录包含空格：`artifacts/deliverables/portable check 20261105-110446/Ticket-Agent/`。

1. 完整解压：116845文件、53427目录；116844份清单文件SHA256零不匹配，133.83秒；见 `extraction.log` 和解压副本 `PORTABLE/extraction-verification.json`。最终补入本次交付证据后另做全包CRC/SHA核验，见 `final-archive-validation.json`。
2. 运行时隔离：使用解压Python `-I -B validate_portable.py <解压ROOT> <结果JSON>`；所有检查模块及 `sys.base_prefix` 位于解压ROOT，无原项目Python/模块借用，网络连接被禁止。结果：`portable-smoke.json` / `.log`。
3. 真实本地流程：原Conversation Mock查GTFS、示例政策、Registry查库存/报价、用户确认建单、模拟支付、退款；最终CANCELLED、账本守恒、库存held/sold归零、外键检查无异常，PAYMENT仅一笔。
4. 原离线CMD `-CheckOnly`：PASS；从工程目录外启动原CMD `-NoBrowser -Port 8740 -RuntimeRoot <副本独立路径>`：健康检查PASS，解释器来自解压包。原在线CMD `-CheckOnly`：预期 missing_key/退出2，发送请求0，不标为Live功能通过。
5. 解压包 Python `-m pytest tests/v39 -q -p no:cacheprovider --basetemp=<独立目录> --junitxml=<证据目录>`：**387 passed / 0 failed / 0 skipped，58.46秒**。原始命令和日志：`portable-v39-command.json`、`portable-v39-pytest.log`、`portable-v39-junit.xml`。
6. 原离线CMD实际启动后的本机Edge + Playwright：1600×1100浅/深、390×844浅/深；**36检查通过/0失败，8截图**。实际查询、选车、报价建单、模拟时间推进、库存过期释放、刷新恢复、新会话隔离及横向溢出均验证。PageError 0，ConsoleError 16 / NetworkFailure 16，均为测试主动拦截外部字体/图标资源，不能记为Console零错误。见 `browser-four-spec/results.json` 和截图。
7. 369个源码/SQL/测试文件与包内归档字节一致；三组保护清单及6个关键数据库/伴随文件与源文件SHA一致，见 `final-protected-coverage.json`。只停止本轮解压副本测试进程，不停止原工作区服务。

历史回归仍为1441 passed / 11 failed / 1 skipped，另199通过子测试。本轮未重新执行旧完整回归；该结果来自已保留的模拟时钟阶段报告，不是本次便携包重测结果。正式103仍BLOCKED，Bridge未启用，独立审查和用户验收未替代。

早期验证驱动曾因Windows命令行拼接引号错误未能执行CMD；修正的是交付测试驱动，保留 `offline-check.log` 原失败证据，随后 `offline-check-r2.log` 和实际浏览器验证通过。未据此修改产品逻辑或旧断言。

## 使用方法与限制

1. 将发布目录中的ZIP、`解压_最新完整包.cmd`、同名PS1放在同一目录，双击解压CMD；默认解压到旁边新的 `TicketAgent-Portable/`。
2. 进入 `Ticket-Agent/`，双击 `启动_离线模式.cmd`。需要在线模型时配置自己的密钥，再用原在线入口。
3. 新铁路场景默认暂停模拟时钟起点 **2026-10-17 00:00（北京时间）**；右栏可主动推进，真实API/Trace时间不受影响。旧场景保留原模式，不自动重置订单。

本次在同一台Windows电脑的新路径、包内独立运行时完成验证；尚未在另一台物理电脑实测，不保证所有Windows环境策略、杀毒软件、端口和字体完全一致。不支持macOS/Linux/Windows ARM直接运行内置x64解释器。真实API、真实铁路、真实支付请求均为0。IMPLEMENTED / OFFLINE_VERIFIED / DATABASE_VERIFIED / BROWSER_VERIFIED；另一台电脑验收、Live API验收和外部独立审查仍待执行。
