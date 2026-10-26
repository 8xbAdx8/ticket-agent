# V3.5.2 持续开发记录

## 2026-10-26 基线与保护

- 实际HEAD07efcd513b89f7f4698e4e73a297e3abcad5476e、分支feat/ticket-agent-v351-rag-quality；仅用户原ZIP未跟踪。创建feat/ticket-agent-v352-rag-live-eval，3933个实际文件SHA256保护，保留V3.5.1事件及当时三文件变更现状，不恢复或覆盖。
- 本轮在线授权尚未获得。Qwen旧4/4、DeepSeek正式5/5、Embedding5/8均保留；新增生成/Embedding/LangSmith请求0。真实新入口必须显式运行才可使用独立额度，不在启动/刷新/导入时请求。
- 首先新增不可变源保护：禁止PolicyIndex直接打开或重建原基线；正式读取先逐文件hash并复制到UUID工作目录，缓存同步复制，只打开副本，退出后核对源未变。每个并行任务不同目录，副本的内部持久化与源的字节/逻辑结果分开记录。

## 模块一：不可变索引与分阶段调查

- 新增target/rag_protection.py、scripts/audit_chroma_v352.py、tests/test_v352_chroma_protection.py；修改rag_store/rag_service只将Chroma指向独立副本，直接打开或重建原基线在任何Embedding请求前拒绝。独立UUID目录与缓存防止并行测试共享持久化路径。
- 实际pytest本模块及原隔离/索引29通过、0失败、0跳过。包含实际Chroma并行两个副本、原文件前后hash、文档/元数据/维度/向量签名、工作副本改写不污染源、零网络与禁止重建。
- 实际运行audit_chroma_v352.py，依次观察副本初始化、读取、查询、关闭与显式WAL checkpoint；源hash完全不变、15文档逻辑签名一致、重建调用0、真实请求0。报告保留各阶段实际字节变化，不反推历史具体写进程；旧事件不删除、不恢复原文件。

## 模块二：48题缓存审计、完整指标与版本支持

- 索引保护提交cf9f5b3。新增target/v352_validation.py和scripts/evaluate_v352_rag.py，保持开发/保留数据及V3.5.1规则不变，记录Recall@1/3、MRR、正确文档排名、误召回、适用/N/A/未运行/无法判定。默认只读缓存，只有--run并显式授权5次Embedding才可执行固定独立账，重试0、生成0。
- 实际默认离线检查48题：真实缓存命中0、缺48条，按10条/批准确需5次新Embedding。Keyword全48的Recall@1=0.84375、Recall@3=1、MRR=0.9375，无答案0/32；保留集与开发集单列。Vector/Hybrid各48未运行，指标为未知null，不以0或旧30成绩填充。未使用旧余3次额度。
- 忠实度追加可选当前/冻结政策version核验：正向引用旧版本报具体错误，版本缺失待人工，否定说明不冒充正向政策。旧55fixture和原参数调用兼容。新测试首次因自建SQLite夹具未关闭导致Windows清理失败，修复显式关闭连接；非原业务库问题。随后组合pytest77项通过，另2子测试通过，真实请求0。

## 模块三：可显式启动的双模型验收

- 48题/版本模块提交545e97a。新增verify_v352_live.py：普通运行只打印计划，--prepare实际用缓存/Chroma副本冻结P11证据且生成/Embedding0；只有用户手动--run才启用独立V3.5.2固定双账（Qwen2、DeepSeek2、共享4），零重试/零Embedding/零LangSmith。一次attempt标记防止重复运行或别名额度，旧账不改。
- 新v352 profile在两Runtime构造客户端前校验固定账与显式命令标记；Prompt、检索模式/Top-K/阈值一致。真实工具必须执行新Chroma检索且question/语料/hash匹配，拒绝偷偷用别的问题生成向量。HTTP审计保存实际派发ToolMessage内容与hash；只有同请求HTTP200再加模型响应才能声称证据已回传。
- 区分协议闭环、Agent结束、原回复、保护层、最终展示和业务成功。SDK桩政策回答45分钟时协议可完整但保护失败停止；不能把模型错误被拦截称作模型答对。默认未授权的real_api报告不创建，Web必须显示未验证。
- 实际prepare与默认计划完成（0真实请求）；两SDK+实际缓存Chroma的正常配对、错答拦截、超时零重试、纯文本非工具成功、2/2/4预算与禁止无标记入口共6专项通过。连同既有SDK/Provider组合29项通过（另11子测试），证据明确offline_sdk_stub，非Live。本轮未执行--run。

## 模块四：页面证据与最终离线入口

- 双模型入口提交d4cdd6e。页面新增真实配对状态、实际ToolMessage/原回复/保护层/展示结果、冻结索引与证据hash，离线SDK即使协议通过也显示未验证；新48题开发/保留/合计与旧30题前后成绩分区，未运行指标不填0。网页只读缓存，原基线不能在页面重建或花旧额度。
- 新增web/rag_acceptance.py和3项UI检查；与原页面共4项通过。补模型实际ID核对与Embedding地域/冻结索引不匹配时拒绝，21项组合通过。无新增请求。
- 新增verify_v352_offline.py，基于本轮3933文件快照，导出独立SDK证据并运行全部pytest、原环境/变异矩阵、48题默认离线检查；旧V3.5.1索引事件单独保留，V3.5.2原源应完全不变。接下来执行完整回归，只有新授权后才运行显式在线入口。

## 全量回归与执行前审查

