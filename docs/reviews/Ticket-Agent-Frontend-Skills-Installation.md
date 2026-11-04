# Ticket Agent 前端 Skills 审查与安装记录

日期：2026-11-02（Asia/Shanghai，按本次客户端日期）。

## 1. 结论与范围

- **已安装** `frontend-design`：仅复制 Anthropic 原版 `SKILL.md` 和 `LICENSE.txt`，不改写、不增加替代 Skill。
- **可选项未安装** `web-design-guidelines`：已审查完整 Skill 目录与原文；其要求每次加载未固定版本的远程规则，且本次固定提交未提供独立 LICENSE 文件。README 声明 MIT，本报告不将其说成没有任何许可声明，也不自行补造 LICENSE。
- 本次只有项目级安装与文档维护；未修改产品代码、CSS、布局、依赖、AGENTS.md、现有两个评测 Skill。未执行任何第三方脚本、安装命令、浏览器测试或应用测试；未 Commit、Push、Merge。
- 未访问 API Key、`.env`、浏览器 Cookie 或凭据存储。联网仅用于通过 GitHub 连接器读取公开上游文件及查阅 OpenAI 官方发现规则；无票务、模型、Embedding、LangSmith 或支付请求。

## 2. 开工现场

| 项目 | 实际值 |
|---|---|
| 项目目录 | `D:\codexproject\ticket-agent` |
| 分支 | `feat/ticket-agent-v36-stabilization` |
| HEAD | `4340b6640025be95e8300a3d625a32cfb431e35d` |
| 开工工作区/暂存区 | 均为空 |
| 项目现有 Skills | `eval-audit`、`write-code-eval`，及已有 `_licenses` |
| 同名检查 | 两个目标目录均不存在；项目/用户 Skill 目录与本轮宿主目录清单未发现同名 Skill |

开工记录保存了全部 2313 个受 Git 跟踪文件的工作区 SHA256，以及现有 5 个 Skill/许可证文件的 SHA256。未读取或重置旧运行账本、数据库及历史产物。

## 3. 固定上游身份与完整目录

通过 GitHub 连接器分别解析 `main`，随后所有目录、文件均按下列完整提交 SHA 获取。GitHub 返回两个提交的签名验证状态均为 verified；本次没有独立进行签名密钥验证，不将该状态当作内容安全保证。

