# V3.3 开发记录

## 2026-10-25 基线与主题

- 恢复点：`0af2712276258fee02573da33688a836738814c6`；分支 `codex/ticket-agent-v33-ui-dashboard`。
- 保留唯一原始未跟踪文件 `docs/showcase/v3展示.zip`，不写入 B 原始目录。
- 基线命令：`.venv-deepseek/Scripts/python.exe scripts/run_deepseek_review_offline.py --out artifacts/runtime/v33-baseline-20261025`。
- 实际结果：DeepSeek 环境 188 测试通过、0 跳过；V3 环境 188 项、58 跳过；V2 环境 188 项、109 跳过；Mock smoke 通过。四条命令均 exit 0，API 0，非回环网络阻断开启，历史关键证据及正式账本未变化。
- 831 个原始核心/数据/Trace/证据/账本文件建立 SHA256 保护清单，清单位于隔离工作目录，最终另行核对。
- 主题文件 `web/design.py`、`web/design.css`：统一深浅色、状态色、卡片、加载、响应式布局和减少动画偏好。不调用 Agent。
- 验证：`python -m unittest discover -s tests -p test_v33_design.py -v`，2/2 通过。实现提交 `fdf4b66`。
- B/C 影响：此时尚未替换入口；公共业务及 Trace 接口不变。

## 2026-10-25 只读数据适配

- `web/evidence.py`、`web/datasets/b_v32_20261020/`、`tests/test_v33_evidence.py`。
- 从 B 提供的结果复制六份原始结构化结果，合并保留 103 条原用例；原断言未改、未执行。manifest 标注 B 独立 Mock、执行日期（报告给定）、精确时间未知、源 SHA 和每个文件哈希。
- 分别维护 legacy 101、langchain 100、选定变异 69、额外探测 16、专项 47、并发检查 10；不相加当总测试数。
- T04 保留漏检；R01 标不适用；F15/M12 保留非 C5 检出；空分母不生成百分比。
- 变异、模型语义恢复与业务正确分别展示；读取历史数据不执行新模型请求。
- 此模块验证结果和提交 SHA 见后续条目。
