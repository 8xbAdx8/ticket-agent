# Ticket Agent V3.9.5 实施报告

日期2026-11-04。状态：IMPLEMENTED；TESTED；BROWSER_VERIFIED（本报告范围）；INDEPENDENTLY_REVIEWED=NOT_RUN；ACCEPTED=PENDING_USER_ACCEPTANCE。继承的冻结产品数据库来源、正式103原始B执行器、Bridge仍BLOCKED。不是整个项目COMPLETE。

## 审计与数据流

现场HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`，原分支、暂存空；完整开工状态/6749文件hash在 `artifacts/runtime/v394-implementation-v395-20261104/before.json`。保留V3.9.4及所有既有修改。Agent静态结果经conversation→共享result_card；快捷查询经Registry记录session.railway_queries；旧默认流程分别记录车站/车次/库存，又在右栏画完整表，造成截图中的重复。

## 实际修改

| 文件 | 原因 |
|---|---|
| web/railway_cards.py（新增） | 纯展示投影、ISO/GTFS超24小时转换、实际时长、独立车次卡、按需经停与节点；仅显示匹配身份的历史模拟库存。 |
| web/railway_queries.py | 复用卡片/站名/经停展示；隐藏默认路线辅助站/库存结果；同查询翻页替换可见页，底层原记录保留；聊天内上一页/下一页，保持参数。翻页异常显示友好提示。 |
| web/conversation.py | 纯读取查询轮优先展示最终车次/经停，避免最后库存结果盖过完整行程；模型结果与快捷查询共用展示。 |
| web/user_features.py | 默认查询后刷新聊天；右栏保留表单和数量/路线摘要，去掉完整重复表。 |
| web/user_layout.css | 仅新增rail卡片/线路/节点样式和手机规则，原页面布局保留。 |
| tests/v39/test_v395_cards.py（新增） | 五项确定性投影/转义/跨日/辅助结果与分页历史保留检查。 |

未修改任何target后端文件、Provider、Schema、8+11工具、Agent.chat/Trace字段、D9/P01或交易状态机。没有新增依赖。查询场景只提供查看经停，不增加建单/支付按钮；原报价与确认流程保留。未自动生成报价，未知票价/库存不编造；已有匹配模拟库存显示为“上次查询模拟余票”，不当成当前真实库存。原报价卡仍由原交易展示路径处理。

## 数据真实性与体验

实际默认查询109班/20一页，首班G7541 05:52→06:51，59分钟，上海虹桥→杭州东；均读当前工具结果，生产代码无硬编码上述数量/车次。未加载经停前只有起终节点，点击后现有Registry读取真实10站，不批量预取。技术字段保留原结果/Trace及页面审计，用户端只展示旅程。单独车站查询仍显示站名；仅默认路线链中的辅助车站记录隐藏。

## 测试与证据

新全套 {'passed': 203, 'failed': 0, 'skipped': 0}；旧回归 {'passed': 1441, 'failed': 11, 'skipped': 1}，另199子测试通过。与V3.9.4原始JSON逐失败/skip ID相同。历史1640通过合并了1441主测试和199子测试，本报告分列，正式103不计入新成绩。Edge四规格{'passed': 48, 'failed': 0, 'page_errors': 0, 'console_errors': 8, 'network_failures': 8}；最后的分页参数去空值由新增Schema负例与新全套复验，旧回归副本早于这项纯展示参数修补，后端始终未改。原始日志、JUnit、SQLite探针与截图见 `artifacts/runtime/v394-implementation-v395-20261104/`。

命令：`.venv-v35/Scripts/python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v394-implementation-v395-20261104/suite-sealed`；`.venv-v35/Scripts/python.exe -B artifacts/runtime/v394-implementation-v395-20261104/run_old_regression.py regression-final`；`node artifacts/runtime/v394-implementation-v395-20261104/browser_final.js`。使用隔离DB/Trace、离线凭据与外联拦截；真实模型/铁路/支付/Embedding/LangSmith请求0。

第一轮开发热加载期间出现CONFIRMATION_WORKER_BUSY，未删除旧失败。分页/经停入口友好处理异常；停旧测试服务后使用全新server-r2隔离库复验通过，未改Worker/事务策略。原11失败/1skip未修复、不归因测试过时。

## 保护和剩余事项

1892/4056/5538相对开工无新增差异，正式103/expect/B、GTFS、阶段八DB、2100Fixture、旧数据库、账本与所有历史证据保留。新查询测试库报价/提案/订单/交易均0、FK空。保护SHA详见verification及最终manifest；不存在通过选择车次绕过交易确认的新路径。

局限：未验证真实模型本轮措辞、实体手机；现有快捷查询历史只存会话内存，尚未统一持久化时间轴。本轮没有新增卡片内选车建单流程，也不根据过期报价推断有效价格；现有报价/确认机制保留。独立审查与用户验收未执行。完成后停止，不提交推送。
