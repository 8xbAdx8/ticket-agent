# V3.9.5 UI测试报告

新V39全套：{'passed': 203, 'failed': 0, 'skipped': 0}。新增5项测试位于tests/v39/test_v395_cards.py：模型分页元数据空值不发送至严格Schema；输入23:50→30:51，预期次日06:51/421分钟；真实ISO区间7小时1分钟/跨日+1；缺时间不能推测时长；HTML转义/不造票价库存；默认辅助查询与分页可见页去重且原列表不改、独立车站保留。

Edge覆盖单/多卡顺序、实际出发到达时间/59分钟、109/20分页、10站按需展开、前后翻页、右栏不重复、技术码隐藏、原四入口及无整页溢出。无报价不生成价格；已有库存带模拟标识。没有新交易选择动作，确认机制由原198项服务/权限/事务测试覆盖，不能当成新卡片完整交易浏览器验收。

旧完整回归{'passed': 1441, 'failed': 11, 'skipped': 1} + 199子测试；逐ID对照V394原JSON一致，完整失败和唯一skip见 `artifacts/runtime/v394-implementation-v395-20261104/verification.json`。无新增skip/xfail或旧断言变更。日志与JUnit：suite-final/和regression-final/results/。只读核对新查询库{'v39_quotes': 0, 'v39_proposals': 0, 'v39_orders': 0, 'v39_transactions': 0}，FK错误[]；不连接被冻结的旧产品数据库。
