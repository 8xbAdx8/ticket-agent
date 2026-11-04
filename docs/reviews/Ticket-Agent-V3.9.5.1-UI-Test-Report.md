# V3.9.5.1 UI与确定性测试

日期2026-11-04（Asia/Shanghai）；HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`，分支feat/ticket-agent-v36-stabilization，暂存空，保留已有未提交成果。证据根目录 `artifacts/runtime/v394-implementation-v3951-20261104/`。使用已完整读取的 `.agents/skills/frontend-design/SKILL.md`，无新增依赖。

新全套{'passed': 218, 'failed': 0, 'skipped': 0}；原全范围{'passed': 1441, 'failed': 11, 'skipped': 1}+199子测试。原始pytest/JUnit/results在suite-sealed/、regression-sealed/results/；逐ID失败和skip同基线，详见verification.json。

新增15项覆盖：路线生成及源数据不改；最多4/去重；关注车次真实时间/下一班；无时间不生成时间建议；真实超24小时经停才生成停站比较；日期/出发站/到达站/cursor四种变更拒绝旧请求；跨session与只读拒绝；空结果/失败清空；railway结果不得调用模型追问生成；真实Conversation.send完整消息进入原工具链，并用SQLite断言0订单/报价/提案/交易；draft日期/路线签名变化；无工具澄清也不调用模型生成器。不是只断言文案。

浏览器覆盖23类要求中滚动/开合/分页/全部20可达、输入框稳定、动态关注/经停问题、最多4、点击原聊天、换日期/路线/会话、导航/手机无横溢出。没有以用户按Chip就保证模型时间筛选正确，真实API不在本轮授权。

最终服务库{'v39_orders': 0, 'v39_transactions': 0, 'v39_quotes': 0, 'v39_proposals': 0}，foreign_key_check=[]。旧库只做文件hash，不连接写入。未引入skip/xfail；所有失败批次保留。

封存补充：相同条件且输出完全相同的新Agent查询也生成独立展示query ID，不修改公开结果或Trace；旧追问不会因内容相同而继续有效。新增回归验证原对象不变、新指纹不同。最终suite-sealed 218/0/0，regression-sealed 1441/11/1+199子测试，失败/skip ID相同；browser-sealed四规格54/54及16截图。原217批次等全部保留。最终SHA与Git见delivery-sha256.json、verification-sealed.json、git-sealed.json。
