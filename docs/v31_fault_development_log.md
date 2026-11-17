# Ticket Agent V3.1 缺陷注入开发记录

日期2026-10-18。接手94efc0c，工作分支codex/ticket-agent-v31-live-faults。未跟踪的原展示ZIP保留。先建立622文件保护清单，再编辑；另保护25个B原判据/结果。最终均未变化。

| 模块与提交 | 文件/工作原理 | 实际验证命令与结果 | B/C影响与未完成 |
|---|---|---|---|
| b7b6363 统一定义与审计 | target/fault_injection.py、tests/test_fault_injection.py；复制参数、记录原值/变异值，不生成模型响应 | python -m unittest tests.test_fault_injection -v，7通过 | 新旁证不改公开契约；当时框架集成待完成 |
| ae7bce8 实际工具路径与沙箱 | Agent、providers、langchain_agent/model、runtime、create_fault_sandbox、新SDK桩测试 | python -m unittest tests.test_live_faults tests.test_agent -v，19通过 | 六项接入；真实验证当时待做；旧Provider行为保留 |
| fe9bafb Web/CLI | 页面开关传入Agent配置，保存旁证并显示状态；CLI接受JSON配置 | UI/SDK/展示23测试通过，Web开关→真实SDK桩→执行器单独1测试通过 | 原会话/历史/JSON/工具表保留，切换配置新建内存会话 |
| 5af85b6 运行器与统计 | verify_live_faults.py、summarize、错误包装修复、统计测试 | 只读质量14测试及故障24测试通过；完整离线回归149通过，B原判据101/100/55全部通过 | 后端failure flag即使没有error字段也必须给模型错误结果；首次失败留档 |
| c6b4fdb 精确场景与沙箱标记 | Web区分只读/全工具沙箱，追加指定车次场景；不改首批输入结果 | UI/统计9测试通过；指定场景后续实际3场景9次API | 不把模型澄清记作注入成功 |
| 03ef15f LangChain Mock写变异隔离 | middleware仅对新框架写变异检查full_sandbox；Legacy不变 | tests.test_live_faults，18通过 | 防止新开关在原库执行写变异 |
| a1bc221 B独立判定汇总 | scripts/summarize_faults.py，合并独立assessment不改原JSONL | 两个实际旁证文件离线汇总通过，缺正式判定两种率为null | B给出质量判据和判定后才可出正式检出/恢复率 |
| fc5bc46 审计边界 | prepared不计成功，单步未重复不计循环成功；CLI准确标记沙箱 | 28项故障测试通过；最终SDK完整153通过，旧V3 102通过/51跳过，旧V2 51通过/102跳过，10项冒烟通过 | 新增2项边界测试，只做离线补验，无新增API |

最终回归命令：`.venv-deepseek/Scripts/python.exe scripts/verify_v3_def06_def07_offline.py --b-root <B原始目录> --baseline artifacts/runtime/v31-faults-20261018/regression-baseline.json --out artifacts/runtime/v31-faults-20261018/delivery-regression`。SDK151通过；旧V3 101通过/50跳过；旧V2 50通过/101跳过；10入口通过；A复用B原判据Legacy101/101、LangChain Mock100/100、Mutation55/55、专项44通过/3 N/A；0外连尝试，B原件不改。

最后仅修改变异审计边界及CLI标签、增2项测试，再执行 `scripts/run_deepseek_review_offline.py --out artifacts/runtime/v31-faults-20261018/post-review-regression`，SDK153通过，旧V3 102通过/51跳过，旧V2 51通过/102跳过，冒烟通过。该补验未重跑B评分、未发送API。

真实请求由用户本轮明确授权“不限制你的真实请求”后执行，仍每场景上限5次、零重试，不改正式5/5账本。首批9场景18请求，补充3场景9请求，共27，输入42038/输出3733 Token，费用未知。日期、路由、引用、重复先触发；跳锁和循环先未触发，指定班次/授权后实际触发。skip后端拒绝是预期安全结果，不伪装正常成功。唯一模拟正常对照生成1锁/1待支付订单，无付款或取消。

开发中失败日志：原始测试用句未匹配保守授权语法；测试连接未显式关闭；后端失败缺error包装；直接按模块运行旧测试时其绝对import不适用（使用unittest discover原运行方式通过）。均如实存development-attempts，未覆盖成通过。

证据公开摘要和实际模型原文在docs/evidence/deepseek/v31-live-faults-20261018。内部推理、认证头、Key不存证；原库/账本/Trace均保留。四份A/B/C交接与对照表已同步。

遗留：B正式Live独立评级、更多随机样本、并发、思考模式及完整八工具真实行为未验证。GitHub默认代理不可达，直接网络连接重置，连接器也未找到可访问仓库；推送另按最终结果记录，不合main、不移动标签。
