# RAG 千题评测：数据、执行与复核

更新日期：2026-10-30。当前项目状态仍以根目录 README 为入口；本文件维护这一项能力的使用和判定规范。

## 最后精简冲刺：Keyword范围修复

题库仍为1.1.1-candidate，430条来源核验与570条待语义复核不变；本轮不改题目、标准答案、原文或集合。规范化重复为0，本地近重复候选1对且同组同集合；203组复用答案片段可查看出题目的，不意味着均已获人工认可。

原始Keyword以单个汉字重合计分，任何常见字都能让知识库外问题获得Top5。千题执行器此前刻意未使用仅适合P01–P15的整体主题门控，也遗漏了可复用的有限属性边界检查。本轮仅在独立Keyword评测路径复用 `target/rag_relevance.py` 已有ATTRIBUTES：问题命中某属性、而57条有效政策全文均没有该属性模式时，返回空证据，保留未过滤候选及拒绝原因。恶意/过期fixture不能扩大有效知识范围。其余查询的排序、分数及原文不变。

没有扩大模型、工具或生产业务路由，没有新增前端改造。曾在development试验IDF二字词覆盖阈值，但正常召回损失明显，因此弃用；开发集试验日志保留，不把试验方案说成最终修复。最终有限规则没有根据holdout结果继续调参。它是有限范围拒绝，不能证明所有保留文档都能回答问题。

同题库、同语料、同代码、同Top5，raw/scoped实际批次分别为 `20261030-032242-0547c9b04c`、`20261030-032242-6a0421efff`：

| 探索指标 | 修复前raw | 修复后scoped |
|---|---:|---:|
| 无答案误召回（150题） | 150/150 | 121/150 |
| Recall@1（850题） | 0.518824 | 0.518824 |
| Recall@3（850题） | 0.783137 | 0.782549 |
| Recall@5（850题） | 0.860392 | 0.859804 |
| MRR（850题） | 0.782373 | 0.781784 |
| 必要证据完整率@5 | 0.787059 | 0.787059 |

430条已核验题的完整命中结果（顺序/分数/内容）一致；29条无答案候选停止返回无关文档；待复核的RAG-0527（互补能力边界与现实发票前提）也被有限属性规则拒绝，损失了原有部分召回。该题原本就没有取齐全部必要文档，此次未将它改判为通过，也没有改其标准答案。保留此风险，不为改善holdout数字添加专例。

**尚未解决：**121条无答案题仍误召回；有限词汇不能可靠分辨所有隐含属性、否定句及语义支持。空检索也不等于已生成正确拒答。真实Embedding、Vector/Hybrid和最终回答质量本轮均未执行，继续列未完成。

可复现命令（raw为保留原行为，默认scoped为修复后行为）：

```powershell
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py validate
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split all --mode keyword --keyword-profile raw
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split all --mode keyword --keyword-profile scoped
.\.venv-v35\Scripts\python.exe scripts/v37_tests.py --case tests/test_rag_benchmark.py --out artifacts/runtime/一个新的专项目录
.\.venv-v35\Scripts\python.exe scripts/regression_center.py
```

本次全部日志、逐题审计、前后指标与最终回归信息保存在 `artifacts/runtime/rag1000-final-sprint-20261030/`。后面的“本轮实际运行记录”是上一轮历史基线，仍原样保留其失败与边界，不冒充本次测试。全程不发送模型、Embedding或LangSmith请求，不修改或清理历史账本、用户数据、并行前端，不提交或推送。

## 交付边界

**当前是 `1.1.1-candidate`，不是“1000道全部验收通过”。** 已编写1000道候选题，430道直接政策/口语题经过AI来源核对及确定性结构检查，570道复杂题保留 `needs_review`。没有声称任何一道经过成员B人工验收。

| 主类别 | 候选 | 已核验标注 | 待复核 / 已验证数量缺口 |
|---|---:|---:|---:|
| 正常政策问答 | 250 | 250 | 0 |
| 同义及口语表达 | 180 | 180 | 0 |
| 多政策组合 | 120 | 0 | 120 |
| 无答案 | 150 | 0 | 150 |
| 条件缺失 | 80 | 0 | 80 |
| 冲突与版本 | 80 | 0 | 80 |
| 提示词注入 | 60 | 0 | 60 |
| 错误前提 | 50 | 0 | 50 |
| 数值边界 | 30 | 0 | 30 |
| 合计 | 1000 | 430 | 570 |

`verified` 表示本版的来源、完整字段和可定位规则核对，不等于人工认证、检索通过或模型回答通过。题库语义审查、检索质量、回答质量各自独立。

