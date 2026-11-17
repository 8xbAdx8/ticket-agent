# 双模式一键启动开发记录

日期：2026-10-18。独立分支 `codex/easy-mode-launchers`，原 V3.2 交付恢复点 `d7daa478d3b53edbc16e532f0a7f358d06e2ef16`。

## 已完成

- 根目录 `启动_离线模式.cmd`、`启动_在线模式.cmd`：可双击，使用脚本目录定位项目，UTF-8控制台，错误时保留提示。
- `scripts/Start-TicketAgent.ps1`：选择已有虚拟环境；在线模式从进程/Windows用户级环境变量读取Key；没有输出或保存Key；不修改系统执行策略。
- `scripts/launch_app.py`：固定模式配置、关闭继承变异和HTTP/向量外部依赖、独立按日数据、独立Live账本、可用端口、健康检查后打开浏览器、停止自己创建的服务。
- `tests/test_launcher.py`：8项自测，覆盖模式隔离、凭据不进入预检结果、缺Key、既有数据不重置、账本只读、端口占用。
- 根目录 `启动说明.md`、README入口：解释Key隐藏输入、费用、Live只读边界和停止方法。

实现提交：`385d0f0`。没有修改target业务核心、现有Mock/Mutation/B用例、requirements或正式预算守卫。手动Live默认复用用户此前授权的累计不限次数配置0；若进程显式设置1—5则保留。账本固定独立路径，不按日重置，不改原正式5/5账本。只有用户在网页点击发送才请求真实模型。

## 实际验证

```powershell
.\.venv-deepseek\Scripts\python.exe -m unittest tests.test_launcher -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Start-TicketAgent.ps1 -Mode offline -CheckOnly
```

- 新增8项通过；完整自测经移除真实凭据、阻断非回环网络的包装运行，188项通过、0失败、0跳过。
- PowerShell源文件语法解析通过；从项目之外的临时工作目录执行 offline/live 两种预检均通过。Live使用假Key，仅确认配置与依赖，不验证Key有效性。
- 实际调用离线启动器，Streamlit在127.0.0.1:18750健康检查通过，页面HTTP200；测试只终止自己创建的服务并确认停止。测试使用--no-browser，未自动打开用户浏览器标签；浏览器打开分支已实现，需用户双击时人工确认。
- 启动器退出码1出现在测试控制器主动终止子服务后，不表示服务启动失败；详情见证据stop_note。
- 原项目712项保护文件哈希不变；正式账本哈希不变；真实模型请求0，没有API费用。
- 首轮新增测试因测试连接未关闭导致Windows临时库清理失败，改用closing并提交后重跑通过；业务代码未因此改变。首轮PowerShell语法检查的外层命令引号展开错误，改为字面量输入后解析通过。

证据：`docs/evidence/launchers/20261018/report.json`、unit.txt、server.txt。没有重新运行B正式测试，不能把V3.2原B复用成绩写成本次新成绩。

## 边界

本轮没有发送新的DeepSeek请求、没有检查真实Key有效性/余额。在线网页只读，不能完成订票写操作；完整模拟购买演示使用离线入口。首次新机器仍须安装依赖；启动器不自动联网安装或升级。关闭浏览器不停止服务，请用对应终端Ctrl+C。原未跟踪展示ZIP保留。
