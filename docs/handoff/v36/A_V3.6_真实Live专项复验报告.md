# V3.6 真实 Live 专项复验

在 `artifacts/runtime/v36-stabilization/live/` 创建独立模拟会话，关闭 LangSmith 自动上报。两个 Provider 各完成 query_tickets、用户确认后 lock_seat、create_order、pay_order 和政策检索；订单、库存与支付均模拟。

- DeepSeek 订单与政策路径：`deepseek-full-summary.json`；Qwen：`bailian-full-summary.json`。真实 API 发送及响应记录见各隔离会话 `traces/`。此前跨轮锁座审计在生成时仍判 fail，历史记录保留；后续代码改成缺少跨轮时序证据时 indeterminate，仅离线验证，尚无修复后 Live 对照。
- DeepSeek 用户取消锁座前后数据库 locks 均为 0，二次取消因无待确认被拒；详见 `deepseek-cancel.json`。Qwen 取消场景在确认前因工具参数错误终止，尚未验证取消，勿标通过。
- 两模型查询不存在订单返回工具失败；DeepSeek 对不存在的锁座查询曾提出不相关锁座提案，未执行；Qwen 自动候补能力问题出现 RAG 拦截。见 `*-queries.json`。
- 最后一次新增 RAG 订单 ID 绑定修复没有再做真实复验；历史回复和 Trace 不覆盖。
