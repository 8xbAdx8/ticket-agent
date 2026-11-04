# 业务状态统一：真实Edge浏览器验收

Edge+Playwright；1600×1100浅/深、390×844浅/深，各26检查，合计104/0/0。32张真实截图：`artifacts/runtime/v394-implementation-business-state-20261104-220744/browser-error-proof-02/`。

流程：新会话→真实GTFS查车/经停→选择车次→3名合成乘客→模拟库存/报价→建单提案/确认→支付提案/确认→Agent查单PAID→选ACTIVE退1人→目标报价/改剩2人→Agent查单CHANGED→注入模型length→确认已提交状态仍正确且无重复交易→历史运行选择→刷新恢复→新会话无他人订单→横向溢出检查。每个关键节点读取真实隔离SQLite，不只断言DOM存在。经停/查询保留真实静态Adapter，模型是离线确定性脚本，不属于真实API浏览器验收。

PageError0；Console错误16；网络失败16，均为拦截`fonts.gstatic.com/.../travel_explore/...svg`。没有将Console错误写成零。原始数据、每项检查和实际SQL在results.json，Playwright脚本`artifacts/runtime/v394-implementation-business-state-20261104-220744/browser-post-live.js`。页面保留旧导航、模型选择、四面板、历史会话与开发者/测试空间。

初次截断注入抛异常被Legacy包装legacy_provider_error，故browser-error-proof第21项失败；保留该批次。最终注入真实`finish_reason=length`走原Agent截断处理，不修改生产分类逻辑，新的browser-error-proof-02四规格全部通过。其他早期失败目录完整保留。

手机信息栏可展开、独立滚动；表格可内部横向查看，页面没有横向溢出。未重做CSS或改变原控件key；新控件使用独立key，旧乘客控件按订单版本清除残留选择。最终测试服务已停止，8502用户服务未操作。

状态：BROWSER_VERIFIED（上述离线模型+真实本地数据/交易范围）；LIVE浏览器全流程未执行。

截图索引：

- `desktop-dark-change-proposal.png`
- `desktop-dark-changed.png`
- `desktop-dark-create-proposal.png`
- `desktop-dark-incomplete-model.png`
- `desktop-dark-paid.png`
- `desktop-dark-pay-proposal.png`
- `desktop-dark-refund-proposal.png`
- `desktop-dark-restored.png`
- `desktop-light-change-proposal.png`
- `desktop-light-changed.png`
- `desktop-light-create-proposal.png`
- `desktop-light-incomplete-model.png`
- `desktop-light-paid.png`
- `desktop-light-pay-proposal.png`
- `desktop-light-refund-proposal.png`
- `desktop-light-restored.png`
- `mobile-dark-change-proposal.png`
- `mobile-dark-changed.png`
- `mobile-dark-create-proposal.png`
- `mobile-dark-incomplete-model.png`
- `mobile-dark-paid.png`
- `mobile-dark-pay-proposal.png`
- `mobile-dark-refund-proposal.png`
- `mobile-dark-restored.png`
- `mobile-light-change-proposal.png`
- `mobile-light-changed.png`
- `mobile-light-create-proposal.png`
- `mobile-light-incomplete-model.png`
- `mobile-light-paid.png`
- `mobile-light-pay-proposal.png`
- `mobile-light-refund-proposal.png`
- `mobile-light-restored.png`
