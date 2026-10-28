# B 正式测试结果：当前会话导入格式

本页面不会执行 B 的断言，也不能由普通对话生成正式结果。请由成员 B 用自己的正式执行器运行当前版本，保存每条用例实际判定和对应 Trace ID，再导出下面的 UTF-8 JSON。此格式是本项目本次新增的交换格式，现有 B 历史 JSONL 不会被自动视为此格式；不要改写历史文件或判定规则。

```json
{
  "schema": "ticket-agent-b-formal-results/1",
  "batch": {
    "batch_id": "示例批次",
    "git_sha": "0000000000000000000000000000000000000000",
    "provider": "deepseek_live",
    "model": "deepseek-flash",
    "mode": "live"
  },
  "results": [
    {"case_id": "E01", "dimension": "边界", "verdict": "indeterminate", "trace_id": "00000000000000000000000000000000"}
  ]
}
```

以上是格式示例，不是实际测试证据，不可用作成绩。`case_id` 和维度必须与 `web/datasets/b_v32_20261020/case_catalog.json` 一致；判定允许 `pass`、`fail`、`indeterminate`、`skipped`、`not_applicable`，不得推断缺失结果。每条必须使用真实 Trace ID，同一批次用例编号不可重复。多轮用例由 B 将最终判定关联到当前会话的一个实际 Trace；没有 Trace 的入口异常用例无法在此视图中关联，不可伪造 ID。

Provider 可用 `deepseek_live` / `bailian_live`（mode 为 `live`）或 `mock` / `langchain_mock`（mode 为 `mock`）。模型必须与对应 Trace 实际记录完全一致；不同模型或运行模式使用独立文件。`git_sha` 为完整 40 位实际提交 SHA，并注明工作区是否存在未提交修改（本交换格式目前无法证明工作区快照）。

在网页进入“质量分析 → 当前会话”，选择包含这些 Trace 的会话，上传 JSON。只统计 Trace ID、会话、Provider、模型和 test_case_label 均匹配的记录。Trace 没有用例标签或标签不符时排除，已标注离线桩的记录不能计为 Live。未匹配项单独列出，未运行或不可判定的维度不算通过。文件只保存在浏览器当前会话状态，不会修改原始文件；重新启动后需重新导入。

系统只核对结构及本地 Trace 关联，无法独立证明文件确实由 B 生成、Git SHA 或断言真实性；正式成绩需要 B 人工核对。当前没有实现自动转换 B 的历史执行 JSONL 或调用 B 的测试执行器，必须由 B 根据真实结果适配导出。
