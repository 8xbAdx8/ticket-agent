# AI Test DSL Contract Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0；34项未跟踪/已修改工作区成果保留。未 reset/clean/checkout/stash；未 commit/push/merge/tag。

当前 Registry 11 个 `railway_*`，无 `railway_lock_seat`。V310 DSL 只接受：
`execution_adapter=v310`、`integration_steps`、真实工具/参数、`confirm(actor="test_user")`、`result./state./db./ui./metrics.` 检查。

本轮新增工具参数 schema 门控：未知参数、缺失 required、type/enum 不匹配均 REJECTED。DeepSeek 原始候选因 `from/to` 等非法参数被拒；Qwen 原始候选因 `name` 代替 `tool`、chat 无检查被拒。

`tests/test_ai_scenario_v310.py` 4 项 PASS；Mock V310 生成→V310Adapter 3 步 PASS。
