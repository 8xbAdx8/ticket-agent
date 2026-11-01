# Ticket Agent V3.7 阶段1.2 移动端布局修复与授权契约核查报告

- 日期：2026-11-01（Asia/Shanghai）
- 分支 / HEAD：`feat/ticket-agent-v36-stabilization` / `139cdbe2fca8c7249847f245cffef1ed0545dd36`
- 性质：阶段1.1 问题修复 + 浏览器复验；未进入阶段2，未开发二维码。
- **结论：四种规格浏览器验收全部通过（43/43）；阶段1可以申请正式验收。** 模型费用授权没有恢复历史 Qwen 勾选，原因是阶段1新增测试明确要求“不增加额外 checkbox”，恢复会产生新失败；详见第5节。

## 1. 原始问题

阶段1.1 在真实 Edge + Playwright 下发现：

1. 390×844 首次加载时侧栏展开（约 300px），遮挡聊天；
2. 390×844 对话产生历史后，聊天区固定 560px，输入框 top=929.47、bottom=1124.47，超出 844 视口；
3. 未找到独立模型费用授权勾选框，只有费用提示、发送按钮和 Embedding 联网勾选。

## 2. 根因分析

### 2.1 侧栏

`web/app.py` 使用 `st.set_page_config(..., initial_sidebar_state="expanded")`，该值对桌面和手机都强制展开；手机端没有按窄屏自动折叠。Streamlit 1.65.0 的 `auto` 是官方支持值：桌面展开、移动端折叠。

### 2.2 输入框

`web/scroll_bridge.py` 已有 `fit()`，它按 `innerHeight - chat.top - composer.height - 24 - 16` 计算聊天高度，并写入 carrier/root/box 的 `height`、`min-height`、`flex-basis`。问题不是公式，而是**执行时机**：

- 组件 iframe 首次挂载时，Streamlit 的 header/run summary 尚未完成布局；
- 首次 `fit()` 读到 `chat.top=0`，算出 `560px` 上限并写成 inline `!important`；
- 之后没有重新 fit，CSS 兜底的 `clamp(...,560px)` 也无法覆盖 inline `!important`；
- 因此输入框被推到 929.47–1124.47。

这不是简单改一个固定高度能解决的问题；修复方式是让现有 bridge 在布局稳定后重新测量，而不是把 560 换成另一个固定值。

### 2.3 费用授权

见第5节；不是阶段1误删，而是更早提交 `d7bfec6` 移除了 Qwen 独立勾选，且阶段1测试 `test_live_fee_copy_does_not_add_or_remove_authorization` 明确断言不应增加额外 checkbox。

## 3. 修改文件

| 文件 | 修改 | 原因 |
|---|---|---|
| `web/app.py` | `initial_sidebar_state="expanded"` → `"auto"` | 使用 Streamlit 官方机制，桌面保持展开、移动端默认折叠 |
| `web/scroll_bridge.py` | 新增 `scheduleFit()`；首次挂载、resize 时在下一帧/180/600/1500/2600ms 重新 `fit()` | 修复 `fit()` 在 Streamlit 布局完成前读到 `top=0` 的竞态；不改公式、不改业务 |
| `web/conversation.py` | **未修改**（SHA-256 与阶段1.1 一致 `2DF0B856...`） | 授权先恢复后按契约回退，最终无净变更 |
| `web/design.css` | 未修改 | 现有 CSS 只作兜底，不需要新增固定高度 |

`git diff -- web/scroll_bridge.py` 为 13 行新增；`web/app.py` 中本阶段只改了 `initial_sidebar_state`（同文件另含阶段1原有改动）。

## 4. 修改前后布局

| 指标（390×844，浅色） | 阶段1.1 | 阶段1.2 |
|---|---:|---:|
| 侧栏首次加载 | x=0，宽 300 | **x=-300，宽 1（折叠）** |
| 聊天区 top / height | 353.47 / 560 | **353.47 / 255.53** |
| 输入框 top / bottom | 929.47 / 1124.47 | **625 / 820** |
| 输入框是否在首屏 | 否，超出 280.47 | **是，距底部 24px** |
| 页面横向滚动 | 无 | 无 |

