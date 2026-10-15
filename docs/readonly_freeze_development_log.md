# V3 只读冻结前质量修复记录

日期：2026-10-16；分支 codex/ticket-agent-deepseek-live；接手 bff292cd79d88b25b72aa4c3880d76d59a9f9786。全程真实 API 请求新增 0，原预算仍 5/5，未开放其他工具。

## 模块：只读能力、错误轨迹与状态文案

- 文件：target/deepseek_runtime.py、target/langchain_agent.py、web/app.py、cli.py、scripts/generate_deepseek_handoff.py；A 测试 tests/test_deepseek_agent.py、tests/test_deepseek_readonly_quality.py。
- 原因：通用订票提示词与只读能力冲突；适配器丢弃后端 ok；失败没有结构化部分工具轨迹；旧 Mock 文案/历史生成器会传播过时状态。
- 修改：DeepSeek 专用只读提示词、越界最终文字拒绝、原始最终文字旁证、工具 false 标记保留、坏参数记录、失败会话清理；Web/CLI 明确历史两工具已验证；停用可能覆写报告的旧生成器。
- 命令：`.\.venv-deepseek\Scripts\python.exe scripts/run_deepseek_review_offline.py --out docs/evidence/deepseek/readonly-freeze-20261016/final-regression`。
- 实际结果：新环境 102 passed；旧 V3 78 passed / 24 skipped；旧环境 35 passed / 67 skipped；10 项 Mock 冒烟含六变异通过；0 外连尝试，361 文件与账本不变。attempt-1 是增强边界用例前的通过记录，保留不覆盖。
- 确定性复核：原 Live 查票末尾邀请订票的保存文字被新守卫拒绝；原政策文字可通过。仅离线文字回放，不是新模型响应。旧生成器实际拒绝运行，没有覆写交接文件。
- 契约：正常 10 顶层字段、5 call 字段不变，docs/contract.md 不改。错误仍抛 DeepSeekError、失败旁证 tokens=null；已确认部分用量为 observed_tokens，不伪造正常成功 Trace。B 需捕获异常，旧错误测试调整仅属 A 自测。
- 未完成/风险：改后真实模型表现未回归；词语守卫有漏检和误拒可能；B 正式用例未运行；其余六工具未开放。失败后该会话内存清理，重新输入完整条件。
- 模块 SHA：本记录与源码一起提交；后续交接说明记录实际源码提交 SHA。最终文档 SHA 见 Git 历史及最终回复。

## 实际模块提交与交接更新

源码/测试/独立证据提交：`e216fdf57ec8f34b84134ba2b30b05e5d6ff5985`。后续文档补充 A 修复报告、B 异常捕获/分组测试和 C 历史回放说明，校正README及既有DeepSeek入口的当前状态。未修改过去真实运行原件或B正式测试层。最终文档提交见git log。
