# 已保存的 DeepSeek Live 原始证据

执行日期：北京时间 2026-10-16 00:12。生成请求 5 次、余额 GET 1 次；不是 MockTransport 桩。

- report.json：运行器保存的概要、用量、两个场景及事件。
- traces/traces.jsonl：2 条正常 Agent 契约记录。
- traces/deepseek_runs.jsonl：2 条完整应用事件记录，不含 reasoning_content/认证头。
- tickets.db：当次独立种子业务库，2,100 条虚构库存、0 锁、0 订单。仅作为只读核对快照，不替代项目 data/tickets.db。

本目录已有文件在审查时没有重写。README 是后加说明。原始文件 SHA256 与一致性结果见 [审查结果](../review-20261016/audit.json)。

当前 API 冻结，账本 5/5 已用尽。不要为了复核本目录而重跑在线脚本；只读回放即可。这里只验证两个只读工具，不代表八工具、100条用例、真实多轮或正式质量评价通过。
