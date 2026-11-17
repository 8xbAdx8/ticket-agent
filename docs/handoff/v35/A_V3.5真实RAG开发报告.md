# A · V3.5 真实RAG开发报告

日期：2026-10-26；分支feat/ticket-agent-v35-qwen38-rag。结论：**有条件交接**。真实Embedding、持久化Chroma、真实检索、Qwen3.8-Flash查票闭环及两次RAG生成已执行，全面质量评价仍由B独立验收。

## 一、基线与版本边界

实际恢复点9f4ab1eb3f34242ff6bc0e8c147c0577263d893a，原分支codex/ticket-agent-v341-answer-integrity；仅用户原ZIP未跟踪。3707个原文件哈希保护，包括旧数据库、Trace、B证据、契约、预算和用户ZIP。未改main、旧标签或原始真实回复。

| 验证/模块 | 源码提交 |
|---|---|
| Embedding/Chroma基础及真实索引 | 17889d9 |
| 固定30问题与真实检索评估 | 0563d4e |
| Qwen真实查票FC（2请求） | 07f36ff |
| 修复本地导入并接续两项RAG生成 | 163c18e079a00a400a567f378c0096cf1e066db1 |
| 隔离RAG变异与前端 | 19294d3 |
| 首轮完整离线验收源码（389项） | bf03b3db8ceabecb40fd56964c0e4ef62a0d419d |
| 固定Qwen预算入口与最终完整离线验收源码（390项） | d2812b9e058b3f627cac8009c2bc7cc02d47a6f8 |

之后是交付文档/证据提交，以git rev-parse HEAD获取最终SHA。不把最终离线/UI源码说成全部已重新Live测试。完整证据索引docs/evidence/v35/summary.json，过程docs/v35_development_log.md。

## 二、实际实现与原理

### 真实模型与独立Embedding

生成默认模型改为qwen3.8-flash，复用原ChatOpenAI兼容适配器、DASHSCOPE_API_KEY和可配置地域Endpoint。显式旧DASHSCOPE_MODEL仍供旧CLI兼容；网页选择Qwen3.8-Flash时显式选新模型、走V3.5独立预算，不把旧qwen-plus结果改名，不自动回退旧模型/Mock。DeepSeek保留，但本轮没有新DeepSeek请求。

新增target/embeddings.py，独立调用/embeddings，默认text-embedding-v4、1024维、每批最多10文本；文档与查询分开缓存。每HTTP尝试先持久化预留额度，错误也消耗；零重试，未知费用/用量保持未知。API只负责真实数值向量，不生成聊天回复。MockTransport返回的向量永远标offline_stub，与real_api缓存隔离。

### Chroma知识库

新增target/rag_store.py：解析原data/policies.md的15条政策，450字符切片、50重叠，本次短政策各一个切片；稳定doc_id/chunk_id、内容版本、source、title保留。真实向量写本地Chroma，保存Embedding模型、维度、语料哈希、切片参数、索引版本和原回执。默认重用有效索引，不在导入/页面刷新时重新向量化。

变更语料/模型/维度时拒绝混用并要求显式重建；文本未变时复用按模型/维度/Endpoint/正文/来源隔离的缓存，只嵌入新增内容。重建创建新集合并归档旧manifest，不删除旧集合。缺失/损坏/空/维度冲突/缺依赖均明确报错。正常目录：artifacts/runtime/v35-rag/index/；缓存embedding-cache.db同父目录。

### 三种检索与Agent

keyword保留原Mock默认；显式新检索入口支持Keyword、真实Vector和Hybrid。Vector按cosine最低0.35过滤，Top-K默认3、按doc_id去重；Hybrid用RRF(k=60)按两组排名融合，不拼接列表。分值类型不同，不能当统一置信概率。

target/rag_service.py保留search_policy(question)及question/hits/count结构，在独立rag_runs.jsonl记录完整检索证据、模式/版本/分数/来源/阶段耗时和Trace关联。新Live向量错误不降级关键词；原Mock默认路径不变。票价/车次/库存继续query_tickets结构化查库，RAG只管政策。

