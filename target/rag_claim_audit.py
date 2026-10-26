"""Finite whole-assertion checks, preserving raw spans and conservative unknowns.

No provider IDs, policy IDs, expiry values, model clients or network calls are used
as shortcuts. Source anchoring and fact support are separate checks.
"""
import re
from collections import Counter
from target.rag_faithfulness import (IDS,NUMBER,QUANTITY,_quantities,_sentences,_conditions,
    _subjects_compatible,_added_constraints,REFUSAL,NEGATIVE_SOURCE)

LABELS=('supported','contradicted','unsupported','indeterminate','not_applicable')


def compact(text):
    text=IDS.sub('',text)
    text=re.sub(r'doc_id\s*[:：]?','',text,flags=re.I)
    text=re.sub(r'[\s*`\[\]（）()【】，,。；;：:>📄-]','',text)
    for old,new in (('不会','不'),('有效期为','有效期'),('有效期是','有效期'),
                    ('下单时','下单'),('锁座时','锁座'),('还需提供','必须提供'),('需要提供','必须提供')):
        text=text.replace(old,new)
    return re.sub(r'^模拟','',text)


def atoms(reply):
    """Lossless source spans; only assertion text is simplified for verification."""
    masked=reply;excluded=[]
    quoted=re.compile(r'(?:用户(?:说|问|原话)|你(?:说|问|提到)|您(?:说|问|提到)|原话(?:是|为)|问题(?:是|为))\s*[：:]?\s*[“"「].*?[”"」]',re.S)
    for match in quoted.finditer(reply):
        excluded.append((match.start(),match.end()));masked=masked[:match.start()]+' '*len(match.group())+masked[match.end():]
    offset=0;previous=''
    for line in reply.splitlines(keepends=True):
        if re.match(r'^\s*>',line) and re.search(r'用户|你问|您问|原话',previous):
            excluded.append((offset,offset+len(line)));masked=masked[:offset]+' '*len(line)+masked[offset+len(line):]
        previous=line;offset+=len(line)
    found=[]
    for start,end in excluded:
        found.append({'start':start,'end':end,'original_sentence':reply[start:end],'assertion':reply[start:end],
                      'kind':'user_quote','factual':False})
    for match in re.finditer(r'[^。！？；;\n]+(?:[。！？；;\n]|$)',masked):
        start,end=match.span();raw=reply[start:end]
        if not masked[start:end].strip():continue
        cleaned=re.sub(r'^\s*(?:[-*>]\s*)?','',masked[start:end]).strip().rstrip('。；;')
        if not cleaned or compact(cleaned)=='':continue
        base={'start':start,'end':end,'original_sentence':raw,'citation_context':masked[start:end],'factual':True}
        if re.search(r'(?:仅|只)支持',cleaned) and re.search(r'助手|我这侧|目前|当前',cleaned):
            for topic,tool in (('模拟查票','query_tickets'),('政策咨询','search_policy')):
                if topic in cleaned:found.append({**base,'assertion':'助手支持'+topic,'kind':'capability','tool':tool,'enabled':True})
            denied=re.search(r'无法(?:为您)?(?:实际)?(?:执行|办理)(.+)',cleaned)
            if denied:
                for word,tool in (('锁座','lock_seat'),('支付','pay_order'),('下单','create_order'),('取消','cancel_order')):
                    if word in denied[1]:found.append({**base,'assertion':'助手不能执行'+word,'kind':'capability','tool':tool,'enabled':False})
            continue
        prefix=re.match(r'^根据[^\n]*?）[：:]|^根据[^：:（(]*[：:]',cleaned)
        if prefix:
            kind='provenance' if re.search(r'政策|知识库|检索证据',prefix.group()) else 'policy'
            found.append({**base,'assertion':prefix.group(),'kind':kind})
            cleaned=cleaned[prefix.end():]
            if not cleaned.strip():continue
        if re.search(r'来源|出处|依据',cleaned) and IDS.search(cleaned) and not QUANTITY.search(IDS.sub('',cleaned)):
            found.append({**base,'assertion':cleaned,'kind':'source_identity'});continue
        parts=re.split(r'且|并且',cleaned)
        for part in parts:
            # Do not detach an if-clause from its result. A validity followed by
            # an expiry condition, however, contains two independent assertions.
            split=re.split(r'[，,](?=(?:超过有效期|过期|若|如果))',part,maxsplit=1)
            for assertion in split:
                if assertion.strip():found.append({**base,'assertion':assertion.strip(),'kind':'policy'})
    return sorted(found,key=lambda row:row['start'])


