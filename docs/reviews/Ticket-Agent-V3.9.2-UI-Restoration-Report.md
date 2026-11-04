# Ticket Agent V3.9.2 — UI Restoration Report

## 结论

原版 Ticket Agent 用户工作空间已恢复；V3.9.1 独立铁路页面不再是用户入口。V3.9 业务通过原版 Agent、原聊天区和右侧栏增量接入，没有重做 UI。

## 恢复依据

- `git show HEAD:web/app.py`：原版 `出行助手 → web.conversation.user_page()` 路由。
- `web/conversation.py::user_page`、`web/user_layout.py/css`、`web/presentation.py`：原版聊天主区、右侧 rail、确认卡、输入框。
- `docs/reviews/Ticket-Agent-V3.7-Phase5-UI-Redesign-Report.md` 与 `artifacts/runtime/v37-phase5-ui-redesign-20261101/`：原版四规格/交互依据。
- 当前 `web/app.py` 的 V3.9.1 分支仅是本轮之前未提交改动；未使用 `git reset/checkout` 整体回滚。

## 实际修改

1. `web/app.py` 恢复原版用户路由，不再调用 `web.railway_simulation.page()`。
2. `web/v39_bridge.py` 新增：在原有 `Conversation._send` 内绑定 V3.9 Context/Service/EffectiveConfig；右侧原 rail 追加铁路订单/待确认/政策。
3. `web/runtime.py` 增加 V3.9 bridge 激活及原版 Live 会话的费用 consent 修复。
4. `web/conversation.py` 在聊天结果区显示真实静态工具结果表，不只用模型转述。
5. `web/railway_simulation.py` 保留为未入口的开发页，不再作为用户主页面；默认 DB 改为独立 `v392-user`。

## 浏览器验收

`artifacts/runtime/v392-original-ui-browser3/`

| 规格 | 检查 | 页面错误 | 截图 |
|---|---:|---:|---:|
| 1600×1100 浅色 | 9/9 | 0 | 1 |
| 1600×1100 深色 | 9/9 | 0 | 1 |
| 390×844 浅色 | 10/10 | 0 | 1 |
| 390×844 深色 | 10/10 | 0 | 1 |
| **合计** | **38/38** | **0** | **4** |

检查：原版 hero/四快捷入口、右侧行程/订单/政策、铁路 rail、模型设置、无独立铁路标题、无“咨询与演示业务/全国铁路模拟出行” radio、静态车次经 Agent 返回、真实工具结果表、手机信息开关、无横向溢出。

离线查询结果：真实 GTFS `FOUND`，工具返回 20 行（UI 默认 limit），G531/G547/G1 等来自阶段八静态库；不是模型编造。

## 未完成

- Qwen 原版 UI 普通对话成功，见 `v392-live-ui-qwen-hello.png`；Qwen UI 车次工具查询仍报通用错误，直接 Qwen API A/B/C 已另行验证。
- DeepSeek 在原版 UI 选择后完成一次真实 API 普通对话，见 `v392-live-ui-deepseek4.png`。
- 原版 UI 的完整 3 人退改签浏览器流程未在 Live 模式下执行；V3.9 业务由测试/SQLite 探针覆盖，不能把 UI 查询截图当交易验收。
