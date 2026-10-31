# P2 已批准场景（approved）

本目录只存放**经过具名人工审核并批准**的 P2 场景，每行一条，按批次分文件：`<batch_id>.jsonl`。

## 准入规则（由 `target/p2_review.py` 强制执行）

1. 必须存在 `review.decision = "approve"`。
2. `review.reviewer` 必须是具名人类，`ai / system / auto / bot / deepseek / qwen / codex` 等一律拒绝。
3. 必须有 `review.reviewed_utc`（ISO 时间）。
4. 加载时会**重新跑完整校验**（Schema、接地逐字、工具白名单、行为一致性）；失败者不加载。
5. `case_id` 必须以 `P2-` 开头；`dataset_version` 不得来自 `rag1000`。
6. 沙箱执行通过**不构成**批准；AI 自评也**不构成**批准。

## 结果归属

P2 的执行结果单独写入 `artifacts/runtime/p2-results/`，**不并入** P0 的 103 条历史成绩或 RAG 1000。

## 生成证据

原始候选与生成证据保留在 `artifacts/runtime/p2-gen/<batch_id>/`（`candidates.jsonl`、`raw/`、`batch.json`、`review.jsonl`），本目录只保存批准后的副本。
