# V3 只读冻结前质量修复记录

## 2026-10-16：B反馈 DEF-06 / DEF-07 定向修复

- 接手HEAD：9f6e551738841874a3a556a45a1c281aa0a1834e，当前分支codex/ticket-agent-deepseek-live。仅修两个缺陷；模型API仍冻结，0真实请求。
- 文件：target/deepseek_runtime.py、write_authorization.py、langchain_agent.py、langchain_model.py；新增tests/test_v3_def06_def07.py、scripts/verify_v3_def06_def07_offline.py；示例标签与两个A测试方法名统一monitor_seat；README及A/B/C新补充报告。
- 原因：只读守卫未区分办理主体及外部渠道；购买/锁座冲突未在模型工具之前澄清。保留原授权及业务前置条件，新增authorization_clarification事件；Mock仅锁座确认不自动下单。
- 实际验证命令：python scripts/verify_v3_def06_def07_offline.py --b-root <B工程目录> --baseline artifacts/runtime/def06-def07-review/protected_before.json --out docs/evidence/deepseek/def06-def07-20261016/delivery-regression，解释器.venv-deepseek/Scripts/python.exe。
- A新SDK环境114通过，原V3环境88通过/26跳过，原环境40通过/74跳过；10项冒烟；B原判据隔离复跑legacy101/101、LangChain98/100（T19 N/A）、变异55/55、pytest101 passed、专项37通过/3 N/A。首次迭代结果单独保留attempt-1，没有覆盖。
- 已知失败：X15要求拒绝锁座时仍调用lock_seat；X16要求旧的“订单已创建/未明确授权”文字，两者与本轮用户明确要求冲突。原样保留失败，不修改B判据，需B独立确认。
- 中间迭代final-regression暴露历史长邀约A01漏判（36通过/1失败/3 N/A）；保留该失败记录，补充明确Agent主体的长邀约检查和测试后，重新完整运行delivery-regression。原测试断言不降低。
- 契约及B/C影响：docs/contract.md不变；澄清轮无工具；B需核对新的澄清和下一轮明确授权后锁座路径；C只演示Mock或历史Live回放。正常字段及显式错误留证保持兼容。
- 原件保护：482项目文件及279个B文件哈希核验，真实账本不变；依赖/语法/敏感检查和详细结果在新证据目录。预算上限不变，未开放其他Live工具，模型真实表现仍待验证。
- Git：本模块源码、A自测、报告与新证据同一个独立提交，完整SHA见本次最终交付回复及git log -1 --format=%H -- target/deepseek_runtime.py。不合并main、不打Tag、不创建Release。交回成员B独立回归，不由A自己宣布最终通过。

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

## 2026-10-16：面向B的新机器交接包与Key教学

- 新增根目录 B_先读我.md、docs/handoff/v3/B_安装运行与APIKey配置详解.md、scripts/handoff_offline_selftest.py；仅交接文档/离线运行入口，无业务代码修改。
- 教程涵盖Python3.12、锁依赖、隔离Mock库、CLI多轮、Web、变异、官方Key获取入口、隐藏输入临时环境变量、仅布尔检查、.env不自动加载、异常与费用。当前API冻结，不提供绕预算启动器。
- 实际验证：pip check通过；12段PowerShell仅语法解析；Mock生成2100库存、查询/多轮锁座下单支付查订单退票成功，共6条Trace；Key是否存在示例仅使用空值/离线假凭据验证，未读取或验证用户真实Key。0外连、0模型请求。证据docs/evidence/deepseek/B-package-20261016/guide_check.json。
- 交接包由已跟踪文件组成，另加准确commit/逐文件哈希manifest；不含.venv/.git/密钥/原库/原Trace/真实预算账本；保留虚构Live证据只读快照。最终ZIP的SHA及解压自测记录保存在ZIP旁。
- 业务源码仍为e216fdf修复；此模块文档提交见Git历史，打包源码版本以manifest为准。新机器全新pip安装未在本轮重装，解压自测复用本机锁定依赖，不能说已在B电脑验证。

- 新交接入口实际命令：`.\.venv-deepseek\Scripts\python.exe scripts/handoff_offline_selftest.py`；102通过、0跳过、0外连、0新API。日志/结果写入docs/evidence/deepseek/B-package-20261016/portable_selftest*；原361文件/真实账本哈希不变。

## 2026-10-16：当前版本代码与功能介绍

- 新增docs/handoff/v3/Ticket_Agent_V3_代码与功能介绍_20261016.md及HTML阅读打印版，含16章、8工具参数、3段实际源码及相对行号、RAG/Trace/会话/六变异和验证边界；源码基线fbabf38d，对应上一交接包。
- scripts/build_v3_code_intro.py只读AST/既有证据提取工具Schema、政策数量与函数，不导入Agent、不请求模型；HTML使用捆绑Node marked生成。
- 实际检查：8个本地链接与源码行号、3段Python语法；Edge桌面及移动宽度无横向溢出，16节/8工具/5代码块正确，0外部请求；可视检查目录、工具参数、Trace、证据等截图。361文件及真实账本未变。证据code-intro-20261016/verification.json。
- 本轮仅文档，不重新运行102项业务自测；引用的是已保存结果，未修改业务代码或契约。当前缺少LibreOffice，未生成未经渲染检查的Word；交付可单独阅读的HTML与可编辑MD。
- 文档不进入此前已生成ZIP，避免覆盖既有哈希；可以单独发送给B/C。Git提交见本模块提交历史。
