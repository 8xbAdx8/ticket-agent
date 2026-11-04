# V3.10 浏览器报告


现场基线：HEAD `953c8823bed988ec53579be794319d69adbf5b34`，分支 `feat/ticket-agent-v36-stabilization`。Codex 的业务状态统一提交已落地；本轮修改文件 5 个、新增 2 个（`web/v39_payment.py`、`tests/v39/test_v310_contract.py`），未修改 D9/P01、GTFS、产品 v391、正式 103/B。未 commit/push/merge/tag。

## 执行

- 桌面 1600×1100 浅/深
- 手机 390×844 浅/深
- 真实 Edge + Playwright
- 核心用户工作空间 25/25 通过；PageError=0，ConsoleError=0，RequestFailed=0
- 8 张核心截图？本轮实际 5 张核心；Live QR/PAID 另存

## 未通过

`v310-extra-browser` 的旧“查车站”入口点击超时：该 `<p>查车站</p>` 在当前业务面板布局下不可见，属于原版铁路辅助入口可见性回归。因此完整浏览器套件为 **25/47**，不能写成 47/47。

## Live

`live-qr2.png` 显示 PAY pending + QR；`live-paid2.png` 显示 PAID。Qwen `qwen-query.png` 显示 109 班。
