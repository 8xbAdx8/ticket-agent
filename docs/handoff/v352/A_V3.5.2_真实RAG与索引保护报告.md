# A · V3.5.2 真实RAG与索引保护报告

更新：2026-10-26。分支`feat/ticket-agent-v352-rag-live-eval`；V3.5.1基线`07efcd513b89f7f4698e4e73a297e3abcad5476e`。成员A负责实现和本模块自测，B负责正式质量评价，C负责验收和演示。**有条件交接：真实双模型协议闭环及48题三模式已完成，全文语义忠实度仍需B独立复核。**

## 1. 实际完成状态

| 功能 | 状态与证据 |
|---|---|
| 原Chroma不可变保护 | 【已实现并验证】原路径直接open/build拒绝，读取/回归用独立UUID副本，源前后hash；3933原文件未变 |
| 旧三文件事件调查 | 【已实现并验证】副本复现SQLite初始化写入、首次读取HNSW写入；旧事件不删除/恢复 |
| 新48题三模式 | 【已实现并验证】5次真实Embedding补齐48条向量，Keyword/Vector/Hybrid各48题实际执行 |
| Qwen真实政策工具往返 | 【已实现并验证】2次HTTP200，实际qwen3.8-flash，search_policy/Chroma/ToolMessage/最终回复完整 |
| DeepSeek相同证据往返 | 【已实现并验证】2次HTTP200，实际deepseek-flash，相同问题、Prompt和政策证据hash |
| 逐句引用/数值/版本检查 | 【已实现并验证】有限规则及异常测试通过；两份实际回答全文判定均indeterminate |
| 全文语义忠实度证明 | 【部分实现】确定性检查之外交B人工复核，不提供模型总体准确率 |
| Web证据回放 | 【已实现并验证】无运行目录时也优先读公开本轮证据；页面不请求API |
| 更多Live无答案/冲突/多轮案例 | 【尚未实现】本轮未执行相应Live验收，原有离线能力不等于新真实成绩 |

## 2. 原索引事件与保护原理

原V3.5.1三文件字节变化现状保留，未自动恢复。独立副本分阶段取证观察到：初始化改写chroma.sqlite3；首次取文档/向量改写data_level0.bin和length.bin；随后query、关闭和显式checkpoint未再改变字节。journal_mode=delete，未观察到WAL/SHM，checkpoint=[0,-1,-1]，build调用0。15文档的ID、正文、元数据、1024维向量内容签名一致。不能据此追认历史具体写进程或SQL。

`target/rag_protection.py`先hash/复制原索引和cache，核对后仅打开副本，退出再核对源；并行任务路径各自独立。直接open/build原基线在Embedding前拒绝。本轮真实检索与全部回归后，原源树SHA256仍为`f65a849870a6a9070920c70c609859538890967fcf0bdd87726094b306648776`。这属于应用级保护，无法阻止其他程序手动改文件；检测变化时失败保留现场，不恢复原件。

## 3. 真实执行与一次本地配置错误

用户追加明确授权“5次Embedding＋4次生成”。独立新账Embedding5/5、Qwen2/2、DeepSeek2/2、共享生成4/4；旧Qwen4/4、正式DeepSeek5/5、Embedding5/8不变。自动重试0、LangSmith0，全部额度已用完。

先执行evaluate_v352_rag.py的显式在线命令，5次HTTP200（10+10+10+10+8条）获得48条真实新查询向量，输入Token504。原30题、开发/保留各24及质量算法未改，不根据保留集调参。

首次双模型入口Qwen被旧DASHSCOPE_MODEL覆盖，在HTTP前触发v352_model_identity_required，实际请求0；同次DeepSeek2次HTTP200完成。原paired-report.json保留不改。提交90f801b将v352隔离环境的两个模型变量都绑定qwen3.8-flash，并增加严格的“仅未派发Qwen续跑”：核验Qwen0/2、DeepSeek镜像账一致且已完成、共享仅2/4，才可执行原授权余下2次，不重试或重跑DeepSeek。新Qwen2次HTTP200，完成新paired-report-resumed.json；原报告hash由续跑记录关联。

## 4. 同证据真实闭环及回答质量

问题固定为“锁座后多久必须完成支付？”。两个真实模型自行返回search_policy调用，参数question均为该原问题；Python实际读取Chroma副本，Hybrid/TopK3/cosine0.35/v351返回P11（version=43aea1ebf3c7b333）。HTTP审计在第二个请求保存实际ToolMessage、call_id、内容hash，再用同request_id的HTTP200和模型响应证明工具结果已回传；没有从回复文字猜工具调用。

