# 验收收口与 UI 精修报告（2026-10-30）

> 本轮不新增功能，只做验收、针对性修复与证据补齐。
> 依据：`Ticket-Agent-DeepSeek-Harness-交接任务书.md`；上一轮成果见 `P0-用户端重构报告.md`。

## 1. 先保护现有成果

| 项 | 值 |
|---|---|
| 分支 | `feat/ticket-agent-v36-stabilization` |
| HEAD | `04b9a42a47e8ca81ce77cca352655708a1e1ea63`（与开工时一致，未移动） |
| 工作区 | 19 个已跟踪文件被修改、34 个未跟踪文件 |
| stash / worktree | 无 stash；只有 `D:/codexproject/ticket-agent` 一个 worktree |
| 本轮操作 | 未 reset、未 clean、未批量删除、未提交、未推送 |

**并行任务（Codex）的产物，本轮全程未触碰**：`target/rag_benchmark.py`、`tests/test_rag_benchmark.py`、`scripts/build_rag_benchmark.py`、`web/rag_benchmark_view.py`、`data/rag1000/`、`docs/architecture/RAG千题评测手册.md`、`README.md`。

文件指纹（本轮改动与关联文件）：

```
artifacts/runtime/ui-p0-20261030/files-sha256.txt
```

本轮我实际改动的文件：`web/design.css`、`web/run_view.py`、`web/developer_workspace.py`、`web/regression_center_view.py`、`web/test_console.py`、`scripts/live_providers.py`、`tests/test_live_provider_ui.py`、`tests/test_unlimited_live_ui.py`、`tests/test_run_phases.py`、`tests/test_test_console.py`。

## 2. Windows ACL 审查

**用户 SID**：`S-1-5-21-305476523-1716576516-3879486982-1001`（`LAPTOP-JRNNDCUQ\W`），工作区所有者同为该账号。

### 改动前（来自诊断脚本的备份，`D:\codexproject\dsh-acl-recovery\acl-backup-4b16459bad3c43f2bdf32551db9d663d.json`）

根目录 DACL 的显式项只有三条 `Modify`（SID `…-1004`、`-646294770…`、`-1781194766…`），其余为继承的 Administrators / SYSTEM / Authenticated Users / Users；**没有本人 SID 的允许项**，也没有 Everyone 拒绝项。当时 `WRITE_DAC=True`、`WRITE_OWNER=False`。

### 本轮两次变更（都只在工作区根目录，未使用 `icacls /reset`、未做整目录重置）

| # | 操作 | 结果 |
|---|---|---|
| 1 | 随附诊断脚本授予本人 SID `FullControl`（**无继承**） | `WRITE_OWNER` false → true，脚本内已验证 |
| 2 | `icacls <root> /grant "LAPTOP-JRNNDCUQ\W:(OI)(CI)F"` | 同一权限带上继承；Windows 传播到已有子目录，`web`、`artifacts\runtime` 均出现 `(I)(OI)(CI)(F)` |

### 改动后（当前 SDDL）

根目录 DACL 现包含：`Everyone:(CI)(DENY)(DC)`、`S-1-4-786291304-708936117:(OI)(CI)(W,D,DC)`、`LAPTOP-JRNNDCUQ\W:(OI)(CI)(F)`、`LAPTOP-JRNNDCUQ\W:(F)`、`CodexSandboxUsers:(OI)(CI)(M)`，以及三条原有 `Modify` 项、继承的 BA/SY/AU/BU；另有一个 `Low Mandatory Level:(OI)(CI)(NW)` 完整性标签。

- 前两项（`S-1-4-*` 允许、`Everyone` 拒绝）与完整性标签**不是本轮加上的**，是 DSH 沙箱每次执行时自行写入的沙箱身份与防删除策略。
- 与备份 SDDL 逐条比对：**原有的三条 Modify 项都还在，本轮没有删除任何权限项**。
- 说明：`icacls` 的列表未显示 `…-1004` 那一项，但 `Get-Acl` 的 SDDL 中有；这是工具显示差异，本轮没有任何 ACL 删除操作，记录在此以免误读。

### 恢复方式

```powershell
pwsh -NoProfile -File 'D:\codexproject\dsh-acl-recovery\acl-backup-4b16459bad3c43f2bdf32551db9d663d.json.ps1' `
  -Path 'D:\codexproject\ticket-agent' -AllowRoot 'D:\codexproject\ticket-agent' `
  -Restore 'D:\codexproject\dsh-acl-recovery\acl-backup-4b16459bad3c43f2bdf32551db9d663d.json'
```

该脚本会还原备份中的原始 DACL（两次授予都会被去掉）。若只想去掉可继承的那一项（会同时失去写权限）：