桌面 1600×1100 未变：聊天 height=560、输入框 y=830.69、bottom=935.69；侧栏仍 x=0、宽 300。

## 5. 模型费用授权契约核查

### 证据链

| 节点 | 事实 |
|---|---|
| `6b101a1`（更早基线） | Qwen Live 使用 checkbox：`确认发送真实 Qwen... 请求（会产生 API 费用）`，key=`user_allow_live`；DeepSeek 为点击发送即确认 |
| `d7bfec6` | `git log -S确认发送真实` 显示该提交移除了 checkbox；提交信息是工作区时间线/LangSmith 面板，并非“费用授权安全改造” |
| `139cdbe`（当前 HEAD） | 无 `user_allow_live`，`_live_request_allowed()` 注释为 “no extra checkbox” |
| 阶段1工作区 | `git diff HEAD -- web/conversation.py` 未触及 `_composer`/`_live_request_allowed` 的授权逻辑 |
| 阶段1新增测试 | `test_live_fee_copy_does_not_add_or_remove_authorization` 两个 provider 子测试都断言 `allowed=True` 且 `user_allow_live` 不存在 |
| 旧测试 | `test_qwen_still_requires_its_original_checkbox` 仍要求 Qwen checkbox；它属于保留的 11 项基线失败 |

### 结论

- 历史确实存在过 Qwen 独立勾选，但在阶段1开始前的 `d7bfec6` 已移除，**不是阶段1误删**。
- 当前契约是：费用提示常驻；用户点击「发送」才产生主问题模型请求；`_live_request_allowed()` 要求当前会话已渲染 composer（`user_compose_session==sid`）；页面加载、切换 Provider、打开设置均不调用模型。
- 追问整理可能在主问题回答后额外调用一次模型，UI 已明确提示“回答后整理追问可能额外使用一次模型服务，点击追问按新消息计费”；没有独立追问勾选。
- **未恢复 Qwen checkbox**：恢复会使阶段1契约测试产生新失败，违反“不修改测试、不制造新失败”；且用户本次明确要求去掉 Qwen 独立费用勾选。

风险：当前“发送即授权”依赖用户点击发送；如果后续新增自动重试、自动追问或后台任务，必须先加回显式门禁，不能直接复用 `_live_request_allowed()`。

## 6. 四种规格验收

| 规格 | 结果 | 证据 |
|---|---:|---|
| A 1600×1100 浅色 | **12/12** | [desktop-1600x1100-light.png](../../artifacts/runtime/v37-phase1-2-20261101/desktop-1600x1100-light.png) |
| B 1600×1100 深色 | **12/12** | [desktop-1600x1100-dark.png](../../artifacts/runtime/v37-phase1-2-20261101/desktop-1600x1100-dark.png) |
| C 390×844 浅色 | **18/18** | [mobile-390x844-light.png](../../artifacts/runtime/v37-phase1-2-20261101/mobile-390x844-light.png) |
| D 390×844 深色 | **18/18** | [mobile-390x844-dark.png](../../artifacts/runtime/v37-phase1-2-20261101/mobile-390x844-dark.png) |

补充截图：

- [首次加载：侧栏折叠、输入框可见](../../artifacts/runtime/v37-phase1-2-20261101/mobile-390x844-first-load.png)
- [手动展开侧栏](../../artifacts/runtime/v37-phase1-2-20261101/mobile-390x844-sidebar-open.png)
- [聊天滚动中：输入框保持底部](../../artifacts/runtime/v37-phase1-2-20261101/mobile-390x844-chat-scroll.png)
- [移动端右侧运行面板可访问](../../artifacts/runtime/v37-phase1-2-20261101/mobile-390x844-rail.png)

