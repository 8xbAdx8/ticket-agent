# V3.5.1 持续开发记录

## 2026-10-26 基线与冻结数据

- 实际基线1b3b6677c571344a35cd344044f5362a90ad88e1，原分支feat/ticket-agent-v35-qwen38-rag；仅用户原docs/showcase/v3展示.zip未跟踪。创建独立feat/ticket-agent-v351-rag-quality，不重写提交或标签。
- 原政策、30题、390项既有测试、历史数据/证据/预算等3862文件建立SHA256保护快照，位于artifacts/runtime/v351-work/protected.json。旧Embedding5/8、Qwen生成4/4保持不变。本轮没有模型、Embedding或LangSmith在线授权，所有验证限定离线。
- 新增两个独立数据文件：开发集24题（16负样本、8正向控制）；保留集24题（16负样本、8正向控制）。独立于原30题，先冻结再进行开发集参数选择；保留集不可用于调参。新问题没有真实查询向量，不能将后续关键词/证据门控成绩冒充新的真实Embedding成绩。

## 模块一：可确定事实的忠实度检查

- 数据冻结提交3dc33b8。新增target/rag_faithfulness.py、cases/rag_faithfulness_v351.json及A专项test_v351_faithfulness.py。只依据实际传入的工具证据：逐句定位来源、数值单位与条件绑定、缺失/错误引用、额外期限费用限制、无证据断言、冲突披露和实际执行事件。
- 对用户明确引用与否定来源单独识别；自动检查有限、全文语义忠实度始终indeterminate，不用局部数值通过当整段正确。原模型文字与字段级依据均保留，失败时不替换为成功回答。
- 实际离线pytest专项57项通过，0失败、0跳过。最初整合联调81项通过（含新检索与两模型SDK及原4项工具RAG测试）；未发送真实HTTP/Embedding/LangSmith请求。B原正式断言未改。
