# C 端完整回归与冻结核验

在开工前和收工后分别从同一 Git 工作区复制实际源码，在两个隔离副本运行 `.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out <独立产物目录>`。P0 fixture ZIP 的 SHA-256 为 `c170b90aaf8dcf03b9c6c918e8024cf72665a4a9082a030700c97e32cba2b9a9`，验证其中 15 个 fixture 文件。保留原测试 ID、断言和环境失败。两次日志中四项失败的实际错误都是回环 RPC `WinError 10061`。本轮未将这些失败记为通过。

| 批次 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|
| 契约历史参考（逐 ID 原件未获得） | 404 | 3 | 0 |
| D 盘开工副本 | 403 | 4 | 0 |
| D 盘收工副本 | 403 | 4 | 0 |

开工和收工的失败 ID 完全相同，新增失败 0，移除失败 0。与历史三条失败的逐 ID 比较仍待原件。

| 开工与收工均失败的 ID |
|---|
| `tests/v39/test_confirmation_rpc.py::test_same_proposal_two_process_clients_one_authority` |
| `tests/v39/test_matrix.py::test_matrix[V39-T011]` |
| `tests/v39/test_matrix.py::test_matrix[V39-T031]` |
| `tests/v39/test_v391_lifecycle.py::test_approved_lifecycle[V39-T072]` |

原始证据位于 `artifacts/runtime/v310-c-workbench-20261111-231748-45b50f/baseline/` 与 `artifacts/runtime/v310-c-workbench-20261111-231748-45b50f/final/`，各保留 `setup.json`、`pytest.log`、`results.json`、`junit.xml`。`regression-comparison.json` 对比 407 个测试 ID 的结果。

冻结核验以 `opening.json` 记录的 2,671 项为范围，覆盖 Git 跟踪、开工时可见的未跟踪文件、数据目录和阶段八静态库。`protection-final.json` 记录收工差异和 Git 前后状态。静态库 SHA-256 前后一致，均为 `e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`。正式 103、B 快照、A/B 源码及共享入口保留。Git HEAD、分支和暂存区保留。测试 SQLite、Trace 和模型日志写在隔离目录。`git diff --check` 通过，Git 仍提示部分开工前已有文件的 LF/CRLF 转换。