def anchor(atom,all_atoms,reply):
    local=list(dict.fromkeys(IDS.findall(atom['assertion'])))
    if local:return local,'inline'
    local=list(dict.fromkeys(IDS.findall(atom.get('citation_context',atom['original_sentence']))))
    if local:return local,'same_original_sentence'
    blank=reply.rfind('\n\n',0,atom['start']);begin=blank+2 if blank>=0 else 0
    preceding=[a for a in all_atoms if begin<=a['start']<=atom['start'] and a['kind']=='provenance' and IDS.search(a['assertion'])]
    if preceding:return list(dict.fromkeys(IDS.findall(preceding[-1]['assertion']))),'paragraph_prefix'
    footers=[a for a in all_atoms if a['kind']=='source_identity']
    if len(footers)==1:
        ids=list(dict.fromkeys(IDS.findall(footers[0]['assertion'])))
        if len(ids)==1:return ids,'explicit_single_document_footer'
    return [],'unbound'


def _duration(text):
    value=compact(text)
    match=re.fullmatch(r'(.{1,14}?)(?:有效期|期限)('+NUMBER+r')(小时|分钟|秒钟|秒|天|日)',value)
    if not match:return None
    quantity=_quantities(match[2]+match[3])
    return (match[1],quantity[0]['value']) if quantity else None


def _quantity_shape(text):
    text=compact(text);values=_quantities(text)
    if not values:return None
    shape='';end=0
    for q in values:
        shape+=text[end:q['start']]+'<'+q['dimension']+'>';end=q['end']
    return shape+text[end:],[(q['dimension'],q['value']) for q in values]


