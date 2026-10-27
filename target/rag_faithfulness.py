"""Conservative, deterministic evidence checks. Never claims full semantic proof.

This module has no model/embedding/network dependency. Only the supplied tool
results are authoritative. A checked numeric claim is narrower than a faithful
answer, and every answer retains an explicit manual-review status.
"""
from decimal import Decimal, InvalidOperation
import re


IDS = re.compile(r'\bP\d+\b')
NUMBER = r'(?:\d+(?:\.\d+)?|[一二三四五六七八九十百两]+)'
QUANTITY = re.compile(r'(?P<n>'+NUMBER+r')\s*(?P<u>小时|分钟|秒钟|秒|天|日|千克|公斤|厘米|米|周岁|岁|次|张|元|%|％)')
UNITS = {'小时':('duration',60),'分钟':('duration',1),'秒钟':('duration',Decimal(1)/60),
         '秒':('duration',Decimal(1)/60),'天':('duration',1440),'日':('duration',1440),
         '千克':('weight',1),'公斤':('weight',1),'厘米':('length',1),'米':('length',100),
         '周岁':('age',1),'岁':('age',1),'次':('count',1),'张':('tickets',1),'元':('money',1),
         '%':('percentage',1),'％':('percentage',1)}
REFUSAL = re.compile(r'无法(?:确认|确定|回答|提供)|不能确认|无(?:相关|足够|可靠).{0,8}(?:证据|依据|政策)|'
                     r'(?:没有|未)(?:检索到|找到|提供|涉及|包含).{0,18}(?:信息|规定|政策|依据|证据|内容)|不在.{0,8}知识库')
NEGATIVE_SOURCE = re.compile(r'(?:未|不|没有)(?:涉及|包含|提供|覆盖)|不存在|不在.{0,8}(?:证据|文档|结果)')
FACT = re.compile(r'有效期|手续费|期限|(?:可|需|必须|应当|允许|支持|限制|仅限|不退|不售|不得|不可).{0,12}'
                  r'(?:退票|改签|支付|取消|打印|购票|购买|免票|携带|报销|提供|提交)|收取|补收|折扣|票价|库存|理赔|赔付')
SUBJECT_GROUPS = (('成人','儿童'),('高铁','机票'),('二等座','一等座','商务座'),('经济舱','特价舱'))
POLICY_TOPICS=('退票','改签','锁座','支付','行李','报销','候补','学生票','儿童票','实名')


