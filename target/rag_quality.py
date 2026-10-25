"""Fixed-label retrieval metrics and scoped, non-LLM answer checks. Unknown stays unknown."""
import re


def query_text(case):
    history=' '.join(m['content'] for m in case.get('history',[]) if m.get('role')=='user')
    return (history+' '+case['question']).strip()


def retrieval_metrics(cases,results,k=3):
    recall=[];rr=[];false_recall=[];failures=0;rows=[]
    for c in cases:
        result=results.get(c['id'])
        if result is None or result.get('error'):
            failures+=1;rows.append({'case_id':c['id'],'status':'retrieval_failed'});continue
        actual=list(dict.fromkeys(h['doc_id'] for h in result.get('hits',[])))[:k]
        expected=set(c['expected_doc_ids'])
        r=len(expected.intersection(actual))/len(expected) if expected else None
        reciprocal=next((1/(i+1) for i,d in enumerate(actual) if d in expected),0) if expected else None
        if expected:recall.append(r);rr.append(reciprocal)
        else:false_recall.append(bool(actual))
        rows.append({'case_id':c['id'],'expected_doc_ids':sorted(expected),'actual_doc_ids':actual,'recall_at_k':r,'rr':reciprocal,
                     'no_answer_false_recall':bool(actual) if not expected else None})
    return {'scope':'retrieval only; no final-answer success inferred','k':k,'cases':len(cases),'answerable_scored':len(recall),
            'no_answer_scored':len(false_recall),'recall_at_k':sum(recall)/len(recall) if recall else None,
            'mrr':sum(rr)/len(rr) if rr else None,'no_answer_false_recall_rate':sum(false_recall)/len(false_recall) if false_recall else None,
            'retrieval_failures':failures,'rows':rows}


def answer_metrics(case,reply,hits):
    from target.rag_service import citation_check
    check=citation_check(reply,hits);norm=lambda s:re.sub(r'\s+','',s)
    text=norm(reply);points=[]
    for point in case['answer_points']:
        asserted=norm(point) in text
        grounded=any(norm(point) in norm(h['content']) and h['doc_id'] in case['allowed_citations'] for h in hits)
        points.append({'point':point,'mentioned':asserted,'supported_in_allowed_evidence':grounded,
                       'status':'supported_fixed_point' if asserted and grounded else 'indeterminate'})
    wrong=[c for c in check['cited_doc_ids'] if c not in case['allowed_citations'] or c not in check['allowed_doc_ids']]
    refusal=bool(re.search(r'无法|不能确认|没有.{0,12}(?:规定|信息|依据|政策)|未.{0,10}(?:规定|涉及|提供)|不包含|无相关',reply))
    no_answer=not case['expected_doc_ids']
    denominator=len(check['cited_doc_ids'])
    return {**check,'wrong_citations':wrong,
            'citation_id_precision':(denominator-len(wrong))/denominator if denominator else None,
            'fixed_point_checks':points,'supported_fixed_points':sum(p['status']=='supported_fixed_point' for p in points),
            'fixed_points':len(points),'no_answer_refusal':refusal and not check['cited_doc_ids'] if no_answer else None,
            'business_status':'failed' if wrong else 'indeterminate',
            'answer_faithfulness':'indeterminate','generation_failure':False,
            'limits':'Literal fixed points and citation IDs do not establish full semantic faithfulness; B reviews unsupported/extra claims.'}


def generation_summary(records):
    checked=[r['assessment'] for r in records if r.get('assessment')]
    citations=[r['citation_id_precision'] for r in checked if r['citation_id_precision'] is not None]
    no_answer=[r['no_answer_refusal'] for r in checked if r['no_answer_refusal'] is not None]
    return {'executed':len(records),'generation_failures':sum(bool(r.get('error')) for r in records),
            'citation_id_precision_mean':sum(citations)/len(citations) if citations else None,
            'no_answer_refusal_rate':sum(no_answer)/len(no_answer) if no_answer else None,
            'business_errors':sum(r['business_status']=='failed' for r in checked),
            'faithfulness':'indeterminate','indeterminate_answers':sum(r['answer_faithfulness']=='indeterminate' for r in checked),
            'scope':'Only actually generated answers, never all retrieval cases or SDK fixtures'}
