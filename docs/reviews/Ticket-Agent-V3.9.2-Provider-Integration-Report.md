# V3.9.2 Provider Integration Report

## Implementation

| 文件 | 改动 |
|---|---|
| `target/v39/registry.py` | 仅允许 `mock/deepseek/bailian`；不再把所有非 Mock Provider 一律判为 `V39_LIVE_NOT_AUTHORIZED`。 |
| `target/deepseek_runtime.py` | `allowed_tools(full_sandbox)` 扩展为旧 8 + V3.9 11；保持 read_only 仅旧两工具。 |
| `target/bailian_runtime.py` | 继承 `max_output_tokens/max_tool_calls/turn_token_budget/max_payload_bytes` 环境配置；允许 full_sandbox 下 V3.9 工具。 |
| `target/live_providers.py` | full_sandbox 使用 6 个模型步、payload 64k、turn budget 32k。 |
| `web/v39_bridge.py` | 原始 UI 会话绑定 V3.9 Context/Service/EffectiveConfig；同一 Registry/业务服务/权限。 |
| `web/runtime.py` | 原版 `Conversation._send` 激活 V3.9 bridge；离线 RailwayDemoProvider；修复默认 Live 会话的费用 consent。 |
| `web/conversation.py` | 原版聊天结果区展示真实静态工具表，不只用模型转述；Live 发送设置 consent。 |
| `web/app.py` | 恢复原版 `user_page` 路由，不再进入独立铁路页。 |

## Shared contract

- 两个 Provider 使用同一套工具定义（旧 8 + V3.9 11）、同一 Registry、同一 V3.9 Service、同一写权限/确认。
- 模型仍只能创建 proposal；不能确认支付/退款/改签。
- `Baseline` 继续只保留旧八工具；V3.9 只在 Feature Flag + Context 下加入。
- 未把 Provider 失败静默降级为 Mock；API 错误显示。

## Limits

- Qwen/DeepSeek B 都完成了真实工具调用，但模型最终汇总的**班次数**与工具实际 40 班不一致；不能称 B 完整事实通过。
- Qwen 原版 UI 普通对话成功；Qwen UI 车次工具查询仍报通用错误。DeepSeek 原版 UI 普通对话成功；两者直接 Python A/B/C 均成功。
- 真实 API 货币成本接口未返回，`cost=null`，不编造。
- 未调用 DeepSeek Harness；Bridge 未启用。

## Status

`PROVIDER_IMPLEMENTED = YES`  
`LIVE_API_VERIFIED = PARTIAL`  
不是独立审查，不是 COMPLETE。
