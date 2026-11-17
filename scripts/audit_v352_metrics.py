"""Independent Fraction-based audit of saved retrieval rows. No API/SDK imports."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def recalculate(cases,results):
    """Macro document recall and first-relevant MRR@3, not hit rate or pooled recall."""
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('duplicate_case_id')
    values={k:[] for k in ('recall_at_1','recall_at_3','mrr','no_answer_false_recall_rate')}
    rows=[];positive=[];negative=[];missing=[];errors=[]
    for case in cases:
        identity=case['id'];relevant=frozenset(case['expected_doc_ids']);result=results.get(identity)
        row={'case_id':identity,'expected_doc_ids':sorted(relevant)}
        if result is None or result.get('status')=='not_run':
            missing.append(identity);rows.append({**row,'status':'not_run'});continue
        if result.get('error'):
            errors.append(identity);rows.append({**row,'status':'indeterminate','error':result['error']});continue
        ranked=[]
        for hit in result.get('hits',[]):
            if not isinstance(hit.get('doc_id'),str):raise ValueError('invalid_doc_id')
            if hit['doc_id'] not in ranked:ranked.append(hit['doc_id'])
        ranked=ranked[:3]
        # Independent enumeration; never uses the production metrics/dedup helper.
        ranks={doc:rank for rank,doc in enumerate(ranked,1) if doc in relevant}
        row.update(status='scored',ranked_doc_ids=ranked,relevant_ranks=ranks,raw_hits=result.get('hits',[]))
        if relevant:
            positive.append(identity)
            r1=Fraction(sum(doc in relevant for doc in ranked[:1]),len(relevant))
            r3=Fraction(sum(doc in relevant for doc in ranked),len(relevant))
            rr=Fraction(1,min(ranks.values())) if ranks else Fraction(0)
            for key,value in (('recall_at_1',r1),('recall_at_3',r3),('mrr',rr)):
                values[key].append(value);row[key]={'fraction':str(value),'value':float(value)}
        else:
            negative.append(identity);value=Fraction(bool(ranked))
            values['no_answer_false_recall_rate'].append(value)
            row.update(recall_at_1=None,recall_at_3=None,mrr=None,no_answer_false_recall=bool(ranked))
        rows.append(row)
    summary={key:{'fraction':str(sum(v,Fraction(0))/len(v)) if v else None,
                  'value':float(sum(v,Fraction(0))/len(v)) if v else None,'denominator':len(v)} for key,v in values.items()}
    return {'metrics':summary,'positive_ids':positive,'negative_ids':negative,'not_run_ids':missing,
            'indeterminate_ids':errors,'rows':rows,'cutoff':3,'ranking':'actual returned unique doc_id order, not re-sorted by score'}


def run(out):
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    source=ROOT/'docs/evidence/v352/live/retrieval48'
    reported=read(source/'report.json');raw=read(source/'rows.json')
    groups={s:read(ROOT/f'cases/rag_quality_v351_{s}.json')['cases'] for s in ('development','holdout')}
    groups['all48']=groups['development']+groups['holdout'];results={m:{} for m in ('keyword','vector','hybrid')}
    labels={c['id']:c for c in groups['all48']}
    for position,row in enumerate(raw):
        mode=row['mode'];identity=row['case']['id']
        if row['case']!=labels[identity]:raise ValueError('saved_row_label_differs_from_frozen_dataset')
        if identity in results[mode]:raise ValueError('duplicate_mode_case_row')
        results[mode][identity]=row['result']
    computed={s:{m:recalculate(cases,rows) for m,rows in results.items()} for s,cases in groups.items()}
    disagreements=[]
    for split,modes in computed.items():
        cohorts=[]
        for mode,audit in modes.items():
            original=reported['metrics'][split][mode];cohorts.append((audit['positive_ids'],audit['negative_ids']))
            for name,value in audit['metrics'].items():
                if value['value']!=original[name]:disagreements.append({'split':split,'mode':mode,'metric':name,'original':original[name],'independent':value})
        if not all(c==cohorts[0] for c in cohorts):disagreements.append({'split':split,'issue':'mode_cohorts_differ'})
    paths=[source/'report.json',source/'rows.json',*(ROOT/f'cases/rag_quality_v351_{s}.json' for s in ('development','holdout'))]
    result={'schema':'ticket-v352-independent-metric-audit/1','real_API_requests':0,
        'original_report_preserved':True,'independent_method':'Exact rational arithmetic from frozen relevant sets and raw returned order; no production helper used',
        'definitions':{'recall_at_k':'macro mean |relevant intersect first K| / |relevant| over scored answerable queries',
                       'mrr':'MRR@3: macro mean reciprocal of first relevant returned rank, zero if none in top3',
                       'no_answer':'Excluded from positive denominators, separate false-recall denominator'},
        'inputs':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'disagreements':disagreements,'status':'passed' if not disagreements else 'failed','computed':computed}
    out.mkdir(parents=True,exist_ok=False)
    with (out/'audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':result['status'],'disagreements':len(disagreements),'real_API_requests':0,
        'all48':{m:x['metrics'] for m,x in computed['all48'].items()}},ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();run(args.out)
