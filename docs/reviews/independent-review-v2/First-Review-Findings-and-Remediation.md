# V2 首轮独立审查发现与整改索引

2026-11-09。此文件由实施者整理独立子 Agent 的只读反馈，不代替最终审查意见。审查者未修改实现、未执行写库测试、未调用真实 API。

首轮裁决 **BLOCKED**，对应旧 `final-regression/` 冻结快照。该批次1875通过、11失败、1跳过及199子测试的证据全部保留；不用于宣称整改后代码通过。

| 发现 | 等级 | 原证据 | 整改 |
|---|---|---|---|
| V310提前返回，工具摘要、P2断言、前置条件和顺序可与实际计划矛盾仍PASS | P1 | `scenario_generator.review`；不存在的railway_lock_seat、未执行PAY、倒序和PAID前置均可放行 | 绑定摘要/顺序；未支持P2断言和非空前置阻止批准；畸形字段REJECTED |
| confirm只验返回status及全局守恒，PAY假PAID但DB未支付可能假通过 | P1 | `scenario_plans.confirm`、`scenario_v310`；原missing_confirmation在CREATE即失败，不能证明PAY防假 | 自动绑定proposal、完整幂等回执、订单、hold、付款/退款/改签明细；新增仅PAY阶段假成功故障 |
| 模型质量读取当前候选，人工编辑后可能被当作模型质量 | P2 | `scenario_quality.model_comparison`；当前10候选未编辑，既有实验未受污染 | UI读取不可变CREATE原件；增加编辑后比较反例 |
| 离线执行继承外部数据源环境，缺硬断网 | P2 | `scenario_v310`及runtime数据源装配；未发现已经发生外连 | 固定Fixture、关闭铁路查询服务、局部socket/DNS阻断；恶意继承环境反例 |
| Trace仅检查文件存在，不能证明同一执行链 | P2 | `scenario_quality.coverage` | 按execution_id/run_id核对每步started/finished事件；空壳或错run文件不计入 |
| 候选畸形expect/摘要类型可能使UI审核崩溃 | P2 | 复审纯函数反例 | 审核返回REJECTED、质量页可处理；新增反例 |
| 旧CREATE/PAY幂等回执与推进后的当前订单状态不同 | P2 | 复审状态推演 | 独立replay_proof核对原回执及前后业务表不变；不把历史回执当当前状态 |
| 重放回执只比ID可能遗漏篡改金额 | P2 | 复审真实退款快照内存变异 | 完整saved==output比较，退款金额+1反例拒绝 |

最终证据改用 `unit-r7.xml`、`adapter-r4-final.json`、`mutations-r4.json`、`final-regression-r4/`、`browser-r3/`。中间失败批次和前几轮完整回归不覆盖、不删除。

仍未把局部规则覆盖、QR的PNG元数据核验、确定性Mock回复检查等同于完整语义质量、二维码像素解码或Live Agent端到端验收。正式103仍BLOCKED，真实候选全部待用户审核。
