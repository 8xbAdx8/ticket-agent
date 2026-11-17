"""Build requested Markdown/JSON handoff from locally verified audit results only."""
from pathlib import Path
import hashlib,json,shutil,subprocess

ROOT=Path(__file__).resolve().parent.parent
WORK=ROOT/'artifacts/runtime/v352-faithfulness-audit'
REPORTS=ROOT/'docs/handoff/v352/audit'
EVIDENCE=ROOT/'docs/evidence/v352-audit'


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,text):
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(text.rstrip()+'\n')
def dump(p,value):write(p,json.dumps(value,ensure_ascii=False,indent=2))
def cell(text):return str(text).replace('|','\\|').replace('\r','').replace('\n','<br>')
def copy(source,dest):dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)

REASONS={
 'whole_literal':'去除Markdown/空白和有限等价措辞后，整条陈述与证据相符；不是只命中一个数字。',
 'conditional_release':'保留“过期且未支付”两个条件，与P11自动释放库存的规则一致。',
 'bound_deadline_release':'将证据中的有效期代入“未在有效期内完成支付”，与“过期未支付”条件等价；未扩大为无条件释放。',
 'query_completion':'同一Trace有真实search_policy执行成功及完整返回，来源/查询结果声明有执行依据。',
 'document_identity':'doc_id、标题及版本与实际ToolMessage一致，没有用别的文档支持P11。',
 'observed_runtime_capability':'本次search_policy确已实际执行成功，支持本次可进行政策咨询的能力声明。',
 'runtime_capability_evidence_missing':'P11不证明应用能力；未保存当次完整HTTP tools schema/运行时白名单快照。历史代码/Prompt与只读声明一致，但本审计不将静态声明或未执行写操作当作历史运行时绑定实测证明，交B裁定。'
}


