# AI 测试体系 V2 独立审查任务

仓库：`D:\codexproject\ticket-agent`。开工HEAD：`c1620cb4e9e8df094494fc77ef3f0d07ef9928c3`，分支 `feat/ticket-agent-v36-stabilization`。未提交，不准据此HEAD假定工作区干净。

只读审查，不修改源码/测试/配置/数据库，不调用模型、Embedding、LangSmith、铁路或支付服务。审查者与实施者分离；子Agent审查不等于外部人员或用户验收。

## 入口和范围

- 新实现：`target/scenario_v310.py`、`target/scenario_plans.py`、`target/scenario_quality.py`、`tests/test_ai_scenario_v2.py`。
- 增量：已有未跟踪 `target/scenario_generator.py`、`web/scenario_generator.py`，不能只看 `git diff HEAD`。
- 对照：`web/business_actions.py`、`web/business_state.py`、`web/conversation.py`、`web/v39_bridge.py`、`target/v39/`、旧P2执行器和预算V2。本轮未修改这些业务实现。
- 首轮发现和整改索引：`First-Review-Findings-and-Remediation.md`。首轮BLOCKED及中间失败证据必须保留。

## 必须反向检查

1. 实际DeepSeek/Qwen请求、原文、候选CREATE、账本能否互相关联；不能把本地Mock当Live。
2. 50 HTTP/400000 Token预算未扩大，未知请求保留预留，费用UNKNOWN。
3. 声明的工具、顺序、预期和前置是否真的执行；不可执行内容不能获得批准。
4. 确认操作是否验证匹配proposal的已提交订单/hold/交易/退款明细/改签；PAY假成功但DB未变必须失败。
5. 旧回执在订单推进后重放是否仍是原回执，金额不可篡改、不能增加交易。
6. 隔离SQLite、静态数据只读、确定性环境断网、会话不串用、模型不能传确认token。
7. 分母是否明确、仅统计实际工具事件，不能把候选数当覆盖；Trace同run/execution关联。
8. 模型质量是否使用不可变CREATE原件，不把人工编辑归于模型。
9. 最终源码SHA是否与最终回归副本一致；11失败和1Skip逐ID与历史比较；保护文件现场重新计算。

## 最终证据索引

主目录 `artifacts/runtime/ai-test-v2-20261109/`：

- `opening.json`：5587保护项、开工源码SHA和Git状态；前轮5586项差异空。
- `unit-r7.xml/log`：最终70项专项；之前失败/通过批次保留。
- `adapter-r4-final.json`、`mutations-r4.json`、`coverage-r4.json`：16真实服务参考计划、5类受控故障；每次真实SQLite及Trace在记录的evidence_root。
- `final-regression-r4/results/`：最终冻结源码的全套原始输出；`final-code-binding.json`。
- `browser-r3/results.json`及17PNG：8规格，51检查，PageError/Console/RequestFailed分开记录。
- `live/`、`live-attempt2/3/4/`：原始请求、响应、候选库、共享预算库、独立用量JSONL；不含API Key。
- `model-comparison-r4.json`、`budget-snapshot.json`、`protection-r4.json`。
- `final/`：交付时冻结复制、完整当前文件补丁、Git差异、源码ZIP、SHA256清单。原静态SQLite不重复塞入包，以原件SHA追溯。

## 已知限制，不能冒充完成

真实候选各5条仍PENDING，用户人工批准0、AI候选V310执行0；16个参考计划不是AI生成。Live Agent端到端NOT_RUN。生成样本只覆盖有限领域，尚未完成全部十领域实验；默认生成输出仍以旧P2结构为主，铁路状态计划需要显式DSL/审核。多轮仅两条完整输入的Mock路径，长上下文/缺参补全、截断/超时、负载和RAG质量未完整验证。QR仅原PNG元数据与金额核对，未做像素扫码。历史正式103仍BLOCKED。

候选审核人是本地审计标签，未实施强身份认证。根目录Git diff包含此前用户成果；两个原有未跟踪文件开工只保存了SHA，无法还原其精确开工文本，因此交付当前完整文件补丁和SHA，不能伪称纯本轮逐行增量。总体保持PARTIAL，用户最终验收待定。