自动化汇总：**43/43 通过**；桌面 12/12、移动 18/18、主题 4/4、功能 4/4、DOM 1/1、Console 4/4。

## 7. 输入框位置测量

### 首次加载 390×844

- 聊天：top 353.47、height 255.53、bottom 609；
- 输入框：top 625、bottom 820；
- 输入框完整处于 844 视口内，距离底部 24px；
- 侧栏 x=-300、宽 1（折叠），聊天不被遮挡。

### 加载历史后滚动

| 聊天滚动 | chat.scrollTop | 输入框 top | 输入框 bottom | page/shell 滚动 |
|---|---:|---:|---:|---:|
| 顶部 | 0 | 625 | 820 | 0 / 0 |
| 中间 | 1318 | 625 | 820 | 0 / 0 |
| 底部 | 2637 | 625 | 820 | 0 / 0 |

聊天 `overflow-y:auto`，scrollHeight=2891、clientHeight=254；输入框位于聊天容器之外，滚动历史时 y 完全不变；页面与 shell 均不滚动。

### 桌面 1600×1100

chat.scrollTop 0/851/1702，输入框 y 始终 830.69；输入框 bottom=935.69，仍在 1100 视口内。

## 8. 侧栏专项

- 390×844 首次加载：`x=-300, w=1`，默认折叠；
- 聊天可见且不被遮挡；
- 点 `stExpandSidebarButton` 手动展开：`x=0, w=300`；
- 点折叠按钮：回到 `x=-300, w=1`；
- 桌面 1600×1100：`x=0, w=300`，行为不变；
- 没有永久隐藏侧栏、没有改导航内容。

## 9. Console 与请求

- Console Error：**0**
- Page Error：**0**
- 请求失败：**0**
- Console Warning：14 条 Chromium feature 提示（如 ambient-light-sensor / battery），不是项目异常；
- 真实模型、Embedding、LangSmith、12306 请求：**0**。

## 10. 回归测试

正式命令：

```powershell
.\.venv-v35\Scripts\python.exe -m pytest tests -q `
  --junitxml=artifacts\runtime\v37-phase1-2-20261101\regression.xml
