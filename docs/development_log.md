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
