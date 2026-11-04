# V3.9.3 DeepSeek 真实API测试

模型 `deepseek-flash`；日期2026-11-04；开发验证，非独立审查。**LIVE_API_VERIFIED=PARTIAL**，不以HTTP200/正常结束冒充业务PASS。

| 批次 | HTTP请求 | Prompt | Completion |
|---|---:|---:|---:|
| live-deepseek | 17 | 142012 | 1925 |
| live-v2-deepseek | 4 | 22203 | 561 |
| live-ui-deepseek | 4 | 18465 | 335 |

成本与剩余额度未知，无Provider计费回执。现有配置加载，未打印密钥；原账本不改，测试账本在各批次usage。计入UI额外追问，不混入主回合。

| 场景 | 调用链正常结束 | 实际工具序列 | finish_reason |
|---|---|---|---|
| live-deepseek / ordinary | True | 无工具 | stop |
| live-deepseek / explicit | True | railway_search_stations, railway_search_stations, railway_query_trips | stop |
| live-deepseek / followup | True | railway_trip_stops | stop |
| live-deepseek / missing_date | True | 无工具 | stop |
| live-deepseek / fill_date | True | query_tickets, railway_search_stations, railway_search_stations, railway_query_trips | stop |
| live-deepseek / unknown_station | True | railway_search_stations | stop |
| live-deepseek / unknown_train | True | railway_query_trips | stop |
| live-deepseek / read_error | True | railway_get_order | stop |
| live-v2-deepseek / missing_date | True | 无工具 | stop |
| live-v2-deepseek / fill_date | True | railway_search_stations, railway_search_stations, railway_query_trips | stop |

上表不是语义PASS表。v2缺日期只追问→补日期使用railway_*同源工具，并返回40总数/40当前页。原UI车次结果静态卡/数量/无通用错误已验；DeepSeek为单Provider隔离配置，双Key切换未验。只读错误工具ok=false保留，模型可解释失败；查询库订单/报价/提案/交易0、FK空。

首批来源/形状误述、旧工具混用、模型措辞风险未抹除。长回答全部时刻/时长/全义正确性未完成验收。原UI截图 `artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/live-ui-deepseek/`；原CLI回复和Trace `artifacts/runtime/v391-d9-lifecycle-v393-20261104-001639/`各批次results.json与session traces/provider_runs.jsonl。完整HTTP和逐请求token见api-accounting-raw.json/summary.json，完整命令见实施报告及保存脚本。