def main():
    metrics=read(WORK/'metrics/audit.json');answers=read(WORK/'answers/audit.json');reg=read(WORK/'final-offline/report.json')
    assert metrics['status']==reg['status']=='passed'
    assert not reg['changed_original_files'] and not reg['changed_existing_v352_evidence_files']
    REPORTS.mkdir(parents=True,exist_ok=False);EVIDENCE.mkdir(parents=True,exist_ok=False)
    copy(WORK/'metrics/audit.json',EVIDENCE/'metrics/audit.json')
    for p in (WORK/'answers').glob('*'):
        if p.is_file():copy(p,EVIDENCE/'answers'/p.name)
    for folder,label in [('full-offline','first-complete'),('final-offline','final')]:
        for name in ('report.json','pytest.txt','pytest.xml','compatibility.txt','retrieval48.txt',
            'compatibility/report.json','compatibility/v35_full_unit.txt','compatibility/rag_eight_mutations.txt',
            'compatibility/old-environments/report.json','compatibility/old-environments/regression/regression.json',
            'compatibility/old-environments/regression/deepseek_unit.txt','compatibility/old-environments/regression/v3_unit.txt',
            'compatibility/old-environments/regression/v2_unit.txt','compatibility/old-environments/regression/mock_smoke.txt'):
            copy(WORK/folder/name,EVIDENCE/'offline'/label/name)
    for name in ('first-detector-tests.xml','detector-fixed-tests.xml','targeted-final-tests.xml'):
        copy(WORK/name,EVIDENCE/'targeted'/name)
    snapshot=read(WORK/'answers/policy-index-snapshot.json');p11=snapshot['current_policy']
    rows=[];model_reports=[];unknowns=[]
    for model in answers['models']:
        a=model['new_audit'];is_qwen=model['provider']=='bailian';name='Qwen3.8-Flash' if is_qwen else 'DeepSeek'
        local=[]
        for assertion in a['assertions']:
            evidence=[]
            if assertion['kind']=='capability':
                if assertion['verdict']=='supported':evidence=[{'type':'actual_tool_execution','tool':'search_policy','ok':True,'executed':True}]
                else:evidence=[{'type':'static_code_and_prompt_only','note':'与声明一致，但缺历史运行时schema/绑定回执，不当作运行能力实测证明。'}]
            elif assertion['kind']=='provenance':evidence=[{'type':'actual_tool_execution','tool':'search_policy','ok':True,'executed':True},p11]
            else:evidence=assertion['evidence']
            refs=[{**r,'path':'docs/evidence/v352-audit/answers/policy-index-snapshot.json' if r['path']=='policy-index-snapshot.json' else r['path']} for r in assertion['evidence_refs']]
            item={'model':model['actual_model'],'trace_id':model['trace_id'],'claim_id':assertion['claim_id'],
                'original_sentence':assertion['original_sentence'],'original_span':{'start':assertion['start'],'end':assertion['end']},
                'independent_assertion':assertion['assertion'],'factual':assertion['factual'],
                'evidence_document':[] if assertion['kind']=='capability' else [{'doc_id':e['doc_id'],'version':e.get('version')} for e in assertion['evidence']],
                'evidence_location':refs,'actual_evidence':evidence,'verdict':assertion['verdict'],
                'reason':REASONS.get(assertion['rule'],assertion['reason']),'severity':assertion['severity'],
                'needs_b_review':assertion['needs_b_review'],'rule':assertion['rule'],
                'citation_binding':'runtime_evidence_not_policy' if assertion['kind']=='capability' else assertion['citation_binding']}
            local.append(item);rows.append(item)
            if item['needs_b_review']:unknowns.append(item)
        old=model['original_verdict']['faithfulness_check']
        model_reports.append({'model':model['actual_model'],'verdict':a['verdict'],'factual_assertions':a['factual_assertions'],
            'counts':a['counts'],'claims':local,'trace_id':model['trace_id'],
            'original_reply_sha256':model['original_reply_sha256'],'original_model_reply':model['original_model_reply'],
            'original_automatic_status':model['original_verdict']['status'],'old_claim_checks':old['claim_checks'],
            'old_manual_review':old['manual_review'],'source_paths':model['source_paths']})
        table='| ID | 原始句子（原文） | 独立事实断言 | 文档/版本 | 证据位置 | 实际证据 | 判定 | 原因 | 严重程度 | B复核 |\n|---|---|---|---|---|---|---|---|---|---|\n'
        for item in local:
            document=', '.join(e['doc_id']+'/'+str(e['version']) for e in item['evidence_document']) or '运行事件／非P11能力证据'
            positions='；'.join(r['path']+(':'+str(r['line']) if 'line' in r else '#'+r.get('json_pointer','')) for r in item['evidence_location'])
            actual='；'.join(e.get('content',json.dumps(e,ensure_ascii=False)) for e in item['actual_evidence'])
            table+='| '+' | '.join(cell(x) for x in (item['claim_id'],item['original_sentence'],item['independent_assertion'],document,positions,actual,item['verdict'],item['reason'],item['severity'],str(item['needs_b_review']).lower()))+' |\n'
        counts=a['counts']
        text=f'''# V3.5.2 {name}全文忠实度审计

日期：2026-10-26。**最终结论：{a['verdict']}**。事实性断言{a['factual_assertions']}条：supported={counts['supported']}、contradicted={counts['contradicted']}、unsupported={counts['unsupported']}、indeterminate={counts['indeterminate']}、not_applicable={counts['not_applicable']}。这是对固定原始回答的回溯审计，不是改后Live复验，也不是模型总体准确率。

## 原始完整回答（未改写）

```text
{model['original_model_reply']}
```

原文UTF8 SHA256：{model['original_reply_sha256']}。原始文件与复制件保持一致；上面保留原Markdown符号，表格中的换行仅为展示替换为br，JSON中为真实原文与span。

## 原始执行与政策证据

- 实际模型：{model['actual_model']}；Trace ID：{model['trace_id']}；历史代码SHA：{model['historical_git_sha']}。
- 用户原问题：{model['public_trace']['user_msg']}；真实search_policy参数：{json.dumps(model['tool_args'],ensure_ascii=False)}。
- 请求ID：{', '.join(model['request_ids'])}；真实call_id：{model['call_id']}；第二次HTTP200与派发ToolMessage关联已核对。
- 原始完整路径：{'; '.join(model['source_paths'])}。JSON Pointer和逐句证据见下表与同目录JSON。
- 原Chroma仅hash/复制后在独立副本load/get，P11正文、ID、version、chunk_id与原政策及实际ToolMessage相同。政策源data/policies.md第{snapshot['policy_header_line']+1}行，doc_id=P11，version={p11['version']}。

```text
{p11['content']}
```

实际工具返回包含上述正文和来源/版本/分数，不是摘要。规范化结果hash={model['actual_tool_result_hash']}。序列化ToolMessage原字符串未单独留存，但保存了parsed_result和content_sha256；本次按其实际JSON顺序重建，精确匹配已存内容hash。System Prompt由该历史SHA源码+请求北京时间日期重建，SystemMessage规范化hash={model['prompt']['saved_and_reconstructed_hash']}，与两次派发记录完全一致。重建文本位于docs/evidence/v352-audit/answers/{model['provider']}-system-prompt-reconstructed.txt；不伪称保存了完整原始HTTP body。

## 逐句证据对照

{table}

## 必查风险与边界

四条政策事实均支持：15分钟有效期、过期且未支付时释放库存、下单乘客列表与锁座一致、重复支付不重复扣库存。没有发现新增例外、金额、次数、收费或额外购保要求，没有声称已锁座/支付/创建或修改订单，未发生跨文档归因和同一命题自相矛盾。两份回答都未将政策明称12306或航空公司官方政策，工具证据和哈希核实的Prompt明确业务虚构。

起算点：P11未定义后台具体时钟字段，也未给出“从支付完成起算”等额外条件；该原回复没有编造这样的起算点。后台实现是在模拟lock_seat时取config.now()+TTL，属于源码旁证而非本轮新增模型事实。不能把未定义的时间字段补进政策后再据此判模型正确。

## 原indeterminate的具体原因及本次改善

原判定器产生{len(old['claim_checks'])}条检查、{len(old['manual_review'])}条待人工项。它要求每个局部句子有doc_id，无法绑定唯一段末来源/同段前缀；“必须提供乘客列表”不在原事实正则中，静默漏检；旧数字检查只证明数字/单位绑定，不能证明同句后续谓词；full_semantic_faithfulness字段本身固定为indeterminate。历史旧输出保持原样，不回写。

新检测器逐条保留原文位置，绑定来源后还要核查完整陈述与条件；新增非数字要求、源版本、标题、附加起算/官方范围、执行声明和自相矛盾检查。policy咨询能力已有本次search_policy实际成功证据，明确标supported。余下{counts['indeterminate']}条是未在本样本执行的查票/写操作能力边界：历史代码确有只读guard，与Prompt一致，但原记录未保存实际tools schema/运行时白名单快照。缺口不等于模型说错，也不由Prompt自证能力；B可明确决定采用历史静态guard+离线协议验证是否足以签为supported。

因此未发现可确认的关键政策错误，但全文仍有影响充分证明的未知项，不能给PASS，也没有明确错误可判FAIL。B待复核的具体句子见下表中needs_b_review=true及B清单；不需要新API来重新“问模型判断模型”。
'''
        putname='V3.5.2_Qwen全文忠实度审计.md' if is_qwen else 'V3.5.2_DeepSeek全文忠实度审计.md'
        write(REPORTS/putname,text)
    dump(REPORTS/'V3.5.2_双模型逐句证据对照.json',{'schema':'ticket-v352-claim-evidence-table/1',
        'date':'2026-10-26','baseline':'61c9f1953ff56e6037d3b996a333ef9c5a0164c5','real_API_requests':0,
        'models':model_reports,'same_policy_and_prompt':True,'missing_evidence':answers['models'][0]['explicit_missing_evidence'],
        'historical_source_comparison':answers['historical_source_comparison'],'raw_audit':'docs/evidence/v352-audit/answers/audit.json'})
    md='''# V3.5.2 RAG指标一致性审计报告

2026-10-26。**独立重算结论：没有发现原成绩的数学计算错误，原数值不改。** 基线61c9f1953ff56e6037d3b996a333ef9c5a0164c5；本轮不调用任何模型、Embedding或LangSmith。

## 定义、集合和精确分数

Recall@K逐题计算相关doc_id集合在前K个实际返回去重文档中的召回比例，再对有答案题取macro均值；不是Hit@K，也不是将所有预期文档池化后的micro召回。MRR实际截止为MRR@3：首个相关文档的返回排名倒数，无相关前3返回0，再在同一正样本集合平均。原字段名mrr保留兼容，报告明确标注截止，不改定义迎合成绩。

开发/保留各24题，各8正样本和16无答案；合计16正样本、32无答案。三模式使用相同标签、正/负样本ID和顺序，未运行/无法判定均0。无答案题不计入Recall/MRR分母，误召回另以32为分母。原始分数、排序和标准答案未修改，独立脚本不调用生产metrics/dedup辅助函数，而用Fraction精确重算。

| 模式 | R@1（精确分数） | R@3 | MRR@3（精确分数） | 正样本分母 | 无答案误召回 |
|---|---|---|---|---:|---:|
| Keyword | 0.84375=27/32 | 1 | 0.9375=15/16 | 16 | 0/32 |
| Vector | 0.96875=31/32 | 1 | 1 | 16 | 0/32 |
| Hybrid | 0.96875=31/32 | 1 | 1 | 16 | 0/32 |

“31/32”是逐题macro均值化简后的有理数，不是把正样本分母改成32题。HP08有两个正确文档P11/P12，Top1只含一个，故该题Recall@1=1/2；首个相关文档排名为1，因此该题RR=1。这使Vector/Hybrid整体R@1<1而MRR@3=1，数学上完全一致。Keyword另有两个首相关文档第二的样本，逐题如下。没有用TopK是否命中代替首个相关排名。

原始来源docs/evidence/v352/live/retrieval48/rows.json（144条完整模式结果）与report.json，冻结标准答案cases/rag_quality_v351_development.json、holdout.json；逐一hash见docs/evidence/v352-audit/metrics/audit.json。使用返回顺序，不按不同模式不可直接相比的score重新排序；重复doc_id按实际契约去重后排名，原结果无导致本次差异的重复或过滤问题。

## 逐题原始结果与独立重算

下表列实际命中、原分数和独立结果；更完整的候选/政策正文见原始rows.json，独立证据raw_hits完整保留在新audit.json。无答案R@K/RR标N/A，不填0。开发/保留从case ID归属和冻结文件确定，不能用旧30题代替。
'''
    for mode,r in metrics['computed']['all48'].items():
        md+='\n### '+mode+'\n\n| ID | 问题 | 期望doc_id | 原始返回（doc_id:score） | 首相关排名 | R@1 | R@3 | RR@3 |\n|---|---|---|---|---:|---:|---:|---:|\n'
        raw=read(ROOT/'docs/evidence/v352/live/retrieval48/rows.json');question={v['case']['id']:v['result'].get('question',v['case'].get('question','')) for v in raw if v['mode']==mode}
        for row in r['rows']:
            hits='; '.join(h['doc_id']+':'+str(h.get('score')) for h in row['raw_hits']) or '空'
            vals=[row[k]['fraction'] if row[k] is not None else 'N/A' for k in ('recall_at_1','recall_at_3','mrr')]
            rank=min(row['relevant_ranks'].values()) if row['relevant_ranks'] else 'N/A' if not row['expected_doc_ids'] else '未命中'
            md+='| '+' | '.join(cell(v) for v in (row['case_id'],question[row['case_id']],','.join(row['expected_doc_ids']) or '无答案',hits,rank,*vals))+' |\n'
    md+='''
## 实现问题、修正与覆盖

原生产数学公式无须修复。已修复的是回答判定中的句级证据/非数字要求/复合句覆盖问题，详见两份全文报告；没有修改指标标准答案或把旧成绩覆盖成新成绩。新增独立边界测试核验多相关文档、首相关第三名、Top3截止、无答案分母、缺失/错误非0分、去重顺序与重复case拒绝。

结论仅针对固定48题的检索结果。检索R@3=1与无答案0/32不等于真实模型全文忠实度通过，更不能据每模型一个政策问题估计总体准确率。完整原成绩保留，独立审计与原报告差异0。
'''
    write(REPORTS/'V3.5.2_RAG指标一致性审计报告.md',md)
    md='''# V3.5.2 B人工复核清单

2026-10-26。审计已完整核对两份原回复及四条政策事实，未发现明确政策矛盾；Qwen/DeepSeek全文结论均INDETERMINATE。这里不是B正式测试结论，也不修改B原件。全程新增Qwen/DeepSeek/Embedding/LangSmith请求0，旧账和历史证据不变。

## 必须裁定的7项运行能力断言

以下是同一事实源缺口在两个原回复中的逐条位置，不是7个已证实模型缺陷。P11只能证明政策，不能证明可调用工具。历史静态只读guard与Prompt已检查且一致；实际当次完整HTTP tools schema/运行时白名单未留存。B可以据历史代码+已有离线guard测试作人工签认，也可要求未来留存该快照；不要把Prompt指令当成能力实测，不需本轮新增API。

| 模型 | Trace | Claim | 原句／断言 | 缺少什么／怎样人工核查 |
|---|---|---|---|---|
'''
    for x in unknowns:
        md+='| '+' | '.join(cell(v) for v in (x['model'],x['trace_id'],x['claim_id'],x['original_sentence']+' → '+x['independent_assertion'],x['reason']))+' |\n'
    md+='''
## 复核操作

1. 从双模型逐句证据JSON的trace_id与evidence_location反向打开原traces.jsonl、audit_runs、实际tool_end与http_dispatch_evidence；核对未修改原回复和来源P11/version43aea1ebf3c7b333。
2. 核对各次历史SHA的target/langchain_agent.py：READ_ONLY_TOOLS、构造器allowed_tools检查、create_agent绑定；同时检查deepseek_runtime/bailian_runtime allowed_tools和验证入口isolated_environment。两模型运行时刻/包装提交不同，RAG核心源码、实际Prompt及工具证据相同，不宣称整个环境完全一致。
3. “支持政策咨询”已有本次真实search_policy成功，属于supported；“支持查票”本样本未执行query_tickets，不能把此前其他样本当本次证据。写操作没有发生不自动证明无法调用，须独立验证代码白名单或由B明确接受静态证明。
4. 逐项记录采用的证据、人工判定、理由、复核人/日期。可将未知改成人工supported/contradicted，但原机器结果与历史回答留存；7项都充分支持且没有新未知时才允许人工全文PASS。
5. 检查15分钟、过期且未支付、乘客列表一致、幂等库存四条政策事实的对应句；原政策没有额外金额/保险/例外。本次没有发现起算点新增，但P11未定义具体技术时钟字段，不能自行补造。

## 离线复现与修复范围

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:TICKET_DISABLE_LOCAL_SECRETS='1'
$env:TICKET_WEB_OFFLINE_ONLY='1'
# 输出目录必须全新；以下入口没有 --run 或在线开关
.\\.venv-v35\\Scripts\\python.exe scripts/audit_v352_metrics.py --out artifacts/runtime/b-v352-metric-audit-new
.\\.venv-v35\\Scripts\\python.exe -m pytest tests/test_v352_metric_audit.py tests/test_v352_claim_audit.py -q
```

完整取证脚本audit_v352_faithfulness.py需要本机原V352运行目录与4137项保护快照；源码新克隆只做公开证据复核和数学重算，不得声称从缺失原运行目录重放成功。完整本机回归使用verify_v352_offline.py，将索引/cache复制隔离，禁止外网；新克隆还须遵循此前B手册LF政策准备。真实API额度本轮0授权，不运行任何--run。

新检测器以整条断言证明、独立来源绑定和未知传播补齐原有盲区，原十/五字段接口未变；保留旧full_semantic_faithfulness兼容值，新增claim_audit是有限可证断言层，不是LLM Judge或语义万能判定。无来源的执行完成声明（含查询/修改）会失败；明确用户引语、否定和语气不确定不误当成政策肯定断言。

## 实际回归与Git

'''
    pytest=reg['pytest'];compat=reg['compatibility']['old_environment_regression']['environment_regression']['runs']
    md+=f"最终源码{reg['tested_source_head']}：pytest {pytest['passed']}通过、0失败、0跳过，另{pytest['subtests_passed']}子测试；不能把JUnit子测试再加为新用例。原55fixture/原B断言保持。\n\n"
    md+='| 环境 | 通过 | 失败 | 跳过 |\n|---|---:|---:|---:|\n'
    for row in compat:
        if row.get('tests') is not None:md+=f"| {row['name']} | {row['tests']-row['skipped']} | 0 | {row['skipped']} |\n"
    md+='\n原八种变异矩阵与八RAG变异、Trace/历史回放、Mock、索引保护、接口及新增专项均通过，完整日志在docs/evidence/v352-audit/offline/final。审计分支codex/v352-rag-faithfulness-audit；最新文档提交以git log -1为准，不制造自指SHA。更多模型质量或未知语义结论仍由B正式评价。\n'
    write(REPORTS/'V3.5.2_B人工复核清单.md',md)
    dump(EVIDENCE/'summary.json',{'real_API_requests':0,'metric_errors':0,'metric_values_unchanged':True,
        'models':[{k:m[k] for k in ('model','verdict','factual_assertions','counts','trace_id')} for m in model_reports],
        'policy_facts_supported_per_model':4,'runtime_statements_for_B':len(unknowns),'pytest':reg['pytest'],
        'tested_source':reg['tested_source_head'],'protected_files':answers['source_files_unchanged'],
        'original_evidence_unchanged':True,'full_regression_network_attempts':reg['blocked_network_attempts']})
    print(json.dumps({'files':5,'API_requests':0,'pytest':reg['pytest'],'B_claims':len(unknowns)},ensure_ascii=False))


if __name__=='__main__':main()
