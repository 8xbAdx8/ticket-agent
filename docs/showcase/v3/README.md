# Ticket Agent V3：界面效果图与功能介绍

**更新：绿色布局已接入实际 Streamlit 前端。** 请使用 [V3 真实前端说明](../../handoff/v3/V3真实前端使用说明.md) 启动，并查看 [最新实际截图](../../evidence/v3_live_ui/delivery_browser/01-query.png)。本目录的 HTML 和原图片仍保持历史属性，没有替换成新的执行结果。

下面记录的是设计材料制作时的旧基线。旧截图/核对脚本假定旧 Web 源码；当前新界面的验证应使用 `scripts/check_v3_live_ui.py` 和 `scripts/capture_v3_live_ui.py --out <新目录>`，避免覆盖本目录历史图片。

材料日期：2026-10-13（Asia/Shanghai）。实际 Agent 源码基线为 `a4d6d62f88f796b39f4f27f239eaa6308d4143b2`；新增材料位于 `codex/ticket-agent-v3-showcase` 分支。

本目录包含两种材料：**效果图**是独立设计稿，读取历史 Mock 数据；**真实截图**由当前 `web/app.py` 在隔离 Mock 环境中实际运行后采集。二者不能混为“已上线的新界面”。真实大模型尚未联网实测。

## 快速使用

直接用浏览器打开 [index.html](index.html)。页面无需安装依赖或联网，支持场景切换、动画、工具参数、JSON、历史回放、核心代码导览。新输入不会提交给 Agent；“播放回放”只播放当前已保存场景。

要运行真正的 Agent，请按照 [成员 B 的 V3手册](../../handoff/v3/B_V3测试对接手册.md) 使用 Streamlit，或运行 `scripts/v3_api_example.py`。正式 A/B/C 分工和交接状态沿用 V3 手册，本素材不产生比赛成绩。

## 文件与用途

| 文件 | 用途 |
|---|---|
| [功能与代码介绍.md](功能与代码介绍.md) | 项目功能、架构、源码位置与核心代码讲解 |
| [比赛讲解稿.md](比赛讲解稿.md) | 可用于作品介绍的简洁口头稿 |
| [图库.md](图库.md) | 所有图片与配图说明 |
| index.html / showcase.css / showcase.js | 可打开、可编辑的完整设计稿源码 |
| demo-data.js / 数据与源码索引.json | 从 V3实际附件和Python源码提取的场景/参数/代码摘录 |
| 效果图/ | 6张PNG：查询、订票、政策、处理中、代码导览、移动端布局 |
| 真实截图/ | 3张PNG与当次真实Mock Trace：查询、订票、政策 |
| 效果图验证.json | 浏览器交互、移动端无溢出、0外部请求、0JS错误的实际结果 |
| 真实截图/browser_check.json | 实际Streamlit浏览器截图的运行信息 |

## 图片选择建议

- 实现证据：使用“真实截图”目录中的图片，并与同目录 JSONL 对照；标题写“LangChain Mock 实际运行”。
- 视觉方案：使用“效果图”目录中的图片，标题写“界面设计稿”；页面内已有设计标识。
- 代码说明：用05-code-tour.png辅助讲解，再引用真实Python文件；设计稿读取了4段实际源码。
- 处理动画：04-processing.png仅展示通用等待状态，不包含模型内部思维链。效果稿中的演示延迟不是Agent实际耗时。
- 数据：查询日期、价格、库存、订单ID、工具参数和耗时均有对应Mock附件；历史记录不代表真实票务或当前库存。

## 重新生成

在项目根目录使用现有V3环境：

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv-v3\Scripts\python.exe scripts/build_v3_showcase.py
```

该脚本读取 `docs/evidence/v3/final_framework/`，按AST提取Python函数，生成展示数据。更新核心源码后，须重新审查、验证再生成。

渲染和真实截图脚本需要Node.js、Playwright和本机Chromium浏览器，仅制作材料时需要。当前素材已提供PNG，查看不需要它们。可把渲染依赖安装到被忽略的运行目录，避免加入Python依赖：

```powershell
npm install --prefix artifacts/runtime/ui-renderer playwright@1.62.1
$env:NODE_PATH="$PWD\artifacts\runtime\ui-renderer\node_modules"
node scripts/render_v3_showcase.cjs --browser "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
.\.venv-v3\Scripts\python.exe scripts/capture_v3_actual.py --browser "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

上述是复现方法，本次实际使用已安装的Playwright1.62.1和Edge155.0.4283.45，无额外安装。浏览器路径按本机安装位置调整。capture脚本只启动并停止自己的隔离服务，原DB、Trace和V1/V2标签不变。

## 本次实际验证

- 6张设计PNG；场景切换、工具参数选择、政策P11来源、动画、代码导览、历史回放、完整JSON均检查通过。
- 390px移动端没有横向溢出；页面0外部HTTP请求、0JavaScript运行错误。
- 3张真实截图：query_tickets；query_tickets→lock_seat→create_order；search_policy。3轮均是langchain_mock，所有调用ok=true。
- 截图前等待指标和表格渲染完成，避免把加载骨架作为最终图。
- 四段代码通过AST从实际源码提取；原99个保护文件另行核对。此处无真实模型成绩或B正式测试指标。
