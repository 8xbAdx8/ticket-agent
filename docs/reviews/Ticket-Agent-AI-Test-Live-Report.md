# AI Test Live Report

现场：HEAD `2bba4caa379b111aadcefd0369e79cf6259e33e7`，分支 `feat/ticket-agent-v36-stabilization`，staged=0；34项未跟踪/已修改工作区成果保留。未 reset/clean/checkout/stash；未 commit/push/merge/tag。

## 网络诊断

```text
api.deepseek.com  DNS ok / TCP ok / TLS 1.3 ok
qwen host         DNS ok / TCP ok / TLS 1.3 ok
HTTP no-key probe 401，证明 HTTP 栈可达
旧 DeepSeek OpenAIConnectionError 不是 DNS/TCP/TLS 错误；本轮已有真实响应
```

## 真实请求

```text
DeepSeek: HTTP 响应收到；raw SHA cf17b562...
  prompt 619 / completion 283
  generation pipeline status FAILED KeyError（compact packet 缺少 references，已修）
  原始候选质量 REJECTED（非法 from/to 参数）

Qwen: HTTP 响应收到；raw SHA ea81433...
  prompt 889 / completion ?
  原始候选质量 REJECTED（非法 step 字段/tool/无 checks）
```

Qwen 上一轮 `acceptance_token_budget_exhausted` 的准确原因：预算公式 `bound = len(raw)+4096+output`；旧 V310 prompt 过大，加上已有未知预留，8669 剩余不足以覆盖 bound。压缩证据后请求可发出，但质量不合格；本轮没有重试。

## 预算

```text
HTTP 17
已知 Token 23,567
剩余 Token 6,878
未知预留 369,555
费用 UNKNOWN
```

真实候选 2 条，质量通过 0，AI 候选执行 0；TEST_ONLY 1 条 PASS。