def audit_claims(reply,hits,*,events=(),policy_versions=None,capability_evidence=None):
    hits=list(hits or []);events=list(events or []);all_atoms=atoms(str(reply));rows=_sentences(hits)
    output=[];allowed={h.get('doc_id') for h in hits};versions=policy_versions or {}
    def success(tool):return [e for e in events if e.get('event')=='tool_end' and e.get('tool')==tool and e.get('ok') and e.get('executed') is True]
    for n,atom in enumerate(all_atoms,1):
        claim=atom['assertion'];ids,binding=anchor(atom,all_atoms,str(reply))
        sources=[r for r in rows if r['doc_id'] in ids]
        evidence=[{'doc_id':h.get('doc_id'),'version':h.get('version'),'source':h.get('source'),
                   'chunk_id':h.get('chunk_id'),'content':h.get('content')} for h in hits if h.get('doc_id') in ids]
        label='indeterminate';reason='No whole-assertion proof; semantic review required';rule='unknown_semantics'
        if atom['kind']=='user_quote' or (REFUSAL.search(claim) and not _quantities(IDS.sub('',claim))) or re.fullmatch(r'[，,\s]*(?:谢谢|您好|你好|请先核对(?:您|你)的?问题|请补充(?:您的)?问题)',claim):
            label='not_applicable';reason='Explicit user quotation/refusal is not an affirmative policy assertion';rule='quoted_or_refusal'
        elif atom['kind']=='capability':
            context=capability_evidence or {}
            if atom['enabled'] and success(atom['tool']):
                label='supported';reason='This capability was actually executed successfully in the same run';rule='observed_runtime_capability'
            elif context.get('runtime_tool_binding_verified') is True:
                active=atom['tool'] in context.get('allowed_tools',[])
                label='supported' if active==atom['enabled'] else 'contradicted'
                reason='Verified runtime tool binding, not a policy fact';rule='runtime_capability'
            else:
                reason='Policy evidence does not establish runtime capabilities; saved HTTP tools schema/binding is absent'
                rule='runtime_capability_evidence_missing'
        elif re.search(r'可能|也许|不一定|或许',claim):
            reason='Uncertain modality is not a definite policy rule';rule='uncertain_modality'
        elif NEGATIVE_SOURCE.search(claim):
            reason='Negative source-scope explanation needs review; not a positive policy citation';rule='negative_source_scope'
        elif any(d not in allowed for d in ids):
            label='unsupported';reason='Citation is absent from actual tool evidence';rule='missing_citation'
        elif any(versions.get(h.get('doc_id')) and h.get('version') and versions[h['doc_id']]!=h['version'] for h in hits if h.get('doc_id') in ids):
            label='contradicted';reason='Retrieved version differs from the frozen/current authoritative version';rule='stale_version'
        elif any(versions.get(h.get('doc_id')) and not h.get('version') for h in hits if h.get('doc_id') in ids):
            reason='Policy version metadata is missing';rule='version_unknown'
        elif any(not any(h.get('title')==title and h.get('doc_id') in ids for h in hits) for title in re.findall(r'《([^》]+)》',claim)):
            label='contradicted';reason='Document title does not match the cited returned document';rule='wrong_document_title'
        elif atom['kind']=='provenance':
            label='supported' if success('search_policy') else 'unsupported'
            reason='Actual successful executed search_policy event exists' if label=='supported' else 'Query-result assertion has no actually executed successful policy tool'
            rule='query_completion'
        elif atom['kind']=='source_identity':
            titles=re.findall(r'《([^》]+)》',claim)
            if ids and evidence and all(any(h.get('title')==title and h.get('doc_id') in ids for h in hits) for title in titles):
                label='supported';reason='Cited document ID/title exists in actual returned evidence';rule='document_identity'
        elif not ids:
            reason='No explicit local, paragraph-prefix, or unambiguous footer citation';rule='no_citation_anchor'
        elif re.search(r'(?:12306|铁路|航司|航空公司|官方).{0,8}(?:规定|政策|统一|要求)',claim) and any('模拟' in h.get('content','') for h in hits):
            label='unsupported';reason='Simulated evidence does not support an affirmative real-world official policy attribution';rule='official_scope_expansion'
        elif re.search(r'(?:从|自).{1,16}(?:起算|开始计时|起)',claim) and not any(compact(claim) in compact(r['text']) for r in sources):
            label='unsupported';reason='Explicit start-of-validity trigger is not stated by the actual evidence';rule='added_time_origin'
        elif _added_constraints(claim,sources):
            label='unsupported';reason='Concrete added mandatory requirement absent from actual cited evidence';rule='added_requirement'
        else:
            direct=next((r for r in sources if compact(claim)==compact(r['text'])),None)
            duration=_duration(claim)
            if direct:
                label='supported';reason='Whole assertion equals evidence after finite spelling/format normalization';rule='whole_literal'
            elif duration:
                options=[(r,_duration(r['text'])) for r in sources if _duration(r['text']) and _duration(r['text'])[0]==duration[0]]
                if options:
                    values={v[1] for _,v in options}
                    label='supported' if values=={duration[1]} else 'contradicted' if duration[1] not in values else 'indeterminate'
                    reason='Same subject validity duration, normalized units; only the complete duration assertion checked';rule='bound_validity_duration'
            else:
                shape=_quantity_shape(claim)
                same=[r for r in sources if shape and (candidate:=_quantity_shape(r['text'])) and candidate[0]==shape[0]]
                if same:
                    label='supported' if any(_quantity_shape(row['text'])[1]==shape[1] for row in same) else 'contradicted'
                    reason='Entire predicate/condition/subject matches; compare normalized quantity units and values';rule='whole_quantity_predicate'
                # Finite conditional equivalence, no naked numeric-match shortcut.
                c=compact(claim);joined=''.join(compact(h['content']) for h in evidence)
                source_release='过期未支付自动释放库存' in joined
                explicit=re.fullmatch(r'(?:超过有效期|过期)未(?:完成)?支付(?:系统)?(?:将)?(?:自动释放(?:已锁定的)?库存|库存(?:会|将)?自动释放)',c)
                timed=re.fullmatch(r'(?:若|如果)?在('+NUMBER+r')(小时|分钟|秒钟|秒|天|日)内未完成支付(?:系统)?(?:将)?自动释放(?:已锁定的)?库存',c)
                if source_release and explicit:
                    label='supported';reason='Expiry AND unpaid → automatic inventory release, with both conditions retained';rule='conditional_release'
                elif source_release and timed:
                    values={v[1] for h in evidence for r in _sentences([h]) if (v:=_duration(r['text']))}
                    value=_quantities(timed[1]+timed[2])[0]['value']
                    if len(values)==1:
                        label='supported' if value in values else 'contradicted'
                        reason='Payment deadline is bound to cited validity duration; unpaid-on-expiry condition retained';rule='bound_deadline_release'
        output.append({**atom,'claim_id':f'C{n:02}','cited_doc_ids':ids,'citation_binding':binding,'evidence':evidence,
            'verdict':label,'reason':reason,'rule':rule,'severity':'high' if label in ('contradicted','unsupported') else 'medium' if label=='indeterminate' else 'low',
            'needs_b_review':label in ('indeterminate','contradicted','unsupported')})
    duration_groups={}
    for row in output:
        duration=_duration(row['assertion'])
        if duration and row['kind']=='policy':
            duration_groups.setdefault((duration[0],tuple(row['cited_doc_ids'])),[]).append((row,duration[1]))
    conflicts=[]
    for members in duration_groups.values():
        if len({value for _,value in members})>1:
            conflicts.append({'claim_ids':[row['claim_id'] for row,_ in members],'values':[value for _,value in members]})
            for row,_ in members:
                row.update(verdict='contradicted',reason='Two affirmative durations for the same subject/source contradict each other',rule='self_contradiction',needs_b_review=True,severity='high')
    counts=Counter(r['verdict'] for r in output)
    factual=sum(r['factual'] and r['verdict']!='not_applicable' for r in output)
    verdict='FAIL' if counts['contradicted'] or counts['unsupported'] else 'INDETERMINATE' if counts['indeterminate'] or not factual else 'PASS'
    return {'schema':'ticket-rag-atomic-audit/1','original_model_reply':reply,'verdict':verdict,
        'counts':{k:counts[k] for k in LABELS},'factual_assertions':factual,'assertions':output,'self_conflicts':conflicts,
        'citation_scope':'Footer/prefix bind a candidate source; support requires a separate complete-assertion proof',
        'scope':'Finite explicit assertions only. Missing runtime binding and unrecognized semantics remain indeterminate; no model judge used.'}
