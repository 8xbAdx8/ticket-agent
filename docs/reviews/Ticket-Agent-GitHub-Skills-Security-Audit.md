# Ticket Agent — GitHub 第三方 Agent Skills 安全审计与安装报告

- 完成时间：2026-11-01T02:44:43+08:00（Asia/Shanghai）。
- 任务：仅审计指定四个GitHub来源并安装PASS原版Skill；未继续V3.7产品开发。
- 结论：16个Skill中2个PASS并安装、14个CONDITIONAL暂缓、0个REJECT；Playwright CLI单独评为CONDITIONAL，未安装。未发现足以认定恶意的证据，不等于运行时安全保证。
- 现场仓库：`D:\codexproject\ticket-agent`；分支 `feat/ticket-agent-v36-stabilization`；HEAD `139cdbe2fca8c7249847f245cffef1ed0545dd36`；暂存区为空。

## 1. 仓库来源和固定版本

通过GitHub连接器读取仓库/提交元数据，按固定SHA从GitHub codeload下载到项目外临时目录；未执行clone hooks、安装器或第三方脚本。更新时间为GitHub元数据，提交时间和推送时间分别保留在JSON中，不据此推断发布稳定性。

| 仓库 / 所有者 | 默认分支 / 固定SHA | 许可证（实际文件） | GitHub updated_at（UTC） | 文件数 |
|---|---|---|---|---|
| [langchain-ai/langsmith-skills](https://github.com/langchain-ai/langsmith-skills) / langchain-ai | main / `d69a8fe41816c1faba25399e60301b79b747d147` | MIT，`LICENSE` | 2026-10-30T14:54:53Z | 44 |
| [ai-evals-course/evals-skills](https://github.com/ai-evals-course/evals-skills) / ai-evals-course | main / `80d5f7b0127c7572ed9e9339937adbfd7240ffeb` | Apache-2.0，`LICENSE` | 2026-10-31T14:38:39Z | 26 |
| [anthropics/skills](https://github.com/anthropics/skills) / anthropics | main / `ca45fc496a3436251f191354091d557da31c15b5` | Apache-2.0，`skills/webapp-testing/LICENSE.txt` | 2026-10-31T18:29:49Z | 446 |
| [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli) / microsoft | main / `0a808078d96496cf2a8fa725143c870354f63cda` | Apache-2.0，`LICENSE` | 2026-10-31T18:07:14Z | 38 |

Anthropic仓库级license元数据为空；仅确认目标`skills/webapp-testing/LICENSE.txt`为Apache-2.0，不将该结论扩展至全仓库。Eval仓库未发现NOTICE文件；安装时额外保留原LICENSE，未改正文。

下载目录：`C:\Users\W\AppData\Local\Temp\ticket-agent-github-audit-3598qbcz`。四份ZIP及554个解压文件的大小/SHA256完整记录在`repository-inventory.json`。解压前检查固定SHA目录前缀、路径穿越、绝对路径、符号链接、大小/文件名冲突；未将完整仓库克隆进项目运行。

## 2. Skill清单、职责和依赖

| Skill | 职责和Ticket Agent适用场景 | 原版工作流依赖 | 评级 / 安装 |
|---|---|---|---|
| langsmith-trace | 追踪采集与检索；可能辅助运行链诊断 | 已认证LangSmith CLI/SDK、环境配置；安装/追踪可能联网 | CONDITIONAL / 暂缓 |
| langsmith-dataset | 数据集创建、同步与管理 | LangSmith CLI、云端读写/删除权限、Key | CONDITIONAL / 暂缓 |
| langsmith-evaluator | 评估器开发及云端评估 | LangSmith/模型SDK、CLI、远端服务及费用 | CONDITIONAL / 暂缓 |
| langsmith-experiment-diagnosis | 只读实验对比与失败分析 | 已认证LangSmith CLI、指定远端workspace | CONDITIONAL / 暂缓 |
| langsmith-custom-apps | Enterprise React评测/反馈应用 | LangSmith Enterprise、React构建工具、云端部署 | CONDITIONAL / 暂缓 |
| langsmith-online-eval-engineering | 在线评估器设计、挂接和回填 | LangSmith SDK、生产规则权限、模型预算 | CONDITIONAL / 暂缓 |
| evals-start | 评测任务路由 | 逻辑依赖其他Eval Skills；本次多数未装 | CONDITIONAL / 暂缓 |
| eval-audit | 本地评测流程审计、缺陷分类与人工标签诊断 | 本地既有材料即可；MCP为可选；无附带脚本/强制包依赖 | PASS / 已安装 |
| error-discovery | 人工Trace标注、失败模式发现 | 生成本地HTTP/写接口、后台轮询、CDN/子代理流程 | CONDITIONAL / 暂缓 |
| evaluate-rag | 检索评测、QA生成和调参 | LLM/Embedding、可重建索引的独立副本 | CONDITIONAL / 暂缓 |
| validate-evaluator | Judge与人工标签一致性、TPR/TNR校准 | LLM、numpy/sklearn；示例建议未固定版本judgy | CONDITIONAL / 暂缓 |
| write-code-eval | 引用ID、工具参数、禁止工具等确定性检查 | 项目现有语言/评测框架；无附带脚本/强制外部服务 | PASS / 已安装 |
| write-judge-prompt | 基于失败模式设计二元Judge | 人工标签、模型接口和独立评测口径 | CONDITIONAL / 暂缓 |
| generate-synthetic-data | 合成样本并执行全管线 | LLM、目标系统调用；需写操作/用量隔离 | CONDITIONAL / 暂缓 |
| build-review-interface | 构建本地人工复核界面 | 生成Web界面、持久化标签和Playwright | CONDITIONAL / 暂缓 |
| webapp-testing | 浏览器、截图、DOM与控制台验收 | Python Playwright、浏览器；4个附带Python示例/助手 | CONDITIONAL / 暂缓 |

全部16个候选目录共34个文件均读取并记录哈希；包括所有SKILL.md、agents/openai.yaml、参考文档、许可证及4个Python文件。Python仅AST解析，未导入或执行。仓库外层脚本/依赖另行清点与模式扫描；非候选Skill、第三方npm发行包、浏览器二进制并未获得逐行/运行时认证。

## 3. 指令、脚本和敏感数据审计

下表逐个给出固定SHA文件及行号。CONDITIONAL表示原版存在超出本次授权的依赖、访问或副作用，并非认定作者恶意。所有暂缓项均未安装；将来需先明确独立副本、凭据、联网/费用、写入范围，再重审。完整指令摘录、影响和建议见security-findings.json。

| Skill / 评级 | 证据路径与行号 | 指令或代码及风险解释 | 影响与处理 |
|---|---|---|---|
| langsmith-trace / CONDITIONAL | [config/skills/langsmith-trace/SKILL.md:54](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-trace/SKILL.md#L54) | 连接LangSmith并建议自动追踪上传、读取.env及远程shell安装CLI；与当前显式脱敏导出边界不兼容。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| langsmith-dataset / CONDITIONAL | [config/skills/langsmith-dataset/SKILL.md:92](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-dataset/SKILL.md#L92) | 数据集上传/删除及非交互--yes，需凭据和云端写权限，存在把历史材料复制到远端的路径。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| langsmith-evaluator / CONDITIONAL | [config/skills/langsmith-evaluator/SKILL.md:49](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-evaluator/SKILL.md#L49) | 远程CLI安装、自更新、模型评估和云端评估器CRUD，新增调用、上传及删除风险。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| langsmith-experiment-diagnosis / CONDITIONAL | [config/skills/langsmith-experiment-diagnosis/SKILL.md:8](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-experiment-diagnosis/SKILL.md#L8) | 原版明确只读且禁止密钥回显，安全设计较好；但仍要求已认证LangSmith CLI和远端实验读取，本次不接入。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| langsmith-custom-apps / CONDITIONAL | [config/skills/langsmith-custom-apps/SKILL.md:117](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-custom-apps/SKILL.md#L117) | 面向Enterprise React应用，涉及构建脚本、push/delete与云端反馈，额外权限与本地Streamlit架构不匹配。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| langsmith-online-eval-engineering / CONDITIONAL | [config/skills/langsmith-online-eval-engineering/SKILL.md:66](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-online-eval-engineering/SKILL.md#L66) | 创建/挂接生产在线评估器和回填，可能持续计费/改保留策略；需工作空间、范围及预算授权。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| evals-start / CONDITIONAL | [skills/evals-start/SKILL.md:7](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/evals-start/SKILL.md#L7) | 只有路由且无可执行代码，但依赖其余工作流；多数目标本次未安装，不安装不完整的自动路由入口。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| eval-audit / PASS | [skills/eval-audit/SKILL.md:24](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/eval-audit/SKILL.md#L24) | 可读取本地既有评测报告和Trace并输出诊断；无必需API、可执行脚本、包依赖或自动上传。 | 可在明确授权的本地评测任务中使用；不授予访问外部服务或改正式判据的权限。 只复制原版目录；保留现有项目保护规则。 |
| error-discovery / CONDITIONAL | [skills/error-discovery/SKILL.md:119](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/error-discovery/SKILL.md#L119) | 生成带写接口的标注服务器、CDN脚本、后台轮询和子代理全库扫描；需脱敏、loopback绑定和明确任务范围。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| evaluate-rag / CONDITIONAL | [skills/evaluate-rag/SKILL.md:121](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/evaluate-rag/SKILL.md#L121) | 含LLM生成QA、Embedding检索及逐配置重建索引；需独立副本/用量授权，不能接触冻结Chroma和千题原件。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| validate-evaluator / CONDITIONAL | [skills/validate-evaluator/SKILL.md:183](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/validate-evaluator/SKILL.md#L183) | 要求运行并反复校准LLM judge，例子引入sklearn/numpy/judgy及未固定版本安装；需人工标签与独立预算。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| write-code-eval / PASS | [skills/write-code-eval/SKILL.md:24](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/write-code-eval/SKILL.md#L24) | 本地确定性检查的指导文档；无脚本、额外依赖、密钥或强制网络，适配引用ID/工具参数/禁止工具检查。 | 可在明确授权的本地评测任务中使用；不授予访问外部服务或改正式判据的权限。 只复制原版目录；保留现有项目保护规则。 |
| write-judge-prompt / CONDITIONAL | [skills/write-judge-prompt/SKILL.md:38](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/write-judge-prompt/SKILL.md#L38) | 涉及模型judge的字段输入/示例及严格二元结论；需人工标签、脱敏和与项目INDETERMINATE/未验证状态的独立口径。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| generate-synthetic-data / CONDITIONAL | [skills/generate-synthetic-data/SKILL.md:109](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/generate-synthetic-data/SKILL.md#L109) | 全LLM管线批量生成/执行，可能增加模型调用或写工具状态；与已有P2职责重叠，须隔离原70候选及人工批准门禁。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| build-review-interface / CONDITIONAL | [skills/build-review-interface/SKILL.md:13](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/build-review-interface/SKILL.md#L13) | 要求新建本地标注界面并自动保存标签、Playwright验收；需明确数据副本/监听权限及依赖范围，不直接安装。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |
| webapp-testing / CONDITIONAL | [skills/webapp-testing/SKILL.md:14](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/webapp-testing/SKILL.md#L14) | 指令要求先运行后读源码；server助手shell=True执行任意传入命令，示例写项目外路径且默认Chromium未指定Edge。 | 按原工作流执行可能超出项目只读/隔离/费用或数据保护边界；本次不安装。 暂缓；另行确认依赖、数据范围、权限及运行边界后重审，不能修改原版冒充已通过。 |

额外逐文件发现：

| 发现 | 固定版本证据 | 影响及处理 |
|---|---|---|
| F-langsmith-trace-upload | [config/skills/langsmith-trace/SKILL.md:54](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-trace/SKILL.md#L54) | 自动追踪与项目独立确认的脱敏导出边界不同。 不执行、不安装；另行明确范围后重审。 |
| F-langsmith-dotenv | [config/skills/langsmith-dataset/SKILL.md:24](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-dataset/SKILL.md#L24) | 可能读取敏感环境配置；--api-key参数也可能暴露于命令日志/进程参数。 不执行、不安装；另行明确范围后重审。 |
| F-langsmith-dataset-yes | [config/skills/langsmith-dataset/SKILL.md:92](https://github.com/langchain-ai/langsmith-skills/blob/d69a8fe41816c1faba25399e60301b79b747d147/config/skills/langsmith-dataset/SKILL.md#L92) | 非交互跳过破坏性操作确认不可直接用于正式历史数据。 不执行、不安装；另行明确范围后重审。 |
| F-webapp-shell | [skills/webapp-testing/scripts/with_server.py:71](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/webapp-testing/scripts/with_server.py#L71) | 执行传入shell命令、继承环境；未做网络/凭据/目录隔离，Windows仅终止shell父进程不能保证子树清理。 不执行、不安装；另行明确范围后重审。 |
| F-webapp-absolute-output | [skills/webapp-testing/examples/console_logging.py:31](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/webapp-testing/examples/console_logging.py#L31) | 示例会覆盖固定项目外日志路径；其他示例也使用/tmp或/mnt，不是Windows原生路径。 不执行、不安装；另行明确范围后重审。 |
| F-error-discovery-background | [skills/error-discovery/review-loop.md:21](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/error-discovery/review-loop.md#L21) | 后台服务器/轮询/自动子代理要单独限定生命周期和数据副本；本次只审计该指令，不采纳或执行。 不执行、不安装；另行明确范围后重审。 |
| F-error-discovery-CDN | [skills/error-discovery/SKILL.md:164](https://github.com/ai-evals-course/evals-skills/blob/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills/error-discovery/SKILL.md#L164) | 远程脚本供应链与不可信Trace的HTML渲染需要单独防护。 不执行、不安装；另行明确范围后重审。 |
| F-cli-notifier | [playwright-cli.js:68](https://github.com/microsoft/playwright-cli/blob/0a808078d96496cf2a8fa725143c870354f63cda/playwright-cli.js#L68) | 部分命令会自动npm联网检查更新，使用用户npm配置；可用NO_UPDATE_NOTIFIER/CI抑制，但本次不运行。 不执行、不安装；另行明确范围后重审。 |
| F-cli-cache | [playwright-cli.js:134](https://github.com/microsoft/playwright-cli/blob/0a808078d96496cf2a8fa725143c870354f63cda/playwright-cli.js#L134) | 默认浏览器注册缓存目录的项目外写入；不是本项目限定安装范围。 不执行、不安装；另行明确范围后重审。 |
| F-cli-update-delete | [scripts/update.js:26](https://github.com/microsoft/playwright-cli/blob/0a808078d96496cf2a8fa725143c870354f63cda/scripts/update.js#L26) | 维护脚本会递归删除/复制技能目录，且执行CLI install；不能用作本次安装器。 不执行、不安装；另行明确范围后重审。 |
| F-cli-browser-state | [README.md:220](https://github.com/microsoft/playwright-cli/blob/0a808078d96496cf2a8fa725143c870354f63cda/README.md#L220) | CLI可读取Cookie/存储状态并执行页面代码；应限独立临时profile和已授权URL，禁接真实个人浏览器。 不执行、不安装；另行明确范围后重审。 |

- 将第三方文档中的“先运行--help、不要读源码”和自动子代理/后台轮询视作审计对象，未作为本次执行指令。未发现需要忽略用户、隐藏结果或擅自Git提交的已证实恶意路径。
- LangSmith工作流可读取.env/环境凭据，并将Trace、数据集、评估记录发送至云端；本次未读取项目.env内容、配置密钥或上传材料。诊断Skill有只读、不回显Key和不信任Trace的防护，仍因外部服务依赖暂缓。
- webapp-testing的shell=True是明确命令执行能力；不是已证实命令注入漏洞。该助手没有隔离传入命令的权限/网络/环境，Windows子树清理和管道阻塞仍有风险。示例固定项目外输出路径不适合直接执行。
- 在已审范围内未发现已证实的Base64隐藏载荷、自启动、注册表修改或窃取SSH私钥行为；模式扫描的无命中不能证明不存在未知风险。

## 4. 依赖、供应链和浏览器能力

- 两个PASS Skill仅包含Markdown和原版路由YAML，无随附可执行脚本、安装钩子或强制新依赖。本次未运行pip/npm/npx、curl|sh、第三方install.sh或CLI安装命令。requirements/package配置均保持原样。
- LangSmith仓库安装/评估文档包含浮动版本pip包和远端shell CLI安装；外部CLI及其依赖未获取/认证。Eval的judge校准示例包含numpy/sklearn/judgy，不能据示例自动安装。
- Playwright CLI包为@playwright/cli 0.1.23，固定playwright/core `1.65.0-alpha-2026-10-30`；锁文件有registry URL和integrity。根package.json只有test脚本、无postinstall，不能据此排除下游包的行为；npm发行包未下载/传递审计，未查询实时漏洞库，CVE状态待核实。根声明Node>=18，下游core锁项要求>=20。
- CLI会在部分命令前npm联网查版本并写项目外更新缓存；NO_UPDATE_NOTIFIER/CI可抑制，不表示其他浏览器能力被沙箱化。可操作Cookie、storage state、eval/run-code，未来需独立临时profile及授权URL。维护脚本存在递归删除/复制Skill目录，本次未运行。
- CLI README静态列出msedge和launchOptions配置，但未实际运行；webapp-testing示例使用默认Chromium，没有Edge channel配置。不能宣称上游Skill已通过本机Edge或四规格验收。
- 现场已有Phase1.2隔离Playwright 1.64.1 + Edge 156.0.4314.50的43/43历史验收，当前没有引入alpha CLI的必要。仓库实际上包含playwright-cli相关Skill，本次仍严格按用户要求只审CLI，未安装其Skill。

## 5. 项目适配性和安装边界

- eval-audit可审视现有Trace/回归、失败分类、人工标签与Judge校准证据；write-code-eval可指导针对引用ID、参数结构、禁止工具等客观规则编写补充检查。本次仅安装文档，没有生成或执行新评测器。
- eval-audit二元Judge建议是可审视的外部方法论，不覆盖既有Recall@K/MRR/无答案误召回分母、忠实度INDETERMINATE、not_verified、103正式断言、七维度和A/B/Mock/Live成绩归属。不得将方法建议自动落实为修改正式判据。
- eval-audit允许已有MCP或本地文件两条入口，本次选择可完全离线的本地材料适用性；安装并不授权将来读取远端、改原Trace或账本。其他Skill名称是后续建议，不构成本地审计必需的运行时依赖，未为补齐路由安装CONDITIONAL项。
- 原agents/openai.yaml中的allow_implicit_invocation=true按原版保留；它影响匹配路由，不授予新联网、费用或写权限。后续使用仍遵守用户任务范围和项目保护规则。

## 6. 实际安装结果及拒绝/暂缓清单

从已固定版本、审计并校验哈希的临时源提取5个纯文本文件，经审计目录暂存后以独占创建方式复制。未覆盖同名目录；没有修改上游SKILL.md或YAML，也没有自制替代Skill。Apache许可证放在无SKILL.md的_licenses目录，不计为第三个Skill。

| 安装文件 | SHA256（与上游一致） |
|---|---|
| `.agents/skills/_licenses/ai-evals-course-evals-skills/LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `.agents/skills/eval-audit/SKILL.md` | `9f4b23dfe06f4c42a28d4bb054d75b5da1bff39ea57e0450689a4f699604bc63` |
| `.agents/skills/eval-audit/agents/openai.yaml` | `cfcb2a19fa1f5e655fe650c2e8f600d9dbff0d82ab7b8fcc3660f4a7c042406b` |
| `.agents/skills/write-code-eval/SKILL.md` | `6acf7d26f1b64d2dd7792675e3afefa0fc7accd6e0efd73184c6dd356c64338b` |
| `.agents/skills/write-code-eval/agents/openai.yaml` | `5e0a5fa940ad295c7693d712221e65c030b06a3e2044a52a772ec175ad61eb7e` |

两个Skill均来源于[ai-evals-course/evals-skills固定提交](https://github.com/ai-evals-course/evals-skills/tree/80d5f7b0127c7572ed9e9339937adbfd7240ffeb/skills)；每目录保留原版SKILL.md和agents/openai.yaml，完整文件表见installed-skills-manifest.json。

暂缓：langsmith-trace、langsmith-dataset、langsmith-evaluator、langsmith-experiment-diagnosis、langsmith-custom-apps、langsmith-online-eval-engineering、evals-start、error-discovery、evaluate-rag、validate-evaluator、write-judge-prompt、generate-synthetic-data、build-review-interface、webapp-testing。各自原因和证据见第3节；本次REJECT为0，不能将“暂缓”描述为检出恶意。CLI单独暂缓。

首次复制尝试在预检读取临时目录时遇WinError 5，尚未写入安装目录。按原源哈希核验后，仅将5个已审文件暂存至审计目录并重试成功；不是自动审批拒绝，也未绕过项目目录写入审批。两次结果记录在installation-attempts.json。

## 7. 安装后核验、项目保护和Git变化

- 静态核验：2个frontmatter合法且name唯一，description与职责和上游一致；5/5文件哈希一致、额外安装文件0。全局目录不存在这两个同名安装，本次不写全局Skill/依赖。
- Codex静态发现条件：项目根.agents/skills/<name>/SKILL.md及必需name/description正确；[官方文档](https://learn.chatgpt.com/docs/build-skills)说明仓库范围扫描该目录。当前回合未实际调用Skill或检查下一轮宿主列表；下一轮应可发现，未出现时可重启。不能把静态发现条件通过写成实际运行验证。
- 1892/1892保护文件哈希一致，差异0；103条B正式目录保持103，七份B manifest文件哈希通过；既有Phase1.2九份源码/测试/CSS哈希一致；接手12个有内容快照的源码、测试、状态和历史报告均保护，其中状态文件只在校验后追加本次记录。
- docs/evidence、web/datasets、data/rag1000、target/p2_*、工具/维度及原正式断言在保护清单范围内未改。没有执行会写SQLite、Chroma、原Trace或账本的产品/测试流程；未对所有运行库进行全盘法证核验。
- 接手时已有6个tracked源码修改：web/app.py、conversation.py、demo.py、developer_workspace.py、presentation.py、scroll_bridge.py；其内容全程保持。阶段1、1.1、1.2报告与新增测试/user_copy.py的接手快照哈希保持；阶段0报告未被本次写入、最后修改时间早于本次审计，最终哈希另记。初始内容快照遗漏了该中文路径，不能对它宣称本次前后哈希比对通过。
- 本次新增：.agents/skills内5个文件、本文、独立审计产物（含7个必需JSON、源固定清单、静态扫描、复制/核验脚本和审计暂存5文件）。唯一修改的既有文件是PROJECT_STATUS.md，只追加历史记录，原字节前缀保留。审计产物位于已有忽略的artifacts路径，不修改.gitignore。
- 暂存区无变化；未Commit/Push/Merge，分支/HEAD不变。git diff --check退出0；已有源码的LF/CRLF提示保留，不改行尾。最终git status、diff名称/统计、全部保护结果及报告哈希保存于verification.json。
- 本次明确执行的项目外文件写入仅独立临时目录中的下载/解压。未安装全局包、未修改用户配置或浏览器profile；没有对全系统其他后台进程的写入做监控。

## 8. 验证命令、证据、限制与停止

本次执行自写静态分析/复制/核验脚本；它们不导入下载源，不代表第三方功能测试：

```powershell
.\.venv-v35\Scripts\python.exe -I -B artifacts/runtime/github-skill-security-audit/build_audit.py
.\.venv-v35\Scripts\python.exe -I -B artifacts/runtime/github-skill-security-audit/install_pass_skills.py
.\.venv-v35\Scripts\python.exe -I -B artifacts/runtime/github-skill-security-audit/finalize_audit.py
git diff --check
git status --short --untracked-files=all
```

结果：16候选/34文件静态审计，2 PASS/14 CONDITIONAL/0 REJECT；CLI 1 CONDITIONAL；2 Skill/5安装文件核验通过；1892保护、9份最新源码及7份B manifest核验通过。未运行pytest、AppTest、真实浏览器或Skill功能；因此本次测试Passed/Failed/Skipped不适用，不记录为0失败全绿。Phase1.2的1098 passed / 11 failed / 1 skipped / 199 subtests、浏览器43/43仅是保留的历史证据，未在本次重跑。

联网仅用于用户指定公开GitHub元数据/固定源码下载，以及核对官方Codex发现文档；真实模型、Embedding、LangSmith业务接口、12306、支付请求均未发起。不得将公开源码联网与“完全离线”混淆。未配置/输出任何真实密钥。

| 产物 | 内容 |
|---|---|
| `repository-inventory.json` | 四仓库来源/SHA/许可证/时间/ZIP及全部文件哈希 |
| `skill-inventory.json` | 16候选、元数据、目录文件哈希、评级 |
| `security-findings.json` | 逐项证据/行号/风险/建议及CLI判断 |
| `dependency-audit.json` | 依赖、安装脚本/生命周期、仓库脚本清单及未核实范围 |
| `compatibility-assessment.json` | 项目适配、指标/授权边界 |
| `installed-skills-manifest.json` | 实际安装目录、上游版本、逐文件SHA256 |
| `verification.json` | 最终Git、原工作区/保护哈希、frontmatter、安装完整性、静态发现条件 |

另存workspace-before.json、source-pins.json、static-scan.json、installation-attempts.json。所有产物位于`artifacts/runtime/github-skill-security-audit/`，不替代原测试证据。

尚未核实：下一轮宿主实际发现/调用、第三方功能运行安全、传递依赖/实时CVE、未来远端权限及用量；它们不影响本次两份无脚本本地指导Skill的静态安装结论。后续若需启用任何CONDITIONAL项，须明确授权范围并重审。

**本次审计和安全安装完成后停止；不进入下一产品阶段，不自动启用任何暂缓能力。**
