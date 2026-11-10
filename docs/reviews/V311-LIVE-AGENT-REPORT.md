# V3.11 双模型真实Agent验收

日期：2026-11-10（Asia/Shanghai）。HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`。整体 **PARTIAL**；未提交、未推送。

## 真实结果

| 场景 | 实际完成 | 未完成 |
|---|---|---|
| DeepSeek pilot | 静态查询、报价/建单提案、确认建单 | 支付提案完成后Oracle误报，未确认支付；原FAIL保留 |
| Qwen pilot | 查询、建单、确认模拟支付，唯一PAYMENT9000分 | 后续生命周期未在该进程继续 |
| DeepSeek新场景 | 建单、支付9000、退一人2850、手续费150；2ACTIVE，PAID，net6150 | 改签提案后单轮Token保护，未确认改签/最终退款 |
| Qwen新场景 | 查询/库存/报价/建单提案 | 单轮Token保护，未确认建单；无订单和交易 |

所有车站、车次、时刻来自项目本地GTFS；库存、报价、订单及资金均为本地模拟。模型自主选择工具，可信test_user通过原确认入口执行已授权的合成业务。未注入RailwayDemoProvider，不是DSL回放。

## 用量与预算

DeepSeek24请求/210954Token；Qwen15请求/110031Token；合计39请求/320985Token。prompt/completion逐请求见账本；39条响应均可结算，未决0、重试0。费用UNKNOWN；不使用未知单价填实际费用。50HTTP总限/各25及输出2048实际设置保留，320000预警触发。剩余11请求未用，不授权后续自动批次。

## 原始失败

DeepSeek pilot把“已支付0分”和未来“会明确提示…”误判支付成功。新Oracle按明确单订单的已提交DEBIT及paid_total核验金额，并限定未来提示模板；真假配对测试和独立复算通过。原FAIL、原件SHA及新重评分开保存，旧订单仍PENDING_PAYMENT。

其余两条为真实 `observed_token_budget_exhausted`：原Agent按单轮已观察Token加最大输出，阻止继续模型调用。不是HTTP50/累计Token硬限耗尽，也不是支付/退款失败。工具task_status=PASS但最终回答没有完成，整轮False。当前未修改原单轮模型/工具/Token边界。

原pilot进程结束后不恢复Secret；后续只在新数据库运行。失败后没有自动重试、没有确认挂起提案、没有重建账本绕限。

## 可复现命令与限制

```powershell
.venv-v35/Scripts/python.exe -B scripts/run_v311_acceptance.py --live --root artifacts/runtime/v310-v311-20261110-implementation
.venv-v35/Scripts/python.exe -B scripts/run_v311_remaining.py --remaining-live --root artifacts/runtime/v310-v311-20261110-implementation
```

这是实际历史执行命令，不能直接重跑以继续消费。脚本检测既有start/请求记录并拒绝重复启动；复审应先只读原件。新一批真实测试须用户另行确认范围，不重置旧账本。

## 证据身份

`artifacts/runtime/v310-v311-20261110-implementation/authorization.json`；SHA256 `b5519df9838dcee7e66066093f9ffdce9144c29933d16ab95347c1420a267bf5`

`artifacts/runtime/v310-v311-20261110-implementation/coverage-final.json`；SHA256 `d74fd76a772f23fdf9cf07b2478bac1a2ea3d170ec66532b81523955bf76a425`

`artifacts/runtime/v310-v311-20261110-implementation/budget-final.json`；SHA256 `239d9bb23b3ffebbe888a49ad0fa6e5aefe218042ad825b3d3696c513dc2333f`

`artifacts/runtime/v310-v311-20261110-implementation/database-verification.json`；SHA256 `0cc7acd2bd8a1f57b4257d36781ab578336a3b345b10dabec39d4d3f5bdd2996`

`artifacts/runtime/v310-v311-20261110-implementation/regression-comparison.json`；SHA256 `c017e1a47884bdd198357bf320a3bcda48ec82ef379c5b09ee43f966ba8c6a45`

`artifacts/runtime/v310-v311-20261110-implementation/protection-final.json`；SHA256 `91740a2751c4bc66d6b992b6159462639c99dcd64f1d35a6e7176fbe43a98ef3`

`artifacts/runtime/v310-v311-20261110-implementation/pilot-summary.json`；SHA256 `32b8cba4ab131fbf0ff05ddc7fac3205509eb16e9e2be4bcecf607ce48df6407`

`artifacts/runtime/v310-v311-20261110-implementation/pilot-reassessment-v2.json`；SHA256 `079a3f49b1c83399631ed666f6a86c6b2c903dfaf66662e76dd9a92696088f41`

`artifacts/runtime/v310-v311-20261110-implementation/remaining-summary.json`；SHA256 `f75525e876cc33d27fc0fb637738f2e4d3f3e87f8638100aea99055c552e46ae`
