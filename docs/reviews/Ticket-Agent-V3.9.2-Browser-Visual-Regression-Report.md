# V3.9.2 Browser Visual Regression Report

## Scope

Original Ticket Agent workspace, not the V3.9.1 independent railway page.

Evidence: `artifacts/runtime/v392-original-ui-browser3/`  
Script: `artifacts/runtime/v392-original-ui-four.js`  
Screenshots: `desktop-light-original.png`, `desktop-dark-original.png`, `mobile-light-original.png`, `mobile-dark-original.png`.

## Results

| 规格 | 检查 | 页面错误 | 截图 |
|---|---:|---:|---:|
| 1600×1100 浅色 | 9/9 | 0 | 1 |
| 1600×1100 深色 | 9/9 | 0 | 1 |
| 390×844 浅色 | 10/10 | 0 | 1 |
| 390×844 深色 | 10/10 | 0 | 1 |
| **合计** | **38/38** | **0** | **4** |

Checks included:

- 原版 hero“出行，从这里开始”、四快捷入口、原顶部栏；
- 原右侧“本次行程摘要 / 我的订单 / 推荐车次 / 常用功能 / 政策速查”；
- 铁路模拟订单/待确认 rail 增量存在；
- 原模型设置入口；
- 不存在独立铁路标题；
- 不存在“咨询与演示业务 / 全国铁路模拟出行” radio；
- 原聊天框发送真实静态查询；
- 聊天结果区出现“真实静态结果”和工具返回表；
- 手机“相关信息 / 常用功能”开关；
- 无整页横向溢出。

## Notes

- 四规格是离线 Mock 会话，验证 UI/静态数据/Agent 接线；不是 Live API 通过。
- 原版四面板/开发者/测试控制台由原有离线回归保护；本轮只对用户工作空间做浏览器回归。
- 真实静态查询显示 20 行（原 planner limit），不是模型编造。
- Qwen/DeepSeek 的 API 验证另见两份报告；Live 浏览器 DeepSeek 普通对话成功，Qwen UI 仍有未解释的通用错误，未计入 38/38。