```

结果：

| 指标 | 值 |
|---|---:|
| Passed | **1098** |
| Failed | **11** |
| Skipped | **1** |
| Subtests passed | **199** |
| 新失败 | **0** |
| 已解决基线失败 | **0** |

11 个失败 ID 与阶段1.1 baseline **完全一致**，没有新增或修改断言。包括：

- `test_configured_online_default_is_deepseek_and_render_never_calls_agent`
- `test_direct_send_permission_is_session_and_provider_specific`
- `test_qwen_still_requires_its_original_checkbox`
- `test_qwen_ten_clicks_survive_timeout_and_saved_replay`
- `test_qwen_ui_consent_automatically_includes_followups_offline`
- 5 个 Qwen 导航/LangSmith 测试
- `test_bailian_user`

阶段1专项 `tests/test_phase1_user_copy.py` 在完整回归中通过；`tests/test_deepseek_direct_send.py` 仍保留原 3 个失败，未通过改测试制造通过。

> 过程说明：首次在仓库根目录直接执行 `pytest -q` 会把 `artifacts/runtime/.../snapshot` 当作测试收集，产生 6941 个 collection error；这是命令范围错误，不是产品失败。随后改用 `pytest tests` 得到上述正式结果。

## 11. 103 条用例与保护资产

- 103 条正式用例目录、B 快照 7 份 manifest、七维度评分口径：未修改；
- 阶段1.1 的 `scope-checks.json` 记录 `protected_count=1892`、`protected_changes=[]`、`formal_catalogue_count=103`；
- 本阶段只改 `web/app.py`、`web/scroll_bridge.py`，未触碰 `data/`、`docs/evidence/`、历史 Trace、API 账本、P2 审批目录；
- `git status` 中没有新增的正式数据或测试修改；`tests/test_phase1_user_copy.py` 是阶段1既有未跟踪文件，本阶段未编辑；
- 原有 11 失败记录、T04 漏检、批准用例 0 均保留，未通过修改断言/统计范围制造通过。

## 12. 历史证据保护

- 阶段1.1 报告 `docs/reviews/Ticket-Agent-V3.7-Phase1.1-Browser-Acceptance-Report.md` 保留；
- 阶段1.1 截图/verification 目录 `artifacts/runtime/v37-phase1-browser-20261101/` 保留，未被覆盖；
- 本阶段所有截图、JSON、日志写入新目录 `artifacts/runtime/v37-phase1-2-20261101/`；
- 未修改 `docs/evidence/`、历史 Trace、API 账本、B 快照。

## 13. Git 最终状态

- 分支：`feat/ticket-agent-v36-stabilization`
- HEAD：`139cdbe2fca8c7249847f245cffef1ed0545dd36`
- 本阶段净修改：`web/app.py`（sidebar auto）、`web/scroll_bridge.py`（延迟 fit）
- 保留的阶段1未提交修改：`web/conversation.py`、`web/demo.py`、`web/developer_workspace.py`、`web/presentation.py`
- 新增：`web/user_copy.py`、`tests/test_phase1_user_copy.py`、`PROJECT_STATUS.md`、`docs/reviews/`
- 未暂存、未 Commit、未 Push、未 Merge；未使用 reset/clean/stash。

## 14. 剩余风险

1. `scheduleFit` 使用多个短定时器；若未来 Streamlit 布局时间显著变化，可能需改为 ResizeObserver；当前 390/844 与 1600/1100 均通过。
2. 移动端首屏欢迎卡片内容较长，bridge 默认回到底部，首屏看到欢迎文案下半部分；不影响输入框可见与聊天操作，本次未扩大范围修改。
3. 历史 Qwen checkbox 与阶段1契约测试冲突仍在：旧测试继续失败，需产品明确最终契约；本阶段不通过修改测试解决。
4. 当前“发送即授权”无独立费用二次确认；后续若加入自动重试/后台任务，必须重新设计授权门禁。

## 15. 证据索引

| 文件 | 内容 |
|---|---|
| `verification.json` | 43 项浏览器检查与环境 |
| `browser-info.json` | Edge / Playwright / Node / Python / 端口 |
| `dom-checks.json` | 首次加载、移动/桌面 bounding box、侧栏 |
| `input-metrics.json` | 桌面/移动三态输入框位置 |
| `layout-before-after.json` | 阶段1.1 vs 1.2 布局数值 |
| `console.json` | Console / PageError / 请求失败 |
| `authorization-contract.json` | 历史 checkbox、HEAD、测试冲突与决策 |
| `regression.xml` / `regression.log` | 完整 pytest 原始结果 |
| `regression-failures.json` | 11 失败 ID 与 baseline 对比 |
| `regression-summary.json` | 1098/11/1/199 汇总 |
| `source-sha256.json` | 相关源码 SHA-256 与 Git 状态 |
| `screenshots.json` | 8 张截图清单与 SHA-256 |
| `app-start.log` | Streamlit 启动日志 |

## 16. 结论

- 问题1（侧栏）：**已修复**，Streamlit `initial_sidebar_state="auto"`；桌面不变，移动端首次折叠。
- 问题2（输入框）：**已修复**，bridge 延迟重算可用高度；390×844 输入框 bottom=820，历史独立滚动，位置稳定。
- 问题3（授权）：**已核查**；历史 Qwen checkbox 不是阶段1删除，当前阶段1契约测试明确要求无额外 checkbox；保留当前机制并记录风险，不伪造授权控件。
- 四种规格：**43/43 通过**；Console 0 error；完整回归 1098/11/1/199，失败集合与基线一致。
- **阶段1可以申请正式验收**；仍需用户确认后，才能进入阶段2。
