# V3.5.2 指标与全文忠实度审计开发记录

## 2026-10-26 基线与指标独立核算

- 实际分支基线feat/ticket-agent-v352-rag-live-eval、HEAD61c9f1953ff56e6037d3b996a333ef9c5a0164c5，仅用户原ZIP未跟踪。建立codex/v352-rag-faithfulness-audit，不动main/标签。用户明确本轮零Qwen/DeepSeek/Embedding/LangSmith请求。
- 新增scripts/audit_v352_metrics.py和tests/test_v352_metric_audit.py，以Fraction从保存的144条原始模式结果独立重算，不复用生产metrics/排序/去重辅助函数。48题标签与原始逐题结果逐一核对，开发/保留/合计三模式一致、差异0；正样本16、负样本32各自同一集合。Recall为macro文档集合召回，MRR实际为MRR@3首个相关文档倒数，不是Hit@K。
- 实际运行audit_v352_metrics.py --out artifacts/runtime/v352-faithfulness-audit/metrics；Keyword R@1=27/32、R@3=1、MRR=15/16；Vector/Hybrid R@1=31/32、R@3=MRR=1。HP08预期两份文档，Top1召回1/2但首个相关排名1解释该差异，不改生产公式或标准答案。
- 新增7项离线数学边界测试全部通过，涵盖多相关文档、首相关第三名、截断、无答案分母、未运行/错误、去重顺序和重复case拒绝。真实请求0。原始成绩与报告保持不变；后续报告将明确MRR@3的截止范围。

## 逐句完整性与确定性检测修复

- 指标提交141a61d。新增target/rag_claim_audit.py，修改rag_faithfulness.py：扩充无数字“必须提供/提交”事实识别，新增保留原文span的断言审计；段末唯一明确来源/同段前缀只负责绑定候选证据，支持结论还必须整句文字/受限同义/单位及条件匹配，不能数字相同就通过整个复合句。
- 新层支持完整数量谓词、有限期限/未支付释放条件、明确新增条件/官方归因/版本或标题错误、同主体自相矛盾；用户引用/否定/不确定措辞分开。原full_semantic_faithfulness保留兼容的indeterminate，新增claim_audit按supported/contradicted/unsupported/indeterminate/not_applicable逐项输出，不覆盖原回答或历史判定。
- 原模块未检查乘客列表要求，DeepSeek首句的15分钟支持也未证明后续条件。新层核对实际完整回答，两个模型各4条政策事实均可支持；政策查询事件与来源声明另核对。实际成功search_policy足以证明政策咨询能力，但Prompt不能证明其他运行时工具能力，未保存的实际tools schema与绑定证据缺口明确留下，不用“本轮没写操作”推断不可能写操作。
- 首轮原回归发现新增句级来源绑定从用户引文误继承P99，已修复为先掩码引用再绑定，原失败日志保留；补无句末标点行解析与段落起点，避免静默漏掉header/footer。原55fixture与相关70项保持通过；新增25专项及7指标测试组合102通过、0失败、0跳过，全离线。

## 原始证据重建与执行声明边界

- 检测提交f9767e8已完整离线534通过、0失败、0跳过、89子测试通过；旧环境及两组八变异通过，3933旧文件和62个真实运行证据均不变，网络尝试0。
- 新增scripts/audit_v352_faithfulness.py，从各次真实运行记录的Git SHA读取历史Prompt源码、按请求的北京时间日期重建SystemMessage，与已保存0fb2deaf...哈希完全匹配；用实际保存的parsed ToolMessage重建序列化文本，精确匹配content_sha256。明确标注重建，不虚构未保存的完整HTTP body/tools schema。
- 直接读取Chroma独立副本的P11正文/元数据/向量签名，对照原政策、实际tool_end、第二次HTTP派发payload、原JSONL、原模型最终全文；不是用新模型评价旧模型。两Provider同证据/Prompt，历史代码SHA/时间不同需分别披露。
- 再补明确“已查询订单/政策/余票”“已修改订单”的实际执行事件核验；新原子未知传播到原manual_review，旧数字检查标记仅证明数字绑定而非整句。追加3专项，组合105通过、0失败、0跳过。原模型回复和既有历史indeterminate旁证不改。

## 最终离线结果与五份正式审计文件

- 最终判定源码55737fef63a8a446f2d20a04a91e5a30fbce209c，全量537通过、0失败、0跳过，另89子测试；新增35项（7指标+28断言专项）。旧DeepSeek513通过/24跳过、V3 438/99、V2 342/195均0失败；原两组八变异/审计/回放/契约等均通过。外网尝试、Qwen/DeepSeek/Embedding/LangSmith真实请求全部0，旧账不变。
- 实际运行audit_v352_faithfulness.py，在独立Chroma副本核实P11，原索引字节与4137项本轮保护输入全部未变。两模型各10事实断言：Qwen7 supported/3 indeterminate，DeepSeek6 supported/4 indeterminate，contradicted/unsupported/not_applicable均0，最终皆INDETERMINATE。四条政策事实各自全部支持；查询来源和本次已执行政策咨询另有事件证据。
- 保留的7项未知明确是查票能力与未执行写操作的能力边界，历史只读guard和Prompt相符但未保存实际tools schema/运行时绑定快照，不由Prompt自证；B可按清单复核代码/离线guard并签署独立判定。没有可确认的关键政策错误，不把未知数当缺陷数或总体准确率。
- 新增scripts/build_v352_audit_reports.py并实际生成docs/handoff/v352/audit五份指定MD/JSON；逐题144条实际结果和精确重算、20条全文断言、原完整回复/参数/ToolMessage/Prompt重建与缺项、历史源SHA比较和日志均可反查。公开证据在docs/evidence/v352-audit；新增Git属性保护原始副本文本字节，旧报告/原始成绩/历史Trace不改。
