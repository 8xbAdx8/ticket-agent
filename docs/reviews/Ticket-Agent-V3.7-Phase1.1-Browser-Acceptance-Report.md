# Ticket Agent V3.7 阶段1.1 浏览器视觉验收报告

- 日期：2026-11-01（Asia/Shanghai）
- 分支 / HEAD：`feat/ticket-agent-v36-stabilization` / `139cdbe2fca8c7249847f245cffef1ed0545dd36`
- 性质：浏览器视觉与 DOM 行为验收，不是业务重构。
- **结论：浏览器验收已真实执行，但阶段1不能宣布全部通过。** 桌面端 12/12 通过，移动端 9/12，存在 3 个移动端布局/可见性问题；另有“模型费用授权”控件缺失的功能差异。

## 1. 验收目标

使用本机真实 Microsoft Edge + Playwright 操作真实运行的 Streamlit 页面，覆盖：

- 1600×1100 浅色 / 深色；
- 390×844 浅色 / 深色；
- 输入框固定与聊天区域独立滚动；
- DOM 结构、Console、页面请求；
- 阶段1用户端文案与功能入口。

不使用静态 HTML、ImageGen 或人工截图替代。

## 2. 实际环境

| 项 | 值 |
|---|---|
| Microsoft Edge | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`，**156.0.4314.50** |
| Playwright | **1.64.1**（`chromium.launch({ channel: "msedge" })`，真实 Edge） |
| Node | v24.15.0 |
| Python | 3.12.14（`.venv-v35`） |
| 应用 | Streamlit 1.65.0，`http://127.0.0.1:8513/` |
| 运行模式 | **离线 Mock**：`TICKET_WEB_OFFLINE_ONLY=1`、`TICKET_DISABLE_LOCAL_SECRETS=1`、`AGENT_PROVIDER=mock`、`AGENT_ENGINE=legacy` |
| 真实模型 / Embedding / LangSmith | **0 次** |

Playwright 原本未安装；本次从本机 npm 缓存**离线**安装到验收目录 `artifacts/runtime/v37-phase1-browser-20261101/tools/`，未修改项目 `package.json`、`requirements` 或锁文件，也没有全局安装。

## 3. 启动

```powershell
$env:TICKET_WEB_OFFLINE_ONLY='1'
$env:TICKET_DISABLE_LOCAL_SECRETS='1'
$env:AGENT_PROVIDER='mock'
$env:AGENT_ENGINE='legacy'
.\.venv-v35\Scripts\python.exe -m streamlit run web/app.py `
  --server.port 8513 --server.address 127.0.0.1 --server.headless true
