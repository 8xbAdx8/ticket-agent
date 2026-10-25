# V3.5 开发记录

## 2026-10-26 基线、授权与依赖

- 实际基线9f4ab1eb3f34242ff6bc0e8c147c0577263d893a，原分支codex/ticket-agent-v341-answer-integrity；仅用户原ZIP未跟踪。新建feat/ticket-agent-v35-qwen38-rag。3707个原始文件哈希在artifacts/runtime/v35-work/protected.json保存，不覆盖历史证据/预算/数据。
- 本轮任务明确授权Embedding最多8请求、Qwen3.8-Flash最多4请求、重试0，独立V3.5账本；DeepSeek新请求没有包含在授权中。LangSmith关闭。所有业务继续模拟，Live仅query_tickets/search_policy。
- 官方模型页确认qwen3.8-flash支持Function Calling，但账号地域权限仍需实测；Embedding官方文档确认text-embedding-v4最多10条/批及1024默认维度，支持OpenAI兼容接口。不修改Codex配置。
- 原环境无Chroma，PyPI当前1.5.9、要求Python>=3.9；另建.venv-v35（Python3.12.14），保留requirements-deepseek-lock.txt全部锁定版本，加chromadb==1.5.9。实际安装成功，旧三个venv不改。安装日志在v35-install.txt；这是依赖网络，不是模型请求。
- 参考：https://docs.qwencloud.com/developer-guides/getting-started/text-generation-models 、https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api 、https://pypi.org/project/chromadb/1.5.9/ 。

## 模块一：Embedding、Chroma与兼容检索入口

- 新增target/embeddings.py：独立HTTP客户端、固定8次预算、批量/查询向量、缓存、显式网络许可、零重试、错误分类与未知用量、向量维度/数值/响应索引校验；离线transport始终标offline_stub，与real_api缓存隔离。
- 新增target/rag_store.py：稳定切片ID、模型/维度/语料/切片参数版本、Chroma持久化、原始API回执与已存向量哈希；显式增量重建，旧集合/manifest保留，启动不调用Embedding。Keyword、Vector、RRF(k=60)Hybrid去重排序，默认vector阈值0.35，不在看过真实评估后调分。
- 新增target/rag_service.py与scripts/rag.py：兼容search_policy原question/hits/count，独立检索/回答旁证与Trace关联，明确网络开关。target/rag.py默认原Mock行为保留；新Live向量失败不回退关键词。LangChain记录原文与引用ID核验，不宣称ID相符就支持全文。
- Qwen默认配置迁为qwen3.8-flash；显式旧DASHSCOPE_MODEL仍兼容，不自动回退。V3.5显式profile才允许生成4次，旧profile仍3次、不改旧账。UI显示和独立验收入口后续模块完成。
- 实际运行python -m unittest discover -s tests -p test_v35_rag.py -v：15通过0失败0跳过，含真实Chroma持久化/增量/维度/损坏、真实httpx+明确离线桩、预算/缓存/异常/密钥不入账。实际生成与Embedding请求均0。旧契约与B正式断言未修改。

## 真实索引与固定质量集

- 模块一提交17889d9。先运行scripts/rag.py plan：15文档/15切片，1024维、每批10，预计索引2请求、30查询3请求，总5/8。原Key仅内存读取，未输出；实际执行scripts/rag.py build --run --out artifacts/runtime/v35-qwen38-rag/authorization-20261026/index-build.json。
- 真实text-embedding-v4索引建立成功：2请求，15个切片，embedding_origin=real_api；索引版本242aa8199c4a8393ded29751。Chroma保存正文/向量/元数据、API回执和向量哈希，不用桩替代。生成模型请求仍0。
- 固定cases/rag_quality_v35.json共30问题（26有答案、4无答案），预期doc_id/允许引用/要点先固定后运行；多轮问题显式带上轮用户上下文。八种RAG注入另外隔离执行，不能混同正常真实索引质量。
- 新增target/rag_quality.py与scripts/rag_eval.py：Recall@3/MRR只统计有答案且执行成功的检索，拒答/引用/回答忠实度另算；全文语义无法证明则indeterminate，不用命中文档代替回答正确。下一步预算内批量真实向量化30问题，不重复向量化原文档。

- 质量集与指标提交0563d4e后实际执行scripts/rag_eval.py --run --out artifacts/runtime/v35-qwen38-rag/authorization-20261026/retrieval-evaluation：真实Embedding新增3次，累计5/8。Vector在26有答案问题Recall@3=1、MRR=1；Keyword及Hybrid Recall@3=0.980769、MRR=0.923077。4条无答案问题误召回率Keyword/Hybrid为1、Vector为0.75，作为实际风险保留，不改阈值/答案追分。
- 新增scripts/verify_v35_live.py固定一次性验收入口：最多2次query_tickets真实Agent、1次预取证据政策生成、1次无答案生成，总4；只用新V3.5双账，不开放其他工具。普通预检不生成，二次--run被attempt文件拒绝；HTTP错误停止后续生成，无自动重试。
- 在线生成前原test_live_providers.py离线SDK15通过；补充默认新模型/显式旧模型、仅V3.5上限4及固定指标/未知忠实度测试，确保新模型不替换DeepSeek、不靠旧Qwen结果冒充新验证。

## 真实Qwen闭环与接续

- 冻结07f36ff后实际--run：qwen3.8-flash两次HTTP200，实际query_tickets闭环成功，Trace185e0fd83d424db2ae6985b776512feb；车次/日期2026-10-27/时刻/价格/余票正确，后置字段检查无错配。请求ID eb51aabf68ea4d30bd277789dd17c330、a33b72af55d84c538fdb67bf6ac7027e；输入1963/输出318。
- 脚本完成FC后，错误地从langchain_core.tracers.context导入tracing_context，ImportError导致尚未尝试两个直接RAG生成。保存原控制台错误、原attempt、原FC Trace与2/4账本，不删除/重跑。
- 修复为项目实际使用的langsmith.tracing_context，并将导入提前到任何请求前，新增本地导入验证。只读已有provider_runs重建function-calling-recovery.json（标明来源SHA），新增严格resume-rag-only：必须已验证FC、账本恰2次且仅一次接续，不执行FC，仍共享原4次账本，不新建别名预算。剩余两请求不是重试。
