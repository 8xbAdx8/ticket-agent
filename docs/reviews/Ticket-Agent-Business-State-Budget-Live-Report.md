# API安全预算V2与受控DeepSeek验收

显式`TICKET_ACCEPTANCE_BATCH`开启，持久SQLite验收账本位于`artifacts/runtime/v394-implementation-business-state-20261104-220744/live-deepseek/acceptance-budget.sqlite`。原日常非阻断用量政策保留。DeepSeek/Qwen都在真实HTTP派发前经过统一预留；新会话/刷新不创建新批次。固定50HTTP、400000Token、320000预警、4096最大输出，非交易最多2次显式受控重试，交易0自动重试，SDK仍0重试。

预留保守UTF8载荷+协议余量+最大输出，未知结果保留预留不作0；结算真实prompt/completion，超出预留立即熔断；账本缺失或策略不符fail-closed，不能自动重建解除额度。费用NULL/UNKNOWN。相同批次跨进程原子BEGIN IMMEDIATE，测试验证50竞争和Token上限、输出上限、2次受控重试、交易拒绝、两个SDK路径。7项预算确定性测试通过，不靠大量真实消费触顶。

| 批次 | 结果 | 新真实HTTP | Token | 说明 |
|---|---|---:|---:|---|
| live-deepseek | BLOCKED | 0 | 0 | 验收脚本未传费用授权参数，原费用保护正确拦截 |
| live-deepseek-attempt-02 | FAIL（最后回答） | 11 | 88221 | 查票/库存/报价/建单提案/页面确认支付/退一人/改两人真实完成；最后查单1024输出上限截断，原日志与交易保留 |
| live-deepseek-readonly-03 | PASS | 2 | 6214 | 同批次账本、同订单，新只读上下文2048输出；只暴露查单工具，金融表指纹不变 |
| 累计 | 受控范围已核验 | 13 | 94435 | 剩37HTTP、305565Token，无未结用量，未到预警 |

不将最后一次PASS覆盖原FAIL；不重放已完成交易。原始模型回复、HTTP/Token记录、Trace/audit/run_events在各sessions与api-usage目录。最后回答逐项为CHANGED、ACTIVE2、REFUNDED1、支付120元、退款24元、手续费6元、净支付96元，符合SQL。真实铁路0、真实支付0、Embedding0、LangSmith0；Qwen真实0，只离线共享预算验证。

实际执行：`.venv-v35\Scripts\python.exe -B artifacts/runtime/v394-implementation-business-state-20261104-220744/live_acceptance_02.py browser-sealed-03`（原批次失败保留）；最后新只读`.venv-v35\Scripts\python.exe -B artifacts/runtime/v394-implementation-business-state-20261104-220744/live_readonly_03.py browser-error-proof-02`。脚本开工闸门要求离线套件、旧失败ID、四规格和源码SHA已验证；已消费批次不能盲目再次执行。

成本未知，不估成零。两个默认旧账本的外部追加已由用户确认来自本人；不是本轮13次请求，见external-ledger-confirmation.json。LIVE_API_VERIFIED仅限DeepSeek受控Conversation/Registry/SQL，未独立审查、未用户最终验收。

完成核对：2026-11-05 00:03（Asia/Shanghai）。13请求真实Prompt Token=90784，Completion Token=3651，合计94435；未知费用不记零。该时间晚于11月4日开工，日期跨日不代表新验收批次。
