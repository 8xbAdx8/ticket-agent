# C 端整合请求

## 主应用导航

涉及 `web/app.py` 的测试控制台路由。由整合者按 B → A → C 顺序接线。在集成提交中从 `web.consistency_audit_view` 导入下表函数并保持原形参。测试场景生成、历史实验室、模型对比、Trace 和集成中心的底层接口及 B 历史数据继续保留。旧静态入口的移除或归档由整合者统一完成。

| 新导航 | 调用 |
|---|---|
| AI 场景总测试 | `competition_page(sessions)` |
| 质量分析 | `quality_page(sessions)` |
| RAG / 多轮 / 安全 | `rag_page(sessions)` |
| 边界与异常测试 | `lab_page()` |
| 性能测试 | `trace_page(trace_dirs)` |

验收时从主应用打开一个用户会话，选定一轮测试，验证五个页面只展示同一 `run_id`。空、失败、换会话和损坏证据时验证结果门禁。确认原有 B 端 Trace 调用 `show_record` 和正式历史入口仍可用。

## A 端四层取证

涉及 `web/conversation.py`、`web/business_actions.py`、实际订单展示组件。已能读取数据库核验回执和可信运行事件。还需要由 A 端在实际生成 Agent 订单状态声明和实际渲染 UI 订单状态的边界分别记录 `agent_order_state_declared`、`ui_order_state_rendered`，字段包括 `event_id`、`session_id`、`run_id`、`operation_id`、`order_id`、`proposal_id`、`order_status` 和事件时点。Agent 事件必须关联来源轮次，UI 事件须关联实际操作并反映显示值。只有业务状态确实被声明或渲染时才发事件。原公共 Trace 和业务数据结构继续使用现有契约。

影响功能准确性、工具调用、多轮与安全。验收同会话多订单、同订单多操作、不同会话和否定文本，再贯通支付、回执与真实页面渲染。旧运行无关联字段时保持无法判定。

## 评委环境与真实模型验收

当前 D 盘缺少 `scripts/evaluator_entry.py`。团队 ZIP 的评委入口有重复 `--mode` 覆盖风险，打包脚本 `--force` 对工作区祖先路径保护不足，现有 manifest 未覆盖全部归档条目。由整合者在独立评委副本修正、复核并运行 `--check-only`。C 端未执行或重建交付包。

真实模型验证需要批准新的 C 端验收批次。先分别验证 DeepSeek 和 Qwen 生成与评判的真实请求、Token、完整响应证据和失败处理，再评估将现有 `scenario_live_agent`、`LiveBatch` 纳入被测 Agent 的在线路径。本轮隔离执行仍使用原有离线 Agent。阶段性验收还需要主导航后真实浏览器检查，以及按授权的同批用例采集 M1–M7 的实际触发、RAG 可判定样本、安全攻防和资源数据。

本轮遵循 C 端冻结清单，项目状态文件更新由整合者在集成后办理。
