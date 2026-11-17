# 成员 A 开发记录

日期按 Asia/Shanghai 记录。仅记录实际执行；Mock 结果不代表真实模型。

## 2026-10-12 接手基线

- 原工作区无 `.git`，无法恢复此前提交历史；在独立分支建立本地 MVP 快照，未推送。
- 缺少：`成员A任务书_被测抢票智能体.md`、`订票.doc`、`README.md`。不猜测缺失任务书，按用户附件和现有契约增量开发。
- 新增文件：`.gitignore`、本记录；基线源文件保持原样。数据库和历史 Trace 原地保留、不纳入 Git。
- 实际检查：`git status --short` 报非 Git 仓库；`rg --files --hidden` 确认源文件；`Get-FileHash` 确认契约及原始素材。
- 契约原始 SHA256：`BFE2F8EBF1EC02B831765286652E50344D1CFCC24D5179BD8FFD78FE6E8C0381`。
- 历史 Trace 原始 SHA256：`9DA6C84898E46585D179C696BC83CF92F0304D43319AAC8620F6248EF6427C0B`。
- 原数据库 SHA256：`C718BF95D07E9645A1963BF8376C68A67598092E4DCE46EBD482BE5956121537`。
- 已识别待修复：Mock 多轮状态混用、skip_lock 无实际效果、退款库存数量错误、订单越权、HTTP 请求体不匹配、测试路径不可隔离。
- B/C 影响：现有契约保持；当前结果尚不具备完整交接条件。
- 提交 SHA：基线提交完成后登记于下一条记录（提交不能包含自身 SHA）。

### 资料补充

用户随后补充任务书与 `订票.doc`，恰在基线提交前到达，已原样纳入基线 `bdb8370250b434f62865ac666fa08fb3c3c7541d`；README 尚在等待落盘。任务书要求保留结构与 8 个工具，并列出 30/5 条线路、15 条政策的扩展里程碑。`订票.doc` 是二进制旧版 Word，需抽取正文后再核对，不能当普通文本读取。初始缺失记录是首次检查时的事实。

## 2026-10-12 数据及隔离配置

- 修改：`config.py`、`data/seed.py`、`data/policies.md`；用途为隔离测试与完整虚构数据集。
- 配置新增 `AGENT_DB_PATH`、`AGENT_TRACE_DIR`，时钟统一北京时间。生成器默认拒绝覆盖，只有显式 `--reset` 才重建。
- 独立新库新增库存唯一约束、非负约束、lock_id 订单唯一约束；既有数据库未迁移、未覆盖。
- 实际命令：`.venv/Scripts/python.exe data/seed.py --path artifacts/runtime/seed-check.db`；输出 2100 条。
- 实际 SQLite 分组查询：高铁 30 条线路 / 7 天 / 1890 条，机票 5 条 / 7 天 / 210 条；`len(load_chunks())` 为 15。
- 问题：旧库仍是原样；B/C 应使用新建隔离库。生成日期之外的查询空结果是预售范围限制。
- B/C 影响：契约不变，环境变量必须在 import 前设置。
- SHA：此模块提交后在后续记录登记。

数据模块提交：`e9b5012cd6a65647eeedbdef236f9fe15f39d7e7`。

## 2026-10-12 工具、订单事务与只读资料核对

- 修改：`target/mock_core.py`、`target/tools.py`、`target/mock_api.py`；新增 `tests/test_core.py`、`scripts/read_legacy_doc.py`。
- 工作原理：所有数据库访问在 `BEGIN IMMEDIATE` 事务中执行；访问时回收过期占座，按乘客数释放库存；限制订单所有者，幂等支付与下单，拒绝非法状态。工具 dispatch 校验 schema；HTTP 保持服务器已有 `{"args": ...}` 请求体。
- 已实际读取 `订票.doc` 的 Word piece table 正文，强调工具/函数调用、虚构数据、模型只选择工具、Python 实际执行；与当前实现方向一致。原文件未修改。
- 命令：`.venv/Scripts/python.exe -m unittest discover -s tests -p test_core.py -v`。首次 2 个测试因测试自身 SQLite 连接未关闭造成 Windows 临时文件清理错误；改用 `closing` 后 4 个自测全部通过（业务幂等、人数库存、过期回收、本人订单限制、参数/故障、候补）。
- `.venv/Scripts/python.exe scripts/read_legacy_doc.py 订票.doc` 成功抽取正文；olefile 仅此辅助脚本需要，主程序无此依赖。
- B/C 影响：工具名称与契约字段不变；错误调用 `ok=false`，新库状态含 `cancelled/expired`，按既有字段返回；候补只监控已有无票班次，不执行后台兑现。
- 待完成：Agent 多轮修复、真实 Provider 错误处理、Web 全开关与入口验证。
- SHA：此模块提交后登记。

