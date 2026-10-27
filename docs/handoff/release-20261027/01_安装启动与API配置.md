# 安装、启动与 API Key 配置

> 当前源码更新：所有 Live 入口和 Embedding 已取消本地累计请求上限。下文正式测试另设限额的说明属于旧交付包；当前无需创建预算批次，旧账本只读保留。Key 配置方法仍适用。请以 [当前使用与测试迁移说明](../unlimited-live/使用与测试迁移说明.md) 为准；此前 ZIP 没有被覆盖。

日期：2026-10-27。本说明面向解压后的新目录；不要覆盖已有环境或历史数据。

## 1. 首次安装

开发和本次验证使用 Windows、Python **3.12.14**。完整依赖以根目录 `requirements-v35-lock.txt` 为准；包括 LangChain、DeepSeek/OpenAI 兼容 SDK、Streamlit、Chroma、pytest。不要把早期 `requirements.txt` 当成完整V3.5环境。

先安装Python 3.12（64位），然后在解压目录打开PowerShell。例如目录为 `D:\ticket-agent`：

```powershell
cd D:\ticket-agent
py -3.12 --version
py -3.12 -m venv .venv-v35
.\.venv-v35\Scripts\python.exe -m pip install -r requirements-v35-lock.txt
$env:PYTHONIOENCODING='utf-8'
```

安装依赖需要访问Python包源。ZIP没有包含虚拟环境或wheel仓库；本次用已有完整依赖验证解压包，未在另一台新机器重新联网安装依赖。无需激活venv，直接使用上述Python路径即可避开PowerShell激活策略问题。

## 2. 无 Key 的离线使用

双击根目录 **`启动_离线模式.cmd`**；也可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Start-TicketAgent.ps1 -Mode offline
```

启动窗口会显示真实地址，默认从 `http://127.0.0.1:8501` 选择可用端口。不要关闭窗口；结束服务按Ctrl+C。页面选择Mock对话，可问“查明天上海到杭州的高铁二等座”“锁座后多久必须完成支付？”。Mock购票演示应使用页面实际查询到的车次，并按提示提供虚构乘客信息。

离线启动强制关闭真实模型、Embedding网络和LangSmith导出；不能在离线启动窗口里切成真正Live。每个Web会话使用隔离模拟库和Trace。开始下一组实验请新建会话，不删除旧证据。

## 3. 配置 DeepSeek Key（隐藏输入）

Key应由接收者在DeepSeek官方控制台自行创建，不发送给A、B、C或聊天工具。下面只把隐藏输入保存为当前Windows用户环境变量，不打印Key：

```powershell
$ticketSecret = Read-Host '输入你自己的 DeepSeek API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY', [Net.NetworkCredential]::new('', $ticketSecret).Password, 'User')
Remove-Variable ticketSecret
```

关闭旧启动窗口，再双击 **`启动_在线模式.cmd`**。默认DeepSeek Live，只读，默认端口8502，具体以窗口为准。Key缺失时，交互终端会提示隐藏输入；无法交互时停止并显示未配置，绝不悄悄回退Mock。单纯启动、打开页面和刷新不会调用模型。

可以在新的PowerShell只核对是否存在，不输出内容：

```powershell
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User'))) { '未配置' } else { '已配置' }
```

默认模型 `deepseek-flash`，默认URL `https://api.deepseek.com`。如需调整，只改文档化的 `DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL`。不要把Key放入 `AGENT_API_KEY`；DeepSeek只读取 `DEEPSEEK_API_KEY`。

## 4. 配置百炼 Qwen3.8-Flash

```powershell
$ticketSecret = Read-Host '输入你自己的百炼 API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', [Net.NetworkCredential]::new('', $ticketSecret).Password, 'User')
Remove-Variable ticketSecret
[Environment]::SetEnvironmentVariable('DASHSCOPE_MODEL','qwen3.8-flash','User')
# 以下仅适合北京地域标准按量付费兼容接口；其他地域/套餐必须填账号对应地址
[Environment]::SetEnvironmentVariable('DASHSCOPE_BASE_URL','https://dashscope.aliyuncs.com/compatible-mode/v1','User')
```

配置不代表账号必然有模型权限。已有DeepSeek Key时，重启在线脚本，在页面选择 **Qwen3.8-Flash Live**，新建会话，确认右上徽标和费用确认都显示Qwen。

**只有百炼Key、没有DeepSeek Key时：** 原一键在线入口默认要求DeepSeek Key；可以直接用已有Streamlit入口，不需要填一个假的DeepSeek Key：

