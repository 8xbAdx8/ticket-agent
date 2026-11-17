# B · V3.5 RAG质量测试手册

日期：2026-10-26。A开发与自测，B独立建立正式断言/质量结论；本目录不是B正式测试成绩。真实与离线证据必须分开。

## 1. 环境与安全起步

新环境使用Python3.12，安装requirements-v35-lock.txt；原.venv/.venv-v3/.venv-deepseek不需升级：

```powershell
py -3.12 -m venv .venv-v35
.\.venv-v35\Scripts\python.exe -m pip install -r requirements-v35-lock.txt
.\.venv-v35\Scripts\python.exe -m pip check
```

锁定Chroma1.5.9及原LangChain/OpenAI等兼容版本。双击启动_离线模式.cmd会优先选择.venv-v35。旧启动_在线模式.cmd仍是DeepSeek入口；网页可显式选Qwen3.8-Flash Live，它不会把旧qwen-plus/Mock冒充新模型。

API Key只在自己机器配置，不发送给队友、不写进JSON、日志或Git。隐藏输入示例：

```powershell
$ticketKey = Read-Host "DASHSCOPE API Key（隐藏输入）" -AsSecureString
[Environment]::SetEnvironmentVariable("DASHSCOPE_API_KEY", [Net.NetworkCredential]::new("",$ticketKey).Password,"User")
Remove-Variable ticketKey
```

模型/地域非敏感变量需与你的账号匹配，不能盲抄北京地址给其他地域/套餐：

```powershell
$env:DASHSCOPE_MODEL="qwen3.8-flash"
$env:DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DASHSCOPE_EMBEDDING_BASE_URL=$env:DASHSCOPE_BASE_URL
$env:RAG_EMBEDDING_MODEL="text-embedding-v4"
$env:RAG_EMBEDDING_DIMENSIONS="1024"
```

Key配置优先级进程（含显式空）>项目.env>Windows用户变量。示例.env的空Key会盖掉用户变量；不要复制空行却期待后备Key生效。设置用户变量后新开终端/重启服务。预检只报告是否配置，不能把configured_unverified当鉴权成功。LangSmith默认关闭，本轮没有新远端上传授权。

## 2. 当前额度与无请求命令

V3.5实际Embedding5/8、Qwen4/4，旧V3.4的4/4及正式5/5不变。**禁止为复测删除/改写账本、复制新路径借额度、改上限或重跑已完成验收。** 当前生成不能再请求。跨机器克隆后账文件不存在，不等于获得新的调用授权。

```powershell
# 只读计划/状态/预检，不发送模型生成或Embedding请求
.\.venv-v35\Scripts\python.exe scripts/rag.py plan
.\.venv-v35\Scripts\python.exe scripts/rag.py status
.\.venv-v35\Scripts\python.exe scripts/live_providers.py --provider bailian --profile v35
```

status需要匹配的Embedding配置才能校验索引；新机器无运行索引应明确missing，不冒用公开快照标记为自己已建库。公开real-index-export.json保存真实原始向量、维度、元数据及回执哈希，供离线核验；它不代表B本机发过Embedding请求。

建库命令scripts/rag.py build --run、批量评估scripts/rag_eval.py --run、真实验收scripts/verify_v35_live.py --run都会涉及真实请求，**本轮已经执行，不要照抄再运行**。未来需要先取得明确的新授权。有效索引直接复用，变更后需显式--rebuild；重建保留旧集合/manifest。任何Live错误不自动回退关键词/旧模型/Mock。

## 3. 离线回归与用例隔离

```powershell
$ticketReview=Get-Date -Format "yyyyMMdd-HHmmss"
.\.venv-v35\Scripts\python.exe scripts/verify_v35_offline.py --out "artifacts/runtime/b-v35-$ticketReview"
```

输出目录必须全新。脚本剥离真实Key、阻断外部Python网络，运行全V3.5、原三环境、原smoke/八变异与新8项RAG实验，快照核对历史账/证据不变。只读已发布docs/evidence/v35/中的原始结果，不向历史目录写文件。

如执行自己的Agent用例：默认AGENT_PROVIDER=mock保留原入口Agent().chat(session_id,message)，每用例独立session/SQLite/Trace；不要把B全部Mock用例直接批量跑到Live。Live错误可能抛类型异常，失败旁证不等于正常十字段JSON；stop也不是业务成功。新侧车文件不改变公共契约。

