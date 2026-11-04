# Ticket Agent V3.9.4 — Browser Report

## 范围

原版 Ticket Agent 用户工作空间，真实 Edge + Playwright；离线 Mock；隔离 `v394-*` 模拟库；未调用真实模型/铁路/支付。

## 规格与结果

| 规格 | 检查 | 结果 | 页面错误 |
|---|---:|---:|---:|
| 1600×1100 浅色：原版布局/四快捷/默认查余票/四步闭环 | 11 | **11/11** | 0 |
| 1600×1100 深色：默认查余票/无横向溢出 | 2 | **2/2** | 0 |
| 390×844 浅色：原版/右栏/默认查余票/无溢出 | 5 | **5/5** | 0 |
| 390×844 深色：原版/右栏/默认查余票/无溢出 | 5 | **5/5** | 0 |
| 右栏三模式（车次/车站/经停） | 6 | **6/6** | 0 |
| 错误恢复/新会话清理 | 3 | **3/3** | 0 |
| 退票费率/P06 默认表单 | 2 | **2/2** | 0 |
| **合计** | **34** | **34/34** | **0** |

主脚本 `results.json` 另有 `errors=[]`（无 pageerror）。四个脚本合计 34 项，8 张截图。

## 实际验证

1. 首页四快捷入口：查余票/问政策/看订单/退票费率均存在。
2. 默认查余票：来源 `GTFS`，**109 班**，当前 20 班，上海虹桥/杭州东，模拟余票 20；不存在“本轮查询未完成”。
3. 四步闭环：`2/4 → 3/4 → 4/4 → 演示完成`；订单 PAID；无真实支付。
4. 右栏查车次：候选选择→静态 109 条；来源/版本/当前页/下一页可见。
5. 右栏查车站：真实 5 条。
6. 右栏查经停：G7541 真实班次→经停记录。
7. 错误恢复：不存在站名查询不污染聊天顶部；随后上海查询恢复；新会话清空。
8. 手机端“相关信息 / 常用功能”开关、右栏展开、默认查余票均可用。
9. 桌面深色/手机浅深无整页横向溢出；输入框/发送按钮保留。
10. 原版 hero、三栏、右侧信息栏、模型设置、历史会话、开发者/测试台入口保留。

## 截图

`artifacts/runtime/v394-browser-final2/`

- `desktop-light-default-ticket.png`
- `desktop-light-demo-complete.png`
- `desktop-dark-default-ticket.png`
- `mobile-light-default-ticket.png`
- `mobile-dark-default-ticket.png`
- `desktop-light-rail-trips.png`
- `desktop-light-rail-stops.png`
- `desktop-light-refund-baggage.png`

## 修改前

- V3.9.3 原版 UI：`artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/ui-sealed/`
- V3.9.2 历史截图：`artifacts/runtime/v392-delivery-20261103-234500/evidence/desktop-light-original.png`

## 限制

- 浏览器不检查 Streamlit DataFrame 的单元格文本（只检查结果卡数量/来源/状态）；SQLite/测试直接断言真实行。
- 没有调用真实模型；Live 浏览器不在本轮范围；未计入通过。
- Console 网络失败未作为通过条件；只对 PageError=0 及交互断言负责。
- 实体手机/缩放/长文本/完整多人退改签浏览器流程未覆盖；由 T077–T100 与 V39 测试覆盖业务，不冒充完整浏览器交易验收。