工具模块提交：`144ab3f6c576077154dda08bbf0e866e00491679`。

## 2026-10-12 Agent、Provider、RAG 与 Trace

- 修改：`target/agent.py`、`target/providers.py`、`target/trace.py`、`target/rag.py`；新增 `tests/test_agent.py`、`tests/test_provider.py`。
- Mock 只把最新 user 之后的工具当本轮执行；之前的查询参数/订单作为上下文；ISO 日期和下周语义按北京时间解析，机票默认经济舱。6 开关均提供实际可触发行为，Web 可用独立 provider 字典隔离。
- 主循环对格式错误/模型异常返回安全提示；仍只用契约的 stop/max_steps_exceeded。使用 perf_counter 真计时，完成时冻结，返回和落盘一致；tokens 累加模型 usage，Mock 为 0。
- OpenAI 风格适配器保留服务器 call id，坏 JSON 送 dispatch 返回失败供模型纠正，禁用自动重试，30 秒超时。官方参考：https://developers.openai.com/api/docs/guides/function-calling 。无 API Key，未联网测试真实模型。
- RAG 返回 doc_id 和项目内 source，可选向量不可用时回退关键词检索；向量实际检索待验证。
- 命令：`.venv/Scripts/python.exe -m unittest discover -s tests -v`；首次复合“订票并支付”被支付分支抢先处理，修复后 10 个实现自测通过。
- 验证含多轮/会话隔离、退票库存、候补、机票购付、6 种变异、异常脱敏、契约 JSON 与保存一致、Provider ID/usage 适配。不是 B 的正式覆盖率或测试成绩。
- B/C 影响：顶层/调用字段完全不变；模型失败也可能 stop，因此 stop 不等于业务成功；全局变异仅限串行 Python 测试，Web 独立字典。
- 待完成：入口与 Web 验证、交接文档；真实模型/向量联网实测仍缺条件。
- SHA：提交后登记于后续条目。

Agent 模块提交：`03b63c8ea5ab082b66a11f3762b2e76b733feed1`。

## 2026-10-12 CLI、示例与可复现证据入口

- 修改 `cli.py`、`run_demo.py`、`cases/demo.json`；新增 `scripts/handoff_example.py`、`scripts/smoke.py`。
- 演示默认创建独立运行目录，不覆盖业务库或历史 Trace；CLI trace 按配置读取并跳过损坏末行；界面标记真实 provider。
- 六例首条由“下周三”改为“后天”：2026-10-12 的下周三为 10-21，超出 7 天数据，不能伪造有票；原“下周三”仍可查，正常返回空。示例变更不涉及团队契约。
- 实际命令 `.venv/Scripts/python.exe scripts/smoke.py` 执行 run_demo、once、batch、标准输入驱动 chat、trace、Python 交接示例；均 exit_code=0。实际日志保存在 `docs/evidence/`（后续 Web 验证提交一并提交）。
- 输出 32 条 Mock trace，Python 示例用 label 显式区分正常与 6 种人为注入（label 在包装证据中，不改 Trace 契约）。
- B/C 影响：复制环境变量可隔离运行；示例可以直接复用；这不是 B 的正式方案和评分。
- 待完成：正式交接报告及人工屏幕验收；源代码 SHA 在后续记录登记。

CLI 模块提交：`78ea322a8f8addc75ef6c22c5d855d726dea11bb`。

## 2026-10-12 Web 与全入口验证

