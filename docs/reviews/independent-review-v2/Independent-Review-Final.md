# Ticket Agent AI 测试体系 V2：独立复审报告

**限定裁决：CONDITIONAL PASS。**

当前冻结源码中的两项 P1 已整改，复审未发现尚未解决的 P0/P1。允许将已实现的离线工程子范围提交用户审查；**完整 V2 仍为 PARTIAL，不能标为 COMPLETE 或 ACCEPTED。**

这是与实施者分离的独立子 Agent `independent_v2_review` 只读代码审查，不是外部人工验收。审查没有修改文件、写数据库或调用真实 API。验证方式为源码审阅、现有数据库只读查询、原始日志核对、SHA256重算及纯内存反向检查。本文件由主实施者将独立审查者最终反馈落盘，裁决和发现归于独立审查者。

## 1. 现场与源码绑定

分支 `feat/ticket-agent-v36-stabilization`；HEAD `c1620cb4e9e8df094494fc77ef3f0d07ef9928c3`。暂存区为空；原有工作区修改及未跟踪成果保留。

独立逐文件比较当前源码与 `artifacts/runtime/ai-test-v2-20261109/final-regression-r4/snapshot/ticket-agent/`：

- target/scenario_generator.py
- target/scenario_v310.py
- target/scenario_plans.py
- target/scenario_quality.py
- web/scenario_generator.py
- web/app.py
- tests/test_ai_scenario_v2.py
- tests/test_ai_scenario_generator.py

八项全部一致，与final-code-binding.json一致，最终回归覆盖当前冻结代码。

对开工manifest中**5587个保护文件重新计算现场SHA256，差异0**。开工源码清单仅发现本轮允许的scenario_generator.py、web/scenario_generator.py修改；原有业务源码没有本轮新增差异。此结论不重新判定历史正式成绩，不代表修复历史差异。PROJECT_STATUS.md随后由实施者做授权文档更新。

## 2. 首轮问题及整改复审

| 问题 | 初始等级 | 最终复审 |
|---|---|---|
| V310审核提前返回，未绑定工具摘要、P2断言和前置 | P1 | 已解决 |
| 成功确认只核对返回状态，缺匹配数据库凭据 | P1 | 已解决 |
| 确认凭据未充分绑定乘客、报价和退款对象 | P1整改扩展 | 已解决 |
| 幂等重放把历史状态当当前状态 | P2 | 已解决 |
| 重放仅比部分字段，可能漏金额变化 | P2 | 已解决 |
| 畸形声明使审核函数抛未捕获异常 | P2 | 已解决 |
| 离线Adapter缺独立网络阻断 | P2 | 已解决 |
| 模型质量读取人工编辑后的版本 | P2 | 已解决 |
| 覆盖率Trace只判文件存在 | P2 | 已加强 |

### 2.1 审核与执行绑定

位置：target/scenario_generator.py的review函数。首轮仅查车站的计划可声明不存在锁座工具、支付断言或PAID前置而PASS。整改后纯函数复现：不存在工具REJECTED，未执行P2期望/未建立前置NEEDS_REVIEW，逆序摘要不能PASS；expect=[]、非字符串工具名、非法别名返回REJECTED，不再抛异常。

### 2.2 确认与数据库凭据

位置：target/scenario_v310.py的confirmation_proof及确认核验入口。

现在核验原proposal已CONFIRMED、对应成功幂等记录完整回执相同、订单/hold/数量/状态；建单乘客和报价绑定payload；付款成功PAYMENT及金额；退款对象绑定_refund_preview并核对明细/手续费/净额；改签绑定目标报价、新hold、差价和有效乘客价格。

独立反向检查：真实退款快照proof=True；退款金额加1分的首确/重放均False；替换为另一同价乘客退款也False。

最终故障证据：返回PAID，DB仍PENDING_PAYMENT、交易0，被committed_confirmation_receipt拒绝。不再依赖状态文案判业务成功。

### 2.3 幂等、隔离、质量与Trace

replay_proof区分首次提交和历史回执，重放要求完整回执及前后业务表不变，不要求历史状态等于当前状态。新增测试覆盖CREATE回执重放时订单PAID、PAY回执重放时订单CANCELLED。

离线Adapter固定Fixture/Test、关闭独立铁路Live、密钥和RAG网络，阻断socket连接及DNS，每次独立目录/模拟库/会话；反例覆盖继承Live环境和主动外连。授权真实生成不在此执行范围。

UI模型比较使用不可变CREATE快照；覆盖率Trace要求同execution/run开始、结束事件，任意现存文件不能充数。

