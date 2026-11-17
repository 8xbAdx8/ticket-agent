# 成员 A：V2 最终交付清单

生成日期：2026-10-13（Asia/Shanghai）。分支：`feat/a-ticket-v2`。
经过回归的源码提交：`1804518c9a312ec0d4ab8cb000124e37ee551887`；本手册是该源码之上的文档提交。
最终交付提交用 `git rev-parse HEAD` 确认；交付标签计划为 `handoff-a-v2-20261013`，仅在检查通过后建立，解析标签可得到最终 SHA，避免文档声称包含自身的提交哈希。
V1 标签保留：`handoff-a-20261012` → `e719956d7c82bd6392c25916d3c193be7e4b452e`。
所有运行结果均为 A 自测；业务虚构。成员 B 报告的 V1 95/100 是其提供的结论，A 未获得完整 judge/用例/原始 execution.jsonl，不能宣称 V2 正式 100/100。


## 已有可核查的交付

- [x] 保留 V1 标签、源文档/开发记录、原库/Trace、B 原始资料；25 文件哈希核对通过。
- [x] 独立 V2 分支，五缺陷分别提交，不修改/合并主分支。
- [x] DEF-01 kind/席别一致性；DEF-02 双向切换与上下文；DEF-03 库存分类回复。
- [x] DEF-04 duplicate_pay 提示且业务幂等不变；DEF-05 政策与明确写请求区分。
- [x] 原入口 Agent().chat 与 10 顶层/5 calls 字段、finish_reason/tool_sequence 语义兼容。
- [x] 8 工具实现保持，Schema 对比一致；query kind/seat 不兼容用既有 error 拒绝。
- [x] Mock/SQLite 虚构业务、默认政策检索及引用，原 CLI 全入口与 HTTP 8 工具冒烟通过。
- [x] Web AppTest 对话/回放/变异恢复、本地 health 启动通过。
- [x] 六缺陷注入仍可复现，恢复后正常政策引用通过。
- [x] 13 新缺陷自测、3 新 SDK 桩自测，连同 V1 12 共 28 自测通过。
- [x] 10 项冒烟检查，32 条独立 Mock Trace；五项 A 对照目标符合。
- [x] 已运行的原 Python API 四轮示例及完整 JSON/JSONL。
- [x] Python/依赖冻结与 PowerShell 独立运行说明；seed 默认拒绝覆盖。
- [x] 真实模式配置/显式验证入口与无 Key 预检；真实 Trace 0 条，未冒称联网验证。
- [x] V2 持续开发记录、A 报告、B 对接、C 演示、V1/V2 对照和本清单。
- [x] 文档由实际代码/Git/证据生成，声明 A/B/C 责任和未完成边界。

## 仍需确认或未完成

- [ ] B 正式 100 条 V2 回归结果、测试指标、缺陷关闭判定；95/100 是 V1 的 B 报告值。
- [ ] B 五个 xfail 的更新与 XPASS/统计规则核查。
- [ ] DEF-03 “建议查询”与 B 正式 F14 期望口径最终确认。
- [ ] 合法 API Key/端点/模型配置及 7 类真实模型验证，模型 Prompt 遵守效果待验证。
- [ ] 可选向量 RAG 实测；生产认证、持续候补、真实票务/资金/实际改签（未在本轮范围完成）。
- [ ] C 人工验收、真实截图、5—10 分钟视频与依据 B 成绩的最终参赛报告。
- [ ] 三人共同确认最终验收；A 自测通过不等于团队验收签字。

## 文件、证据与 Git 定位

V2 运行核心 target/providers.py / tools.py / agent.py；其余 mock_core、rag、trace、CLI、Web 和 seed 沿用原实现。测试新增 tests/test_v2_defects.py / test_v2_provider.py；执行和生成脚本位置见 A 报告。接口契约为未修改 docs/contract.md。
分支 `feat/a-ticket-v2`；已验证源码 SHA `1804518c9a312ec0d4ab8cb000124e37ee551887`；最终完整交付 HEAD 由标签 handoff-a-v2-20261013 解析（检查通过后建立）。V1 原标签 `e719956d7c82bd6392c25916d3c193be7e4b452e` 不移动。
B 材料：B_V2测试对接说明.md、原 contract、api_example、defects 对照、regression 原 Trace 和连续开发记录；B 的正式 judge/cases 未混入。
C 材料：C_V2验收演示说明.md、A 技术报告、对照和可回放 Mock Trace；录屏分镜是建议，尚未制作。

| 证据 | 实际路径 |
|---|---|
| V1 文档/日志快照与保护清单 | docs/evidence/v2/v1_snapshot/ |
| V1 五问题 A 原复现 | docs/evidence/v2/v1_reproduction/ |
| V2 五修复 A 实际复现 | docs/evidence/v2/v2_reproduction/ |
| 28 自测与 10 冒烟/32 Trace | docs/evidence/v2/full_unit.txt、regression/ |
| 原 API 四轮真实 Mock 示例 | docs/evidence/v2/api_example/ |
| 无 Key 真实预检 | docs/evidence/v2/real_preflight/preflight.json |
| 保护/源码/Schema/六变异一致性 | docs/evidence/v2/audit_first.json；后续 final 审计另存 |

已知限制详见 A/B 手册：Mock 有限语法、旧库日期窗口、预览截断、stop 不等于成功、会话重置不恢复库存。尚无 B 的 V2 新缺陷清单，不能写“零 Bug”。交接文档自身不重复运行核心测试，只有源代码变化才需重跑。

成员 A 开发交接状态：**有条件交接**。B 可开始正式回归，C 可开始 Mock 验收/演示；远端真实模型验证、正式成绩和最终验收未完成。