## 4. 固定质量集与断言

cases/rag_quality_v35.json有30条：26有答案、4无答案，固定expected_doc_ids/allowed_citations/answer_points和场景；在Live前冻结，SHA见A报告。每题在live/retrieval-evaluation/report.json保存三模式真实命中、排名、分数、来源、索引版本与实际查询Embedding回执。

多轮RQ29显式把上一轮用户上下文拼入embedding_query，不能说已经完成真实多轮模型记忆验收。RQ30保留同证据对照入口；DeepSeek本轮没有生成样本，不借历史成绩填入本轮矩阵。空索引、服务错误、恶意文档等异常由独立RAG故障实验覆盖，不把正常30题的语料偷偷改成污染索引。

Keyword得分为原字词重叠，Vector为1-cosine距离并按0.35过滤，Hybrid按RRF(60)融合两个排名。Top-K3、按doc_id去重；不同分值不可当统一概率。阈值与标准答案在看到成绩后未修改。

检索与生成分开：命中正确文档不代表最终回答正确；工具执行成功不代表业务完成；无答案误召回与生成是否拒答也是两个维度。细分公式与分母见V3.5_RAG质量集与判定标准.md。

## 5. 新侧车与真实向量溯源

rag_runs.jsonl记录ticket-rag-retrieval/1及ticket-rag-answer/1：trace_id、question、mode、hits、Embedding模型/来源/receipt、索引版本、rank/score/source、独立耗时、原回复、引用ID核验。实际FC仍由公共Trace/provider_runs/audit_runs提供，不从最终文字推测工具调用。

真实向量证据real-index-export.json逐切片带原API向量、请求ID、原向量哈希、Chroma存储哈希和数值误差。输入哈希、向量哈希与embedding-budget.json同一次HTTP行对应；缓存不是新请求，回执可能被多个切片引用，不能重复累计Token。generation-request-audit.json区分项目request_id与未捕获的服务端ID。

derived-live/rag_runs.jsonl是从已保存Live结果显式导出的回放侧车，不伪造新的执行时间或API调用。原generation-result.json的初始机械误判保留，generation-assessment-review.json指出修复后的否定范围复核；不得把它视为模型重新生成成功。

## 6. 八种RAG变异与B应验项目

在网页RAG知识库选择RAG变异后显式运行“隔离离线RAG变异”。后台独立Chroma、stub向量及预算，无付费请求；before/after、executed、expected、judgement、原政策SHA均留证。不得用其分数冒充真实Embedding质量。公开已执行结果在offline/rag-mutations/。

| 开关 | 独立核验重点 |
|---|---|
| rag_missing_doc | P11确实从副本消失，不能再据此回答15分钟 |
| rag_conflicting_doc | 当前政策与60分钟测试政策冲突可见，不盲信其中一条 |
| rag_stale_doc | 旧版/过期政策识别，正常库没有污染 |
| rag_wrong_citation | P99未出现在证据，模型原文/注入后文本分开 |
| rag_low_similarity | 0.01低分经过阈值后被拒，不伪造置信度 |
| rag_prompt_injection | 文档恶意指令当作数据并报告风险，不泄露Key |
| rag_empty_index | 独立空Chroma明确不可用，不回退为成功 |
| rag_embedding_error | 明确503异常、无重试/无降级、失败计入桩预算 |

原八变异与本8种各自独立，不改变原B判定。正常库文件/版本前后应一致。有限关键字风险检查不是通用安全证明，B应探索绕过和误报。

优先独立验收：无答案3/4误召回、Hybrid劣于Vector的样本、自然语言要点支持度、否定引用与正向乱引的区别、过时/冲突/注入规则、增量/损坏恢复、缓存维度/来源隔离、旧接口/Mock/八变异、页面不自动调用API。完整语义忠实度仍需人工/独立规则判定，不能只逐字匹配或全部交给被测模型打分。

## 7. 已验证边界

本轮真实FC是query_tickets；两次RAG回答来自冻结的真实检索证据直接生成，每题1请求，非实际search_policy工具Agent完整闭环。后者两个Provider的SDK离线桩已验证。Qwen生成额度4/4耗尽，不继续调用；后置预算/评分/风险/UI修复仅离线验证。原报告中的旧模型/旧指标保留原版本归属。
