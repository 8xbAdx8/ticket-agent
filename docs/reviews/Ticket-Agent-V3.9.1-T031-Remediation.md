# T031：失败退款尝试与重试整改

原实施将同一提案重放视为第二次尝试，不能证明两个独立提案竞争时正式失败记录的语义。本次保留原矩阵、旧源码快照与旧失败批次，版本化修订T031并新增T069–T072及技术异常检查。

## 实现与可观察状态

1. 提案冻结所选乘客、有效价格快照、毛额、手续费、净退款及订单quote/hold。退款动作允许最多两张独立待确认卡，其他动作保留原唯一门禁。
2. 首次业务失败提交正式refund_request、FAILED refund_item、FAILED REFUND交易及分摊，回执保存于幂等记录。订单票面、ACTIVE状态、库存、成功付款/退款/手续费均不变。失败尝试金额表示当时的请求意图，不表示已经退款。
3. 同一提案/参数重放直接返回原失败回执；同键异参报IDEMPOTENCY_CONFLICT。
4. 新提案使用新幂等身份，可以成功退款；原FAILED行保持原值，不覆盖、不转成成功。
5. 两个独立提案通过两个客户端进程同时请求唯一确认Worker。SQLite BEGIN IMMEDIATE串行化交易，最多一个成功；败方基于冻结意图提交正式FAILED记录。成功唯一索引继续限制每乘客一次成功退款。此测试不声称部署了多个独立确认Worker。
6. SQL技术故障注入在交易插入处，整事务回滚：请求/明细/账本均不残留，token未消费，订单、库存和原回执不变。
7. 新数据库触发器要求FAILED或SUCCEEDED退款完成前，有同状态同订单REFUND交易、完整分摊、明细总额/手续费/净额守恒；仅页面拒绝事件不算正式退款历史。

## 证据

- 测试：`tests/v39/test_matrix.py`的T031；`tests/v39/test_v391_lifecycle.py`的T069、T070、T071、T072及技术故障测试；`tests/v39/test_v391_constraints.py`。
- 新批次：`artifacts/runtime/v391-d9-lifecycle-20261103-150639/batch-05/pytest.log`、`results.json`、`junit.xml`。
- 真实SQLite表探针：该目录`db-probes/V39-T069.json`至`V39-T072.json`；包含请求、明细、交易、分摊、库存、事件和有效价格快照。
- 原实现冻结副本：本批`baseline-source/`；原历史运行目录`artifacts/runtime/v39-implementation-20261103-130321/`保持原件。

验证范围为本地模拟服务、SQLite约束和开发测试；未调用真实支付或模型，未完成独立审查和用户验收。
