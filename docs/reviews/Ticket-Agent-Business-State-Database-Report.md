# 业务状态统一：SQLite核验

这是开发验证，不是独立审查。原业务政策与数据库Schema未改。

证据：`artifacts/runtime/v394-implementation-business-state-20261104-220744/database-final-probe.json`、`browser-error-proof-02/results.json`中的databaseProbes、`suite-post-live/results.json`。所有测试用全新隔离库，冻结产品库只Hash未连接。

| 流程 | 已提交订单 | ACTIVE / REFUNDED | 支付分 | 退款分 | 费用分 | 净支付分 |
|---|---|---|---:|---:|---:|---:|
| 三人支付 | PAID | 3 / 0 | 9000 | 0 | 0 | 9000 |
| 退一人 | PAID | 2 / 1 | 9000 | 2400 | 600 | 6600 |
| 剩两人改一等座 | CHANGED | 2 / 1 | 12000 | 2400 | 600 | 9600 |

最终 `12000-2400=9600=9000有效票面+600成功手续费`。一笔PAYMENT9000、一笔REFUND2400、一笔CHANGE_SUPPLEMENT3000；改签退差不是乘客退款，相关旧测试保留。当前hold.remaining_quantity=2，已退款明细不进入新hold；新旧区间事件/主库存原件见探针。FK检查空。四个浏览器订单均得到相同守恒结果，且只各有一笔支付。生成报价阶段无订单；原确认前无创建订单；用户确认才提交。

新增测试真实检查数据库归属、读取不触发过期写入、重复确认返回原回执、辅助审计失败不把已支付改成失败、取消不等于失败、撤销权限后确认被拒且允许撤回、错误操作不冒充工具已执行、读取dict/list一致、截断模型不重放交易。337项中亦包含已有并发/退款失败/幂等/事务回滚/双引擎/D9/P01测试，未降断言。

真实模型原第5条消息回答截断时，库已经CHANGED。新只读核验前后金融业务表SHA指纹完全相同，见`live-deepseek-readonly-03/results.json`，未重复支付、退款或改签。

状态：DATABASE_VERIFIED（本轮隔离业务范围）。原simulation-v391.sqlite来源问题仍BLOCKED，未在该库重复任何交易。
