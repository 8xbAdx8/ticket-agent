# 给成员 B：先读我

这是包含只读质量修复的 Ticket Agent V3 交接包，替代旧 bff292cd 版本。源码版本与文件哈希见 PACKAGE_MANIFEST.json；当前是只读测试候选，正式测试结论由 B 给出。

**先打开[从零安装、运行与 API Key 配置详解](docs/handoff/v3/B_安装运行与APIKey配置详解.md)，按顺序操作。** 示例目录要替换成自己的实际解压位置。

推荐顺序：解压 → Python 3.12 → 安装锁定依赖 → 离线自测 → 新建 Mock 数据 → CLI/Web → 读历史 Live 证据 → 学习配置 API Key。

```powershell
py -3.12 -m venv .venv-deepseek
.\.venv-deepseek\Scripts\python.exe -m pip install -r requirements-deepseek-lock.txt
.\.venv-deepseek\Scripts\python.exe -m pip check
.\.venv-deepseek\Scripts\python.exe scripts/handoff_offline_selftest.py
```

锁定环境中 A 自测 102 项通过；B 正式 100 条用例不在本包内，请保留自己的测试工程、判定器和旧结果。SDK 桩不联网，不需要 Key。跳过必须单独登记。

**API Key 可以按教程安全配置，但真实 API 当前冻结：5 次生成请求已用完，剩余 0。禁止 Live 发送或 --run、提高额度、另建账本绕过。** 本包不含密钥、真实预算账本或原业务数据库；没有账本不是新额度。只有 query_tickets 和 search_policy 有基础历史 Live 证据，另外六工具未开放 Live；改后 Prompt 尚未联网回归。

- [B 冻结版本与异常处理](docs/handoff/v3/B_V3只读冻结测试交接_20261016.md)
- [A 修复报告及测试结果](docs/handoff/v3/A_V3只读冻结质量修复报告_20261016.md)
- [C 历史 Live 回放和演示](docs/handoff/v3/C_V3只读冻结演示说明_20261016.md)
- [团队接口契约](docs/contract.md)
- [已保存的真实 API 报告](docs/evidence/deepseek/api-20261016-001224-2c3484/report.json)

新测试使用独立 Mock 库和 Trace。包内证据目录的 tickets.db 是只读虚构快照，不要重置或用作新测试库。旧源码/文档保留历史日期，最新要求以本说明和冻结交接为准。
