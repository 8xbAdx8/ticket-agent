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
