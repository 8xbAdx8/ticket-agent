# B · V3.5.2 独立测试与判定手册

日期：2026-10-26。A负责实现和自测，B负责正式断言、指标与缺陷评价。原B文件不改。

## 1. 环境与运行产物

使用Python3.12与requirements-v35-lock.txt（Chroma1.5.9、pytest9.1.1）。索引/cache位于Git忽略的运行目录，只有源码克隆并不包含它们。A另提供artifacts/deliverables/Ticket-Agent_V3.5.2_离线RAG基线_20261026.zip，SHA见docs/evidence/v352/baseline-package.json。

基线包仅在**全新项目克隆**根目录解压，若artifacts/runtime/v35-rag/index或embedding-cache.db已存在，禁止覆盖，换一份新克隆。包内是历史真实向量，不含Key、票务业务库或API预算；导入不代表B发过真实请求或获得新授权。当前在Windows/Chroma1.5.9验证，其他平台兼容性待确认。

```powershell
cd D:\codexproject\ticket-agent
py -3.12 -m venv .venv-v35
.\.venv-v35\Scripts\python.exe -m pip install -r requirements-v35-lock.txt
$env:PYTHONIOENCODING='utf-8'
$ticketReview=Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv-v35\Scripts\python.exe scripts/verify_v352_offline.py --current-only --out "artifacts/runtime/b-v352-$ticketReview"
```

脚本剥离真实Key并阻断外网；原472项及新增专项全部收集，新旧环境重复执行不相加。A有旧三个venv可省略current-only跑矩阵；新机器不能把缺失的旧环境记为已测。

## 2. 离线检索与索引复核

```powershell
.\.venv-v35\Scripts\python.exe scripts/audit_chroma_v352.py --out "artifacts/runtime/b-v352-index-$ticketReview"
.\.venv-v35\Scripts\python.exe scripts/evaluate_v352_rag.py --out "artifacts/runtime/b-v352-quality-$ticketReview"
.\.venv-v35\Scripts\python.exe scripts/verify_v352_live.py --prepare
```

以上不请求模型/Embedding。原件只hash/复制，Chroma只打开UUID副本；检查source_files_before/after、logical_before/after及阶段changed_files。不要为了相同hash恢复原件。48题默认缺向量时只测Keyword，Vector/Hybrid保持not_run。保留开发/保留集合，不修改标准答案或按保留集调参。

Recall@1/3按预期文档召回比例计算；MRR按首个正确文档排名倒数；32无答案题的Recall/MRR不适用，误召回另计。first_correct_rank可检查HP02/HP06排序不足。新48与旧30分别统计。

## 3. 真实API授权前的配置

本轮A没有发新请求。DASHSCOPE_API_KEY用于Qwen/Embedding，DEEPSEEK_API_KEY用于DeepSeek；只在自己机器配置，不发给A/C、不写报告/Trace。隐藏输入到Windows用户环境：

```powershell
$ticketSecret=Read-Host 'DASHSCOPE API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY',[Net.NetworkCredential]::new('',$ticketSecret).Password,'User')
Remove-Variable ticketSecret
$ticketSecret=Read-Host 'DeepSeek API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY',[Net.NetworkCredential]::new('',$ticketSecret).Password,'User')
Remove-Variable ticketSecret
```

新开终端。地区/套餐Endpoint必须匹配账号；现有冻结索引使用北京兼容地址https://dashscope.aliyuncs.com/compatible-mode/v1，若显式配置其他Embedding地址，入口会停止要求迁移，不偷偷混用。进程空值或.env空Key会覆盖用户变量，先确认实际来源。LangSmith保持关闭。

## 4. 只有用户明确授权后才执行

下面是会计费的命令，A本轮没有执行；不能因看到代码块就当作已授权。两个命令分开、顺序运行，不并行，不删除attempt/账本重跑。

```powershell
# 授权新Embedding最多5次，填充新增48题，生成0次
.\.venv-v35\Scripts\python.exe scripts/evaluate_v352_rag.py --run --authorize-embedding-requests 5 --out "artifacts/runtime/b-v352-real48-$ticketReview"
# 另授权Qwen最多2次+DeepSeek最多2次生成，合计4；Embedding0
.\.venv-v35\Scripts\python.exe scripts/verify_v352_live.py --run
```

固定V3.5.2账根artifacts/runtime/v352-rag-live-eval/authorization-20261026，独立bailian-generation.db、deepseek-generation.db、generation-total.db、embedding.db。旧4/4、5/5、5/8都不改。错误/超时同样占额度，重试0；已attempt不能创建别名路径借额度。缺Key会停，不自动Mock。

## 5. 双模型正式判定

核查同一问题、system_prompt_sha256、实际model ID、索引/语料版本、ToolMessage规范化结果hash和HTTP request_id。回传证据以http_dispatch_evidence及同request_id的HTTP200为依据，不能只看reply中写了P11。

分别判定：模型真实响应、工具实际执行、协议闭环、Agent结束、确定性忠实度、人工未知、最终展示和业务结果。原文保留，保护拦截不算模型答对；stop不代表业务成功。CLI非0表示未完整结束/被拦截，0也不证明全文语义。real_function_calling_verified在offline_sdk_stub中必须false，桩Token不计真实用量。

重点独立扩展：不存在引用、同ID但不支持结论、数值/时间条件错误、冲突/过时政策、无关文档编造、无证据时拒答、未执行操作声明、并行副本隔离。十字段/五字段与异常语义沿用原契约；查看rag_runs/provider_runs/audit_runs旁证，失败不能伪装成功公共Trace。