当前1000题划成505个意图组。180个口语样本与相应原始意图同组；相同政策子句的多个探针也归组。不能宣传为1000个独立能力。去重使用规范化、中文双字片段候选筛选和编辑相似度；不是完整语义去重证明。当前识别出1对近重复边界题，已同组同集合保留，供B复核其不同边界目的。

## 文件及原始资料保护

- `data/rag1000/v1.1.1/cases.jsonl`：每行一个完整用例。
- `schema.json`：JSON Schema，使用锁定依赖中已有的jsonschema校验。
- `corpus.json`：冻结的60条原始记录；57条active，P56过期、P57冲突、P58恶意文档均为测试样本。
- `active-policies.md`：正常检索只读取57条有效政策。指定场景才向独立检索输入增加fixture，不修改正常索引。
- `development.json`、`validation.json`、`holdout.json`：实际699/151/150题，而不是强行拆开语义组凑700/150/150。
- `manifest.json`：文件SHA-256、语料来源、划分算法、固定种子20261029、旧48题文件哈希及版本变更原因。
- `scripts/build_rag_benchmark.py`、`scripts/rag_benchmark_banks.py`：明确写出的题目与来源绑定；不调用模型生成问题，不随机更换数字凑题。
- `target/rag_benchmark.py`：验证、意图分组、指标、只读缓存检索、回答检查、独立运行目录和报告。
- `scripts/rag_benchmark.py`：独立CLI，不替换原有30/48题脚本。

构建器只接受**不存在**的输出目录；不会覆盖已冻结版本。保留本轮初稿 `v1`、`v1.0.1`、`v1.1.0`：先补充显式条件，再补充初始审计已经发现的等价来源，最后修正“互补政策对照不等于真实冲突”的复杂题行为标签。前面的探索结果未删除。不能拿不同标注版本的指标变化宣传检索器变好了。

划分先连接同意图组和本地近重复候选，再按类别/难度加权分配。仅共享政策来源不会全部绑定同组。各集合和全文哈希已冻结。本轮可做一次探索性全量评估，但不按holdout失败题反复调阈值；没有调整业务检索器或标准答案来换成绩。后续标注修订须升版本，保存差异、理由及B复核依据。

旧 `cases/rag_quality_v351_development.json` 与 `rag_quality_v351_holdout.json` 的48题保持独立，仍用旧15条政策评估；不混进新增1000题分母。

## 数据契约与校验

每题包括ID、版本、主类别、标签、问题、能否直接回答、预期文档、逐项原文和文档版本、答案要点、适用条件、禁止断言、预期行为、澄清字段、引用、检索/回答/安全规则、难度、来源、意图组、集合和审查来源。

`required_evidence[].quote` 必须是实际政策原文的子串，版本必须相同；答案要点必须绑定这些原文。无答案题的 `expected_doc_ids=[]`，另外记录具体知识缺口，P54/P60只表示出题时的拒答设计依据，不作为该事实的支持证据。无答案、缺少输入、文档冲突和业务能力边界分别分类。

单文档事实确有等价来源时，显式记录 `alternative_doc_ids` 和对应原文；例如P16部分归属要求也可由更宽范围的P13支持。不能把引用另一份真实等价来源误报为无来源。真正的多政策题仍须取齐全部必要证据，不因命中任意一篇就成功。

冲突集包括真实矛盾、过期/攻击样本以及互补政策的反例。互补对照的预期行为是解释规则，而非强行发现不存在的矛盾。只有P56/P57/P58这样的测试样本而无有效业务来源时，预期证据不足。P01/P07报销凭证退票、P08/P14/P28候补实现与文字差异、退票恰好48小时等仍须B独立裁定；不能擅自编出版本优先级。

## 运行方式