def _number(text):
    try:return Decimal(text)
    except InvalidOperation:
        digits={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
        if text in digits:return Decimal(digits[text])
        if '百' in text:
            left,right=text.split('百',1)
            return Decimal(digits.get(left,1)*100)+(_number(right) if right else 0)
        if '十' in text:
            left,right=text.split('十',1)
            return Decimal(digits.get(left,1)*10+digits.get(right,0))
        raise ValueError('unsupported_number')


def _quantities(text):
    result=[]
    for match in QUANTITY.finditer(text):
        try:value=_number(match['n'])*UNITS[match['u']][1]
        except ValueError:continue
        result.append({'text':match.group(),'dimension':UNITS[match['u']][0],
                       'value':str(value.normalize()),'start':match.start(),'end':match.end(),
                       'negated':bool(re.search(r'(?:不是|并非|不等于|不为)\s*$',text[max(0,match.start()-5):match.start()]))})
    return result


def _strip_user_quotes(reply):
    # Only explicitly attributed user quotations are excluded. Policy quotations
    # stay visible and must be supported like any other affirmative answer.
    excluded=[]
    pattern=re.compile(r'(?:用户(?:说|问|原话)|你(?:说|问|提到)|您(?:说|问|提到)|原话(?:是|为)|问题(?:是|为))\s*[：:]?\s*[“"「](.*?)[”"」]',re.S)
    def remove(match):
        excluded.append(match.group());return ' ' * len(match.group())
    text=pattern.sub(remove,reply)
    lines=[];previous=''
    for line in text.splitlines():
        if re.match(r'^\s*>',line) and re.search(r'用户|你问|您问|原话',previous):
            excluded.append(line);lines.append('')
        else:lines.append(re.sub(r'^\s*>\s*','',line))
        previous=line
    return '\n'.join(lines),excluded


def _clauses(text):
    result=[]
    for match in re.finditer(r'[^。！？；;\n]+',text):
        clause=match.group().strip()
        if not clause:continue
        if result and not IDS.sub('',re.sub(r'[\[\]（）()，,：:\s*]+','',clause)):
            result[-1]['text']+=' '+clause
            continue
        for part in re.split(r'但是|但|然而|不过|实际上',clause):
            if part.strip():result.append({'text':part.strip(),'start':match.start(),'end':match.end()})
    return result


def _future_query_offer(claim, text, start):
    """Recognize only a query-offer list item; never suppress facts or actions."""
    if not re.fullmatch(r'-\s*查询(?:某日|某天|指定日期|两地)[^，,。；;\n]{0,50}(?:余票|票价)(?:与票价)?', claim):
        return False
    if _quantities(claim) or re.search(r'已|成功|必须|需要|可售|有票|无票|收取|支付|手续费', claim):
        return False
    lines=text[:start].splitlines()
    while lines and re.match(r'^\s*-\s',lines[-1]):
        lines.pop()
    return bool(lines and re.search(r'(?:我|本助手)(?:可以|能够)帮(?:您|你)?[：:]\s*$',lines[-1]))


def _added_constraints(claim,evidence):
    # Only finite, explicit extra requirements with concrete objects can be
    # disproved by this small closed policy corpus. Other wording stays unknown.
    objects=('购买保险','买保险','绑定银行卡','信用卡','会员','服务费','身份证原件','提前一天','人脸识别')
    findings=[]
    for term in objects:
        if re.search(r'(?:必须|需要|须|强制|仅限).{0,8}'+re.escape(term),claim) and not any(term in r['text'] for r in evidence):
            findings.append({'type':'unsupported_added_requirement','claim':claim,'object':term,
                             'basis':'Explicit requirement absent from the actual cited policy clauses'})
    return findings


def _conditions(text):
    # Exact finite interval categories distinguish P01's >=48h, 24..48h and
    # <24h branches. Unknown paraphrases remain manual review rather than pass.
    result=[]
    pattern=re.compile(r'(开车前|开车后|起飞前|起飞后)\s*(不足|超过|不满)?\s*('+NUMBER+r')\s*(?:至|到|[-—~～])?\s*('+NUMBER+r')?\s*(小时|分钟|天|日)\s*(以上|以内|内|以下|之后|后)?')
    for match in pattern.finditer(text):
        a=_number(match[3])*UNITS[match[5]][1]
        b=_number(match[4])*UNITS[match[5]][1] if match[4] else None
        qualifier='range' if b is not None else match[2] or match[6] or 'unspecified'
        result.append((match[1],str(a.normalize()),str(b.normalize()) if b is not None else None,qualifier))
    return result


def _subjects_compatible(claim,source):
    for group in SUBJECT_GROUPS:
        claim_terms={s for s in group if s in claim};source_terms={s for s in group if s in source}
        if claim_terms and source_terms and not claim_terms.intersection(source_terms):return False
    return True


def _sentences(hits):
    rows=[]
    for hit in hits:
        for base in re.split(r'[。；;\n]',str(hit.get('content',''))):
            parts=re.split(r'[，,]',base)
            # A condition followed by ", fee=5%" is a single rule, while
            # "adult20kg, child10kg" must remain two scoped factual rows.
            texts=[base] if _conditions(parts[0]) else parts
            for text in texts:
                if text.strip():rows.append({'doc_id':hit.get('doc_id'),'text':text.strip(),
                                             'title':str(hit.get('title','')),'source':hit.get('source')})
    return rows


def _contradicted_restriction(claim,rows):
    if re.search(r'不(?:可以|允许|支持|收取)|不可|不得|不能',claim):return None
    templates=(
        (r'改签后.{0,6}(?:可|允许|支持).{0,4}退票',r'改签后.{0,6}不退'),
        (r'取消后.{0,8}(?:可|允许|支持).{0,4}支付',r'取消后.{0,8}(?:不可|不得|不能)支付'),
        (r'未支付订单取消.{0,8}(?:要|需|收取).{0,4}手续费',r'未支付订单取消不收取手续费'),
        (r'特价.{0,8}(?:可以|支持|允许)退票',r'特价.{0,24}不支持退票'),
    )
    for affirmative,negative in templates:
        if re.search(affirmative,claim):
            found=next((r for r in rows if re.search(negative,r['text'])),None)
            if found:return found
    if re.search(r'(?:商务座|一等座).{0,8}(?:可以|支持|允许).{0,6}(?:购买|儿童票)',claim):
        found=next((r for r in rows if '商务座' in r['text'] and '不售儿童票' in r['text']),None)
        if found:return found
    return None


def _execution_claims(text,events):
    tools={'锁座':'lock_seat','下单':'create_order','创建订单':'create_order','支付':'pay_order',
           '付款':'pay_order','取消订单':'cancel_order','退票':'cancel_order','退款':'cancel_order',
           '查询订单':'query_order','查询政策':'search_policy','查询余票':'query_tickets','修改订单':'modify_order'}
    findings=[];checks=[]
    pattern=re.compile(r'(?:(?:(?:我|我们|系统|订单(?:\s*[A-Za-z0-9_-]+)?|操作)?(?:已经|已)(?:为你|为您|帮你|帮您)?)|成功(?:完成)?)\s*'
                       r'(?:完成|成功)?\s*(锁座|创建订单|下单|支付|付款|取消订单|退票|退款|查询订单|查询政策|查询余票|修改订单)')
    for match in pattern.finditer(text):
        tail=text[match.end():match.end()+12]
        previous=text[max(0,match.start()-12):match.start()]
        if re.search(r'未|没有|尚未|如果|假设|若|当',previous):continue
        if re.match(r'订单(?:的|不|可|需|会|应|须)',tail):continue
        tool=tools[match[1]]
        confirmed=[e for e in events if e.get('event')=='tool_end' and e.get('tool')==tool and e.get('ok') and e.get('executed') is True]
        check={'claim':match.group(),'required_tool':tool,'status':'supported_execution' if confirmed else 'failed'}
        checks.append(check)
        if not confirmed:findings.append({'type':'unsubstantiated_execution','claim':match.group(),'required_tool':tool,
                                          'basis':'No successful, actually executed matching tool_end event'})
    for match in re.finditer(r'(?:已|已经|成功)(?:调用|执行)\s*`?([a-z_]+)`?',text):
        tool=match[1];confirmed=[e for e in events if e.get('event')=='tool_end' and e.get('tool')==tool and e.get('ok') and e.get('executed') is True]
        checks.append({'claim':match.group(),'required_tool':tool,'status':'supported_execution' if confirmed else 'failed'})
        if not confirmed:findings.append({'type':'unsubstantiated_execution','claim':match.group(),'required_tool':tool,
                                          'basis':'Explicit tool execution claim has no actual successful event'})
    return checks,findings


def _conflicts(hits):
    values={}
    for hit in hits:
        for match in re.finditer(r'锁座(?:有效期|期限)\s*('+NUMBER+r')\s*(小时|分钟|秒)',hit.get('content','')):
            value=str((_number(match[1])*UNITS[match[2]][1]).normalize())
            values.setdefault(value,[]).append(hit.get('doc_id'))
    return [{'field':'lock_expiry_minutes','values':values}] if len(values)>1 else []


def check_answer(reply,hits,*,events=(),question='',policy_versions=None):
    """Check only decidable claims against evidence, retaining raw model output.

    ``failed`` is an observable contradiction/unsupported asserted action.
    ``checked_scoped_facts`` means finite checks found supported claims only;
    it deliberately leaves full semantic faithfulness indeterminate.
    """
    hits=list(hits or []);events=list(events or []);text,excluded=_strip_user_quotes(str(reply))
    allowed=sorted({h.get('doc_id') for h in hits if h.get('doc_id')})
    cited=list(dict.fromkeys(IDS.findall(text)))
    findings=[];checks=[];unknown=[];refusal=bool(REFUSAL.search(text))
    rows=_sentences(hits)
    for clause in _clauses(text):
        claim=clause['text'];ids=list(dict.fromkeys(IDS.findall(claim)))
        negative=bool(NEGATIVE_SOURCE.search(claim))
        wrong=[d for d in ids if d not in allowed]
        if wrong and not negative:
            findings.append({'type':'nonexistent_citation','claim':claim,'doc_ids':wrong,'basis':'IDs absent from actual retrieved tool evidence'})
        if negative:
            checks.append({'claim':claim,'cited_doc_ids':ids,'status':'negative_evidence_reference','basis':'References explain unavailable scope, not positive policy support'})
            continue
        if policy_versions:
            for doc_id in ids:
                expected_version=policy_versions.get(doc_id)
                matching=[h for h in hits if h.get('doc_id')==doc_id]
                for hit in matching:
                    actual=hit.get('version')
                    if expected_version and actual and actual!=expected_version:
                        findings.append({'type':'stale_policy_version','claim':claim,'doc_id':doc_id,
                            'expected_version':expected_version,'actual_version':actual,
                            'basis':'Positive citation uses a version different from the frozen/current policy corpus'})
                    elif expected_version and not actual:
                        unknown.append({'claim':claim,'doc_id':doc_id,'reason':'policy_version_metadata_missing'})
        if _future_query_offer(claim,text,clause['start']):
            unknown.append({'claim':claim,'reason':'future_capability_offer_not_policy_fact'})
            continue
        # A numbered input prompt with an explicitly illustrative date is not
        # a claim about an existing policy, trip or booking.
        if re.fullmatch(r'\s*\d+[.、]\s*乘车/乘机日期[（(]如[“"\']?\d{1,2}月\d{1,2}日[”"\']?[）)]\s*',claim):
            unknown.append({'claim':claim,'reason':'requested_date_example_not_policy_fact'})
            continue
        all_quantities=_quantities(IDS.sub('',claim));quantities=[q for q in all_quantities if not q['negated']]
        factual=bool(all_quantities or FACT.search(claim)) and not bool(re.search(r'请(?:提供|补充|说明)|[?？]',claim))
        if not factual or (refusal and REFUSAL.search(claim) and not quantities):continue
        evidence=[r for r in rows if r['doc_id'] in ids] if ids else []
        if not hits:
            findings.append({'type':'no_evidence_positive_claim','claim':claim,'basis':'Policy assertion with empty actual retrieval evidence'})
            continue
        if not ids:
            supported_values={(q['dimension'],q['value']) for row in rows for q in _quantities(row['text'])}
            missing=[q for q in quantities if (q['dimension'],q['value']) not in supported_values]
            if missing:
                findings.append({'type':'unsupported_uncited_quantity','claim':claim,'missing_quantities':missing,
                                 'basis':'Asserted quantity has no matching value/unit anywhere in actual retrieved evidence'})
            unknown.append({'claim':claim,'reason':'no_locatable_citation'})
            checks.append({'claim':claim,'status':'indeterminate','reason':'No local doc_id anchors this assertion'})
            continue
        if re.search(r'可能|也许|不一定|或许',claim):
            unknown.append({'claim':claim,'reason':'uncertain_modality_requires_review'})
            checks.append({'claim':claim,'status':'indeterminate','reason':'Hedged claim cannot be classified as a definite rule'})
            continue
        topics=[topic for topic in POLICY_TOPICS if topic in claim]
        if len(topics)==1 and evidence and not any(topics[0] in row['text']+row['title'] for row in evidence):
            findings.append({'type':'citation_policy_category_mismatch','claim':claim,'policy_topic':topics[0],
                             'cited_doc_ids':ids,'basis':'The stated policy category is absent from the cited clause and document title'})
        contradiction=_contradicted_restriction(claim,evidence)
        if contradiction:
            findings.append({'type':'restriction_contradiction','claim':claim,'doc_id':contradiction['doc_id'],
                             'evidence_text':contradiction['text'],'basis':'Explicit positive permission contradicts a scoped prohibition'})
            continue
        findings.extend(_added_constraints(claim,evidence))
        for denied in (q for q in all_quantities if q['negated']):
            applicable=[r for r in evidence if _subjects_compatible(claim,r['text']) and (not _conditions(claim) or _conditions(r['text'])==_conditions(claim))]
            values={q['value'] for row in applicable for q in _quantities(row['text']) if q['dimension']==denied['dimension']}
            if values=={denied['value']}:
                findings.append({'type':'denies_authoritative_quantity','claim':claim,'denied':denied,
                                 'basis':'Explicit denial contradicts the sole applicable value in the actual cited evidence'})
        if not quantities:
            normalized=re.sub(r'[\s\[\]【】*：:,，]','',IDS.sub('',claim))
            found=next((r for r in evidence if normalized and normalized in re.sub(r'\s','',r['text'])),None)
            if found:checks.append({'claim':claim,'status':'supported_literal','doc_id':found['doc_id'],'evidence_text':found['text']})
            else:
                unknown.append({'claim':claim,'reason':'semantic_support_requires_review'})
                checks.append({'claim':claim,'status':'indeterminate','reason':'Non-numeric semantic paraphrase is not automatically proved'})
            continue
        condition=_conditions(claim)
        candidates=[r for r in evidence if _subjects_compatible(claim,r['text']) and (not condition or _conditions(r['text'])==condition)]
        needed={(q['dimension'],q['value']) for q in quantities}
        supported=[]
        for row in candidates:
            facts={(q['dimension'],q['value']) for q in _quantities(row['text'])}
            if needed<=facts:supported.append(row)
        if supported:
            has_unbound_condition=not condition and any(_conditions(r['text']) for r in supported)
            if has_unbound_condition:
                unknown.append({'claim':claim,'reason':'conditional_policy_scope_omitted'})
                checks.append({'claim':claim,'status':'indeterminate','reason':'Numeric values exist but their policy condition is omitted'})
            else:
                checks.append({'claim':claim,'status':'supported_scoped_quantities','quantities':quantities,
                               'sources':[{'doc_id':r['doc_id'],'evidence_text':r['text'],'source':r['source']} for r in supported],
                               'basis':'Same citation, compatible subjects/explicit interval, quantities with normalized units'})
        elif evidence:
            all_facts={(q['dimension'],q['value']) for r in evidence for q in _quantities(r['text'])}
            missing=[q for q in quantities if (q['dimension'],q['value']) not in all_facts]
            unbound=[q for q in quantities if not any(_subjects_compatible(claim,r['text']) and
                     any(v['dimension']==q['dimension'] and v['value']==q['value'] for v in _quantities(r['text'])) for r in evidence)]
            condition_decidable=bool(condition) and all(c[3] not in ('unspecified','之后','后') for c in condition)
            if missing or condition_decidable or unbound:
                findings.append({'type':'unsupported_quantity_or_scope','claim':claim,'cited_doc_ids':ids,
                                 'claim_quantities':quantities,'missing_quantities':missing,
                                 'condition':condition,'evidence':[{'doc_id':r['doc_id'],'text':r['text']} for r in evidence],
                                 'basis':'Numeric value/unit/subject/explicit conditional branch does not match the cited clause'})
            else:
                unknown.append({'claim':claim,'reason':'numeric_binding_not_proven'})
                checks.append({'claim':claim,'status':'indeterminate','reason':'Numbers occur across separate evidence clauses; no single bound support'})
    execution_checks,execution_findings=_execution_claims(text,events);checks.extend(execution_checks);findings.extend(execution_findings)
    conflicts=_conflicts(hits)
    disclosed=bool(re.search(r'冲突|不一致|相互矛盾|两种不同|无法判断.{0,8}(?:哪|采用)',text))
    if conflicts and not disclosed:
        if any(c.get('status','').startswith('supported') for c in checks):
            findings.append({'type':'undisclosed_conflicting_policy','conflicts':conflicts,'basis':'Conflicting actual sources exist but reply selects a numeric rule without disclosure'})
        else:unknown.append({'claim':text,'reason':'conflict_not_explicitly_explained'})
    from target.rag_claim_audit import audit_claims
    atomic=audit_claims(reply,hits,events=events,policy_versions=policy_versions)
    for assertion in atomic['assertions']:
        if assertion['verdict'] in ('contradicted','unsupported'):
            findings.append({'type':'atomic_'+assertion['rule'],'claim':assertion['assertion'],
                'basis':assertion['reason'],'claim_id':assertion['claim_id'],'evidence':assertion['evidence']})
        elif assertion['verdict']=='indeterminate':
            unknown.append({'claim':assertion['assertion'],'reason':'atomic_'+assertion['rule'],
                            'claim_id':assertion['claim_id'],'evidence':assertion['evidence']})
    for checked in checks:
        if checked.get('status')=='supported_scoped_quantities':
            checked['checked_scope']='quantity_bindings_only_not_the_entire_compound_sentence'
    status='failed' if findings else 'indeterminate' if unknown or atomic['verdict']=='INDETERMINATE' or not checks else 'checked_scoped_facts'
    return {'schema':'ticket-rag-faithfulness/1','status':status,'original_model_reply':reply,'question':question,
            'allowed_doc_ids':allowed,'cited_doc_ids':cited,'claim_checks':checks,'findings':findings,
            'manual_review':unknown,'refusal_observed':refusal,'no_evidence_refusal':refusal and not findings if not hits else None,
            'conflicts':conflicts,'conflict_disclosed':disclosed if conflicts else None,'excluded_user_quotes':excluded,
            'full_semantic_faithfulness':'indeterminate',
            'claim_audit':atomic,
            'limits':['Finite rules do not prove all semantic claims or the completeness of an answer.',
                      'Unknown paraphrases/implicit conditions require B independent review; this is not a model-generated judge.']}
