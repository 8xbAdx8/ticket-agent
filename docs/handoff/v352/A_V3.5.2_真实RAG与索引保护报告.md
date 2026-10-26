# A · V3.5.2 真实RAG与索引保护报告

日期：2026-10-26。分支feat/ticket-agent-v352-rag-live-eval；实际基线07efcd513b89f7f4698e4e73a297e3abcad5476e。当前为**有条件交接**：工程保护、离线验收和显式在线入口已实现；本轮尚未获得真实请求授权，不能写成两个模型的新Live已通过。

## 1. 原索引事件与本轮保护

保留V3.5.1三文件字节变化事件及其现状，没有恢复、覆盖或删除原件。本轮开始对3933个实际文件取SHA，涵盖原业务库/Trace、索引/cache、预算、B原件、原472项测试、30题和新增48题。

在独立副本分阶段调查，实际观察：初始化Chroma改写chroma.sqlite3；首次读取文档/向量时改写data_level0.bin和length.bin；查询、关闭及显式checkpoint未再改写。副本journal_mode=delete，未观察到WAL/SHM文件，checkpoint结果[0,-1,-1]。build被禁止且调用0，因此本次复现不依赖重建或Embedding；15条文档、元数据、维度、向量内容签名前后一致。该实验解释了读操作也可能落盘，不能追认当时具体历史进程或SQL语句。

新增target/rag_protection.py：

- 原路径直接client/open/build均拒绝，重建在任何Embedding调用前阻止。
- 读取先逐文件hash，复制到UUID工作目录，核对源/副本一致后只打开副本。
- 缓存也复制，退出再次校验源；副本内部字节变化与源变化分别记录。
- 并行任务用不同目录/Chroma system，自动测试核对相同逻辑签名、不同工作路径及原件不变。

这是应用级保护；不能阻止用户或其他程序直接改文件。复制期间源发生变化会失败保留副本，不自动恢复原件。证据：docs/evidence/v352/chroma-forensics.json。

## 2. 48题评估与限制

原开发/保留集各24题不变，没有新调参。已确认新48查询在真实缓存命中0，需要5次新Embedding（10条/批）。默认入口只做Keyword与缓存审计，没有偷用旧5/8的剩余3次。

| 集合Keyword | 正样本/无答案 | Recall@1 | Recall@3 | MRR | 无答案误召回 |
|---|---|---:|---:|---:|---:|
| 开发24 | 8/16 | 1 | 1 | 1 | 0/16 |
| 保留24 | 8/16 | 0.6875 | 1 | 0.875 | 0/16 |
| 合计48 | 16/32 | 0.84375 | 1 | 0.9375 | 0/32 |

Vector/Hybrid各48题尚未运行，Recall/MRR/误召回均未知。Recall/MRR对32个无答案题不适用，不能填0。旧30题真实向量与V3.5.1离线重放另列，不拿它们代替新48题。

## 3. 真实双模型验收入口

新增scripts/verify_v352_live.py：默认仅计划；--prepare实际在Chroma副本读取已缓存RQ01，冻结同一问题、语料/索引版本、Hybrid/TopK3/0.35/v351、工具结果规范化hash。已执行准备，生成/Embedding均0。

用户明确--run后才创建本轮generation-attempt及固定独立双账：Qwen2、DeepSeek2、共享4，重试0，Embedding0，LangSmith关闭。两Runtime在客户端构造前核对固定路径/上限/显式命令标记，不修改旧Qwen4/4或正式DeepSeek5/5。

真正模型选择search_policy，Python必须实际查Chroma且query/语料/结果hash与冻结条件一致；问题改写而缓存不匹配则失败，不偷偷补向量。HTTP审计保存ToolMessage快照、call_id和内容hash；需同request_id的HTTP200与模型响应，才能判断证据回传，不能从最终文字推测。

SDK离线测试使用实际ChatOpenAI/ChatDeepSeek与实际缓存Chroma，唯模型HTTP为明确MockTransport。正常配对、45分钟错答保护、超时零重试、纯文本不算工具调用成功、2/2/4持久预算均验证。此结果不是Live自主决策成绩。

## 4. 忠实度、展示与兼容

延续字段/句子级数字单位、时间条件、引用、冲突、无证据和执行事件检查，新增正向引用旧version失败、缺版本待人工。真实缓存向量还须匹配原API回执vector hash；不能仅看origin标签。全文语义仍indeterminate。

公共Agent.chat十字段、calls五字段和search_policy返回结构未变。原Mock/八原变异/八RAG变异/B正式断言保留。页面新增两Provider对照、实际证据、保护层和最终展示分离、新48与旧30区分；无Live文件显示未验证，离线SDK文件不得显示Live成功。

## 5. 文件与提交

新增：rag_protection.py、v352_validation.py；audit_chroma_v352.py、evaluate_v352_rag.py、verify_v352_live.py、verify_v352_offline.py；web/rag_acceptance.py及四个test_v352*.py。现有rag_store/service、faithfulness、LangChain、两个Runtime、live_providers、request_accounting与RAG页作兼容增量。原依赖锁不改，沿用Python3.12/Chroma1.5.9环境。

提交：cf9f5b3索引保护；545e97a评估/版本；d4cdd6e双模型入口；bd2f8cb页面/回归；2fdc340执行前缓存/语料核验。最终全量结果、最终源码SHA见docs/evidence/v352/offline/final/report.json；后续文档提交不伪称新的Live。

最终源码2fdc340b107d79180adf2351f3e0d3380f2400bb：pytest499通过/0失败/0跳过，另89子测试通过（JUnit588含子测试，不再加算）；原472项保留、新增27项。旧DeepSeek环境476通过/23跳过、V3环境401通过/98跳过、V2环境305通过/194跳过，均0失败。原smoke、原八变异25审计记录及八RAG实验通过。3933文件无变更、外网尝试0、新API请求0。

## 6. 未完成与下一步

两个模型修复后真实RAG闭环、同证据真实对照、新48题Vector/Hybrid仍待授权。建议分开授权并顺序运行：Embedding5次填48题；生成4次（每模型2）。也可只验生成4次，复用RQ01缓存，不要求先做48题向量。

不清账、不借旧额度、不自动重试；单个模型两次内未完成就记录失败。未来Token/费用以真实接口及可靠账单为准，当前无新请求。B独立评价，C只演示带来源记录，不能把离线成绩改名为Live。
