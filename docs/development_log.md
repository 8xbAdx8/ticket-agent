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
