# V3.9.5.1 实施报告

日期2026-11-04（Asia/Shanghai）；HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`，分支feat/ticket-agent-v36-stabilization，暂存空，保留已有未提交成果。证据根目录 `artifacts/runtime/v394-implementation-v3951-20261104/`。使用已完整读取的 `.agents/skills/frontend-design/SKILL.md`，无新增依赖。

IMPLEMENTED / TESTED / BROWSER_VERIFIED（下述范围）；独立审查NOT_RUN、用户验收待定；冻结产品DB来源/正式103/Bridge继承BLOCKED。不是整个项目COMPLETE。

修改清单：

| 文件 | 原因 |
|---|---|
| web/railway_cards.py | 内部三卡滚动区；经停可开合/缓存；关注车次状态；列表下本地追问。 |
| web/user_layout.css | 原卡片紧凑高度与实测间距、内部滚动边界、手机高度、Chip换行，原产品网格不重写。 |
| web/railway_followups.py（新增） | 纯生成器、上下文指纹、条件签名、失效校验、最多4条Chip入队，不访问数据库或模型。 |
| web/railway_queries.py | 查询记录时更新/清空铁路追问上下文，保留全部原始结果及20条分页。 |
| web/railway_defaults.py | 默认查询记录复用上述注册入口，不改变Registry和业务。 |
| web/conversation.py | 原追问消费/execute扩展铁路队列，原费用/忙/只读检查保留，非铁路原组件保留；已有铁路结果时不再显示空聊天提示。 |
| web/runtime.py | 仅UI Conversation追问生成阶段跳过铁路辅助模型请求；绑定真实结果，不改Agent/Provider执行。 |
| tests/v39/test_v3951_followups.py（新增） | 15项确定性上下文/生成/失败/原Conversation+真实SQLite副作用验证。 |

没有修改任何target/后端源码、SYSTEM_PROMPT/TOOLS/DIMENSIONS、8+11 Schema、Provider、D9/P01、库存/退款/改签/资金状态机、GTFS或旧库。没有真实模型/Embedding/铁路/支付/LangSmith请求；生成Chip不产生模型费用。查看经停仍走原Registry，点击Chip走原Conversation和当前模型。

测试：新全套{'passed': 218, 'failed': 0, 'skipped': 0}；旧回归{'passed': 1441, 'failed': 11, 'skipped': 1}，另199子测试，失败/Skip逐ID和V395完全一致；原11失败和唯一skip未修复、不删除、不改旧断言。历史1640通过=1441主测试+199子测试。本轮217=原203+新增15，不冒充正式103。

Edge四规格{'passed': 54, 'failed': 0, 'page_errors': 0, 'console_errors': 8, 'network_failures': 8}；补充日期/路线/新会话7/7；实际截图已检查桌面三张/手机内滚动/Chip与经停，原12截图加4个Chip截图见browser-sealed/。Console与网络失败独立记录，受限测试拦截fonts.gstatic.com图标，不能称Console0。

首轮浏览器三卡高度检查失败，测得实际16px间距后纠正；首轮按钮绝对定位不可靠改正常布局。suite-02有216/1，原Mock将带“订单”的否定文案误路由查询订单，已把完整追问改为“仅执行只读查询”，最终真实Conversation确实调用railway_query_trips，保留失败日志而非改旧断言。context-browser初次日期定位匹配React Aria group导致自动化失败，改为实际日期spinbutton后复验7/7，不是业务失败。

保护三组{'protected_1892': {'count': 1892, 'changed': []}, 'historical_4056': {'count': 4056, 'changed': []}, 'protected_current_5538': {'count': 5538, 'changed': []}}；6755个开工文件SHA核对，仅上述授权展示/上下文增量变化，原正式103/B/2100Fixture/GTFS/阶段八DB/旧tickets/冻结v391库/账本/历史失败包均保留。查询浏览器库{'v39_orders': 0, 'v39_transactions': 0, 'v39_quotes': 0, 'v39_proposals': 0}、FK错误[]，没有创建交易。保护原清单及HEAD/staged/Git diff见本批次JSON；不提交推送。

复现命令：`.venv-v35/Scripts/python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v394-implementation-v3951-20261104/suite-sealed`；`.venv-v35/Scripts/python.exe -B artifacts/runtime/v394-implementation-v3951-20261104/run_old_regression.py regression-final`；`node artifacts/runtime/v394-implementation-v3951-20261104/browser_final.js`、context-browser-r2.js、browser_chips.js。已有目录不可覆盖，复验需用新批次。测试清空凭据且拦截外联，新库/Trace均隔离；原数据库不连接、不迁移。

局限：时间条件是完整自然语言追问，经原Agent/工具处理；本轮未修改Mock时间筛选算法或验证真实模型的筛选/比较回答质量，不能把发送成功当成Live语义通过。快捷查询历史仍为会话内存，未统一持久化时间轴；实体手机触控、任意浏览器缩放未验。原正式103/独立审查/用户验收继续保留各自状态。

停止：完成报告、PROJECT_STATUS与SHA清单，停本轮临时服务后等待用户验收。

封存补充：相同条件且输出完全相同的新Agent查询也生成独立展示query ID，不修改公开结果或Trace；旧追问不会因内容相同而继续有效。新增回归验证原对象不变、新指纹不同。最终suite-sealed 218/0/0，regression-sealed 1441/11/1+199子测试，失败/skip ID相同；browser-sealed四规格54/54及16截图。原217批次等全部保留。最终SHA与Git见delivery-sha256.json、verification-sealed.json、git-sealed.json。