工具结果规范化hash：`44f4e38a0d6fb00442dc6b42398a179c62f13f601902ba35ca1a19d0a314363c`；实际系统Prompt hash两边一致。Prompt含固定验收问题和只读限制，本次是受控政策样本，不代表自然问法泛化能力。原模型回复、保护判定、最终展示分别保留，未静默改答。

两模型都回答15分钟、过期释放库存、乘客列表需一致、重复支付不重复扣库存，均引用P11，未发现确定性错误、错误doc_id或越权工具；Agent结束stop不等同业务成功，business_success仍null。DeepSeek首个15分钟句有局部引用支持，后续句仍待复核；Qwen把来源放在末尾，有限句级规则无法可靠将其传播到每句。故两者citation_status为checked_ids_match、全文faithfulness为indeterminate，不能写“忠实度100%”。

## 5. 检索质量与真实用量

新48题中16有答案、32无答案；开发/保留各24题（8/16）。合计Keyword Recall@1/3=0.84375/1、MRR0.9375；Vector/Hybrid各0.96875/1、MRR1；误召回均0/32。保留集Keyword0.6875/1、MRR0.875，Vector/Hybrid0.9375/1、MRR1；开发集三模式均1/1/1。Recall按多预期文档召回比例计算，Top1不足但MRR=1可能同时成立。无答案Recall/MRR不适用，不能填0。完整144条模式结果、分数和排名见live/retrieval48/rows.json。旧30成绩另列。

真实Token：Qwen输入1921/输出143，DeepSeek输入1878/输出133，Embedding504。模型阶段延迟分别4984/12121ms；检索633/970ms；Agent总5674/13161ms。单样本、执行时点不同，不能推导总体速度/准确率。费用未知，无可靠账单，不假造估价或0元。

## 6. 代码、契约、测试与提交

新增rag_protection、v352_validation、四个V352脚本、web/rag_acceptance及V352专项；现有rag_store/service、faithfulness、LangChain、两个Runtime、live_providers、request_accounting增量适配。契约十字段、工具调用五字段、search_policy结构、原Mock/八种原变异/八种RAG变异/B正式断言均保留，依赖锁不变。

模块提交cf9f5b3索引保护、545e97a评估/版本、d4cdd6e真实入口、bd2f8cb页面/回归、2fdc340完整性、a7529f6原离线交付、90f801b模型配置/安全续跑、8e655fd公开证据回放。源码验收SHA为`8e655fd19e99c0adc406554bf56e8184f49e686d`；最终文档提交以git log -1为准，避免自指SHA。

90f801b全量离线502通过、0失败/0跳过、另89子测试通过；旧DeepSeek478通过/24跳过、V3 403/99、V2 307/195，均0失败。原smoke、原八变异25审计记录、八RAG变异通过。后续8e655fd仅调整新克隆公开证据回放，AppTest5通过，并再跑完整离线，最终原始日志见offline/authorized-final。所有离线过程真实请求0；旧3933和已有V352真实证据均hash不变。不要将JUnit包含的子测试重复相加。

## 7. 证据与交接边界

运行原件在artifacts/runtime/v352-rag-live-eval/authorization-20261026；公开原样副本在docs/evidence/v352/live。prepared冻结政策、实际HTTP/ToolMessage/Trace、初次0HTTP失败、续跑关联、新48原始结果、逐句判定均保留。原离线未授权摘要保留为preauthorization-summary.json，旧live-status.json保留历史背景，最新为authorized-live-status.json。

B优先复核末尾引用的支持关系、条件完整性和无答案/冲突扩展，分别统计检索、协议和回答质量；C按新手册回放已发生的两条真实记录，不重发API。剩余额度0，更多真实验证需新授权。当前可交给B独立测试及C带限制演示，不能宣称正式比赛成绩或全文语义全部通过。

新克隆交付验证还发现换行格式限制：Git归档中的政策为CRLF，冻结索引对应LF，安全校验拒绝导致Vector/Hybrid各48题无法判定。首次结果和原归档字节保留；只在另建全新克隆中验证纯换行差异、备份其原文件后准备LF格式，未改原项目或索引/manifest。随后0网络完整重放48题三模式，与本轮真实向量成绩完全一致。B手册提供该明确准备步骤；非全新工作区不得自动格式修复。详见clean-cache-replay.json，不能宣称未准备的任意检出都能直接复验。
