# V3.5.1 持续开发记录

## 2026-10-26 基线与冻结数据

- 实际基线1b3b6677c571344a35cd344044f5362a90ad88e1，原分支feat/ticket-agent-v35-qwen38-rag；仅用户原docs/showcase/v3展示.zip未跟踪。创建独立feat/ticket-agent-v351-rag-quality，不重写提交或标签。
- 原政策、30题、390项既有测试、历史数据/证据/预算等3862文件建立SHA256保护快照，位于artifacts/runtime/v351-work/protected.json。旧Embedding5/8、Qwen生成4/4保持不变。本轮没有模型、Embedding或LangSmith在线授权，所有验证限定离线。
- 新增两个独立数据文件：开发集24题（16负样本、8正向控制）；保留集24题（16负样本、8正向控制）。独立于原30题，先冻结再进行开发集参数选择；保留集不可用于调参。新问题没有真实查询向量，不能将后续关键词/证据门控成绩冒充新的真实Embedding成绩。
