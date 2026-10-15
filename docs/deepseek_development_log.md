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


## 2026-10-16：已有 Live 证据审查与交接（无新API）

- 接手4ac1b756a1d8e652e7a9999bf43e1ae3b65701a5；审查/回归提交190e723f7d8fa1b54e5ce5123a1b87c07af9fcca。分支不变，原V1/V2/V3标签不移动。
- 读取用户已运行的api-20261016-001224-2c3484：Hello + 查票2请求 + 政策2请求，合计5生成；余额GET另1次。输入4796、输出563，费用未知；额度5/5，不增加。
- scripts/audit_deepseek_live.py只读核对声明调用、执行事件、公共Trace、回复事实、隔离SQLite与账本；原356文件及真实记录哈希不变。
- scripts/run_deepseek_review_offline.py清除真实Key并限制非回环网络；新环境88通过；旧V3 78通过/10跳过；旧V2 35通过/53跳过；Mock入口检查通过。0外连尝试，原账本/361文件不变。
- scripts/check_ticket_handoff_security.py检查工作区、ZIP/DOCX和可达Git历史；无凭据发现。旧ignored脚本只含私钥头比较字面量，不是实际私钥。
- 新增A审查、B正式测试交接、C历史Live回放说明；原五份报告加当前状态，旧原文清晰归档。当前仓库没有B完整100条源码，只能说明复用，不冒充正式执行。
- 发现并保留LIVE-REVIEW-01：只读查票答复仍邀请办理订票；交B定级，当前不修功能。另记录旧模式/验证标签和历史报告生成器的过时状态风险。
- 只提供原始Live隔离库只读快照（2100库存、0锁、0订单），不替代原库。CLI只读历史回放已执行；无新真实API。
- 后续文档/打包提交的最终SHA以Git历史和PACKAGE_MANIFEST为准。本轮可在安全通过后仅推送当前分支，不合main、不推标签、不强推。

## 2026-10-16：只读冻结前最小质量修复

详见 [专项持续记录](readonly_freeze_development_log.md)，源码提交 `e216fdf57ec8f34b84134ba2b30b05e5d6ff5985`。正常返回结构未改；专用只读Prompt、输出拒绝、失败工具留证与状态文案已离线验证。A自测102通过，旧V3 78通过/24跳过，旧环境35通过/67跳过，10冒烟含六变异通过；0新真实API、预算不变、旧证据不覆盖。B正式100条与新Prompt联网回归尚未执行。
