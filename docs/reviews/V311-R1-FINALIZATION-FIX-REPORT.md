# V3.11-R1 Finalization Fix Report

HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，未 commit/push。本轮只做离线整改，没有调用真实模型；原 R1 86 条请求、原始 FAIL、Trace、checkpoint、10 个 SQLite 和旧证据全部保留。

## 根因

旧 `target/scenario_r1_lifecycle.py::R1Run.finalize` 把 summary 写到：

```text
<batch-root>/r1-summary.json
```

所有 provider、所有 execution 共用该路径；`save()` 使用 `open('x')`，第二次 finalize 产生 `FileExistsError`。原始 pilot/lifecycle 结果中的 `finalize_error: FileExistsError` 就是这个归档冲突，不是业务执行失败，也不是重复交易。

## 修复

- summary 移到 `checkpoints/<execution_id>/summary.json`；
- 每个 execution_id 独立目录；
- finalize 幂等：已有同 phase summary 时直接返回 `idempotent=True`；phase 不同返回 `R1_FINALIZE_STATUS_CONFLICT`，绝不覆盖；
- checkpoint 写入仍为不可变新文件；
- 归档失败不改变业务行 PASS/FAIL；
- 旧文件、旧 FAIL、旧 checkpoint 不删除、不改写。

## 测试

`tests/test_ai_scenario_r1.py::test_r1_finalize_is_idempotent_and_never_overwrites`：

```text
first.finalize -> idempotent=False
second.finalize -> idempotent=True
summary bytes unchanged
conflicting phase -> ValueError
```

R1 测试最终 **6/0/0**。

## 旧证据

原始 `pilot-summary.json` / lifecycle outcome 中的 `finalize_error` 保留；新代码只影响后续运行，不回写历史。
