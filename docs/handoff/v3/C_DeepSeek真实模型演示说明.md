# 只读质量修复后的最新说明（2026-10-16）

源码修复提交 `e216fdf57ec8f34b84134ba2b30b05e5d6ff5985`。请先看 [当前冻结交接](C_V3只读冻结演示说明_20261016.md)。两工具已有历史Live证据，其余六工具未开放；本轮102项A离线自测通过，新增API请求0，额度仍5/5。新提示词尚未联网回归；旧ZIP bff292cd是修复前版本。

下方保留前次审查/演示背景，其中“待修复话术”“过时标签”已由本轮离线修复，旧缺Key结论仅属于历史。

---

# 最新演示：2026-10-16 回放已验证 Live 证据

当前仅允许回放，不发API请求。请用 [C 已验证证据演示](C_DeepSeek已验证证据演示_20261016.md)，展示原始tool_calls、参数、结果、最终回复和Token；明确标注“真实Live历史记录离线回放”。仅query_tickets/search_policy通过，不演示Live下单或付款。

5次额度已用完，费用未知。Mock界面/动画不能作为实时Live证明，B正式成绩仍待提供。

---

## 历史存档：2026-10-15 演示安排原文

下面的在线Hello/发送方案现在禁止执行；当时“无真实成功”不代表10月16日审查后的状态。

# C：DeepSeek 真实模型演示说明

日期：2026-10-15（Asia/Shanghai）。分支 `codex/ticket-agent-deepseek-live`，已验证源码与证据提交 `d40b005ebdad2a57c8a09aa86d97911e1203f344`，接手基线 `85d457a4f34b4fad848ded4cf9c2d7334813c399`。本批文档会形成后续提交；最终 SHA 用 `git rev-parse HEAD` 获取。本轮未推送远程分支。

**真实 API 尚未验证。** 实际没有检测到可用环境密钥，生成请求 **0 次**，余额 HTTP 请求 **0 次**。连通性、密钥有效性、余额、实际返回模型 ID、真实 Function Calling 均跳过；真实 Token 为“不适用/未知”，本轮无 API 调用费用，不代表账户总账单为零。

**成员 A 开发交接状态：有条件交接。** A 的代码与离线验证可以交 B 接入回归；DeepSeek 实际效果和 C 的真实模型演示暂不能验收。A 不提供 B 正式成绩，不把 SDK 桩或 LangChain Mock 当作真实模型结果。

## 可以怎样介绍

模型像调度员，负责理解自然语言、选择“查余票”或“查政策”；LangChain 像流程控制台，负责调用 Python 工具并把结果送回模型；工具负责读取虚构票务数据和政策。最终文字、参数和执行记录可供测试。当前可以介绍代码和离线验证，不能说“真实 DeepSeek 演示已成功”。

报告中把数据来源分清：业务一直模拟；模型决策在 Live 下应来自 DeepSeek，在 Mock 下来自规则剧本。二者不同维度。当前新增 2 个 DeepSeek 只读工具的接入准备，旧系统 8 工具仍保留，不等于 DeepSeek 已实测全套订票。

## 部署与真实演示的两种安排

按 [B 的接入说明](B_DeepSeek真实模型测试对接说明.md) 配置环境和密钥。自动完整检查与现场演示**共用累计 5 次**，不能各运行一次绕过额度。

方案一：B 先运行完整检查，预计耗用 1+2+2 次。确认报告通过后，C 可以在网页历史回放中展示保存的真实 Trace，不再新调用模型。若需现场新问答，先取得额外预算授权。

方案二：为了在同一 5 次额度内录网页，先只运行 Hello 连通检查（1 次），然后在网页进行一次查询和一次政策咨询（通常各 2 次）。这也是实际验证，不是已完成结果。若模型多次调用或出错，应停下记录，不自动再试。

```powershell
.\.venv-deepseek\Scripts\python.exe scripts/check_deepseek_api.py --run --connection-only
# 使用 B 手册里的 DeepSeek 环境变量，且 DEEPSEEK_MAX_MODEL_CALLS=2。
$demoRun = Get-Date -Format "yyyyMMdd-HHmmss-ffff"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\deepseek-demo-$demoRun\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\deepseek-demo-$demoRun\deepseek_live"
.\.venv-deepseek\Scripts\python.exe data/seed.py
.\.venv-deepseek\Scripts\python.exe -m streamlit run web/app.py
```

此前已经用过生成请求时，剩余不足 5，不要重新开始完整演示。预算耗尽不能删除账本、换路径或改脚本继续试。

## 建议拍摄顺序与验收条件

1. 介绍界面左侧“DeepSeek Live · 只读”、deepseek-flash 和两个工具；不要拍环境变量或 Key 输入过程。
2. 输入“查明天上海到杭州的高铁二等座”。拍处理中提示、最终回复、余票卡片、右侧 query_tickets 和参数；卡片数据必须来自本轮工具结果。
3. 展开工具原始结果与完整 JSON，显示 provider、model、Token、耗时和成功标记；stop 不能单独作为业务成功证据。
4. 输入“锁座后多久必须完成支付？”。拍 search_policy、P11 等来源；本次不执行支付。
5. 展示历史回放、源码导览；说明它们不产生新的模型调用。引用 report.json/账本实际数值，不把离线截图数字搬到 Live 报告。

当前同步接口只有通用“正在处理请求...”动画，没有模型思维展示，也没有逐阶段实时事件。动画本身不是模型调用证据。遇到 missing key、401/402、超时或预算用尽，拍脱敏错误类别，保留报告和 Trace；不要拍后台原始错误正文、认证头或内部推理。

当前 `docs/evidence/deepseek/mock_browser_final` 的截图是 Mock 回归；`offline_sdk` 是 SDK 桩，均不能作为 DeepSeek 成功图片。真实模式拍摄要等合法密钥和实际成功。最终成绩由 B 提供，C 再完成作品介绍、验收和视频。
