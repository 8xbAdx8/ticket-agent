# B · V3.5.2 独立测试与判定手册

更新：2026-10-26。A已实际完成5次Embedding和Qwen/DeepSeek各2次生成；本轮额度全部耗尽。B负责正式评价，本手册不修改B原测试及标准答案。

## 1. 新机器准备

使用Python3.12和requirements-v35-lock.txt，当前验证Windows/Chroma1.5.9/pytest9.1.1。源码克隆不带运行索引/cache；A提供`artifacts/deliverables/Ticket-Agent_V3.5.2_真实RAG离线复验缓存_20261026.zip`，公开SHA及成员hash见docs/evidence/v352/cache-package.json。

仅解压到**全新克隆根目录**。任何目标路径已存在都不能覆盖，换一份新克隆。包内包括不可变旧索引/旧cache、本轮48条真实新查询cache；不含Key、.env、业务库、预算账本或在线授权。旧的“离线RAG基线”ZIP另保留，不含新48查询，两个包不能叠加覆盖。回放历史向量/模型证据不代表B本机发过真实请求。

```powershell
cd D:\codexproject\ticket-agent
py -3.12 -m venv .venv-v35
.\.venv-v35\Scripts\python.exe -m pip install -r requirements-v35-lock.txt
$env:PYTHONIOENCODING='utf-8'
$ticketReview=Get-Date -Format 'yyyyMMdd-HHmmss'
```

先核对新克隆政策文件的换行格式：Git导出/部分检出会得到CRLF，冻结索引记录的是LF原文。它们语义相同，但原始字节hash不同会被索引安全层拒绝。**仅在全新克隆**执行下面准备命令；它先验证仅去掉CRLF就精确匹配冻结hash，再备份新克隆中的原文件，绝不改索引、manifest、原项目或政策文字。若仍不匹配则停止，不重建索引。本轮实际新克隆复验保留了首次格式失败，执行此准备后全部48题三模式指标与原真实运行完全一致，新增API0。非全新工作区遇到不匹配应保留现场，不执行格式写入。

```powershell
$ticketPolicySetup=@'
from pathlib import Path
import hashlib,json
p=Path('data/policies.md');raw=p.read_bytes()
manifest=json.loads(Path('artifacts/runtime/v35-rag/index/manifest.json').read_text(encoding='utf-8'))
expected=manifest['corpus_hash']
if hashlib.sha256(raw).hexdigest()==expected:
    print('Policy bytes already match; no file changed.')
else:
    lf=raw.replace(b'\r\n',b'\n')
    assert hashlib.sha256(lf).hexdigest()==expected, 'STOP: not a newline-only mismatch'
    backup=Path('artifacts/runtime/v352-fresh-clone-policy-before-lf.bin')
    with backup.open('xb') as f: f.write(raw)
    p.write_bytes(lf)
    print('Fresh clone only: original bytes backed up; LF identity verified; index untouched.')
'@
.\.venv-v35\Scripts\python.exe -c $ticketPolicySetup
# 前面命令有错误时停止；不要继续补向量或修改manifest。
.\.venv-v35\Scripts\python.exe scripts/verify_v352_offline.py --current-only --out "artifacts/runtime/b-v352-$ticketReview"
.\.venv-v35\Scripts\python.exe scripts/evaluate_v352_rag.py --out "artifacts/runtime/b-v352-quality-$ticketReview"
```

两条验收命令均不请求API；安装依赖可能访问包仓库，区别于计费模型请求。完整离线入口剥离Key、禁止外网、建立私有索引/cache副本。B缺旧venv时用current-only；不把未安装的旧环境算作已测。A最终502通过/0失败/0跳过，另89子测试，不是B正式成绩。不要仅看评估进程退出码或completed：还须核对每模式已评分样本数、indeterminate_cases和not_run_cases均符合预期；首次换行不匹配时Vector/Hybrid各48题无法判定的记录如实保留。

## 2. 复用原Mock正式用例

保留B原100/101条及Mutation断言原件。按原执行方式先跑legacy Mock，再分别跑LangChain Mock；原八变异及八RAG变异独立记录，不能把变异注入触发率当正常Agent准确率。本轮没有把B断言改为适应Live自然语言。

沿用from target.agent import Agent；Agent().chat(session_id,message)。十字段为session_id/provider/model/user_msg/steps/tool_sequence/reply/finish_reason/tokens/total_latency_ms；calls仍tool/args/ok/latency_ms/result_preview五字段。stop只表示循环结束，不表示业务成功。相同测试问题在不同Provider使用独立session/SQLite/Trace；随机UUID和环境切换必须在每次Agent构造前完成，不能复用前一Provider的内存会话。

## 3. 本轮真实证据如何复核

