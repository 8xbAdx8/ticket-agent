# AI测试体系V2及既有未提交成果Git归档

日期：2026-11-09。用户明确授权“提交github”。归档分支 `feat/ticket-agent-v36-stabilization`；开工及远端预检查SHA均为 `c1620cb4e9e8df094494fc77ef3f0d07ef9928c3`。本记录所属提交为此次归档，准确提交SHA及推送结果以Git历史和推送回执为准。

## 范围

包含现有未提交的乘客提案修复、独立模拟时钟、启动/原UI接线，以及AI场景生成器与V2隔离执行/评估、测试和对应报告。没有改写这些已经完成的业务实现。

测试结论保留：最终专项70/0/0；完整回归1891/11/1，另199子测试通过，历史失败/Skip ID无增减；Edge八规格51/51。总体PARTIAL；独立只读子AgentCONDITIONAL PASS限定已测离线子范围，用户尚未最终验收。归档和推送不改变验收状态。

## 审查证据保存方式

为避免在Git中重复加入大量测试数据库/解压副本，完整独立审查材料保存为单一原始ZIP：

`artifacts/deliverables/Ticket-Agent-AI-Test-V2-Independent-Review-20261109.zip`

- 大小：8,545,749字节。
- SHA256：`e0e49118e069abc03481b7ef672416eb7be7014a9d097dbeca05a3d8bbd4e141`。
- 文件清单：`docs/reviews/independent-review-v2/final-file-sha256.json`。
- ZIP包含完整源码快照、当前文件补丁、Git现场、原始生成请求/响应、候选及预算账本、隔离业务SQLite/Trace、测试输出、17张截图、保护SHA及独立复审。它是审查包，不是完整便携运行包。
- Git同时保留实施报告、审查任务书、首轮发现和最终复审Markdown。报告中指向本地`final/`的材料，在ZIP的`independent-review-v2/final/`中可找到。
- 冻结审查包保持原SHA；本归档说明及项目状态的提交记录在冻结后增量更新，不重打或覆盖原ZIP。

## 本机保留且不提交

- `data/v39/`现有业务SQLite及WAL/SHM，尤其来源历史存在争议的simulation-v391.sqlite。
- 原始`traces/train-data-events/`及运行时数据。
- `docs/reviews/independent-review-v2/final/`等重复解压材料、源码ZIP和原始测试数据库副本，完整内容已在单一审查ZIP中。
- 其他`artifacts/runtime/`、便携运行大包、缓存、虚拟环境、真实密钥和本地配置。

上述本地原件没有删除、清理、重置或覆盖。本次没有改变.ignore规则，没有将SQLite当成产品种子数据上传。测试和运行所需大型静态原件继续按历史路径/SHA追溯，不代表从Git新克隆即可取得全部大数据。

## 安全与Git纪律

待提交源码和审查ZIP已按已配置密钥、Token模式和私钥模式扫描；图片不做OCR，扫描不是绝对无敏感信息保证。Git原系统代理失效，仅对本次远端命令使用空http/https代理配置，未修改用户或系统环境。

仅向现有分支正常推送；不Force Push、不Merge、不Tag、不Release。暂存路径采用明确白名单，原有数据库及历史成果留在本机。
