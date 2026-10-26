# B · V3.5.1 独立验收手册

日期：2026-10-26。A提供实现和自测证据；B保留正式断言、缺陷评价和成绩解释权。本轮不得将旧Mock100条的确定性语言断言直接作为Live逐字标准。

## 1. 环境与无请求入口

沿用.venv-v35与requirements-v35-lock.txt（含pytest9.1.1/Chroma1.5.9），不要求升级旧环境。新机器安装：

```powershell
cd D:\codexproject\ticket-agent
py -3.12 -m venv .venv-v35
.\.venv-v35\Scripts\python.exe -m pip install -r requirements-v35-lock.txt
```

直接运行离线验收（输出目录必须全新）：

```powershell
$ticketReview=Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv-v35\Scripts\python.exe scripts/verify_v351_offline.py --current-only --out "artifacts/runtime/b-v351-$ticketReview"
```

脚本剥离真实密钥、阻断外部Python网络，用pytest收集全部适用测试。A机有旧三个环境，可省略--current-only附加原V3.5/旧环境矩阵；新机器不能把不存在的旧环境说成已验证。原390项与新增专项不跨环境相加，最终passed/failed/skipped查offline/report.json与pytest.txt。

回归显式复制Chroma索引/cache到本轮目录，原库不得直接作为可写测试夹具。首次A全量运行已发现原索引3文件字节变更，副本核对逻辑内容一致、未自动恢复；事件在chroma-retention-incident.json。initial_baseline_changed_before_this_run与本轮changed_original_files必须分别查看，不能只看测试status就宣称历史完全不变。

重新独立重放检索：

```powershell
.\.venv-v35\Scripts\python.exe scripts/evaluate_v351_rag.py --out "artifacts/runtime/b-v351-quality-$ticketReview"
```

此命令纯本地，读取公开真实向量，不需要Key、不请求API、不写原索引。开发选择先保存，保留集随后评分；B可重复冻结算法的结果，不应按保留集调整规则再继续称其为盲测。新48题Vector/Hybrid仍未运行。

## 2. Mock与新版RAG配置边界

`Agent().chat(session_id,message)`十字段和steps[].calls[]五字段未变；search_policy仍返回question/hits/count。默认Mock且没有AGENT_RAG_MODE时走原路径，六/八变异、旧测试无需为了新模型重写。

测试新RAG可显式设置AGENT_RAG_MODE=keyword/vector/hybrid、RAG_QUALITY_PROFILE=v351、RAG_ALLOW_NETWORK=0。新版正式Live隔离入口已默认hybrid/v351/cache-only；裸Agent未配模式仍是旧兼容路径，必须记录实际配置。低层PolicyIndex.retrieve默认v35用于历史重放，新质量需显式quality_profile='v351'。不要将两种profile结果混记。

每用例独立session、模拟SQLite、Trace与输出目录。只读Live仍仅query_tickets/search_policy，其他六工具禁止，不能为验证RAG开放写操作。新查询没有缓存时应明确失败，不能自动花费旧余3次Embedding或降级为关键词成功。

## 3. 证据与断言重点

- baseline_30_queries.json/md复核原30题90组实际结果，不能修改旧V3.5 report。
- quality/selection.json、summary.json、rows.jsonl、holdout.json复核分母、算法SHA、原始/优化后列表、实际拒绝理由。原30三模式用真实缓存向量，开发/保留只测Keyword。
- rag_runs.jsonl新增candidate_hits/rejections/sufficiency/quality_profile；这些是旁证，公共十字段/五字段没有添加。空证据建议澄清/拒答，不等于模型已执行拒答。
- ticket-rag-answer/1的faithfulness_check含逐句findings、claim_checks、manual_review和original_model_reply。所有full_semantic_faithfulness仍indeterminate。
- 明确错误引用抛rag_wrong_citation，其他确定不一致抛rag_answer_inconsistent；延续原Live异常语义，不能将异常当作普通成功JSON。原始model_final/provider旁证保留；finish_reason=stop不等于业务成功。
- SDK协议证据外层标offline_sdk_mock_transport。内部mode=live仅表示适配路径，Token是桩数，不能统计进真实模型调用/费用。

建议独立增加未见表达，重点查：能力映射过窄/漏过未知属性、HP02/HP06正确文档第二、退票条件绑定、否定/用户引语/跨句引用、额外期限和比例、未执行动作声明、冲突未披露、恶意文档与损坏索引。不要通过改B正式判据换通过率。

## 4. 真实模型复验的前置条件

本轮真实请求0，旧Embedding5/8、Qwen4/4、V3.4共享4/4及正式DeepSeek5/5均不变。禁止删账、复制别名、调大上限、关闭budget guard或直接使用--run。Key配置沿用V3.5手册的本地环境变量方式，不发送给A、不出现在JSON/Trace/截图。

只读计划：

```powershell
.\.venv-v35\Scripts\python.exe scripts/prepare_v351_acceptance.py --out "artifacts/runtime/b-v351-plan-$ticketReview"
```

该脚本没有真实执行开关。待用户明确新授权后，最小申请Qwen2+DeepSeek2生成、缓存命中0Embedding、重试0，并增加固定V3.5.1验证profile绑定独立账，不改旧账。新48题完整Vector/Hybrid需要另申请最多5次Embedding（10条/批），不能把它算进0Embedding的最小闭环方案。

若预览优化后的固定证据，加--retrieval-file docs/evidence/v351/optimized-RQ01-chroma-cache-only.json；对应已保存方案在acceptance-plan-chroma/plan.json。本轮对索引/cache副本实际执行了该查询且禁止Embedding请求，命中P11。数学重放与实际Chroma的浮点分数可有小误差，不能用不同精度的hash强行比较；未来两Provider应共用实际Chroma冻结结果。

两Provider必须隔离数据库/会话，但系统Prompt、问题、RAG profile、工具证据规范化hash一致；模型自行选工具。分别判断协议、检索、回答、保护层，模型错误被拦截不能写成模型答对。所有实际成功/失败/未运行、Token未知及费用未知分别记录，正式质量结论由B提供。