PowerShell在项目根目录运行，使用项目现有 `.venv-v35`。本入口**没有联网补齐、模型生成或LangSmith上传选项**，即使环境中有Key也不自动发请求。

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py validate
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split development --mode keyword
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split validation --mode keyword
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split holdout --mode keyword
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split all --category no_answer --mode keyword
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split all --case-id RAG-0001 --mode keyword
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py compatibility
```

`validate`退出0仅表示结构、冻结文件、证据绑定及本地分组检查通过；另看 `complete_1000_verified=false`，不能把退出0当成1000题全部验收。

真实缓存模式示例（路径必须换成**真实存在且匹配本版57条语料**的文件，命令本身不请求网络）：

```powershell
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split development --mode vector --index "你的兼容索引目录" --cache "你的真实问题向量缓存.db"
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split development --mode hybrid --index "你的兼容索引目录" --cache "你的真实问题向量缓存.db"
```

只提供旧15条政策的索引不兼容。Vector/Hybrid需要模型、维度、语料哈希、文档ID/版本/内容、向量哈希和成功真实API来源回执匹配；缺问题向量时记录blocked，绝不偷偷请求Embedding，也不降级Keyword或哈希向量。两种模式使用相同相关性和指标口径，Hybrid确实执行RRF(k=60)，并先对向量文档去重。cosine阈值0.35、最多20个候选融合、保存Top5；未套用仅覆盖P01–P15的V3.5.1有限主题门控。它是独立基准路径，不冒充业务Agent当前路由结果。

Chroma先复制到独立工作目录再打开；源索引和工作目录不得包含彼此。SQLite原缓存连只读连接都不打开，先复制DB/WAL/SHM再从副本做备份，避免源共享内存文件被SQLite修改。每次连接显式关闭，防止Windows占用文件。复制中源缓存变化会拒绝使用该副本。真实来源回执仍是本地历史证据，并非本轮重新在线认证。

失败重跑和报告：

```powershell
# 将路径换成上一轮真实批次目录；重跑生成新目录，原结果保留。
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py run --split all --mode keyword --retry-run "artifacts/runtime/rag-benchmark/上一轮run_id"
.\.venv-v35\Scripts\python.exe scripts/rag_benchmark.py report --run-id "实际run_id"
```

批次写入 `artifacts/runtime/rag-benchmark/<run_id>/`：报告JSON/Markdown、逐题JSONL、CSV、语料快照、题库manifest及文件哈希回执。JSONL每题追加；报告定期检查点保存，正常或捕获中断时最终落盘。突然杀进程时以已保存JSONL为准，不假称完整执行。API请求、Token、费用、来源、源码指纹、dirty、参数和时间分别记录；真实Token/费用没有新调用依据时为null。

`state=completed`只表示选定检索任务执行完，可能全部质量失败。缺缓存为blocked；异常为error；主动取消为cancelled。CLI执行不完整返回2（PowerShell可能包装成非零错误），不静默算成功。当前没有后台任务队列和浏览器进程强制取消；后端支持逐题取消回调，Ctrl+C保留已保存记录。

## 指标定义与边界

- Recall@K：单题已返回相关文档数 / 标注的全部相关文档数，然后宏平均。显式等价来源都属于相关文档集合；不把命中任意一篇写成文档Recall=1。
- MRR：去重后的检索列表中第一个相关文档的倒数排名，未命中为0；不是Top-K布尔命中。
- 证据完整率：多政策题取齐全部必要文档；单一事实允许明确列出的等价来源任意一份支持。因此它与“取齐所有相关文档”的Recall不同。
- 多文档覆盖：仅对真正需要多份文档的题目计算，不把等价来源算成多政策任务。
- 无答案误召回：只对主类别no_answer计算，统计是否返回文档。其他澄清和能力边界题不混入无答案分母。
- 每个指标都保存有效分母；无有效样本为null，不造0。
- `metrics`是候选标注的探索成绩；`verified_only_metrics`另列430道已核验标注。按类别、难度和政策来源有独立分组。

850道有相关文档标注，不等于850道可以直接作答：其中包括需要澄清和冲突解释的问题。检索返回了文档也不等于模型已把它用作结论。

## 回答证据与忠实度

本轮没有生成1000份模型回答。直接检索结果只保存为候选上下文，`delivered_context=null`；不伪装成“已经发给模型”，也不补造Agent Trace ID。

可用CLI `--answers <JSON列表文件>`导入已有回答。每项需要 `case_id`、完全相同的 `question`、`raw_reply`、实际上下文 `context`、`context_sha256` 和 `origin`（historical_real_api/offline_fixture/human_authored）。如果模型只收到检索结果的子集，还需 `retrieval_sha256` 绑定完整检索快照，并且所有上下文文档必须来自该快照。可提供provider/model/request_id/tokens/tool_events，但这些外部声明不自动等于已认证Live证据。

判定复用现有全文/原子断言检查器，保留原始回复、句子、支持原文、引用绑定、矛盾、未知项和规则。supported/contradicted/unsupported/indeterminate/not_applicable分开统计，未知进入事实分母但不计通过。额外检查答案要点及条件的字面覆盖；没出现只标待语义复核，不武断说条件缺失。禁止词出现在否定句或引述中不会仅凭字符串触发直接FAIL。

引用ID正确率不等于引用蕴含；“提到了15分钟”不等于全文忠实。拒答出现不等于拒答正确；完整语义、复杂条件、冲突解决和攻击抵抗保留人工复核字段。没有真实回答时，这些结果全部是未评估/null。离线固定回复只验证检测器，不算Live成绩。导入元数据也保留 `real_api_evidence_verified=false`，因为本入口没有独立认证其远端来源。

## 本轮实际运行记录

最终使用版本及批次请读 `artifacts/runtime/rag1000-development/final-verification.json` 和对应报告原件。首轮1.0.1与1.1.0探索结果保留，不能冒充最终源码复跑。

1.1.1候选版Keyword实际批次为 `20261030-030121-ea73db2a32`：1000道检索执行完成，669道满足本版检索条件，331道不满足。这是包含待复核标签的探索性成绩，不是B正式通过数，更不是模型回答成绩。

| Keyword探索指标 | 实际值 | 分母 |
|---|---:|---:|
| Recall@1 | 0.518824 | 850 |
| Recall@3 | 0.783137 | 850 |
| Recall@5 | 0.860392 | 850 |
| MRR | 0.782373 | 850 |
| 必要证据完整率@5 | 0.787059 | 850 |
| 多文档证据覆盖@5 | 0.725788 | 296 |
| 无答案误召回 | 150/150 | 150 |

另列430道来源核验题：Recall@1=0.623256、@3=0.856977、@5=0.926744、MRR=0.770388、必要证据完整率=0.937209。由于允许等价来源，完整证据不要求把所有同义支持文档都取齐，因此与文档Recall不同。

独立公式重新计算与报告一致；1000道Keyword再次检索的完整命中快照差异为0。Vector批次 `20261030-030121-903d1fe96c`、Hybrid批次 `20261030-030121-95ca1f5ec5` 各1000道blocked：当前扫描范围内未发现与冻结57条语料匹配的真实索引，不生成新向量来伪装已完成。全部1000道回答仍为not_evaluated。旧48题独立Keyword兼容检查已执行，原文件哈希不变。

本轮新增专项42项通过。第三轮全项目隔离副本pytest实际861项通过、124子测试通过、0失败、0跳过；附加V3.7离线哈希RAG和5种启动配置检查通过，可选性能步骤未执行。**整个回归批次未通过保护检查**：执行期间并行前端工作修改了 `tests/test_run_phases.py` 与 `tests/test_test_console.py`，源码发生变化，不能宣称最新联合工作区已冻结全绿。批次为 `artifacts/runtime/regression-center/20261030-030530-1448df39/`。前两次记录也保留，包括自身开发中修改测试，以及观察到全局用量日志追加/临时探针移除的保护失败。全局用量日志的旧字节前缀完整保留；不回滚、删除或擅自归属并行请求。

本任务评测器无模型/Embedding/LangSmith请求，隔离回归外部网络阻断守卫未发现连接尝试。并行进程的全局日志变化不充当本任务Live验证，也不能因此宣称整个正在使用的仓库没有其他在线请求。

本轮没有修正业务检索算法以追求高分。已观察到Keyword对无答案候选存在大量误召回；应作为后续质量改进输入，不能把基准执行成功宣传成RAG质量已达标。Vector/Hybrid真实缓存完整评估尚未完成；无新模型生成，因此不能报告回答准确率。

专项测试入口：`scripts/v37_tests.py --case tests/test_rag_benchmark.py --out artifacts/runtime/一个全新目录`。完整离线回归：`scripts/regression_center.py`；它将当前源码放入隔离副本并阻断外部连接。B原断言、原Trace、历史索引和正式账本不改动。

## 成员B的独立复核

1. 先执行validate并核对manifest、语料原文和实际缺口；不是看到1000行就认定完成。
2. 优先审查570道needs_review：多文档是否全部必要、无答案是否确无规定、缺条件是否真影响判断、冲突还是互补、攻击预期是否明确、数值边界是否有唯一依据。
3. 逐题材料见 `artifacts/runtime/rag1000-development/B-review.json`。记录审核人、日期、依据、批准/拒绝/需修订和具体修改；不要直接批量把pending改成verified。
4. 检查P01/P07与P08/P14/P28的真实矛盾；P44只解决改签48小时，不能套给退票。
5. 审查505组语义划分及唯一近重复候选；本地算法没有证明所有潜在语义泄漏都不存在。
6. 标签修订发布新版本，旧题库/结果不覆盖；避免针对已经看过的holdout检索失败调参。
7. 有兼容真实索引和查询缓存后再独立跑Vector/Hybrid；需要新增API请求时另行授权并单独计量。当前不需提供Key。
8. 回答评测单列模型、真实调用与导入证据，未知留待判定，不为形成漂亮分数而放宽正式标准。

## 成员C的演示

测试控制台 → RAG知识库 → “千题RAG评测”。展示候选/已核验/待复核、意图组及类别；选择development和Keyword后手动启动，进度来自已落盘题目。展开失败题可核对预期文档、实际原文、排名和检索快照哈希，再下载本批报告与JSONL。

展示Vector/Hybrid缺缓存时应明确说“未完成真实向量评估”；展示无答案误召回说明真实质量问题，而不是隐藏失败。版本比较须保持题目集合、配置和语料一致；不同标注版本不能归因成模型优劣。界面没有自动联网模型演示，本轮也不改造另一位开发者正在处理的前端样式。
