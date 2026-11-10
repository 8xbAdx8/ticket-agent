# AI Test Quality Gate Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0；34项未跟踪/已修改工作区成果保留。未 reset/clean/checkout/stash；未 commit/push/merge/tag。

## 强制矩阵

查询需参数/结果/分页；建单需 proposal、确认、order、ACTIVE hold；支付需 PAID/金额/PAYMENT；退款需乘客/item/净额/手续费/REFUND；改签需原/新车次/报价/差价/新 hold；取消需状态/库存/幂等；权限/多轮/RAG/异常按真实证据检查。

## 本轮真实拦截

- DeepSeek：`unknown tool argument` / `missing required argument` / `type enum mismatch`，REJECTED。
- Qwen：`unknown fields`、`invalid registry tool`、`deterministic checks required`，REJECTED。
- 只有 `metrics.foreign_keys_ok` 的弱用例测试 REJECTED；支付无 `test_user` confirm 的用例 REJECTED。

质量 PASS 不能等于执行 PASS；本轮没有质量 PASS 的真实候选。