```

启动日志：`artifacts/runtime/v37-phase1-browser-20261101/app-start.log`（HTTP 200）。

## 4. 四规格结果

| 规格 | 截图 | 检查项 | 结果 |
|---|---|---|---:|
| A 1600×1100 浅色 | [desktop-1600x1100-light.png](../../artifacts/runtime/v37-phase1-browser-20261101/desktop-1600x1100-light.png) | 12 | **12/12** |
| B 1600×1100 深色 | [desktop-1600x1100-dark.png](../../artifacts/runtime/v37-phase1-browser-20261101/desktop-1600x1100-dark.png) | 12 | **12/12** |
| C 390×844 浅色 | [mobile-390x844-light.png](../../artifacts/runtime/v37-phase1-browser-20261101/mobile-390x844-light.png) | 12 | **9/12** |
| D 390×844 深色 | [mobile-390x844-dark.png](../../artifacts/runtime/v37-phase1-browser-20261101/mobile-390x844-dark.png) | 12 | **9/12** |

补充证据：

- [移动端首次加载默认侧栏](../../artifacts/runtime/v37-phase1-browser-20261101/mobile-390x844-fresh-default.png)：390px 新加载时侧栏展开，覆盖聊天区。
- [移动端侧栏关闭后的实际内容](../../artifacts/runtime/v37-phase1-browser-20261101/mobile-390x844-light.png)。
- [移动端右侧运行面板可滚动访问](../../artifacts/runtime/v37-phase1-browser-20261101/mobile-390x844-rail.png)。
- [桌面端模型设置](../../artifacts/runtime/v37-phase1-browser-20261101/desktop-model-settings.png)、[DeepSeek 在线选择](../../artifacts/runtime/v37-phase1-browser-20261101/desktop-deepseek-selected.png)。

## 5. 桌面端验收（12/12 通过）

- 主导航、用户工作空间、开发者工作空间、测试控制台入口均可见；
- 用户端双栏：聊天列 x=341.59、宽 772.33；右侧栏 x=1177.92、宽 380.48，同 y=254.69；
- 输入框在聊天区下方：聊天 bottom=814.69，输入框 y=830.69，bottom=935.69（<1100）；
- 页面无横向滚动：`scrollWidth=1600`，viewport=1600；
- 车次表、政策卡片、订单查询结果、五阶段运行面板均正常显示。

## 6. 输入框固定与独立滚动

### 桌面端：通过

| 聊天滚动位置 | 聊天 scrollTop | 聊天 scrollHeight / client | 输入框 y | 页面滚动 |
|---|---:|---:|---:|---:|
| 顶部 | 0 | 2260 / 558 | 830.69 | 0 / 0 |
| 中间 | 851 | 2260 / 558 | 830.69 | 0 / 0 |
| 底部 | 1702 | 2260 / 558 | 830.69 | 0 / 0 |

- 聊天区域 `overflow-y:auto`，可独立滚动；
- 输入框不在聊天容器内（`composeInsideChat=false`）；
- 滚动历史时输入框 y 完全不变，页面 shell 不滚动。

### 移动端：相对固定通过，但初始不可见（未通过）

| 聊天滚动位置 | 聊天 scrollTop | 输入框 y | 页面 shell 滚动 |
|---|---:|---:|---:|
| 顶部 | 0 | 929.47 | 0 |
| 中间 | 1166 | 929.47 | 0 |
| 底部 | 2333 | 929.47 | 0 |

- 输入框相对聊天容器仍然固定，不随历史消息滚动；
- **但 390×844 初始视口中输入框 bottom=1124.47 > 844**，必须先滚动整个页面才能看到输入框；
- 失败检查：`mobile/composer_in_viewport`。

## 7. 移动端发现的问题

### P1：390px 首次加载侧栏默认展开并遮挡聊天

新开 390×844 页面（不是从桌面缩放）时：

- `stSidebar` 边界：`x=0, width=300`；
- 聊天区 `x=16, width=358`，被 300px 侧栏覆盖；
- 截图：[mobile-390x844-fresh-default.png](../../artifacts/runtime/v37-phase1-browser-20261101/mobile-390x844-fresh-default.png)；
- 失败检查：`mobile/sidebar_default_covers_chat`、`mobile/fresh_chat_visible`。

用户必须先点侧栏左上角「«」才能看到聊天。阶段1要求“手机端聊天优先显示”，当前不满足。

### P1：移动端输入框初始不在 844px 视口内

- 聊天区固定高度 560px，输入框 y=929.47、bottom=1124.47；
- 首次打开只看到聊天上半部分，输入框在页面下方；
- 页面可以滚动到输入框（`composer_reachable_by_scroll` 通过），但不是“输入框固定在对话区域底部且可见”的体验；
- 失败检查：`mobile/composer_in_viewport`。

### 已通过项

- 单栏堆叠：右侧运行面板在输入框下方，`x=16, width=358`；
- 右侧面板可通过页面滚动访问（`rail_scroll_into_view` 通过），没有被 `display:none` 隐藏；
- 无横向滚动：`scrollWidth=390`；
- 可见按钮均未超出屏幕；
- 聊天内容无 DOM 级横向溢出。

## 8. 深浅主题

主题由项目自己的「外观」单选控制，不是 Playwright `color_scheme`：

- 点击「深色」后 `body` 背景变为 `rgb(17, 24, 32)`；
- 点击「浅色」后 `rgb(251, 252, 253)`；
- 桌面、移动端均通过；
- 主题检查 4/4 通过，无 BLOCKED。

## 9. 阶段1功能检查

| 项 | 结果 |
|---|---|
| 用户端欢迎语简洁 | 通过：“查车票、问政策、查看订单，用一句话开始。” |
| 演示数据来源明确 | 通过：“车票为演示数据，政策为示例条款” |
| 不提供真实出票 | 通过：“不真实出票 / 不提供真实出票” |
| 不真实扣款 | 通过：“不会真实扣款” |
| 示例政策说明 | 通过 |
| 离线不可用提示友好 | 通过：“DeepSeek 在线服务暂不可用……不会自动切换” |
| 确认操作中文说明 | 通过文案：“锁座、下单、支付、退票会先请你确认”；**实际确认弹窗未触发/未验证** |
| 技术诊断集中在开发者端 | 通过：用户端仅保留“服务诊断（开发者）”入口 |
| 测试控制台独立 | 通过：导航入口存在 |
| Provider 选择 | 通过：`Legacy Mock / LangChain Mock / DeepSeek Live / Qwen3.8-Flash Live` 四项可选 |
| **模型费用授权** | **未发现独立“确认发送真实请求”勾选框**；当前只有费用提示 + 发送按钮，另有 Embedding 联网勾选框。若阶段1要求保留原模型费用授权控件，此项不满足 |
| 原业务规则/控件 | 通过基本流程：离线连续发送 5 条消息，查票、政策、订单查询、追问均正常；未执行真实写操作/支付 |

## 10. Console / 请求

| 项 | 结果 |
|---|---|
| Console Error | **0** |
| Page Error | **0** |
| 请求失败 | **0** |
| Console Warning | 14 条，均为 Chromium “Unrecognized feature”等浏览器提示，不是项目异常 |

## 11. 未通过 / 未验证 / BLOCKED

### 未通过

1. `mobile/composer_in_viewport`：390×844 下输入框初始 bottom=1124.47，超出视口；
2. `mobile/sidebar_default_covers_chat`：首次加载侧栏 300px 覆盖聊天；
3. `mobile/fresh_chat_visible`：同上，首次加载聊天不可见；
4. `function/model_fee_authorization_present`：未发现独立模型费用授权勾选框（功能差异，需产品确认）。

### 未验证

- 实际“确认执行模拟操作”弹窗：未触发写操作；
- 真实业务错误提示：本次未触发模型/工具错误；
- 真实模型/Embedding/LangSmith：按任务要求 0 请求。

### BLOCKED

**无。** Edge、Playwright、Streamlit、主题控制均可运行。

## 12. 代码与 Git

- **未修改任何产品代码**；没有修改 `target/`、SYSTEM_PROMPT、103 用例、评分口径、历史 Trace、账本、B 快照、`docs/evidence/`、`data/rag1000/`。
- 新增：`artifacts/runtime/v37-phase1-browser-20261101/`（截图、verification、DOM、Console、源码 SHA、工具）；
- 新增：本报告；
- 增量更新：`PROJECT_STATUS.md` 第12节；
- Git 仍为 `feat/ticket-agent-v36-stabilization` / `139cdbe...`；阶段1原有未提交修改保留；未 Commit/Push/Merge。

## 13. 阶段1结论

- **桌面 1600×1100（浅/深）**：视觉、双栏、输入框固定、主题、Console 均通过；
- **移动 390×844（浅/深）**：单栏、右侧面板访问、无横向滚动通过；**输入框初始不可见 + 侧栏默认遮挡聊天**，不能判定移动端通过；
- **阶段1不能正式完成验收**，建议先修复移动端两处布局（侧栏初始折叠、聊天高度/输入框随视口自适应），再重跑本报告脚本；
- 模型费用授权缺失属于功能契约差异，需用户确认阶段1是否要求保留独立勾选框。

## 14. 证据索引

| 文件 | 内容 |
|---|---|
| `verification.json` | 37 项检查、环境、Console、DOM 快照 |
| `browser-info.json` | Edge / Playwright / Node / Python / 启动命令 |
| `dom-checks.json` | 桌面/移动/首次移动的 bounding box、滚动属性 |
| `input-metrics.json` | 顶部/中间/底部三态输入框位置 |
| `console.json` | Console 错误/警告、PageError、失败请求 |
| `function-summary.json` | 阶段1功能项结果 |
| `source-sha256.json` | 相关源码 SHA-256 |
| `screenshots.json` | 截图清单与 SHA-256 |
| `app-start.log` | 启动日志 |
| `desktop-*.png` / `mobile-*.png` | 四规格与补充截图 |
