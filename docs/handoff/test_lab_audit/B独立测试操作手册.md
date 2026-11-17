# B 独立测试操作手册

本材料提供被测系统和 A 的自测证据，正式用例、判定标准与成绩由 B 独立负责。请先记录 Git SHA，安装项目依赖并按 README 启动。

PowerShell 在项目根目录：

```powershell
.\.venv-v35\Scripts\python.exe scripts/audit_test_lab.py --out artifacts/runtime/test-lab-b-matrix
.\.venv-v35\Scripts\python.exe scripts/verify_unlimited_live_offline.py --out artifacts/runtime/test-lab-b-regression
```

输出目录必须是新的；两条命令为离线隔离测试，不调用真实模型。运行 Web 后进入测试工作台，选择 Legacy Mock 或 LangChain Mock，选择场景、填写用例 ID 与输入，先执行正常基线，再只打开一个变异执行；保存每次会话 ID、Trace、JSON、工具参数与判定。并发订单对照仅操作临时模拟库。关闭变异或新建会话后再测，避免混淆。

五个结论分开记录：注入是否发生、平台是否检出、Agent 是否识别、Agent 是否恢复、业务是否正确。重复查询可同时“缺陷检出”和“业务正确”。indeterminate 和 not_applicable 不得计入 PASS；异常查 sidecar，而非只看 stop。刷新后在“本地实验按会话ID回放”输入先前 `web-` 加 12 位小写十六进制 ID，可读取保存证据，但不恢复多轮上下文。

DeepSeek 和 Qwen 本轮仅离线替身验证；真实测试须团队另行授权并配置自身密钥、主动勾选真实请求确认。模型只读两工具；真实调用会计费且不得静默降级 Mock。检查参数、实际工具结果、原始回答、公开回答、失败原因和 unknown Token；自然语言不宜全部逐字比较。特别复核改写政策、含糊路由、跨标签并发及历史两条 Trace。不要更改 B 的历史原件；分别统计 Mock 与 Live。

本轮源码测试提交 `08560abd8d111c70da1dd63e58659c113cd02b15`；交接文档所在提交以 `git rev-parse HEAD` 为准。离线回归：679 项通过，103 个子测试通过；JUnit 失败 0、错误 0、跳过 0。真实模型、Embedding、LangSmith 请求均为 0。原始文件核对 18369 项，变更 0 项。详细结果见 `docs/evidence/test_lab_audit/offline-report.json` 和 `protected-receipt.json`。