| 上游 | 固定提交 | 审查目录 | 完整目录内容 |
|---|---|---|---|
| [anthropics/skills](https://github.com/anthropics/skills/tree/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design) | `ca45fc496a3436251f191354091d557da31c15b5` | `skills/frontend-design/` | `SKILL.md`、`LICENSE.txt`；无子目录、脚本、可执行文件或二进制资源 |
| [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/skills/web-design-guidelines) | `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62` | `skills/web-design-guidelines/` | 只有 `SKILL.md`；无子目录或脚本 |

另核对两仓库根目录；读取 Anthropic 的 `THIRD_PARTY_NOTICES.md`，以及 Vercel 的 README、package.json。其他 Skill、仓库级脚本、安装器和依赖均未安装或执行，不宣称已审计整个上游仓库。

## 4. 静态审查发现

### frontend-design

- 内容为设计方向、排版、颜色、布局、文案和自我审视指导；建议未来设计时按需截图，但不授权本次浏览器测试或产品修改。
- 未发现读取 API Key、环境文件、Cookie、凭据库的指令或代码；未发现上传本地文件、遥测、部署或提权操作。
- SKILL.md 无外部 URL、网络命令、远程规则加载、代码块或附带脚本。许可证中的 Apache URL 为条款引用，不是执行请求。
- 原版指导的视觉偏好可能与项目约束不同，后续仍以用户授权、演示业务边界、正式测试契约及既有工程限制为准。安装不代表允许重做界面。
- [原始许可证](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design/LICENSE.txt)为 Apache License 2.0，全文逐字节保留。本次仅两个文本文件，没有引入根目录第三方声明列举的软件、字体或二进制组件。
- 审查结论：适合本次限定范围内的原版静态复制。静态审查不等于保证未来所有使用均无风险。

### web-design-guidelines（可选，未安装）

- 原文是 UI 审查流程；无读取 API Key、`.env`、Cookie 或外传项目内容的明确指令，也无附带脚本。
- 每次审查要求抓取 `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`。该地址在另一个仓库的浮动 `main` 上：即使固定本 Skill 提交，运行时规则仍会变化；当前 Skill 哈希不能覆盖未来远程内容。
- 本次只识别该外部加载要求，未加载或执行远程规则，不声称远程规则已经安全验证。
- 固定提交的 Skill 目录及仓库根目录未提供独立 LICENSE 文件；[README 的 License 节](https://github.com/vercel-labs/agent-skills/blob/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/README.md)声明 MIT，package.json 没有 license 字段。`LICENSE` 路径查询返回 404。
- 为满足本次可追溯安装与保留原始 LICENSE 的要求，本次不安装可选项，不修改其原文来固定远程规则、不编写替代 Skill。未来如需启用，需先解决完整许可材料与远程规则的审查、版本留证策略。

## 5. 安装文件与原始 SHA256

目标：`D:\codexproject\ticket-agent\.agents\skills\frontend-design\`。安装前再次检查目标不存在；以独占创建方式新建目录/文件，未覆盖现有文件。原文按 UTF-8 字节复制，不转换换行或 frontmatter。

| 原始文件 / 安装文件 | 字节数 | 原始与安装 SHA256（相同） | Git blob SHA-1 |
|---|---:|---|---|
| `skills/frontend-design/SKILL.md` → `.agents/skills/frontend-design/SKILL.md` | 9390 | `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3` | `a5333457c414d20d625f307df945842c0952ecc3` |
| `skills/frontend-design/LICENSE.txt` → `.agents/skills/frontend-design/LICENSE.txt` | 10174 | `0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594` | `f433b1a53f5b830a205fd2df78e2b34974656c7b` |

未安装的 Vercel SKILL.md（1231 字节）原始 SHA256：`f4647ca866a3accf763777f83e7682954f0187cd6bea7eea0399796652414e8f`；Git blob：`ceae92ab319216a68274168fba9b63b998b65997`。仅在非发现路径的审查证据中留存，不能被当作已安装。

连接器取得的所有 6 份文件内容均重算 Git blob SHA-1，与固定提交目录条目完全匹配，再计算 SHA256；并非把网页渲染文本当作原始文件。安装文件又与核验后的原始字节比较一致。

## 6. Frontmatter、发现路径及冲突

- 原版 `name`：`frontend-design`。
- 原版 `description`：`Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults.`
- 原版 `license`：`Complete terms in LICENSE.txt`。
- 使用已有 PyYAML 的 safe_load 验证 YAML 映射、字符串字段与名称/目录一致性；不安装新依赖。Vercel 原文 frontmatter 亦可解析，名称 `web-design-guidelines`，metadata version 为 `1.0.0`；解析通过不代表已经安装。
- [OpenAI 官方本地发现文档](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)说明 Codex 扫描当前目录至仓库根之间的 `.agents/skills`；本次目标位于项目根下，符合项目级发现规则。下一轮可使用 `$frontend-design`；若列表未刷新，重启 Codex。当前轮未通过真实美化任务验证触发效果，不冒充已完成 UI 验收。
- 未在用户级/全局目录安装或更改配置。与现有两个评测 Skill 名称不同、职责不同；没有更改其文件或 AGENTS.md。
- 使用已安装 `skill-installer` 的来源/目标/防覆盖规范，按用户要求通过连接器静态获取和复制；未运行其安装脚本或上游 `npx`/npm 脚本。使用 `openai-docs` 仅核对官方发现规则，未使用新 Skill 修改产品。

## 7. 本次检查、文件变化与证据

实际检查：开工/收尾 Git 状态与 HEAD；两份完整 Skill 目录；许可证与根目录元数据；6 份原始 blob 哈希；安装字节 SHA256；YAML；现有 Skill 名称冲突和 5 文件完整性；2313 个既有受跟踪文件前后哈希（仅授权维护的 PROJECT_STATUS.md 发生变化）；`git diff --check`。

本次新增：

- `.agents/skills/frontend-design/SKILL.md`（原版）。
- `.agents/skills/frontend-design/LICENSE.txt`（原版）。
- `docs/reviews/Ticket-Agent-Frontend-Skills-Installation.md`（本报告）。

本次修改：`PROJECT_STATUS.md`，只追加此次工具安装状态和证据索引，版本/开发阶段/历史成绩保持。

本地独立证据目录：`artifacts/runtime/frontend-skills-installation-20261102/`，包含 `before.json`、`upstream.json`、`static-audit.json`、`name-conflicts.json`、`installed.json`、`verification.json`。该目录为非发现路径，不替代原始上游来源。

应用测试 Passed / Failed / Skipped：本次未运行，均不新增计数；已有 1356/11/1 等成绩仅属于此前阶段七，正式103重评仍 BLOCKED。无浏览器测试、真实 API 请求、依赖安装、提交或推送。

本次到此停止，等待用户授权下一步美化任务。
