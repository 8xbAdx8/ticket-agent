# DeepSeek 接入持续开发记录

日期：2026-10-15。分支 `codex/ticket-agent-deepseek-live`。接手 HEAD `85d457a4f34b4fad848ded4cf9c2d7334813c399`；原有未跟踪展示压缩包保持原样，不加入本次提交。

| 模块 | 文件与原理 | 实际验证 | Commit / 团队影响 |
|---|---|---|---|
| 安全配置/环境 | config.py、deepseek_runtime.py、requirements-deepseek*、gitignore；官方地址/唯一 Key/5 请求持久预算 | 8 项离线 runtime 测试通过，pip check 通过；Windows SQLite 连接清理失败已修正并保留失败日志 | e93a0e5746039d9d601c30e3129abee644203957；B 用独立环境，C 不展示密钥 |
| 独立连通检查 | scripts/check_deepseek_api.py、3 项脚本控制流测试；余额/短 Hello/两个工具，成功失败跳过分类 | --run 实际跳过，0 在线请求；3 个脚本桩测试通过 | 622d665526f14335b1d219c197d9f608142ce600；B 检查 JSON status，不仅看退出码 |
| 框架/会话/Trace/Web/CLI | Agent、LangChainAgent、runtime、Web/CLI、SDK 10 项自测、离线复现脚本；真实 SDK 接已有 create_agent | 新环境 88 通过；原 V3 78 通过/10 跳过；原 V2 35 通过/53 跳过；10 入口检查、11 轮 8 工具 Mock、5 轮 Mock 浏览器通过 | d40b005ebdad2a57c8a09aa86d97911e1203f344；正常契约不变，错误/未知 Token 独立异常；B 正式规则未改 |
| 交接与核对 | 本生成脚本、5 份交接报告、当前结果摘要、机器核对脚本 | 依据保存日志/元数据生成，不发送 API | 后续文档提交，最终 SHA 在最终回复/ git log 提供 |

早期问题记录：1. SQLite 的 with connection 不关闭连接，Windows 临时 DB 清理失败，改为显式 closing；2. 原 V2 未装 httpx，新测试应 skip 而不是 import error；3. 10 月 13 日 DB/Trace 哈希在接手前已有变化，保留用户当前数据，新增 --baseline-manifest 检查本次 356 文件；4. 源码插入安全检查导致行号改变，A 浏览器代码导览检查改为动态行号，不更改 B 判定。

证据索引见 docs/evidence/deepseek/handoff_summary.json。源码提交对应上述文件和实际命令；后续仅文档与核对补充。没有真实 API 成功/失败结果；有无 Key 检查及明确跳过，不把 MockTransport 与真实 API 混计。尚未完成：真实只读闭环、在线多轮与安全、其余 6 工具开放、思考协议、正式 B 评价和 C 验收。
