# V3.5.1 持续开发记录

## 2026-10-26 基线与冻结数据

- 实际基线1b3b6677c571344a35cd344044f5362a90ad88e1，原分支feat/ticket-agent-v35-qwen38-rag；仅用户原docs/showcase/v3展示.zip未跟踪。创建独立feat/ticket-agent-v351-rag-quality，不重写提交或标签。
- 原政策、30题、390项既有测试、历史数据/证据/预算等3862文件建立SHA256保护快照，位于artifacts/runtime/v351-work/protected.json。旧Embedding5/8、Qwen生成4/4保持不变。本轮没有模型、Embedding或LangSmith在线授权，所有验证限定离线。
- 新增两个独立数据文件：开发集24题（16负样本、8正向控制）；保留集24题（16负样本、8正向控制）。独立于原30题，先冻结再进行开发集参数选择；保留集不可用于调参。新问题没有真实查询向量，不能将后续关键词/证据门控成绩冒充新的真实Embedding成绩。

## 模块一：可确定事实的忠实度检查

- 数据冻结提交3dc33b8。新增target/rag_faithfulness.py、cases/rag_faithfulness_v351.json及A专项test_v351_faithfulness.py。只依据实际传入的工具证据：逐句定位来源、数值单位与条件绑定、缺失/错误引用、额外期限费用限制、无证据断言、冲突披露和实际执行事件。
- 对用户明确引用与否定来源单独识别；自动检查有限、全文语义忠实度始终indeterminate，不用局部数值通过当整段正确。原模型文字与字段级依据均保留，失败时不替换为成功回答。
- 实际离线pytest专项58项通过，0失败、0跳过（55个固定fixture与3个边界/作用域检查）。最初整合联调81项通过，后续补不同政策类别数字误用反例；未发送真实HTTP/Embedding/LangSmith请求。B原正式断言未改。

## 模块二：检索范围与Hybrid修复

- 忠实度模块提交6d5ba51。原30题90组结果逐项复核，真实RRF(60)与余弦均能重构；归一化/距离方向无明显错误。Hybrid等权排名同分和关键词单路噪声复活导致劣化，不将其归咎于API。
- 新增target/rag_relevance.py：有限政策主题/交通范围、知识库未提供的请求属性与个人条件缺失检查，保留候选及拒绝原因。Hybrid仅融合向量阈值合格候选，范围过滤后重排，固定向量权重0.7/关键词0.3、RRF60。向量阈值仍0.35，不为追成绩极端提高。
- 原PolicyIndex低层默认v35以兼容历史调用；显式新rag_service默认v351，旧Mock未设AGENT_RAG_MODE时保留原实现。新版Live入口显式hybrid/v351/cache-only，不自动嵌入新查询。CLI提供显式quality-profile，原评估原件不改。
- attach_answer整合字段级忠实度；错引沿用rag_wrong_citation，其余明确不一致报rag_answer_inconsistent，保存原回复和失败旁证、不伪造成功公共Trace。未知语义保留indeterminate。
- 实际pytest检索/原索引与原Agent RAG39项通过；开发集三候选阈值均保留8个正向控制并拒绝16个负样本，保守选0.0。原30回归发现“还能退吗”省略退票漏识别，保留初次结果，修复自然语言省略后复核：Keyword Recall0.980769/MRR0.961538，Vector/Hybrid均1；无答案三路0/4。这是缓存真实向量离线重放，不是新的Live验证。保留集仍未评分，冻结本模块后执行一次。