## 3. 最终证据核对

根目录 `artifacts/runtime/ai-test-v2-20261109/`。

| 项目 | 独立核对结果 | 证据 |
|---|---|---|
| 专项 | 70 passed /0 failed /0 skipped | unit-r7.xml |
| 完整回归 | 1891 passed /11 failed /1 skipped | final-regression-r4/results/results.json |
| 子测试 | 199 passed，单独统计 | 同上 |
| 全回归退出码 | 1，不是全绿 | 同上 |
| 确定性参考计划 | 16/16，110步 | adapter-r4-final.json |
| 注入故障 | 5/5被拒绝 | mutations-r4.json |
| 浏览器 | 51/51，17张PNG | browser-r3/ |
| PageError | 0 | 浏览器结果 |
| Console/网络失败 | 32/32，外链字体阻断记录保留 | 浏览器结果 |
| 保护 | 5587项，0差异 | 现场重算、protection-r4.json |

独立比较原冻结与最终R4：失败ID新增0、减少0；Skip ID新增0、减少0。原11失败和唯一Skip没有隐藏、删除或改写通过。

浏览器含桌面/笔记本/窄屏/手机深浅主题、经UI导入参考计划/审核/执行V310查询/刷新恢复和原导航。审阅桌面浅色和手机深色实际截图，未见明显横向溢出。未在浏览器验证真实模型生成完整提交流程，不能外推所有在线功能验收。

## 4. 覆盖率准确含义

| 指标 | 结果 | 限定含义 |
|---|---|---|
| 工具 | 11/11 | 实际执行铁路工具 |
| 流程 | 5/5 | 声明查询/建单/支付/退款/改签 |
| 状态 | 6/6 | 声明状态集合 |
| 状态转换 | 10/10 | 声明十条转换 |
| 安全 | 7/7 | 七个固定参考计划 |
| 异常 | 4/4 | 四类固定计划 |
| 多轮 | 1/1 | 两条各自完整条件的Mock输入 |
| 回复一致性 | 1/1 | PAID查询不再说等待支付 |
| Trace | 110/110 | 同execution/run开始结束关联 |
| 故障 | 5/5 | 本轮注入五种故障 |
| RAG | N/A | 未测回答质量 |
| Live Agent | 0/2 | 未完成双模型Agent端到端 |

这些分母不涵盖所有业务、自然语言或未知故障，不能称全面覆盖。

## 5. Live和预算真实性

只读核对：DeepSeek两次有响应生成5条，Qwen两次有响应生成5条；10候选全PENDING，history仅CREATE，无人工修订，runs0。没有自动执行或冒充人工批准。

预算：14次预留请求尝试、4响应、10未知预留；已知21776Token，已计入或预留369499，剩余30501；实际费用UNKNOWN。失效代理请求未按零释放。未发现绕过预算或Mock冒充Live。未访问上游账单，不能独立证明服务端费用；生成成功不代替Live Agent执行。

## 6. 保留的非阻塞P2及未完成项

1. 通用质量页“断言完整性”仍主要判断有结构化检查，建议改称存在率或进一步检查目标覆盖。
2. 通用质量页Trace仍为文件存在级；覆盖率页更强，二者强度应明确区分。
3. 金融Oracle有限，不等于穷举全部P01边界、逐乘客费用、并发和恢复。
4. QR核对PNG元数据，未解码像素。
5. 多轮与回复检查范围小，未证明缺参补全、长上下文、任意业务成功声明真实性。
6. Live Agent、RAG回答质量、超时/截断及吞吐未验收。
7. 正式103仍BLOCKED，本轮不是正式重新计分。

未测事项不能包装为PASS，不应为补数字擅自请求API或批准候选。

## 7. 最终状态和条件

| 状态 | 结论 |
|---|---|
| OFFLINE_VERIFIED | 已实现子范围成立 |
| DATABASE_VERIFIED | 已执行计划和凭据范围成立 |
| BROWSER_VERIFIED | 本轮页面/记录交互范围成立 |
| LIVE_GENERATION_VERIFIED | 受控候选生成响应证据存在 |
| LIVE_AGENT_VERIFIED | NOT_RUN |
| INDEPENDENTLY_REVIEWED | 本次只读代码与证据范围成立 |
| ACCEPTED | 待用户 |
| 整体V2 | PARTIAL |

**CONDITIONAL PASS条件**：保留范围说明、历史失败和未测项，不把参考计划覆盖率、候选生成、局部浏览器通过解释为完整V2验收。本复审不授权提交、推送、真实服务调用、自动批准候选或扩展下一阶段。