```powershell
icacls "D:\codexproject\ticket-agent" /remove:g "LAPTOP-JRNNDCUQ\W"
```

## 3. 两项既有失败：复现与定性

两项失败的报错完全相同：`TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'`，位置都在 `result.stdout + result.stderr`。

### 复现

- 单独跑这两个测试：**通过**。
- 用 `scripts/v37_tests.py --case` 跑：**复现失败**。
- 加诊断探针后发现：同样的子进程调用，**带密钥时 `stdout` 是 `None`**；不带密钥时是 `str(125)`。
- 把子进程输出重定向到文件：`rc=0`，文件 203,940 字节，首行是合法 JSON。
- 直接解码该文件：**有 100 处非法 UTF-8 序列**；按 GBK 解码则完全合法，末尾是本轮的中文 `scope` 文本。

### 根因

`scripts/live_providers.py` 用 `json.dumps(..., ensure_ascii=False)` 打印。调用方控制台是 zh-CN（cp936）时，中文被写成 GBK 字节；父进程用 `encoding="utf-8"` 读取，CPython 的读线程抛 `UnicodeDecodeError`，`communicate()` 因此返回 `stdout=None`，子进程 `rc` 仍是 0。测试随后做 `None + str`，抛出与真实原因无关的 `TypeError`。

### 密钥输出：独立核实结论 —— **没有泄漏**

| 验证方式 | 结果 |
|---|---|
| 子进程输出重定向到文件（203,940 字节） | `offline-preflight-fixture` 出现 **0** 次（UTF-8 与 GBK 两种解码都是 0） |
| 直接运行并捕获（407,826 字节） | 0 次 |
| 报错性质 | 断言根本没有执行——在 `stdout + stderr` 就崩了 |

所以这条失败**不是密钥输出缺陷**，是编码缺陷 + 测试写法缺陷叠加，掩盖了真实原因。

### 定性

- **真实产品缺陷**：CLI 的 stdout 编码取决于调用方控制台，UTF-8 读取方会失败。
- **测试自身错误**：无条件拼接 `stdout + stderr`，把解码失败伪装成 TypeError。

### 修复

- `scripts/live_providers.py`：新增 `emit()`，stdout 一律 `ensure_ascii=True`（纯 ASCII，任何读取方都能解析，`json.loads` 后中文不变）；面向人的提示（LangSmith 相关）改走 `stderr`，stdout 只留 JSON 通道。
- 两个测试：解码加 `errors="replace"`，并在拼接前 `assertIsNotNone(result.stdout, '子进程输出无法按 UTF-8 解码……')`；密钥断言原样保留，未弱化。
- 复验：两条单独通过；`--case tests/test_live_provider_ui.py` 7/7 通过；整轮回归 0 失败。

## 4. UI 精修

### 4.1 用户端：输入框红框

不是错误态。探针结果：`aria-invalid=null`，静止时 wrapper 边框 `rgb(240,242,246)`；**聚焦时变成 `rgb(255,75,75)`**——这是 Streamlit 内置主题的默认主色 `#FF4B4B`，`design.py` 注入的 `--primary-color` 只影响读 CSS 变量的组件，碰不到 BaseWeb 的聚焦态。

修复：在 `design.css` 里把文本框/数字/日期/多行输入的聚焦边框改为 `var(--ta-accent)`，并用 `:not(:has(input[aria-invalid="true"]))` 保留真正的无效态红色。复测聚焦边框为 `rgb(8,127,114)`。

### 4.2 用户端：状态与证据

- 运行阶段（查票 / 检索政策 / 等待确认 / 执行模拟操作 / 完成）只读当前 `run_id` 的事件；没有记录到的阶段显示「未发生」。
- 结构化车次表、政策证据（编号 / 版本 / 位置 / 分数 / 原文）、真实 API 费用确认均保留；Live 未配置时发送禁用、不自动切 Mock。
- 桌面 1440、窄屏 900、深色主题均已实拍。

### 4.3 开发者端

- 事件卡片优先显示：事件名 · 状态 · 工具 · 耗时，以及**参数摘要 / 结果摘要 / 时间**。
- 原始事件 JSON 收进默认折叠的展开项（原来是 `expanded=1`，直接铺开）。
- 默认选中**最新一次运行**（此前默认落到最旧的一次，会被误读成历史回放）。
- 三栏各有一条运行身份条，标签为「当前运行 / 历史回放 / 独立调试」，都指向同一个 `run_id`。

### 4.4 测试控制台

