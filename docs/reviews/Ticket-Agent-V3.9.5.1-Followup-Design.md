# V3.9.5.1 局部设计与追问方案

日期2026-11-04（Asia/Shanghai）；HEAD `4340b6640025be95e8300a3d625a32cfb431e35d`，分支feat/ticket-agent-v36-stabilization，暂存空，保留已有未提交成果。证据根目录 `artifacts/runtime/v394-implementation-v3951-20261104/`。使用已完整读取的 `.agents/skills/frontend-design/SKILL.md`，无新增依赖。
先审计、后实施：原追问在web/runtime.py::_record_followups生成并持久化，web/conversation.py::_followup_suggestions渲染、_queue_followup/_consume_followup入队，最终execute→Conversation.send。HEAD历史及当前均保留旧组件；V395未删除它，但快捷铁路查询只走Registry，不经过原追问生成，因而没有路线专属追问。非铁路聊天、政策、订单继续原机制，铁路场景避免通用建议与铁路建议同时出现。

沿用现有蓝色ta-accent、浅/深色背景和16px正文；参考既有色板蓝#1556D0、浅蓝#E6EFFF、白#FFFFFF、深蓝#102338、灰蓝#91A5BD，CSS仍引用原主题变量。原190px收起卡片×3+浏览器实测16px间距×2=602px内部列表；首轮按12px估计导致裁切，已据实测纠正。原时刻/站名/线路轴保留，按钮采用正常流布局；桌面三张基准，手机min(60dvh,720px)按实际视口内部滚动，不强迫手机放三张。简图：查询摘要 / [三张卡片内部滚动区] / 最多四个追问Chip / 原分页。滚动区contain控制滚轮边界，保留鼠标、触控板和touch-action:pan-y；实体触摸未实测。

Pure builder：输入sid、原查询row（含路线ID、日期、cursor/limit、真实data）、已有站名映射、关注trip_id、已取得经停；输出label、完整message、train_id、service_date、origin/destination ID、context_id。没有数据库/网络调用。

路线建议按真实当前页时间分布生成明确半开区间06–12、12–18、18–次日00时；缺时间不生成时间问题。关注车次后从其真实到发时间生成更早出发/到达、相邻车次比较；已获经停可询问最长停站、站点数、目的地前一站、较短区间时长。最多4个且label去重。建议依赖当前页，不暗示已比较全109班。

Context SHA含会话与原查询内容，新查询/日期/路线/翻页变化即失效；关注车次变化重新build，旧message需在当前有效集合中；draft签名检查已提交表单/查询条件；新会话sid隔离、只读历史禁止发送。尚未提交的Streamlit表单编辑尚未同步服务器，直到提交才会更新上下文；不宣称能拦截服务器尚未知的编辑。

点击只入队，_consume_followup重新校验后由原execute发送，保留费用就绪/待确认/只读检查和权限链。铁路回复及铁路Chip产生的无工具澄清均跳过辅助模型追问生成；真实发送仍可产生原主请求费用，界面说明。原非铁路模型追问保留原授权行为。

多卡片独立开合保留；缓存按sid+query+trip隔离，第一次点击才查询原railway_trip_stops，收起/再次展开复用已得详情。最后一次点击的车次成为关注对象，不含购票确认意义。不自动创建报价、订单、支付或退款。

封存补充：相同条件且输出完全相同的新Agent查询也生成独立展示query ID，不修改公开结果或Trace；旧追问不会因内容相同而继续有效。新增回归验证原对象不变、新指纹不同。最终suite-sealed 218/0/0，regression-sealed 1441/11/1+199子测试，失败/skip ID相同；browser-sealed四规格54/54及16截图。原217批次等全部保留。最终SHA与Git见delivery-sha256.json、verification-sealed.json、git-sealed.json。
