# V3.5.2 指标与全文忠实度审计开发记录

## 2026-10-26 基线与指标独立核算

- 实际分支基线feat/ticket-agent-v352-rag-live-eval、HEAD61c9f1953ff56e6037d3b996a333ef9c5a0164c5，仅用户原ZIP未跟踪。建立codex/v352-rag-faithfulness-audit，不动main/标签。用户明确本轮零Qwen/DeepSeek/Embedding/LangSmith请求。
- 新增scripts/audit_v352_metrics.py和tests/test_v352_metric_audit.py，以Fraction从保存的144条原始模式结果独立重算，不复用生产metrics/排序/去重辅助函数。48题标签与原始逐题结果逐一核对，开发/保留/合计三模式一致、差异0；正样本16、负样本32各自同一集合。Recall为macro文档集合召回，MRR实际为MRR@3首个相关文档倒数，不是Hit@K。
- 实际运行audit_v352_metrics.py --out artifacts/runtime/v352-faithfulness-audit/metrics；Keyword R@1=27/32、R@3=1、MRR=15/16；Vector/Hybrid R@1=31/32、R@3=MRR=1。HP08预期两份文档，Top1召回1/2但首个相关排名1解释该差异，不改生产公式或标准答案。
- 新增7项离线数学边界测试全部通过，涵盖多相关文档、首相关第三名、截断、无答案分母、未运行/错误、去重顺序和重复case拒绝。真实请求0。原始成绩与报告保持不变；后续报告将明确MRR@3的截止范围。
