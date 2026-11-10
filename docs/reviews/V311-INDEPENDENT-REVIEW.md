# V3.11 最终独立只读审查

审查者：当前对话显式委派的 `independent_v2_review` 子Agent；不是实施者自测、不是外部人工验收。本文根据其最终对话回传整理；审查者无文件修改、数据库写入或API请求。

**限定裁决：CONDITIONAL PASS；完整项目 PARTIAL；用户 ACCEPTED 待定。**

## 独立方法与代码绑定

源码审阅、只读SQLite、原日志、SHA及纯内存反向检查。HEAD/分支/暂存区核实不变；当前10个关键源码/测试与R3冻结副本逐字节一致。未沿用V2验收结论。

## 初审发现与复审

| 初始P1 | 复审结论 |
|---|---|
| 库存只与事件自洽 | 完整hold/quote/区间身份核验已补，残留sold反例拒绝 |
| 缺任务完成断言也PASS | 无Spec NOT_SCORED；任务/不变量/错误/整轮分别记录 |
| 不同调用拼接正确参数和成功 | 参数与同一次ok=True调用绑定，反例失败 |
| 失败退款掩盖已完成业务 | before/after、失败明细及交易、资金/库存保留核验已补 |
| 预算初始化中断缺guard | 原子DDL、每事务核验、原accounting接LiveBatch、失败关闭 |
| 拒绝只看提案取消 | decline_proof保证业务表不变，新增订单等反例拒绝 |
| 原失败从覆盖分母消失 | 互斥整轮统计保留原17行及3FAIL，重评另列 |

P2亦修复：P01联动、旧audit复用、扩额审计原子性、金额0/未来提示误报、退款成功证据、UI整轮结论及预算文案。

## 独立核对的结果

- R3 1971/11/1另199子测试，退出1；新V311 76项全部通过；旧失败/Skip逐ID无变化。
- 5587项现场重新SHA：5586一致，唯一预算测试差异与用户批准SHA一致。
- Live四个数据库：DS pilot未付款、Qwen pilot唯一PAYMENT9000；DS新场景PAYMENT9000/REFUND2850/fee150/net6150/2ACTIVE；CHANGE待确认；Qwen新场景只有CREATE提案，无订单。
- 两次observed_token_budget_exhausted：taskPASS但passedFalse，未确认挂起提案，未扩单轮预算。
- Live原始17行14PASS/3FAIL/0未评分；旧误报重评另存；Live9/11工具、4/5流程、2/6状态、3/10转换。
- 账本39（DS24/Qwen15），Token320985（210954/110031），未决0，自动重试0，费用UNKNOWN。
- r8浏览器64/64、8规格真实主题，PageError0、Console24/网络24；另读浏览器实际数据库PAID及唯一PAYMENT9000，末条虚假成功被拒绝。

## 保留条件

回复一致性有限规则；Live完整改签/取消/连续退款未完成；RAG、真实HTTP故障、长上下文与吞吐未完成；SDK故障不冒充HTTP真实异常；Trace存在不等于语义正确；用户及外部人工验收未完成。旧103仍BLOCKED。

本裁决只覆盖有证据的工程及验证范围，不授权继续调用API、确认旧提案、提交或推送。初审BLOCKED与整改过程保留；条件通过不能扩展为项目COMPLETE。

## 证据身份

`artifacts/runtime/v310-v311-20261110-implementation/authorization.json`；SHA256 `b5519df9838dcee7e66066093f9ffdce9144c29933d16ab95347c1420a267bf5`

`artifacts/runtime/v310-v311-20261110-implementation/coverage-final.json`；SHA256 `d74fd76a772f23fdf9cf07b2478bac1a2ea3d170ec66532b81523955bf76a425`

`artifacts/runtime/v310-v311-20261110-implementation/budget-final.json`；SHA256 `239d9bb23b3ffebbe888a49ad0fa6e5aefe218042ad825b3d3696c513dc2333f`

`artifacts/runtime/v310-v311-20261110-implementation/database-verification.json`；SHA256 `0cc7acd2bd8a1f57b4257d36781ab578336a3b345b10dabec39d4d3f5bdd2996`

`artifacts/runtime/v310-v311-20261110-implementation/regression-comparison.json`；SHA256 `c017e1a47884bdd198357bf320a3bcda48ec82ef379c5b09ee43f966ba8c6a45`

`artifacts/runtime/v310-v311-20261110-implementation/protection-final.json`；SHA256 `91740a2751c4bc66d6b992b6159462639c99dcd64f1d35a6e7176fbe43a98ef3`


## 最终补充证据（2026-11-10）

主SDK浏览器r8为64/64，补充控件/历史r7为24/24及16张PNG，两批分别计量，不合并成完整功能覆盖率。主批PageError0/Console24/网络24；补充批PageError0/Console16/网络16，外部字体图标均主动阻断。共25张最终截图，深浅主题真实不同。截图中的SDK批次11请求/165Token是合成记账，不属于真实39请求/320985Token。

批量审批实际数据库有3条APPROVED：原Mock场景及本次两个可批准夹具；审批由脚本代表测试用户点击，仅用于Mock/确定性夹具，不是外部人工身份核验，也未自动批准真实AI候选。details-r5完成5项后定位超时，整批仍未完成；其批量审批子证据由只读SQLite和history旁证，不把该失败脚本改PASS。

独立补充审查确认invalid_parameters/full_refund仍PENDING且原件重新review为REJECTED。这是既有DSL参考夹具与准入门禁不兼容，阻塞完整AI候选业务闭环验收。手工预审Live场景、SDK支付和两个合格夹具均不能替代该缺口。本轮未修改旧执行器或降低门禁；限定CONDITIONAL PASS/项目PARTIAL不变。

证据 `artifacts/runtime/v310-v311-20261110-implementation/browser-r8/results.json`；SHA256 `ba3da5ded63b734172534cd3de30eb934fa3b39c2866f578bf772d34fea24e2d`。

证据 `artifacts/runtime/v310-v311-20261110-implementation/browser-details-r7/results.json`；SHA256 `fafa843b9b51a8119fccd4ac2cf75c06fe5d719cc0f3e408180d3a720f28a622`。

证据 `artifacts/runtime/v310-v311-20261110-implementation/browser-supplement.json`；SHA256 `7fe37d6521745afd24f4cb723a37789d56dd2cbc3b8781d91cab199b98f1eac3`。

证据 `artifacts/runtime/v310-v311-20261110-implementation/browser-candidate-verification.json`；SHA256 `83ab44038e2f5454d9e205db153746b125240ad537f648444fe14f08d43171e4`。

证据 `artifacts/runtime/v310-v311-20261110-implementation/approved-test-id-mapping.json`；SHA256 `302d9b5b60d8b82db60875595d377a66e6d1c16107a890cb4d9b0c3055f85430`。