LangChain工具路径对DeepSeek/Qwen共用，原模型文字与引用ID检查单独落盘，错误引用可拦截。ID合法不等于来源支持整句。提示注入/明显过时/冲突的有限规则可报告风险，不能宣称覆盖所有攻击或政策冲突。

### 八种新RAG变异与前端

新增rag_missing_doc、rag_conflicting_doc、rag_stale_doc、rag_wrong_citation、rag_low_similarity、rag_prompt_injection、rag_empty_index、rag_embedding_error。均显式执行在隔离Chroma副本，保留前后证据和独立判定，使用标注的桩向量，不污染正常真实索引。原八变异没有增删或重写。

Streamlit新增RAG知识库页：真实索引与预算状态、可执行三模式检索/增量构建、文档来源/排名/分数/正文、30问题指标、真实生成回放、独立延迟、离线RAG变异及原JSON/历史功能。正常刷新不调用API。Qwen4/4已满，不能为演示自动再生成。窄嵌入视口侧栏可能遮挡内容，建议外部宽窗口；当前不宣称所有响应式尺寸都通过视觉验收。

## 三、真实验证结果

### A/B：Embedding、持久化与30问题

索引15文档/15切片，模型text-embedding-v4，维度1024，索引版本242aa8199c4a8393ded29751。真实建库2请求，30个固定问题批量向量化3请求，共5/8。已重新打开Chroma核验；逐文档原始API向量哈希与请求输入哈希、回执及Chroma浮点结果对应，最大误差小于1e-6。完整原始向量导出real-index-export.json，可检查来源，不是随机或哈希向量。

固定数据集cases/rag_quality_v35.json在真实评估前提交，SHA256为375a751649d6bcebe43102dd2c80c28ec95d073375ea651d6a8674db4987b6f9。30问题：26有答案、4无答案，Top-K3、阈值0.35。

| 模式 | Recall@3（26） | MRR（26） | 无答案仍召回（4） | 检索异常 |
|---|---:|---:|---:|---:|
| Keyword | 0.980769 | 0.923077 | 4/4 | 0 |
| Vector | 1.000000 | 1.000000 | 3/4 | 0 |
| Hybrid | 0.980769 | 0.923077 | 4/4 | 0 |

这证明本次固定集合的检索结果，不代表最终回答准确率。无答案误召回明显，Hybrid未优于Vector，原结果如实保留，未在看到成绩后调阈值或改预期。多文档Recall按预期ID召回比例，MRR取首个相关文档排名倒数；无答案不计Recall/MRR分母。

### C/D/E：真实Qwen生成

查票Agent Trace185e0fd83d424db2ae6985b776512feb：模型实际请求query_tickets，Python查询独立SQLite，工具结果按call ID回传，模型第二次回答。输入日期2026-10-27上海→杭州高铁二等座，三车次G7301/G7302/G7303时刻06:00/09:17/12:34，票价均73、库存35/47/51；原回复与工具一致，未执行写操作。整轮6539ms。

政策RQ01：使用真实Vector预取证据单次生成，“15分钟，过期未支付释放库存，依据P11”，输入590/输出36，3654ms。无答案RQ26：“无法确认”，说明P01/P07/P09均未涉及保险理赔，输入652/输出59，3333ms。两项都是实际qwen3.8-flash响应。

总生成4/4：FC2次+直接RAG2次。**真实search_policy工具的Agent完整往返没有另测**，该工具整合通过两个Provider的实际SDK离线桩；不能把预取证据单次生成冒称又做了政策工具Live闭环。DeepSeek同证据真实生成未执行。

初始脚本在完成FC后从错误模块导入tracing_context，发生本地ImportError；保留原2次请求、Trace、标记及控制台错误。修为现有langsmith.tracing_context并前置导入，仅接续尚未尝试的RQ01/RQ26，共享同一个4次账本，不重跑FC、不重置、不重试。

初始机械评分误将拒答的否定范围引用当作正向引用，原generation-result.json评分保留。修复判定器并新增正反例，不改数据集/原回复；generation-assessment-review.json离线复核：两样本引用ID均合法、1个无答案样本明确拒答，业务错误按该窄规则0，**全文答案忠实度和引用支持度仍indeterminate（2个）**，需B独立复核。不能宣传整体100%正确率。

