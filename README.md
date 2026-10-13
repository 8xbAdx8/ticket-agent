# Ticket Agent

面向智能体测试比赛的模拟出行服务助手。**所有车次、航班、政策和支付均为自建虚构数据，不连接真实票务或支付系统。**

保留原 MVP 结构及 `docs/contract.md`。成员 A 开发被测 Agent；B 设计和执行正式测试；C 持续跟进、组织验收与作品报告/录屏。

## V3 增量交付（2026-10-13）

独立分支 `feat/a-ticket-langchain-v3`：真正使用 LangChain 1.x `create_agent` 执行模型/工具循环，先验证两工具原型，再接入全部8工具。使用 `InMemorySaver` 隔离会话、middleware记录原契约Trace，并独立核验模拟写操作授权。原V2引擎仍默认可用。

- [A V3开发报告](docs/handoff/v3/A_V3开发完成报告.md)
- [B V3测试对接](docs/handoff/v3/B_V3测试对接手册.md)
- [C V3验收拍摄](docs/handoff/v3/C_V3验收与拍摄说明.md)
- [V2/V3技术对照](docs/handoff/v3/V2_V3技术对照报告.md)
- [V3交付清单](docs/handoff/v3/V3最终交付清单.md)
- [V3持续记录](docs/v3_development_log.md)、[实际框架证据](docs/evidence/v3/final_framework/verification.json)

新增[界面与讲解材料](docs/showcase/v3/README.md)：6张独立设计效果图、3张真实Streamlit Mock截图、可打开的HTML/CSS/JS源码，以及功能/架构/核心代码介绍和比赛讲解稿。设计稿使用历史Mock数据回放，与现有应用实际截图分别标注；查看图与页面无需安装渲染依赖。

实际A自测：V3环境56项通过；原V2环境旧28项通过、新框架28项明确跳过。两套环境每套10项入口/服务检查通过；LangChain Mock 11轮API覆盖8工具及CLI/Web通过。真实大模型尚未联网实测；B正式成绩、C人工验收待完成，状态为**有条件交接**。

V3使用独立 `.venv-v3`，保留原 `.venv` 与旧依赖锁文件。已有原环境时：

```powershell
.\.venv\Scripts\python.exe -m venv .venv-v3
.\.venv-v3\Scripts\python.exe -m pip install -r requirements-v3-lock.txt
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_ENGINE="langchain"
$env:AGENT_PROVIDER="mock"
$env:AGENT_LC_TOOLSET="all"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\v3-$runId\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\v3-$runId\langchain_mock"
.\.venv-v3\Scripts\python.exe data/seed.py
.\.venv-v3\Scripts\python.exe -m streamlit run web/app.py
```

首次没有Python环境先运行 `py -3.12 -m venv .venv`；已有环境不重复创建。只读原型改 `AGENT_LC_TOOLSET=read_only`；切回V2改 `AGENT_ENGINE=legacy` 并重启。六种变异仅legacy开放。可运行示例为 `scripts/v3_api_example.py --output-dir 新目录`，框架验证为 `scripts/verify_v3.py --toolset all --output-dir 新目录`；均使用V3解释器，拒绝覆盖既有输出。

Live沿用原4个模型环境变量，新验证入口 `scripts/validate_langchain_live.py` 默认只预检；有效Key且显式--run才远端调用。SDK桩验证不是实测模型成绩。下方V2章节保留作为历史说明，默认入口仍legacy。

## V2 历史交付（2026-10-13）

独立分支 `feat/a-ticket-v2`：已修复交通切换席别、切回高铁、售罄回复、重复支付提示和支付政策路由五项问题。A 实际通过 28 个自测、10 项入口/服务检查、32 条 Mock Trace；六变异仍可触发。B 正式 V2 全量回归与真实模型运行待完成，不能宣称正式 100/100。

- [A V2 开发报告](docs/handoff/A_V2开发完成报告.md)
- [B V2 测试对接](docs/handoff/B_V2测试对接说明.md)
- [C V2 验收演示](docs/handoff/C_V2验收演示说明.md)
- [V1/V2 缺陷对照](docs/handoff/V1_V2缺陷修复对照.md)
- [V2 最终清单](docs/handoff/A_V2最终交付清单.md)
- [V2 持续开发记录](docs/v2_development_log.md)、[V2 实际证据](docs/evidence/v2/regression/verification.json)

`scripts/smoke.py` 现在默认新建 V2 证据目录并拒绝覆盖已有目录。V1 标签 `handoff-a-20261012`、原库/Trace/文档/证据均保留。交接状态：**有条件交接**，B 可正式回归、C 可拍摄 Mock；真实模型无 Key，仅提供独立预检/显式运行入口 `scripts/validate_real_provider.py`。

## Windows PowerShell 快速运行

建议安装 Python 3.12。如果 `python --version` 没有输出或打开商店，使用实际 Python 安装路径建立环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\manual\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\manual\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe cli.py once "帮我查明天上海到杭州的高铁"
.\.venv\Scripts\python.exe cli.py chat
.\.venv\Scripts\python.exe cli.py batch cases/demo.json
.\.venv\Scripts\python.exe -m streamlit run web/app.py
```

数据库已存在时 seed 默认拒绝覆盖。若明确需要重建上述**隔离测试库**，关闭 CLI/Web/HTTP 后运行 `python data/seed.py --reset`。换新 Trace 目录保留既有记录。

不安装任何包也能运行 Mock + CLI（标准库），`python run_demo.py` 默认独立目录；Web/HTTP/真实 Provider 需对应依赖。`requirements-lock.txt` 是本次实际验证环境的完整冻结，`requirements.txt` 为原有可选依赖范围。

## V1 历史交接与证据

- [成员 A 开发完成报告](docs/handoff/A_开发完成报告.md)
- [成员 B 测试对接手册](docs/handoff/B_测试对接手册.md)
- [成员 C 验收与演示手册](docs/handoff/C_验收与演示交接手册.md)
- [最终交付清单](docs/handoff/A_最终交付清单.md)
- [持续开发记录](docs/development_log.md)、[接口契约](docs/contract.md)
- [实际验证记录](docs/evidence/verification.json)、[32 条 Mock Trace](docs/evidence/mock_traces.jsonl)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke.py
.\.venv\Scripts\python.exe scripts/handoff_example.py
```

这是成员 A 的实现自测与入口冒烟，不是成员 B 的正式测试方案或比赛成绩。

## 真实模型与当前边界

适配器使用 OpenAI 风格 Chat Completions function calling。设置 `AGENT_PROVIDER=openai`、`AGENT_API_KEY`、`AGENT_BASE_URL`、`AGENT_MODEL` 后重启进程。Key 只通过环境变量安全注入，不能写入仓库或截图。无 Key 会给出配置错误，不会假冒真实模型运行。

**本次仅验证 Mock、SDK 模拟响应和本地服务；真实模型联网、可选向量检索、正式比赛测试与人工录屏验收均待完成。** 固定模拟用户身份，不提供生产登录系统；候补只返回任务凭据；实际改签、儿童/学生票折扣和身份证核验尚未实现。已有原数据库不会自动扩展或按天刷新，新库覆盖生成当天及之后六天，共 2100 条记录。

每轮默认追加 `traces/traces.jsonl`，可用 `AGENT_TRACE_DIR` 隔离。GitHub 私有仓库为 `8xbAdx8/ticket-agent`，V1 与 V2 独立分支/标签保留；V2 不合并或覆盖原默认分支。
