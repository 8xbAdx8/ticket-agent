# V3.9.1 账本追加确认与保护基线补充记录

2026-11-03；用户明确回复：“是，保留追加并以当前账本继续”。此确认只解除上一批报告中的账本追加来源/保护基线待确认项，不代表用户接受全部V3.9.1成果，也不授权真实API、模型费用、Harness、Bridge或Git操作。

## 现场核对

账本`artifacts/runtime/api-usage/bailian/dbc4325ea7a9515b7a04/requests.jsonl`仍为272726字节，SHA256为`75677a5f9fd4a769fbcc9ce417a94ab70643c44b458c7e6eb09c86899b019e06`。相对开工268991字节追加3735字节，原前缀SHA `07782195950cd4f2a79851c0d577cf28ac28810aa9666992242400690ec6dcc7`完整。未出现额外追加。记录用户确认，不虚构具体操作者或会话的独立归因证据。

1892组原样；4056/5538组保留同一账本的已批准差异，以精确当前SHA建立增量覆盖记录。核对后无未批准差异。原始清单、开工manifest、旧待确认结论及旧ZIP不改、不删，不能把旧SHA改成新SHA后声称历史零差异。

新证据目录：`artifacts/runtime/v391-ledger-baseline-confirmation-20261103-163842/`，含user-confirmation.json、effective-protected-baseline.json、状态增量证明、更新版审查任务和v2 ZIP/manifest/封存核验。

## 状态和测试

IMPLEMENTED、TESTED维持；保护追加待确认阻塞已解除。INDEPENDENTLY_REVIEWED=NOT_RUN；ACCEPTED=PENDING_USER_ACCEPTANCE；正式103与Bridge仍为原有BLOCKED。本次只更新文档及审查包，不改产品/测试/数据库或运行服务。

修改前重新逐SHA核对上版封存980文件，均无变化；沿用前批实际164/0/0、新增20项包含其中、旧1441/11/1和199子测试、浏览器128/128及20截图。此次未重新运行这些测试，不把沿用结果称为新测试。

旧ZIP SHA为`67959162f8dff0e57ce78f469bcadd1b3d410f9795317c1dc18cdad2b71d3d8d`，完整保留；v2加入本确认及更新后的PROJECT_STATUS.md，旧实施报告的第9/10节待确认项作为历史保留，由本记录增量取代。v2独立审查仍须用户人工转交，不自动派发或调用模型。

本次变更文件：PROJECT_STATUS.md、本补充报告、新证据目录（含生成脚本、确认/保护回执、任务书、SHA清单和新ZIP）。HEAD仍4340b6640025be95e8300a3d625a32cfb431e35d，分支不变，无暂存、提交、推送、合并、Tag或Release。
