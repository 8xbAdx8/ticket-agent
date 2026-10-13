# Ticket Agent V3 持续开发记录

日期按 Asia/Shanghai；所有验证为 A 自测，B/C 正式结论单独确认。

## 2026-10-13 审查与 V2 基线保护

- 读取 V3 用户任务书、README、依赖、config、contract、Agent/Provider/8 工具/Trace/RAG 与 V2 五份手册和证据。接手 HEAD f8b493ad13bcbf7d4814d798d2ef2f223373b1ac，工作区原来干净，包含标签之后的 Web 增强。
- V1 标签 e719956d7c82bd6392c25916d3c193be7e4b452e；V2 标签 6ef683a50f60970dbd4ded1678a818d026afcbde，均不移动。当前 Agent 为自研循环，项目 .venv 无 LangChain/LangGraph；B judge 与正式 V2 execution.jsonl 不存在，真实 API Key 未配置。
- 从最新 V2 建立 feat/a-ticket-langchain-v3。V2 核心文本和 99 个原文件 SHA256 保存至 docs/evidence/v3/v2_baseline/；原 DB/Trace/失败证据/旧手册不改写。
- 新增 scripts/snapshot_v3_baseline.py；实际运行 .venv/Scripts/python.exe scripts/snapshot_v3_baseline.py 成功。
- pip index 实际查询稳定版本：langchain 1.4.5、langchain-openai 1.7.1；对照官方 create_agent/middleware/checkpointer 文档。新增 requirements-v3.txt 和单独 .venv-v3，原 .venv 与 requirements-lock.txt 保留。
- B/C 影响：新增 engine 模式将保持旧返回字段，legacy 继续默认；最小原型先只接 query_tickets/search_policy，不把 V2 原循环包成框架节点。
- 官方资料：https://docs.langchain.com/oss/python/langchain/agents 、middleware/custom 、short-term-memory 。安装与原型验证结果在后续条目登记。
- 本阶段 SHA 在下一阶段登记。