原件在artifacts/runtime/v352-rag-live-eval/authorization-20261026；Git可读副本在docs/evidence/v352/live。优先看paired-report-resumed.json、authorized-evidence-review.json及runs/*/traces；paired-report.json保留初次Qwen0HTTP本地配置失败，不将其计为API失败。

Qwen Trace b4c2d6e91b594b24b0e078dfdb7d333d；DeepSeek Trace 2c9a9c4e4f99497c931a48e792c2eb49。两边工具search_policy(question=锁座后多久必须完成支付？)，P11/version43aea1ebf3c7b333。核对模型真实tool_calls→tool_start/实际tool_end→第二个http_dispatch_evidence中的call_id/ToolMessage→相同request_id的HTTP200→最终model_final。工具规范化hash两边均44f4e38a0d6fb00442dc6b42398a179c62f13f601902ba35ca1a19d0a314363c，系统Prompt hash一致。

分别统计：API响应、真实模型身份、实际工具执行、协议闭环、Agent结束、引用ID、句子事实、人工未知、业务结果。两模型原回复均为15分钟且P11真实，确定性错误0；全文语义indeterminate，尤其Qwen末尾来源与前文句子关联应人工检查。未完成语义审核不能填“通过”，保护拦截不能算模型答对。自然语言不用全篇逐字匹配；优先对真实工具名、参数、结果、引用、明确事实和错误状态断言。

## 4. 48题与索引验收

开发/保留各24（各8有答案、16无答案），不可改答案或按保留集调参。docs/evidence/v352/live/retrieval48/rows.json含48×3条问题、期望doc_id、命中/分数；report.json分开发/保留/合计计算正确排名和指标。Keyword合计R@1=.84375/R@3=1/MRR=.9375；Vector/Hybrid各.96875/1/1；误召回均0/32。无答案Recall/MRR不适用；多预期文档导致R@1<1但MRR=1是合法情况，不改计算标准。

运行audit_chroma_v352.py --out全新runtime目录可在副本复核SQLite/HNSW写入阶段；只hash/复制原件，比较byte与logical两个结论，禁止为对齐hash自动恢复原件。新48缓存包齐全时默认评估应三模式全部运行、Embedding0；若显示missing_queries则先检查包安装路径，不自行运行--run补向量。

## 5. API Key如何安全配置（不等于获得新额度）

只在自己的机器隐藏输入，不发给A/C、不写文件/Trace/报告：

```powershell
$ticketSecret=Read-Host 'DASHSCOPE API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY',[Net.NetworkCredential]::new('',$ticketSecret).Password,'User')
Remove-Variable ticketSecret
$ticketSecret=Read-Host 'DeepSeek API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY',[Net.NetworkCredential]::new('',$ticketSecret).Password,'User')
Remove-Variable ticketSecret
```

新开终端；受保护项目.env或显式进程空Key会覆盖用户变量，诊断只显示是否存在，不打印内容。Qwen配置DASHSCOPE_MODEL=qwen3.8-flash，DASHSCOPE_BASE_URL必须匹配地域/套餐；本轮实际为https://dashscope.aliyuncs.com/compatible-mode/v1。Embedding空间冻结为text-embedding-v4/1024维/相同地域，差异会拒绝混用。DeepSeek为deepseek-flash、https://api.deepseek.com。LANGCHAIN_TRACING_V2/LANGSMITH_TRACING保持false。

## 6. 在线命令历史与当前禁重跑边界

以下是A已获授权并执行过的记录，不是请B再次执行：

```text
python scripts/evaluate_v352_rag.py --run --authorize-embedding-requests 5 --out artifacts/runtime/v352-real48-20261026
python scripts/verify_v352_live.py --run
python scripts/verify_v352_live.py --run --resume-unattempted-qwen
```

第二条只派发DeepSeek2；第三条严格限定初次Qwen0HTTP模型配置失败，核验原报告及共享/单独账后仅使用未派发Qwen2。原generation-attempt、paired-report和DeepSeek证据不变，续跑不是额外授权或服务失败自动重试。当前独立Embedding5/5、Qwen2/2、DeepSeek2/2、共享4/4，剩余0。不可清账、改路径或反复续跑；新的正式Live测试需用户另行明确授权、建立新方案，不能借旧Embedding余3次或手动不限额入口。

## 7. B优先独立判定项目

- 逐句检查P11数字/期限/乘客约束/重复支付描述及末尾引用是否支持全部结论，unknown另列，不伪造自动通过率。
- 扩展无答案、条件缺失、冲突、旧版本、未执行却声称已操作的确定性与人工案例；Live尚未执行这些新场景。
- 核验只读白名单query_tickets/search_policy，其余六工具代码层禁止；本轮实际只调用search_policy，不宣称查票/写操作新Live通过。
- 检查十/五字段、错误预算与Token未知语义、并行副本隔离、原Mock/Mutation不回归。
- Mock、SDK离线桩、真实检索缓存回放、真实模型协议、语义质量分开出表；单政策样本不推广为模型整体准确率。