## 四、请求、Token和费用

独立授权根artifacts/runtime/v35-qwen38-rag/authorization-20261026/。Embedding账embedding.db固定8，生成账generation.db和generation-total.db固定4；生成四条按同UUID逐项一致。原V3.4的4/4、正式5/5不变。

| 类别 | 实际请求 | Token | 自动重试 | 实际费用 |
|---|---:|---|---:|---|
| Embedding | 5/8 | 输入/total1122，无生成输出 | 0 | 未知 |
| Qwen生成 | 4/4 | 输入3205、输出413 | 0 | 未知 |
| DeepSeek / LangSmith | 0 / 0 | 本轮未调用 | 0 | 无新增此类调用 |

生成request_id是项目稳定ID，服务端ID未捕获时为未知，不冒用LangChain run ID。HTTP间隔可由记录时间戳推导，模型/案例阶段耗时单独记录，不混作纯网络耗时。用量有真实接口依据，但无可靠账户账单/费率证明实际费用，不能写成免费。Embedding余3次未自动使用，生成额度已耗尽。

## 五、实际回归与文件

新增35项A自测，原355项保留；A原test_live_provider_ui.py仅把旧Bailian标签改为新模型标签，未改变缺Key/隔离/不联网的判据。B正式用例、B原报告和八变异代码不改。

| 环境 | 收集 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|---:|
| .venv-v35 | 390 | 390 | 0 | 0 |
| 原DeepSeek环境 | 390 | 377 | 0 | 13 |
| 原V3环境 | 390 | 308 | 0 | 82 |
| 原V2环境 | 390 | 212 | 0 | 178 |

原smoke、八变异25记录/8标注、新RAG8项均通过。离线总入口scripts/verify_v35_offline.py剥离Key并阻断外部Python网络；网络尝试0、真实请求0，最终3815个回归保护文件未变。首轮389项及其3722个文件检查原件保留；初始3707文件另核验未变。最终结果见docs/evidence/v35/offline/final-guards/report.json。不同环境重复收集不累加为成绩。

新增核心文件：target/embeddings.py、rag_store.py、rag_service.py、rag_quality.py、rag_faults.py；scripts/rag.py、rag_eval.py、verify_v35_live.py、verify_v35_offline.py；web/rag_page.py；cases/rag_quality_v35.json；四个test_v35*.py；requirements-v35.txt/lock。现有rag/配置/模型注册/LangChain/界面与启动器作兼容增量。Python3.12.14、Chroma1.5.9；其余原锁定版本保留，pip check通过。

## 六、未完成和交接

已真实验证：Embedding/Chroma/Vector/Hybrid、Qwen查票闭环、基于真实检索的政策回答与拒答。已离线验证：工具RAG接入/错误引用停止、旧兼容、8种新故障、缓存/预算/异常、前端按钮与证据。

仍待B独立确认：无答案误召回改善；Hybrid融合与阈值泛化；政策变更/冲突/注入有限规则的误报漏检；自然语言忠实度；30问题以外的样本；多轮真正Live；DeepSeek同证据对照；search_policy Agent真实完整往返；不同账号地域、并发索引更新与缓存损坏恢复。后置风险/评分/UI修复只离线验证，无剩余生成额度做新Live复验。

独立环境不修改旧venv，但团队需安装Chroma依赖；索引/cache是运行产物而非提交密钥。完整真实向量快照与证据已交付，可离线审查，正式重新建库/生成必须显式授权且受预算限制。成员A开发交接状态：**有条件交接**。

最终本地安全核对在内存比对3个已配置密钥，未发现待交付文件含这些秘密；检查JSON/JSONL无认证头或内部推理内容，3707个初始保护文件未变，原测试只允许A界面标签的精确替换。完整结果security_review.json、逐文件哈希evidence_index.json可复核。精确匹配不能证明所有未知秘密不存在，不把安全检查当全项目绝对保证。
