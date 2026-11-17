# 成员 B V3.3 前端与数据展示验收手册

日期：2026-10-25。A 交付新的 Streamlit 展示与实验层；原被测 Agent 入口、工具及判据不变。以下是可复现条件与检查入口，不代替 B 的正式测试方案和质量评价。

## 安装与启动

推荐 Python 3.12，沿用 `requirements-deepseek-lock.txt`；本轮没有升级依赖。已有环境无需重装。

```powershell
cd D:\codexproject\ticket-agent
# 离线：无需 Key。双击文件也可。
.\启动_离线模式.cmd
# 在线配置预检：不发送模型请求
.\.venv-deepseek\Scripts\python.exe scripts/launch_app.py --mode live --check-only
# 新版 A 自测，输出目录必须全新
.\.venv-deepseek\Scripts\python.exe scripts/verify_v33_offline.py --out artifacts/runtime/v33-b-review
```

直接运行网页时，应先明确 Mock 和安全环境；优先使用原启动器，避免继承其他工具实验环境。

```powershell
$env:AGENT_PROVIDER="mock"
$env:AGENT_ENGINE="legacy"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MUTATIONS="{}"
$env:LANGSMITH_TRACING="false"
$env:LANGCHAIN_TRACING_V2="false"
.\.venv-deepseek\Scripts\python.exe -m streamlit run web/app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

## 模式与隔离

- 出行助手：普通用户输入、卡片、历史会话；没有变异配置。常见模拟写操作多一步 UI 确认，后端原身份/幂等/授权仍有最终约束。
- 测试工作台：总览、实验室、Trace、质量、对比、集成六页。
- 新用户/实验：`artifacts/runtime/v33/user/<sid>/`、`lab/<sid>/` 各自保存数据库及 Trace。变异或引擎配置变化新建实验，旧证据保留；原库未重置。
- 普通用户显式独立 MockProvider，不读取旧全局 mutation 注册表。测试时仍应使用新会话/新库，避免同一模拟会话的订单与库存继承。
- 普通用户新建会话不删除旧文件；历史会话仅当前 Streamlit 内存有效，重启不等于恢复对话记忆。

## 保留的测试入口

```python
from target.agent import Agent
agent = Agent()
result = agent.chat("b-v33-independent", "查明天上海到杭州的高铁")
```

字段和语义仍以 `docs/contract.md` 为准：session_id/provider/model/user_msg/steps/tool_sequence/reply/finish_reason/tokens/total_latency_ms；调用仍为 tool/args/ok/latency_ms/result_preview。旁证不加进公共契约；`stop` 不表示业务成功。

原正式用例仍由 B 自己的执行器运行。本仓库没有擅自合并或修改 `judge/`。网页的“B 原用例输入（A 实验复用）”只逐轮复用输入，不执行正式断言或 setup，也不形成 B 成绩。原 V3.2 界面可通过 `streamlit run web/legacy_app.py` 做独立兼容检查；新默认入口是 `web/app.py`。

## 数据与指标验收

在总览选择数据批次，检查代码版本、执行日期、来源、粒度和分母：

| 数据 | 应显示 |
|---|---|
| B Legacy 正式功能 | 101/101；103 定义中 2 不适用 |
| B LangChain 正式功能 | 100/100；103 定义中 3 不适用 |
| B 选定变异 | 69/69 组合被任意规则检出；不宣称所有幻觉零漏检 |
| B 专项 | 45 通过、0 失败、2 原 N/A；旧 generated 日期单列 |
| B M8 | 10 条检查，不冒充 10 个模型案例 |
| A 历史离线 | 与 B 分开，SDK 桩不算 Live |
| A 当前隔离实验 | 只读本浏览器已保存的非 Live 审计，不混入 B 批次 |

来源副本在 `web/datasets/b_v32_20261020/`；manifest 的哈希应与原六份结果一致。快照来自你 2026-10-20 的回传，未重跑或改变原断言。总览原始下载保留该批范围；表格筛选只作用于对应表格，CSV 与其筛选后的可见行一致，原文件不写回。

维度图是既有用例通过率，不是代码覆盖率、RAG 忠实度或真实模型成功率。没有对应维度/历史批次时显示未提供或暂无足够数据。

## 实验室与八种变异

选择 Mock 引擎、场景、开关，点击“执行测试”才调用 Agent。只切换控件不执行。先跑正常组，再单独启用一项，再恢复正常模式，避免混合注入干扰归因。

| 标识 | 建议输入 / 路径 | 可核对事实 |
|---|---|---|
| date_offset | 查明天上海到杭州的高铁 | 日期偏移、原参数与实际校验 |
| skip_lock | 订明天上海到杭州的高铁 | 下单尝试、后端拒绝、无有效订单 |
| repeat_call | 查明天上海到杭州的高铁 | 实际派发次数，不仅看文字 |
| infinite_loop | 抢明天北京到上海的票 | 有限重入、终止，不算业务成功 |
| route_error | 退票手续费怎么算 | 政策意图与实际查票不一致 |
| no_citation | 锁座后多久必须支付 | 来源删去，检查原始/可见结果与回复 |
| hallucinated_train | 查明天上海到杭州的高铁 | 工具可见 G9999，原库/原结果无 G9999 |
| concurrent_duplicate_order | 运行并发订单对照（离线） | 正常与影子库、订单数、唯一性断言 |

M8 对话按钮会禁用，必须走独立并发入口。LangChain Mock 写变异使用原 full_sandbox 校验，仅在新隔离目录生成匹配 marker；不放宽后端约束。默认 Live 中 skip_lock/infinite_loop 不适用，不允许为了演示开放其他六工具。

## Trace 与问题证据

实验室与 Trace 页分别展示：注入、平台检出、Agent 识别、Agent 恢复和业务正确。`None` 不显示成功。展开实际事件可以看参数验证、工具结果及规则；并列查看 original / mutated，表格列出变化字段。

JSON 支持搜索、展开、代码块复制和脱敏下载。历史十字段记录没有旁证时，明确提示未提供；只读回放不重新调用模型。Blob 需相邻目录、大小和哈希均正确；缺失不按完整证据处理。

当前卡片取完整工具返回。B 原压缩 execution.jsonl 没有完整参数、数据库和当前审计文件，界面不能从文字补出这些字段。正式回归建议保存每用例库快照、完整公共 Trace、audit/blob、判定 JSON、环境和代码 SHA。

## 幻觉与并发边界

- “质量分析 → 变异热力图”可切到额外 16 条探测；T04 是漏检，R01 未触发且不适用，F15/M12 是其他规则命中。点图或详情选择器应看到同一行数据。
- A 的 8 个标注规则样本独立展示；6 条可判定、2 含糊，不能据此声称通用模型准确率 100%。
- M8 B 10 条检查与 A 历史/当前后端对照分别标注；影子库故意缺陷不是原数据库存在重复订单。
- 原 B 脚本低于变异阈值仍 exit 0、异常可能漏计失败等问题本轮未替 B 修改。请由 B 维护正式入口，继续保留旧结果。

## Live 后续验收

本轮真实请求 0，不因有 Key 就自动测试。将来获授权后只用环境变量 `DEEPSEEK_API_KEY`，启动原在线脚本，额外勾选页面真实费用确认。不得把 Key 发给 A、写进用例/JSON/Trace或截图。

默认仍只有 `query_tickets` 和 `search_policy`；必须分别统计 Mock 与 Live、原始历史与当前执行。自然语言不宜全用逐字断言，应检查工具、参数、实际结果、引用、异常和预算。预算路径/上限由原启动器保持，正式 5/5 不改；手动不限累计模式也不是免费。

B/C 交接前需 B 独立确认新版 UI、数据口径和回放；A 的自测报告不等于 B 正式 V3.3 结论。

## A 最终离线验证结果

被测源码 `c462ed50a015a9a09b136fd156d8d35cb6a34a54`：完整依赖环境 222 通过、0 失败、0 跳过；V3 环境 163 通过、59 跳过；V2 环境 111 通过、111 跳过，均收集 222 项。Mock smoke、25 条八变异运行记录与 8 个标注样本通过。缺 Key / 假 Key 只预检，不验证真实账户。详情和原日志在 `docs/evidence/v33/20261025/`，请先看 `兼容性与离线验收报告.md` 和 `report.json`。

拉取后重启旧 Streamlit 服务再验收。建议 B 首先核查 T04 漏检、原脚本退出码/N/A 风险，以及新版页面切换是否保持会话与来源分母；这些事项未由 A 改正式判据或补造通过结果。