- 页面顶部新增**最近批次结论**：流程结论、用例样本（含通过/失败/跳过/未记录）、RAG 已评估项、未评估项，再列归属、时间、Git 与逐步范围，然后才是页签下钻。
- 用例明细先给「用例结论」计数行，再筛选、详情、断言与日志。
- 字号：表格 12 → 12.5px，表头 11.5px 加字距，说明文字 12px。
- A 自测与 B 正式成绩、已评估与未评估、跳过与通过，全部保持文案与状态区分。

## 5. 验证证据

### 测试

| 项 | 结果 |
|---|---|
| 完整离线回归 | **866 passed / 0 failed / 0 skipped**，另有 **124 subtests passed** |
| 退出码 | 0 |
| 真实 API 请求 | 0（`real_api_requests: 0`） |
| 输出目录 | `artifacts/runtime/ui-p0-20261030/final-uplift` |

本轮新增/调整的专项测试：`tests/test_run_phases.py`（事件卡片摘要、耗时缺失不臆造、转义）、`tests/test_test_console.py`（用例计数、未评估不判通过、变异缺失判定、批次不可比）、以及前面两项 CLI 测试的健壮化。

### 截图（`artifacts/runtime/ui-p0-20261030/shots/`）

| 状态 | 文件 |
|---|---|
| 用户端正常（查票） | `query-1440.png` |
| 用户端欢迎态 | `home-1440.png` |
| 等待确认 | `confirm-1440.png` |
| 政策证据 | `policy-evidence-1440.png`、`policy-1440.png` |
| 演示面板 | `demo-1440.png` |
| 深色主题 | `dark-query-1440.png` |
| 窄屏 | `home-narrow-900.png`、`query-narrow-900.png` |
| Live 未配置（不可执行） | `live-missing-1440.png`，并以探针取证：`sendDisabled=true`、缺失提示存在、费用确认存在、高级设置存在 |
| 开发者端 当前运行 | `dev-current-1440.png` |
| 开发者端 历史回放 | `dev-history-1440.png` |
| 开发者端 独立调试 | `dev-debug-1440.png` |
| 测试控制台 | `console-cases-1440.png`、`console-rag-1440.png`、`console-mutation-1440.png` |

日志：`artifacts/runtime/ui-p0-20261030/final-uplift/pytest.log`、`repro-key-leak.log`、`repro-guard/`、`files-sha256.txt`。

## 6. 未解决风险

1. **实时执行中间帧没截到。** 离线 Mock 单轮约 5 ms，`send` 后 0.35 s 的截图已经是完成态。实时阶段条（`web/run_view.py::phase_at`）只有单元测试与代码路径覆盖，**没有真实截图**，不声称截到过。
2. **用户端「工具失败」在离线 Mock 里不可达。** 用四类异常请求（超量订票、缺参数、过去日期、无票线路）探测，全部成功或转为候补，没有失败分支。`st.error` 渲染由 `tests/test_v33_app.py::test_failure_does_not_replace_model_output_with_success` 与 `tests/test_web_live_ui.py::test_failure_does_not_show_ticket_cards` 覆盖，**没有伪造失败截图**。
3. RAG 的「引用支持」「回答正确」仍是未评估——批次不产生新回答，没有依据；界面按未评估展示。
4. 变异矩阵是 B 的历史只读数据，本轮未重跑。
5. 并行的后端改动仍在推进；本轮回归结果对应运行时刻的代码树（`git dirty=True`）。
6. `icacls` 与 `Get-Acl` 对某个未解析 SID 的显示不一致，已记录；本轮未做任何 ACL 删除。

## 7. 最终 Git 状态

- 分支与 HEAD 未变：`feat/ticket-agent-v36-stabilization` @ `04b9a42a47e8ca81ce77cca352655708a1e1ea63`。
- 未提交、未推送、未合并；工作区保留全部改动。
- 本轮新增到「已修改」清单的文件：`web/design.css`、`web/run_view.py`、`web/developer_workspace.py`、`web/regression_center_view.py`、`web/test_console.py`、`scripts/live_providers.py`、`tests/test_live_provider_ui.py`、`tests/test_unlimited_live_ui.py`、`tests/test_run_phases.py`、`tests/test_test_console.py`。

## 8. 下一阶段建议

1. 让实时阶段条可被观测：给工具执行加一个**仅测试环境生效**的可配置延迟，而不是为了截图改产品逻辑。
2. 把用户端失败路径做成可复现的故障注入用例（走既有 fault injection 机制），补一张真实失败截图。
3. 等生成批次落地后，把 RAG 的引用支持与回答正确从「未评估」推进到「已评估」，并保持四个维度各自的分母。
4. 单独排期处理 `icacls`/SDDL 显示差异，确认该 SID 是否仍需要访问，再决定是否用备份脚本收敛权限。
