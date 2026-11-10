# V3.11 故障注入与恢复

日期：2026-11-10（Asia/Shanghai）。HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`。整体 **PARTIAL**；未提交、未推送。

## 实际验证

| 故障 | 注入点 / 独立验证 |
|---|---|
| 模型超时/畸形 | 已初始化原模型类_generate抛异常；原Agent错误、DB无订单，后续新只读查询恢复 |
| 工具超时/错误 | 原Service.inventory方法边界；工具失败不当成功，后续只读查询恢复 |
| 数据库失败 | 原_create写入后、事务提交前抛异常；真实SQLite订单/hold/交易全部回滚 |
| 部分业务失败 | 原退款故障分支；FAILED请求/明细/交易保留，库存与成功金额不变，新提案成功且旧失败仍存在 |
| 重复请求 | 相同Conversation request_id重放，无新增HTTP或工具执行；重复确认返回原回执 |
| 中途断开 | 已保存会话只读恢复，发送被拒绝，业务状态SHA不变；不恢复Secret |
| 用户拒绝 | 原确认入口approved=False，提案取消，独立对比全部业务表无副作用；之后禁止确认该提案 |
| 真实Token保护 | 双模型各一新轮次被原单轮保护截断；整轮FAIL且未执行待确认操作，无自动交易重试 |

## 不能扩大解释的边界

模型故障是在SDK模型方法边界注入，不是真实网络超时或HTTP畸形JSON解析验证。duplicate/mid_disconnect是显式测试驾驶器动作，不是隐藏后台故障。技术回滚和业务FAILED分别判定，不能用UI拒绝事件冒充refund_request历史。

故障原始marker在R3冻结副本 `artifacts/runtime/v310-v311-test-*/cases/*/fault-*.json`；逐测试身份test-source.json；run-NNN.json保留before/after、原始events及原始结果。失败行可被负例测试预期并检出，不冒充业务成功。专项76/0/0包含纯函数/预算/正常流程与负例，并非76条Live业务成功。

## 技能使用

- eval-audit：基于实际V310旧证据审查独立Oracle、审批、分母与伪通过。发现并修复库存残留、缺任务断言、失败凭据及统计遗漏；没有引入未校准LLM Judge。
- write-code-eval：每个规则有输入、预期、失败条件；补真/假/边界反例。文字规则仅有限显式业务声明，通用语义NOT_RUN。
- 未采纳：不把相似度当业务正确性；不为生成追问/评分额外调用模型；不把Skill建议当已验证事实。

## 证据身份

`artifacts/runtime/v310-v311-20261110-implementation/authorization.json`；SHA256 `b5519df9838dcee7e66066093f9ffdce9144c29933d16ab95347c1420a267bf5`

`artifacts/runtime/v310-v311-20261110-implementation/coverage-final.json`；SHA256 `d74fd76a772f23fdf9cf07b2478bac1a2ea3d170ec66532b81523955bf76a425`

`artifacts/runtime/v310-v311-20261110-implementation/budget-final.json`；SHA256 `239d9bb23b3ffebbe888a49ad0fa6e5aefe218042ad825b3d3696c513dc2333f`

`artifacts/runtime/v310-v311-20261110-implementation/database-verification.json`；SHA256 `0cc7acd2bd8a1f57b4257d36781ab578336a3b345b10dabec39d4d3f5bdd2996`

`artifacts/runtime/v310-v311-20261110-implementation/regression-comparison.json`；SHA256 `c017e1a47884bdd198357bf320a3bcda48ec82ef379c5b09ee43f966ba8c6a45`

`artifacts/runtime/v310-v311-20261110-implementation/protection-final.json`；SHA256 `91740a2751c4bc66d6b992b6159462639c99dcd64f1d35a6e7176fbe43a98ef3`
