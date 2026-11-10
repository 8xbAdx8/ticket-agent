# V3.11 覆盖率与分母

日期：2026-11-10（Asia/Shanghai）。HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`。整体 **PARTIAL**；未提交、未推送。

| 模式 | 工具 | 流程 | 状态 | 转换 | 全部非重放轮次Trace |
|---|---:|---:|---:|---:|---:|
| live_agent | 9/11 | 4/5 | 2/6 | 3/10 | 11/11 |
| sdk_stub_agent | 11/11 | 5/5 | 6/6 | 10/10 | 100/101 |
| browser_sdk | 6/11 | 3/5 | 2/6 | 2/10 | 5/5 |


Live原始17行：14通过、3失败、0未评分；失败包含原Oracle误报1行（单独重评，不删除）及Token保护截断2行。任务断言PASS不代表整轮PASS。SDK原始142行101通过/40失败/1未评分；40行含预期故障与负例，不能称40个pytest失败；专项76个pytest全部通过。

通过轮次的Live Trace为8/8，全部Live非重放模型轮次11/11。SDK全部Trace100/101，其中1条为有意在audit产生前抛异常的测试，独立run错误保留；不从分母删掉。

## 细分矩阵边界

- 11工具正常执行均有SDK原图证据；Live仍缺完整改签与取消。
- 新增32个原Agent非法参数测试：10种缺必填（railway_get_order无必填，明确N/A）、11种错误类型、11种未知参数。每项检查无订单/hold/交易副作用。
- 服务故障注入主要针对inventory；没有证明11个工具各自8种维度全部覆盖。此子矩阵PARTIAL，不能用11/11 distinct计数代替88格完成。
- 7个安全维度没有完整的本批次逐场景计分，标记NOT_SCORED/PARTIAL；已验证未经确认不建单、拒绝无副作用、模型无确认身份、重复确认/请求及只读恢复等子路径。
- RAG6类目标NOT_RUN；旧回归RAG测试不等于本轮Agent回答质量验收。
- 多轮SDK及Live存在；回复一致性仅有限显式业务声明规则，非通用语义判断或人工校准LLM Judge。
- 模型生成、候选质量、人工批准、工具执行、可信确认、数据库结果、恢复结果分别记录。重评只解释误报，不改变旧运行状态。

完整逐项ID见R3 results.json与coverage-final.json中的source_run_files；原始SDK记录来自R3冻结副本。模式不混算正式成绩。

## 证据身份

`artifacts/runtime/v310-v311-20261110-implementation/authorization.json`；SHA256 `b5519df9838dcee7e66066093f9ffdce9144c29933d16ab95347c1420a267bf5`

`artifacts/runtime/v310-v311-20261110-implementation/coverage-final.json`；SHA256 `d74fd76a772f23fdf9cf07b2478bac1a2ea3d170ec66532b81523955bf76a425`

`artifacts/runtime/v310-v311-20261110-implementation/budget-final.json`；SHA256 `239d9bb23b3ffebbe888a49ad0fa6e5aefe218042ad825b3d3696c513dc2333f`

`artifacts/runtime/v310-v311-20261110-implementation/database-verification.json`；SHA256 `0cc7acd2bd8a1f57b4257d36781ab578336a3b345b10dabec39d4d3f5bdd2996`

`artifacts/runtime/v310-v311-20261110-implementation/regression-comparison.json`；SHA256 `c017e1a47884bdd198357bf320a3bcda48ec82ef379c5b09ee43f966ba8c6a45`

`artifacts/runtime/v310-v311-20261110-implementation/protection-final.json`；SHA256 `91740a2751c4bc66d6b992b6159462639c99dcd64f1d35a6e7176fbe43a98ef3`
