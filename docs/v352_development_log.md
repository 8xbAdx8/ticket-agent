# V3.5.2 持续开发记录

## 2026-10-26 基线与保护

- 实际HEAD07efcd513b89f7f4698e4e73a297e3abcad5476e、分支feat/ticket-agent-v351-rag-quality；仅用户原ZIP未跟踪。创建feat/ticket-agent-v352-rag-live-eval，3933个实际文件SHA256保护，保留V3.5.1事件及当时三文件变更现状，不恢复或覆盖。
- 本轮在线授权尚未获得。Qwen旧4/4、DeepSeek正式5/5、Embedding5/8均保留；新增生成/Embedding/LangSmith请求0。真实新入口必须显式运行才可使用独立额度，不在启动/刷新/导入时请求。
- 首先新增不可变源保护：禁止PolicyIndex直接打开或重建原基线；正式读取先逐文件hash并复制到UUID工作目录，缓存同步复制，只打开副本，退出后核对源未变。每个并行任务不同目录，副本的内部持久化与源的字节/逻辑结果分开记录。

## 模块一：不可变索引与分阶段调查

- 新增target/rag_protection.py、scripts/audit_chroma_v352.py、tests/test_v352_chroma_protection.py；修改rag_store/rag_service只将Chroma指向独立副本，直接打开或重建原基线在任何Embedding请求前拒绝。独立UUID目录与缓存防止并行测试共享持久化路径。
- 实际pytest本模块及原隔离/索引29通过、0失败、0跳过。包含实际Chroma并行两个副本、原文件前后hash、文档/元数据/维度/向量签名、工作副本改写不污染源、零网络与禁止重建。
- 实际运行audit_chroma_v352.py，依次观察副本初始化、读取、查询、关闭与显式WAL checkpoint；源hash完全不变、15文档逻辑签名一致、重建调用0、真实请求0。报告保留各阶段实际字节变化，不反推历史具体写进程；旧事件不删除、不恢复原文件。
