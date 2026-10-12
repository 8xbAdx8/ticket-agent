# Ticket Agent V2 开发记录

日期使用 Asia/Shanghai；记录真实执行，区分 B 的报告结论与 A 的实现自测。

## 2026-10-13 接手 V1 与 B 资料

- 分支起点：`30b21da57f432677d8e12cd76e24a8e0895c35f3`，建立 `feat/a-ticket-v2`；原标签 `handoff-a-20261012` 保留在 `e719956d7c82bd6392c25916d3c193be7e4b452e`。
- 工作区原来仅有两份新提供的未跟踪资料：根目录 `B_缺陷分析报告.md`、`B的总结_测试层.docx`。原样保留，Word 仅只读提取正文。
- 阅读契约、Agent/Provider/工具/业务/RAG/Trace、V1 四份交接手册。与 V1 标签对比 `target/`、config、seed、policies 无差异。
- B 报告声明 100 用例 95 通过/5 失败，DEF-01..05 为 F03/M11/F14/F13/T25；此为引用 B 的结果，不是 A 重跑确认。
- 实际目录检查未发现 `judge/`、`results/execution.jsonl` 或 B 的测试用例；不运行不存在的 judge，不改 B 断言。
- 配置检查只输出是否存在 Key：当前无 API Key，provider=mock。真实模型仅准备接入/验证脚本，联网待验证。
- 新增 `scripts/reproduce_v2_defects.py`：按 B 原输入在五个独立库和 Trace 路径复现；业务日期冻结 2026-10-13，用于可比的 V1/V2 观察，不代表 B 完整回归。
- B/C 影响：契约、原证据/数据库/Trace 不动；原始 B JSONL 不在仓库，后续需 B 提供或独立运行。
- SHA：基线准备提交后在下一条记录登记；每个缺陷另行提交。

- 实际复现命令：`.venv/Scripts/python.exe scripts/reproduce_v2_defects.py --output-dir docs/evidence/v2/v1_reproduction --label v1-before-fixes`；五个 A 观察目标均未满足（0/5），成功复现 B 描述的五个现象。每个场景独立模拟库，原始 Trace 追加至独立子目录；观察 JSON 包含实际输入/参数/回复。
- V1 证据和手册另存只读快照 `docs/evidence/v2/v1_snapshot/`；manifest 保留契约、原库/Trace、开发记录、原始 B 资料与 V1 文档哈希。不会将 A 复现 Trace 冒称为 B 的原始执行 JSONL。
