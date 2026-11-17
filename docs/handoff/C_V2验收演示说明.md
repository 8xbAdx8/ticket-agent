# 成员 C：V2 验收与演示说明

生成日期：2026-10-13（Asia/Shanghai）。分支：`feat/a-ticket-v2`。
经过回归的源码提交：`1804518c9a312ec0d4ab8cb000124e37ee551887`；本手册是该源码之上的文档提交。
最终交付提交用 `git rev-parse HEAD` 确认；交付标签计划为 `handoff-a-v2-20261013`，仅在检查通过后建立，解析标签可得到最终 SHA，避免文档声称包含自身的提交哈希。
V1 标签保留：`handoff-a-20261012` → `e719956d7c82bd6392c25916d3c193be7e4b452e`。
所有运行结果均为 A 自测；业务虚构。成员 B 报告的 V1 95/100 是其提供的结论，A 未获得完整 judge/用例/原始 execution.jsonl，不能宣称 V2 正式 100/100。


## 项目是什么、实际 AI 在哪里

这是在虚构高铁/航班环境里运行的出行助手。它需要查库存、锁住座位、创建订单、查询政策，执行过程可追踪。相比只生成文字的聊天机器人，它会执行工具，并把工具结果用于下一步决策；测试比赛可以据此检查选错工具、错误参数、重复调用、忘记锁座、无来源回答等问题。
模拟环境让输入、库存与错误可重现，不涉及真实票务/资金。Mock 模式由人工规则决定动作，不能说它是实际大模型自主推理；真实模式由远端模型选择工具，当前没有 Key，尚未实测。RAG 帮助提供有编号的虚构政策依据。主循环/工具/业务与模型分开，测试层只读约定 JSON，便于三人并行。

## 环境部署

实际验证 Python 3.12.14；openai 3.29.0、streamlit 1.65.0、fastapi 0.143.0、uvicorn 0.54.0、pandas 3.0.6、pytest 9.1.1，安装 requirements-lock.txt。以下在项目根目录的 Windows PowerShell 运行，不要把 Key 显示到镜头：

```powershell
# 在项目根目录执行；新机器先建立环境并安装冻结依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:PYTHONIOENCODING="utf-8"
$env:AGENT_PROVIDER="mock"
$env:AGENT_USE_HTTP="0"
$env:AGENT_VECTOR_RAG="0"
$env:AGENT_MAX_STEPS="8"
$v2Run = "v2-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0,6)
$env:AGENT_DB_PATH="$PWD\artifacts\runtime\$v2Run\tickets.db"
$env:AGENT_TRACE_DIR="$PWD\artifacts\runtime\$v2Run\traces"
.\.venv\Scripts\python.exe data/seed.py
.\.venv\Scripts\python.exe cli.py chat
```

已有虚拟环境时跳过前两条；系统 python 若打开商店，改用已安装 Python 3.12 的实际可执行文件建立环境。`seed.py` 遇到已有库拒绝覆盖，新目录无需 --reset。每次全新独立用例换新运行目录，环境变量在导入 config 或启动程序前设置。


退出 CLI 输入 q，再启动 Web：

```powershell
.\.venv\Scripts\python.exe -m streamlit run web/app.py
```

首次出现 Email 可留空回车。浏览器打开终端给出的 localhost 地址；默认 8501。终端保持运行，Ctrl+C 停止。端口占用可加 --server.port=8502。页面顶部应该显示 mock，左侧变异“无”；Mock 不需要 Key。
找不到模块时确认在根目录、使用 .venv 的 Python；库已存在就换新目录；无票先看日期/路线/席别与真实 Trace，不能把所有空结果都当作缺陷；页面没有记录先发送消息，离线回放读取配置 Trace 目录，标题仍写默认 traces/traces.jsonl。

## 验收操作（以下功能均已通过 A 自测，人工逐步验收仍待你确认）

每一行发送文字后，检查右侧工具表、args、ok、完整 JSON；连续多轮保持同一会话。换场景可清空会话，但订单/库存不会随之恢复，购买场景重复太多时停服务、换全新运行目录并 seed。

| 场景 | 输入与顺序 | 应看到的结果 | 成功依据/日志 |
|---|---|---|---|
| 有票查询 | 查明天上海到杭州的高铁 | 列出有余票的班次 | query_tickets，kind=高铁/二等座，ok=true |
| 交通切换 | 上条后发送 那机票呢 → 还是高铁吧 → 后天呢 | 机票经济舱，再高铁二等座；后天沿用路线/方式 | 比较连续 3 条 trace 的 kind/seat_type/date |
| 含糊请求 | 换个交通方式 | 询问选择何种方式 | 不执行猜测查询；tool_sequence 为空 |
| 售罄提示 | 清空会话后：查明天北京到上海的高铁二等座 | 目标二等座售罄，建议查其他席别但不承诺有票 | 单次 query，结果余票 0，reply 区别于空匹配 |
| 无匹配 | 清空会话后：查明天上海到成都的高铁 | 没有符合条件班次 | query 返回空，不能说已售罄 |
| 订票 | 订明天上海到杭州的高铁 | 创建待支付模拟订单 | query→lock→create，均 ok，保存 order_id |
| 政策 | 上条后问 锁座后多久必须完成支付？ | 15 分钟并引用 P11 | search_policy，不能 pay/cancel |
| 重复支付 | 支付我刚才的订单。 → 支付 | 首次支付成功，第二次“订单已支付，本次没有重复扣款。” | 两次 pay，第二次预览 duplicate_pay=true |
| 取消与退款 | 在已支付订单后 帮我退掉 | 模拟退款并带政策来源 | cancel_order、手续费/退款/P01；不是实际资金退回 |
| 候补 | 清空会话后：抢明天北京到上海的票 | 虚构监控任务 | query→monitor，正常 stop；只生成凭据 |
| 订单查询 | 查我的订单 | 本人订单列表 | query_order，不能显示其他用户订单 |
| Trace 回放 | 页面下方选择回放记录 | 展示完整历史 JSON | 与发送后的 session/input/tools 相符 |
| 六变异 | 每次只勾一个，按 B 手册对应输入 | 看到日期错误/跳锁座/重复/循环/误路由/缺引用 | 对照 B 手册的实际序列；恢复后新会话 |

