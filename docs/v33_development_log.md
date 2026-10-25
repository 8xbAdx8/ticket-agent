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

- 验证：`python -m unittest discover -s tests -p test_v33_evidence.py -v`，4/4 通过；提交 `3ac5d04`。

## 2026-10-25 会话服务、Trace 与数据页面

- `web/runtime.py` 将用户/实验配置、数据库、Agent 记忆及 Trace 分离；锁内恢复原模块配置，不修改 target。重复提交 ID 返回原回执；默认 Live 强制两工具只读并保留原预算配置。用户界面确认仅是附加层，原后端授权仍是执行依据。
- `web/conversation.py` 展示真实工具卡片和模拟操作确认；`web/presentation.py` 对缺失票价/余票显示未提供，车程只按工具已有时间计算。
- `web/trace_view.py` 展示实际模型选择、参数校验、执行、变异前后、原 JSON、字段搜索与脱敏导出。缺阶段起止时不绘制瀑布；聚类视图明确不表示全局时序。
- 验证：`python -m unittest discover -s tests -p test_v33_runtime.py -v`，5/5 通过；提交 `198c4a2`。
- `web/charts.py`、`web/dashboard.py`、`web/quality.py` 提供七维度、状态分布、耗时散点、检出分布、八变异矩阵、幻觉与并发专题。无充分可比批次时不制造趋势。提交 `d9c2162`。
- `web/comparison.py`、`web/integrations.py`：按共同用例比较两个 Mock 引擎，历史 Live 单列；已有 create_agent/LangGraph/InMemorySaver 如实声明，LangSmith 上报关闭，百炼只有预留配置接口。提交 `bbab70f`。
- 第一次新版 AppTest 10 项中 1 项失败：UI 操作确认未识别以“订明天”开头的短句。补充 UI 确认分类；原业务授权未修改。M8 表格异构布尔/数字列改为文本呈现，消除 Arrow 类型警告。原始失败日志保留在隔离工作目录。
- 第二次新版 AppTest 10/10；合并 V3.3 模块自测共 21/21。命令 `python -m unittest discover -s tests -p test_v33*.py -v`。
- B/C 影响：新前端最终入口和导航正在联调；原十字段及工具五字段不变，B 原断言不修改。

## 2026-10-25 双入口、边界修复与证据表格

- `4c661e3`：接通新版 `web/app.py` 双工作空间与 `web/laboratory.py`；保留 `web/legacy_app.py`，原五个 A UI 测试仅修改入口引用，原断言保留。`test_v33_app.py` 覆盖新默认入口。沿用前述 21/21 模块结果。
- `349ef96`：扩展 `web/runtime.py` 全局变异隔离、`web/evidence.py` Blob/未知数据和图表边界；扩展 AppTest。分阶段命令均为 `python -m unittest discover -s tests -p test_v33*.py -v`（使用完整依赖环境），27/27、29/29、30/30、31/31 逐次通过；隔离日志 `artifacts/runtime/v33-work/v33-modules-expanded.txt`、`v33-mutations-ui.txt`、`v33-final-ui.txt`、`v33-frozen-ui.txt`。7 种聊天变异和独立 M8 路径实际执行，不代表 Live。
- `7b97a5c`：`web/design.py/css` 将证据表格统一深浅主题，增加实际过滤及匹配可见行的 CSV 导出；公式前缀转安全文本。新增测试后 34/34 通过，原 SDK + MockTransport 验证两次桩请求闭环与 rerun 不重发。日志 `v33-theme-tables.txt`。未修改 target 或真实请求预算。
- `c462ed5`：`web/dashboard.py` 总览来源过滤改成三列紧凑工具栏；相同模块命令 34/34 通过，日志 `v33-layout-final.txt`。不改变统计口径。
- B/C 影响：默认 UI 导航变更，旧 UI 可显式启动；公共 Agent 十字段/工具五字段、原测试数据与正式层保持不变。新前端需 B/C 独立人工确认。

## 2026-10-25 最终回归、截图与交接

- 新增 `scripts/verify_v33_offline.py`，去凭据并阻断非回环 Python 网络，串行执行原三环境回归、八变异审计和配置预检；输出必须全新，防止覆盖证据。该脚本不产生模型请求。
- 实际命令：`.venv-deepseek/Scripts/python.exe scripts/verify_v33_offline.py --out artifacts/runtime/v33-release-check-20261025`。被测源码 `c462ed50a015a9a09b136fd156d8d35cb6a34a54`。
- 最终结果：完整依赖环境 222 通过、0 失败、0 跳过；V3 163 通过、0 失败、59 跳过；V2 111 通过、0 失败、111 跳过（各收集 222）。Mock smoke、原八变异审计 25 记录与 8 标注样本通过。缺 Key 预检 exit 2 符合预期，假 Key 仅配置预检 exit 0。B 正式层未重跑。
- 开工原 831 文件哈希不变；最终验证器当时保护 844 文件也未变；范围和快照时间不同。正式账本仍 5/5，本轮 API 0、费用 0、真实 Token 未产生。
- 实际启动仅回环 Mock Streamlit 服务，逐页操作并逐张检查 13 张原生 JPEG。覆盖两主题与 1920×1080、1366×768、1024×768，无整页横向溢出。真实图表加载后再截图，早期加载态保留在隔离目录；浏览器原生下载的 M7 JSON 与截图 Trace ID 一致。没有生成效果图替代截图。
- 页面热更新时曾出现导入竞争；最终重启冻结服务后验证，最终服务日志没有该异常。历史浏览器断连消息来自主动停止旧服务，不声称累计 console 无错误。
- 新增 `docs/evidence/v33/20261025/` 离线、兼容、视觉与安全证据；新增 A/B/C V3.3 手册和未来集成设计，更新 README 与启动说明。所有未完成集成、新 Live 和 B/C 最终验收明确标识未验证。
- 原始开发日志不覆盖，API/正式账本/历史 Trace 不修改。最终文档证据提交 SHA 由 `git log` / 最终回复提供，避免文件自引用；前九项实现提交已逐项列出。
