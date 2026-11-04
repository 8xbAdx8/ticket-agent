# V3.9.5 浏览器报告

实际本机Edge/Playwright，桌面1600×1100、手机390×844，各浅/深主题。最终计数：{'passed': 48, 'failed': 0, 'page_errors': 0, 'console_errors': 8, 'network_failures': 8}。Console与requestfailed分别记录，包含被本地测试拦截的fonts.gstatic.com图标请求，不声称Console为0。全部原始浏览器输出在 `artifacts/runtime/v394-implementation-v395-20261104/browser-final/results.json`。

修改前采用用户当前截图（当前查询表格）及V394原件artifacts/runtime/v394-browser-final2/desktop-light-default-ticket.png。修改后8截图：browser-final下desktop-light/desktop-dark/mobile-light/mobile-dark各cards.png与stops.png。已实际查看桌面和手机截图，时间对齐、站名和跨行线路轴清晰，卡片与经停在原聊天滚动容器内，右栏收起时手机聊天优先。整页无横向溢出；经停默认按需展开，不把经停当换乘。

首轮browser/保留热加载Worker占用失败；browser-r2复验，browser-final最后加实际时刻/运行时长断言与手机收栏截图。最终测试不只检查HTML存在，也点击经停、下一页和上一页。无真实模型/铁路/支付请求。未使用实体手机，未重验全交易流程；不得称整个项目验收通过。
