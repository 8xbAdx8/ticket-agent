# C 端变更清单

以下清单以本轮开工工作区为起点。

| 文件 | 变化 |
|---|---|
| `target/scenario_v310.py` | 在既有执行器上增加受目录、引擎和变异白名单约束的隔离工作台入口，原 `run(case, *, fault=None)` 保留 |
| `target/scenario_workbench.py` | 新增五阶段流水线、现有 Provider 接入、QA-09 校验、AI Judge、同轮门禁与四份材料导出 |
| `target/scenario_workbench_evidence.py` | 新增当前会话快照、Trace 关联、脱敏和已执行检索证据提取 |
| `target/scenario_workbench_summary.py` | 新增唯一统计汇总、42 单元、双轨质量、分组变异和实测性能聚合 |
| `target/consistency_audit.py` | 新增四层状态关联，防止跨会话、跨订单、跨提案匹配 |
| `web/consistency_audit_view.py` | 新增五个板块渲染入口，复用现有组件和用户会话状态，使用专属运行指针 |
| `tests/test_consistency_audit.py` | 新增完整证据、缺失、冲突、串单和重复事件反例 |
| `tests/test_scenario_workbench.py` | 新增隔离双引擎、重复候选、越界引用、导出 SHA、页面门禁、真实 M8 探针和离线授权反例 |
| `docs/reviews/C-*` | 新增实施、差异、测试、回归、复核、整合请求和 SHA 文件 |

开工前已有的 `target/scenario_v310.py` QA-09 改动保留并作为本轮起点。`web/app.py`、`web/evidence.py`、`PROJECT_STATUS.md`、现有旧页面和 A/B 端文件以开工字节为准。开工现场已经缺失 `artifacts/deliverables/Ticket-Agent-AI-Test-V2-Independent-Review-20261109.zip`，本轮保留这一状态。专属运行与测试副本位于新增、已忽略的 `artifacts/runtime` 目录。