- 源码bd2f8cb首次全量498通过、89子测试通过，0失败/0跳过；旧环境矩阵和两组变异通过，3933保护文件未变，真实请求/网络尝试0。网页实际检查两模型未验证、新48题Vector/Hybrid空值、旧30分区及只读缓存；窄窗口可折叠侧栏，原图留证。
- 执行前审查补强真实缓存向量必须匹配API回执中的向量hash，不能仅凭origin标签；生成前重新校验冻结语料和缓存完整性，防止已准备后被外部改写。协议闭环成功但保护拦截时CLI退出非0，原回复与协议事实仍保留；实际模型ID缺失不冒称模型已核实。新增完整性反例，专项18项通过，之后重跑全量。

## 最终离线结果与交付

- 最终源2fdc340b107d79180adf2351f3e0d3380f2400bb：verify_v352_offline.py --out artifacts/runtime/v352-final-offline-20261026实际pytest499通过、0失败、0跳过，另89子测试通过；原472保留并新增27，不把JUnit588重复相加。
- 原DeepSeek环境476通过/23跳过、V3环境401通过/98跳过、V2环境305通过/194跳过，均0失败。原smoke、两组变异通过；3933保护文件完全未变，原索引本轮字节无变化，V3.5.1事件仍保留；真实请求/网络尝试0。
- 五份A/B/C/质量/费用报告与完整证据已写入docs/handoff/v352和docs/evidence/v352。B另获只含历史向量索引/cache的离线基线ZIP，CRC及源文件hash核验通过，不含API预算授权。网页实际截图显示两模型未验证、新旧集合分区，可折叠侧栏阅读。
- 本轮未执行任何--run。真实双模型需另明确授权4生成；新48题需要另5Embedding。代码和离线可交接，Live与全量向量成绩暂缺，保持有条件交接，不伪造或混用旧成绩。
- 交付安全检查已在内存比对3个当前配置秘密，并逐一解压扫描基线ZIP成员，未发现这些秘密；3933初始文件、本轮原索引字节和全部旧预算未变。新正式账/attempt没有被创建为已执行，待授权状态如实保存；公开证据以SHA256索引核对。

## 用户追加授权后的首次真实执行与最小配置修复

- 用户明确授权“5次Embedding＋4次生成”，固定新账Embedding5、Qwen2、DeepSeek2/共享4，自动重试0、LangSmith0。旧账不改，authorization.json保存原话和源码a7529f6。实际5次Embedding全部HTTP200，总输入Token504，48条新查询向量均补齐；完整三模式检索已运行，原索引hash不变。
- 首次生成入口Qwen在HTTP前被v352_model_identity_required拦截，派发0次；原因是旧DASHSCOPE_MODEL覆盖AGENT_MODEL。DeepSeek实际2次HTTP200，search_policy执行、真实缓存Chroma结果回传与最终回复闭环完成；原paired-report.json、DeepSeek两条预算记录及Trace全部保留。
- 最小修复仅在v352隔离环境同时指定DASHSCOPE_MODEL=qwen3.8-flash。新增--resume-unattempted-qwen：必须是Qwen本地模型配置失败且0派发、DeepSeek已完成且共享/单独账2条记录完全一致，才可使用原授权剩余Qwen2；新独占续跑标记和新报告，不创建新预算，不改原报告，不重跑DeepSeek。其他失败或已有Qwen派发一律拒绝续跑。
- Web分别判断单Provider真实工具闭环和双模型公平对照，0HTTP配置失败不记API失败或Live成功。离线回归入口追加冻结现有V352真实证据/账本hash。两SDK+实际Chroma离线专项12通过、0失败、0跳过，包含旧qwen-plus覆盖、仅Qwen续跑、原记录字节保留和重复续跑拒绝；HTTP全部MockTransport，新增真实请求0。

## 授权额度内完成双模型与全部48题

- 配置/安全续跑提交90f801b88705dd1806f3274123e8bfa6329c76bb。真实Qwen续跑只发2次HTTP200，DeepSeek原2次不重跑，Embedding原5次不重跑；独立共享账4/4、各模型2/2、Embedding5/5，旧账和3933原文件完全不变，重试/LangSmith均0。
- 两模型都真实选择search_policy(question=锁座后多久必须完成支付？)，从相同冻结Chroma副本检索P11，并在第二个HTTP200请求回传实际ToolMessage；证据规范化hash44f4e38a0d6fb00442dc6b42398a179c62f13f601902ba35ca1a19d0a314363c、系统Prompt hash一致。原模型回复、公共JSONL及旁证逐一核对一致。初次Qwen0HTTP失败保留在paired-report.json，完成后的新记录在paired-report-resumed.json，禁止覆盖原件。
- 新48题三模式完整实际评估：Keyword Recall@1/3=0.84375/1、MRR0.9375；Vector/Hybrid各0.96875/1、MRR1；无答案均0/32。保留24题Keyword0.6875/1、MRR0.875，Vector/Hybrid0.9375/1、MRR1；开发24题各1/1/1。未更改开发/保留集或质量规则，未根据保留集调参。
- 实际Token：Embedding504；Qwen输入1921/输出143；DeepSeek输入1878/输出133。费用未知，无可靠账单。Qwen/DeepSeek都回答15分钟、引用P11且无确定性错误，但全文忠实度indeterminate；句级引用关联/语义仍交B人工判定，不宣称总体准确率。
- 90f801b完整离线回归502通过、0失败、0跳过，另89子测试；旧DeepSeek478通过/24跳过、V3 403通过/99跳过、V2 307通过/195跳过，均0失败，原八变异和八RAG变异通过。原3933文件和已有61个V352运行证据不变，外网尝试0。
- 交接页面新增优先读取公开本轮实际48题结果，避免B新克隆无runtime报告时误显示旧的未运行指标。实际AppTest5通过（0API），包括无runtime、读取公开新48成绩和未验证模型状态。另建真实索引/新查询缓存ZIP供B离线复验，保留先前基线ZIP，不含密钥、预算或新在线授权。
