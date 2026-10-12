# GitHub 仓库交接

仓库地址：https://github.com/8xbAdx8/ticket-agent

创建方式：在已登录的个人账号下建立私有仓库，发布现有 `feat/a-ticket-handoff` 分支和 `handoff-a-20261012` 交付标签；保留已有开发提交，不新建或合并 main。

本次同步用户在 2026-10-12 再次执行 smoke.py 产生的真实日志，并重新生成四份交接报告，保证 JSON 示例、运行时间与证据一致。报告中的“未推送”描述的是此前开发交接阶段；本文件及开发日志记录随后由用户明确要求的 GitHub 发布阶段。

## 队友获取项目

私有仓库需要仓库所有者先在 GitHub 的 Settings → Collaborators 中邀请队友；本次没有代为发送邀请。接受邀请并登录 GitHub 后：

```powershell
git clone https://github.com/8xbAdx8/ticket-agent.git
cd ticket-agent
```

然后按 README.md 建立 Python 环境，或直接用可用 Python 运行 `python run_demo.py` 做无 Key 的 Mock 演示。成员 B 看 `docs/handoff/B_测试对接手册.md`，成员 C 看 `docs/handoff/C_验收与演示交接手册.md`。

仓库只包含源码、依赖、任务资料、交接文档和模拟测试证据，不上传 `.venv`、临时数据库、缓存、`.env` 或本地打包 ZIP。队友需要自己生成当前日期的模拟库。GitHub clone 不包含开发现场原 DB/历史 Trace，报告保护文件核验需要原现场；运行 Agent 和基本自测不依赖这些原文件。

`handoff-a-20261012` 仍指向最初的交接版本；当前分支另包含之后的测试证据和 GitHub 交接提交。四份手册中引用该标签的最终提交是原交接快照，不应与后续分支 HEAD 混淆。
