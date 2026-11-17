# 八工具 Live 模拟购票说明

2026-10-28。旧版本恢复点：`backup/pre-eight-tools-20261028`，SHA `fc35968000f2dd5f0610729c7ec02d6d743b7fc8`。本工作分支 `codex/live-eight-tools-20261028`。

## 启动与使用

双击 `启动_在线模式.cmd`，新建 DeepSeek 或 Qwen 会话。两模型请求真实 API，票务数据使用每个会话独立的模拟数据库。虚构的默认账户联系号码为 13800000001，乘客姓名仅用于模拟，勿输入真实个人信息。

建议逐轮操作：

1. `查明天上海到杭州的高铁二等座`
2. `帮我订明天上海到杭州G7301二等座，乘客张三`；在网页确认模拟操作。
3. 核对订单后发送 `支付刚才的订单`，再次确认模拟操作。
4. 可再请求 `查询我的订单` 或 `取消刚才的订单`，均为模拟操作。

八个工具为 query_tickets、monitor_seat、lock_seat、create_order、pay_order、cancel_order、query_order、search_policy。Live 的写工具只运行在新建、带标记的本地沙箱，不连接真实铁路、航司和支付系统。支付与取消仍需当轮明确授权和订单检查，订票不等于授权支付。真实模型 API 收费，单轮调用上限、超时与零 SDK 自动重试保留。

测试工作台选择 DeepSeek 或 Qwen 模拟票务模式，M2、M4 可勾选；M8 使用“运行并发订单对照（离线）”。M2 或 M4 被业务校验或调用上限终止时，属于实验结果，要结合 Trace 查看，不代表正常订单已成功。候补只是模拟任务，没有后台持续监控，也没有自动通知。

## 本轮证据

- DeepSeek 三轮完整流程：`artifacts/runtime/full-live-20261028/deepseek-338e3558/live-result.json`，实际查询、锁座、创建订单和模拟支付，SQLite 订单状态为 paid。
- Qwen 三轮完整流程及后续复验：`artifacts/runtime/full-live-20261028/bailian-5e5b396e/live-result.json`、`artifacts/runtime/full-live-20261028/bailian-8d2dc92f/live-result.json`。
- DeepSeek 模拟查订单、取消和政策检索：`artifacts/runtime/full-live-20261028/deepseek-38c51653/live-result.json`。其中政策检索工具实际成功，但模型添加了与先前退款相关的解释，后置忠实度检查返回 `rag_answer_inconsistent`；该轮没有完成，保留原始记录，不计通过。
- 实际候补工具：`artifacts/runtime/full-live-20261028/monitor-2ee97251/traces/`。模型说明模拟任务不会后台监控或自动通知。
- M2：DeepSeek `artifacts/runtime/full-live-20261028/skip_lock-be963ea8/traces/`，Qwen `artifacts/runtime/full-live-20261028/skip_lock-4d50c7c7/traces/`。无效锁座订单被拒绝。
- M4：DeepSeek `artifacts/runtime/full-live-20261028/infinite_loop-53c36f7a/traces/`，Qwen `artifacts/runtime/full-live-20261028/infinite_loop-fee948fe/traces/`。调用上限终止。
- 本机浏览器已实际完成 DeepSeek 查票、确认模拟下单、确认模拟支付，订单卡显示已支付；本次独立会话 Trace 在 `artifacts/runtime/v33/user/web-ad325d284a64/traces/`。另在浏览器确认 Live 实验室的 M2/M4 可选；Qwen 完整流程经 Python `Conversation` 实际验证。
- 离线全量主环境：`artifacts/runtime/full-live-20261028/offline-release/report.json`，710 通过、117 子测试通过、0 失败/跳过。随后界面修改追加针对性回归 40 通过、2 子测试。B 原有正式数据和断言未修改；A 的页面断言根据新标签作了兼容更新。

## 已知限制

自然语言模型不保证每次选择相同工具。票务字段的自动校验对不确定内容不会保证全语义正确；如果检测到明确错配，页面显示警告并以实际工具记录为准。政策忠实度规则可能把模型结合先前订单结果的说明判为无法通过；上述真实失败需后续进一步处理。监控和支付均为虚构；用户关闭会话后不保证自动恢复模型上下文。正式评分须成员 B 独立验收，不能声称无 Bug 或正式用例全部通过。

本轮实际真实模型生成请求：DeepSeek 37 次（输入 90,641、输出 3,958 Token），Qwen 20 次（输入 48,331、输出 2,180 Token）；以 `artifacts/runtime/full-live-20261028/usage/` 中的请求日志为依据。实际费用未知，Embedding 和 LangSmith 未用于本轮验证。
