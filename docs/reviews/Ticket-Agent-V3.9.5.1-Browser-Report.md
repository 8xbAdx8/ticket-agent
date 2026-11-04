# V3.9.5.1 浏览器验收

日期2026-11-04（Asia/Shanghai）；HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`，分支feat/ticket-agent-v36-stabilization，暂存空，保留已有未提交成果。证据根目录 `artifacts/runtime/v394-implementation-v3951-20261104/`。使用已完整读取的 `.agents/skills/frontend-design/SKILL.md`，无新增依赖。

真实本机Edge+Playwright。桌面1600×1100、手机390×844，各浅/深。最终{'passed': 54, 'failed': 0, 'page_errors': 0, 'console_errors': 8, 'network_failures': 8}；额外上下文场景7/7，另四规格同流程重跑并追加Chip截图，不合并为独立用例数量。主浏览器每规格实际测list.clientHeight、scrollHeight、20张卡矩形、第三张底边/第四张顶边。桌面602px=3×190+2×16，三张完整且第四张不撑高列表。手机60dvh内滚动，全部20张仍在DOM可滚到底，输入框y坐标不变；展开后容器高度相同，折叠后20张仍在，再展开复用数据。真实鼠标点击和脚本滚动验证，不只检查HTML存在；实体触摸/触控板硬件未实测。

browser-sealed/results.json含主断言/Console/requestfailed分别记录；browser-chips含同流程和每规格chips.png、three.png、expanded.png、sent.png。context-browser-r2/results.json核验新日期、新路线和新会话，原失败context-browser日志也保留。前图取用户V395截图及artifacts/runtime/v394-implementation-v395-20261104/browser-final/原件，未覆盖历史截图。

实际目视检查桌面三卡/手机经停，以及列表下Chip换行、浅深色、时间站名/固定输入；内部多层滚动用overscroll-behavior:contain避免滚轮滚到边界带动外层。仍可通过列表外区域滚动聊天。原四入口、模型设置/导航、测试台未删除。

尚未进行真实Qwen/DeepSeek调用、Live筛选质量、实体手机及全交易浏览器生命周期；不冒充这些验收通过。

封存补充：相同条件且输出完全相同的新Agent查询也生成独立展示query ID，不修改公开结果或Trace；旧追问不会因内容相同而继续有效。新增回归验证原对象不变、新指纹不同。最终suite-sealed 218/0/0，regression-sealed 1441/11/1+199子测试，失败/skip ID相同；browser-sealed四规格54/54及16截图。原217批次等全部保留。最终SHA与Git见delivery-sha256.json、verification-sealed.json、git-sealed.json。