```powershell
cd D:\ticket-agent
$env:AGENT_PROVIDER='bailian'
$env:AGENT_ENGINE='langchain'
$env:AGENT_LC_TOOLSET='read_only'
$env:LANGCHAIN_TRACING_V2='false'
$env:LANGSMITH_TRACING='false'
Remove-Item Env:TICKET_WEB_OFFLINE_ONLY -ErrorAction SilentlyContinue
Remove-Item Env:TICKET_DISABLE_LOCAL_SECRETS -ErrorAction SilentlyContinue
.\.venv-v35\Scripts\python.exe -m streamlit run web/app.py --server.address 127.0.0.1 --server.port 8502
```

配置加载顺序为进程变量（包括显式空值）→项目本地 `.env` →Windows用户变量。不要机械地将含空Key的 `.env.example` 复制成 `.env`，否则会遮蔽已配置用户变量。遇到401/未配置，先核对变量来源、地域和权限，不在报告中贴完整配置。

## 5. 真实发送和费用

输入只读问题，勾选该模型的费用确认，再点击发送。一次对话可能产生多次模型生成请求：先选工具，再收到结果后回答；“问一次”不等于只计费一次。日常手动Web会话为两Provider分别记账，不设累计次数上限；仍保留单轮防循环、超时、Token限制和零自动重试。费用以服务商账单为准，未知用量不能写成0。

本包不复制A的正式预算数据库，也不赋予B自动批量付费测试授权。正式验收应另建有上限的独立计划和账本，不能删除历史账本来重复消费。不要直接重跑旧 `--run` 验收命令。

Live仅可 `query_tickets`、`search_policy`。锁座、订单、支付等六工具由代码层阻止。模型超时、API错误、工具错误、保护层拦截，都应按失败/未知记录，不能把 `finish_reason=stop` 当作业务通过。

## 6. 可选 LangSmith

LangSmith用于上传经过筛选的本轮执行记录，不是模型提供商，也不负责执行查票。默认关闭，缺少Key不影响本地Trace。

```powershell
$ticketSecret = Read-Host '输入你自己的 LangSmith API Key（隐藏输入）' -AsSecureString
[Environment]::SetEnvironmentVariable('LANGCHAIN_API_KEY', [Net.NetworkCredential]::new('', $ticketSecret).Password, 'User')
Remove-Variable ticketSecret
[Environment]::SetEnvironmentVariable('LANGCHAIN_PROJECT','ticket-agent-team-review','User')
[Environment]::SetEnvironmentVariable('LANGCHAIN_ENDPOINT','https://api.smith.langchain.com','User')
# 启用本项目的白名单手动导出，不开启SDK自动全量追踪
$env:TICKET_LANGSMITH_EXPORT_ENABLED='true'
& '.\启动_在线模式.cmd'
```

如果账号使用其他地域端点或需要工作空间，使用其匹配的 `LANGCHAIN_ENDPOINT` 和 `LANGCHAIN_WORKSPACE_ID`。不要同时配置互相冲突的LANGCHAIN/LANGSMITH别名。不要为图方便开启SDK自动全量上报；本项目会禁用它。

先完成一条Live对话，展开“LangSmith可选远端追踪”，检查脱敏JSON预览，再勾选上传同意并点击导出。没有执行记录时按钮禁用是正常的。最多1次POST+3次GET；202仅代表接受，只有GET读取到同ID且内容匹配才算远端验证成功。暂时404显示待验证；已有ID只读重核验，避免重复POST。分享截图先检查预览没有个人信息。

## 7. RAG和常见问题

包内已带冻结的真实15条政策索引、旧查询缓存和新增48题缓存；不必重新建库。Keyword无需网络；Vector/Hybrid复用已有向量。新问题没有缓存时，Embedding网络和预算仍受独立守卫控制，不能把未执行写成通过。不得直接打开或重建原始Chroma基线；测试由独立副本读取。

- 模块缺失：确认使用 `.venv-v35\Scripts\python.exe`，安装完整lock文件。
- 无法启动或端口占用：保留终端错误，查看实际选用端口；指定端口的手动命令可换一个空闲端口。
- 更新代码后UI仍旧：Ctrl+C停止旧服务再重启，单纯刷新不能保证重载所有模块。
- 左侧模型与历史徽标不同：明确选择对应历史会话或点击新建；左侧是新会话默认模型。
- Live失败：在工作台保存JSON、旁证和脱敏错误，先确认Key/URL/模型/账本，禁止反复点击发送来排障。
- 双模型回答不确定：看工具证据和逐句审计，交B复核；不能凭语句流畅度判定政策准确。

## 8. 完全离线自检

在刚解压、未改源文件的目录运行：

```powershell
.\.venv-v35\Scripts\python.exe scripts/check_team_package.py
```

该命令无需Git，先校验文件，再清除子进程凭据、阻断外网、复制索引，执行完整pytest、Mock冒烟、48题三模式和启动预检。结果在新建 `artifacts/runtime/package-check-*/report.json`；原文件变化会使校验失败。它不安装依赖，不产生真实API请求。需要修改源码测试时另复制工作目录，不修改交付原件。