stop 只表示循环结束，操作成功还要看 ok、结果与回复。错误时截图保存输入、会话 ID、模式、开关、右侧 JSON；复制当前隔离目录的 traces.jsonl，注明对应行/日期、branch/SHA。保存失败证据，不编辑原记录。页面“完整 JSON”是最终契约记录，长工具预览可截断。

## 5—10 分钟视频分镜建议（这是建议，尚未拍摄）

| 时间 | 操作/画面 | 讲解重点 |
|---|---|---|
| 0:00–0:45 | 标题、模拟环境与团队分工 | A 被测 Agent，B 正式测试，C 验收作品；Mock 边界 |
| 0:45–1:30 | 展示启动命令和页面 provider=mock | 依赖冻结、独立库、零 Key 离线运行 |
| 1:30–2:45 | 查询→机票→高铁→后天 | V2 交通/席别和多轮继承修复，聚焦右侧参数 |
| 2:45–3:30 | 北京上海二等座售罄 | 不把 0 票当可售；其他席别只是待查询建议 |
| 3:30–5:15 | 订票→政策→支付→重复支付 | 工具顺序、政策 P11、模拟幂等；拍 reply+trace |
| 5:15–6:15 | infinite_loop 开关并抢无票班次 | max_steps_exceeded 及 monitor 重复，证明注入仍存在 |
| 6:15–7:00 | 恢复正常、清会话、正常政策检索 | 开关恢复后引用回归，保存独立记录 |
| 7:00–8:00 | 离线回放、V1/V2 对照和真实预检 | 真实待验证，B 正式 V2 成绩待提供 |

适合报告的截图：交通切换前后 args、售罄回复、P11 引用、重复支付 duplicate_pay、8 步截断、完整 Trace 回放、A 自测运行摘要。请截取你实际操作的画面，不能把本文建议称为已经验收/拍摄。
若要展示真实模型，先完成有效 Key 配置及真实隔离测试，再使用实际 trace；不得把 SDK 桩或 Mock 模型字段截图解释为真实模型性能。

## 参赛技术资料的位置与当前完成情况

- 架构和 8 工具：A_V2开发完成报告.md、target/agent.py、target/tools.py。
- Prompt：target/agent.py 的 SYSTEM_PROMPT；Mock/远端协议：target/providers.py。
- 政策与检索：data/policies.md、target/rag.py；支付后端：target/mock_core.py（V2 沿用）。
- 轨迹机制：target/trace.py；接口合作：docs/contract.md（未修改）。
- 五缺陷原因/提交/风险：V1_V2缺陷修复对照.md；过程：docs/v2_development_log.md。
- A 实际证据：docs/evidence/v2/regression/、v2_reproduction/、api_example/。
- 当前完成：A 28 自测、10 冒烟、32 Mock Trace、5 个对照目标及六变异通过；是 A 结果，不能换算 B 正式得分。

当前没有 API Key。`preflight.json` 明确 api_key_present=false、real_model_tested=false、real_trace_count=0：**真实模型待验证**。

已实现 OpenAI 风格 Chat Completions 适配器，SDK 测试桩检查调用 ID/工具结果回传、错误和最大步数，不能算模型自主决策测试。Prompt 已增加 V2 规则，第三方端点是否支持全部协议需实测。

有合法有效 Key 时，由使用者通过安全环境注入 `AGENT_API_KEY`，不要写入源码、文档、录屏或聊天。配置 `AGENT_PROVIDER=openai`、服务方提供的 `AGENT_BASE_URL` 和支持工具调用的 `AGENT_MODEL` 后，重启进程并显式运行：

```powershell
$v2Real = "artifacts/runtime/real-" + [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts/validate_real_provider.py --output-dir $v2Real --run
```

这是实际远端 API 调用，可能产生服务方费用。没有 --run / 没有 Key / provider 不是 openai 时仅预检。8 个独立场景覆盖单轮、多轮交通切换、工具回传、查锁下单、RAG、工具故障、正常停止、强制 MAX_STEPS=1；每个场景使用临时虚构库。上限场景是人为缩小步数的验证，不能据此称模型自然死循环。
每个 result.json 保存输入、完整消息（含工具参数/结果和服务器 call_id）、实际回复/Trace、耗时、调用错误与“完成情况待确认”；finish_reason=stop 不保证业务成功。模型认证/网络失败也会保存失败回复，不能当作成功。Mock 与真实附件放在不同目录，不与 V1 Trace 混用。
协议参考：[OpenAI Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。本次未迁移 API 或新增契约字段。


当前可做 Mock 验收与录屏；正式比赛通过率、测试覆盖率、性能指标和缺陷关闭数必须由 B 给出。C 结合 B 的真实回归结论形成最终作品，不能写“V2 已 100/100”。可选向量 RAG、生产登录、持续候补、真实支付/改签并非本轮完成项。
