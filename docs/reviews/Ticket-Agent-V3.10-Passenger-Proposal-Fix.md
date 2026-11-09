# V3.10 乘客姓名与重复建单提案修复

日期：2026-11-05（Asia/Shanghai）。起始HEAD `c1620cb4e9e8df094494fc77ef3f0d07ef9928c3`，分支 `feat/ticket-agent-v36-stabilization`。本轮是定点修复及离线开发验证；未提交推送、未独立审查、未调用真实模型/铁路/支付/Embedding API。

## 根因与真实证据

故障会话 `web-9733b739a75f`。原第二轮“买D3145的票”在缺少姓名时，模型把“请提供乘客姓名”填入passengers。原服务仅验证非空，生成了待确认提案 `P069496e1f18348f78ce5fe6f0ce36565`，而文字仍在追问姓名。第三轮用户输入“三三”，模型复用报价创建第二张提案，被 `PROPOSAL_ALREADY_PENDING` 拦截，随后整轮 `tool_execution_failed`。原运行和数据库未改，未重放用户交易。

原件：`artifacts/runtime/v33/user/web-9733b739a75f/traces/audit_runs.jsonl` 第2/3条、`audit_blobs/f93654be70664479e36c92f44acd8f01ced2f496459b2945ac2e317fd545063c.json`、session-replay.json。只读核验时该会话无订单。旧提案/报价有原有效期，本轮不恢复过期数据或确认权限。

## 最小修复范围

| 文件 | 修改 |
|---|---|
| target/v39/passengers.py（新增） | 有限占位文本检查，保留“三三”、单字、外文、合成姓名；不是实名验证，也不能证明任意模型姓名都来自用户 |
| target/v39/service.py | 建提案与确认建单都拒绝占位姓名；同报价/会话/owner/scenario的未确认错误旧提案可在有效姓名重建时原子撤销并替换，原payload与失败历史不改、旧令牌失效、新卡仍须用户确认 |
| target/v39/registry.py | 仅railway_create_order的PASSENGER_NAME_REQUIRED返回NEEDS_INPUT及missing_fields，不把追问当交易失败；无proposal/order/hold/transaction写入 |
| web/v39_bridge.py | 会话有效Prompt要求先询问姓名；旧错误卡明确警告且确认按钮禁用，撤销保留；原SYSTEM_PROMPT及公开Schema不动 |
| web/run_view.py | NEEDS_INPUT只显示等待补姓名、尚未执行交易，不把工具返回误写成交易完成 |
| tests/v39/test_passenger_proposals.py（新增） | 24个参数化实例：占位/正常姓名、双引擎、真实SQL、旧提案与令牌、异常回滚、并发、权限及真实Streamlit组件交互 |
| PROJECT_STATUS.md | 增量记录本次结论及范围，旧报告不改 |

旧正常提案不会自动覆盖，原重复提案拦截保持；替换只针对有限占位文本的旧错误提案，要求原hash匹配、token未使用、没有关联订单且同一quote。不同报价/用户、写权限撤销及已提交业务均不能通过该路径改变。取消与新卡写入同一SQLite事务；事务失败旧卡/令牌/Secret完整保留。旧卡历史payload不覆盖，新增INVALID_PASSENGER_PROPOSAL_REPLACED审计关联新proposal_id。

## 实际测试

| 批次 | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| suite-01（21项新增） | 366 | 0 | 0 |
| suite-final（新增3项UI/并发） | 368 | 1 | 0 |
| suite-final-02（最终） | 369 | 0 | 0 |
| 原完整回归（不含V39） | 1441 | 11 | 1 |
| 额外子测试单列 | 199 | 0 | 0 |

新增24项均通过，原345项未改。suite-final的一次旧T072进程池异常来自新增AppTest替换Windows进程入口；原失败日志保留，新增fixture恢复__main__后全套重跑通过，没有改旧测试或增加skip/xfail。旧完整回归11失败/1Skip与上一批逐ID完全一致，无新增旧测试失败，见test-summary.json。不是项目全绿；正式103仍BLOCKED。

执行命令：

```powershell
.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v310-passenger-proposal-fix-20261105-020128/suite-final-02
.venv-v35\Scripts\python.exe -B artifacts/runtime/v310-passenger-proposal-fix-20261105-020128/run_regression.py old-regression
```

不可覆盖已有输出；复跑须改为新目录名。源码快照、JUnit、逐项结果、pytest.log和隔离数据库在各批次目录。最终Streamlit AppTest实际勾选确认框验证：正常提案可确认；旧占位提案始终禁用确认、仍可撤销；读取页面不创建订单。双引擎走真实Registry/Service，以确定性模型复现“缺姓名→三三→一张待确认卡”，不是只断言回复文字。未运行真实API或本轮Edge四规格浏览器验收，不宣称Live/BROWSER_VERIFIED。

## 保护与已知边界

D9/P01、支付/退款/改签/库存执行代码、数据库Schema、原八工具与铁路十一工具Schema、SYSTEM_PROMPT、DIMENSIONS不改。旧数据及原失败记录保留，冻结simulation-v391.sqlite只Hash不连接。保护结果见verification.json；原1892项清单按开工现值比对。既有数据库/WAL/Trace未清理。真实API请求0、真实费用无新增。

有限占位列表不能替代对所有自然语言姓名来源的语义核验；模型仍可能犯其他错误。因此保留用户确认、权限与原账本边界。本轮没有扩大自动替换正常提案、恢复旧订单或交易重试。过期报价必须重新查询/报价；不能用旧错误卡直接确认“三三”。

Skill：已读write-code-eval，采纳可验证的SQL/事件/权限/原子性与双引擎检查；不使用LLM Judge、不增加依赖、不改变正式评分。

状态：IMPLEMENTED / OFFLINE_VERIFIED；INDEPENDENTLY_REVIEWED=NOT_RUN；ACCEPTED=PENDING_USER。没有“保证零bug”的结论；本次实际回归未发现新增旧测试失败。