- 修改 `web/app.py`，新增 `tests/test_web.py`、`requirements-lock.txt`、`docs/evidence/*`；顺带澄清 `config.py`/`target/agent.py` 注释及 `target/providers.py` 他人订单拒绝分支（不改契约）。
- Web 每个浏览器独立 sid/Agent/变异字典，6 checkbox + 一键恢复，错误状态提示、完整 JSON、历史记录选择回放。适配已安装 Streamlit 的 width 参数。
- 实际命令 `.venv/Scripts/python.exe scripts/smoke.py`：12 个成员 A 自测通过，10 条运行/服务检查通过，32 条 Mock trace 保存。
- Web 首次测试路径错误（AppTest 相对调用文件解析）；改绝对项目内路径后通过。AppTest 实际发送购票、支付、退票、RAG、死循环，检查所有开关及恢复、JSON 回放；本地 Streamlit 服务 `/_stcore/health` 返回 ok。
- 真正启动 uvicorn，本地 HTTP 调用全部 8 工具均成功；`AGENT_USE_HTTP=1` 的 Agent 查/锁/下单/支付链路通过。
- 版本：Python 3.12.14；依赖实际版本见 `docs/evidence/verification.json` 与完整冻结文件，不冒充原计划版本。
- 契约/历史 Trace/原数据库 SHA256 与首次检查一致。Web 和 HTTP 临时服务验证后已终止。
- B/C 影响：Web 控件只影响对应浏览器会话；多个客户端仍共享固定模拟身份和配置数据库，不能作为生产权限系统。
- 限制：无真实模型 Key、无向量模型验证、未由人对浏览器画面/录屏验收；这些必须保持待验证。
- SHA：此模块提交后登记。

Web/验证模块提交：`8262db81838d45fe3d827d75ae8a4246a2304038`。

## 2026-10-12 正式文档、教学说明与交付核验

- 新增 `README.md`、`docs/development_summary.md`、`scripts/generate_handoff.py`、`docs/handoff/` 四份报告及来源清单；README 在用户补充说明后仍未出现在实际根目录，故补上快速运行文档，未覆盖已有文件。
- 报告生成器读取当前源码的工具 schema/AST 行号、线路/政策数量、Git 日志和实测 JSON/日志，拒绝引用哈希已变化的验证代码；明确 10 个顶层字段，保留契约完全不变。
- 包含 A/B/C 分工、关键代码与教学、真实 API 状态、隔离/恢复、完整 JSON 示例、8 工具参数及返回差异、C 验收取证/截图/视频分镜，以及有真实状态的检查表。
- 实际命令：`.venv/Scripts/python.exe -W error scripts/generate_handoff.py`、`.venv/Scripts/python.exe scripts/generate_handoff.py --check`；生成 4 份且 source_hash_check/contract_unchanged/report_check 均通过，32 条 Trace 的字段/顺序核验通过。
- 文档检查修复了生成器 Windows 字符串转义与控制字符校验、URL 被误识别为绝对磁盘路径的校验规则；最终 JSON 示例可解析，报告不含本机绝对路径或 Key。
- 待验证/未完成均如实记录：真实模型联网、向量、优惠/改签/身份完整建模、后台兑现、B 正式测试与 C 人工验收；不提供编造的覆盖率/性能/缺陷数。
- B/C 影响：可独立按手册跑 Mock 和保存证据，正式职责未被代做；最终判断有条件交接。
- 本模块最终提交 SHA：通过交付标签 `handoff-a-20261012` 用 `git rev-parse handoff-a-20261012` 精确取得；最终回复会给完整 SHA。避免在一个 Git 提交里自引用它自己的哈希。未 push/merge。

## 2026-10-12 用户要求建立 GitHub 仓库

- 范围：用户明确要求建立项目 GitHub 库；以已登录个人账号 `8xbAdx8` 下的私有 `ticket-agent` 为目标，上传现有功能分支，保持原交付标签。
- 文件：保留用户再次运行 smoke.py 的 `docs/evidence/` 修改；同步四份报告与 manifest；新增 `docs/github_handoff.md`，`.gitignore` 新增交付包目录排除。
- 实际检查：`gh auth status` 确认登录；`git remote -v` 为空；`gh repo view 8xbAdx8/ticket-agent` 未找到仓库；当前跟踪文件的常见私钥/令牌模式扫描未发现秘密。
- 用户提供的最新验证日志：12 个 A 自测 OK，verification.json 中所有运行项 exit_code=0，仍为 Mock，真实模型/向量均未实测。
- 报告同步验证：运行 `scripts/generate_handoff.py` 与 `--check` 核验当前源码/保护文件哈希、报告内容和 32 条 Trace。提交包含真实新日志，不覆盖或丢弃用户运行结果。
- B/C 影响：取得私有仓库访问权限后可 clone；须按 README 自建模拟库。邀请队友由用户决定，本次不代发。
- GitHub 创建/推送将在此提交完成后执行；结果和本阶段 SHA 由最终回复及远端分支确定。此前文档中的“未推送”是原交接阶段历史状态。
