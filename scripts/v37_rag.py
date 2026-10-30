"""Offline V3.7 corpus quality; independent Chroma index with labelled hash vectors."""
import argparse,json,hashlib,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))

def vector(text):
    v=[0.0]*128
    for i in range(max(1,len(text)-1)):
        j=int(hashlib.sha256(text[i:i+2].encode()).hexdigest()[:8],16)%len(v);v[j]+=1
    norm=math.sqrt(sum(x*x for x in v)) or 1
    return [x/norm for x in v]

def evaluate(out):
    from target.rag_store import keyword
    import chromadb
    from chromadb.config import Settings
    out.mkdir(parents=True,exist_ok=False)
    docs=json.loads((ROOT/'data/v37/policies.json').read_text(encoding='utf8'))
    active=[{**d,'chunk_id':d['doc_id']} for d in docs if d['status']=='active']
    client=chromadb.PersistentClient(path=str(out/'index'),settings=Settings(anonymized_telemetry=False))
    col=client.create_collection('v37_offline_hash',metadata={'hnsw:space':'cosine'})
    col.add(ids=[d['doc_id'] for d in active],embeddings=[vector(d['title']+d['content']) for d in active],documents=[d['content'] for d in active])
    cases=json.loads((ROOT/'data/v37/quality.json').read_text(encoding='utf8'));rows=[]
    for c in cases:
        kw=keyword(active,c['question'],k=3)
        q=col.query(query_embeddings=[vector(c['question'])],n_results=3)
        vd=q['ids'][0];kd=[x['doc_id'] for x in kw]
        fused={}
        for items in (kd,vd):
            for rank,d in enumerate(items,1):fused[d]=fused.get(d,0)+1/(60+rank)
        for mode,ids in [('keyword',kd),('offline_hash_vector',vd),('offline_hash_hybrid',sorted(fused,key=lambda d:-fused[d])[:3])]:
            rank=next((i for i,d in enumerate(ids,1) if d in c['expected']),None)
            rows.append({**c,'mode':mode,'hits':ids,'first_relevant_rank':rank})
    metrics={}
    for mode in ('keyword','offline_hash_vector','offline_hash_hybrid'):
        pos=[r for r in rows if r['mode']==mode and r['expected']];neg=[r for r in rows if r['mode']==mode and not r['expected']]
        metrics[mode]={'positive_samples':len(pos),'recall1':sum(r['first_relevant_rank']==1 for r in pos)/len(pos),
            'recall3':sum(r['first_relevant_rank'] is not None for r in pos)/len(pos),
            'mrr':sum(1/r['first_relevant_rank'] if r['first_relevant_rank'] else 0 for r in pos)/len(pos),
            'no_answer_false_recall':sum(bool(r['hits']) for r in neg),'negative_samples':len(neg)}
    result={'documents':len(docs),'active':len(active),'embedding_origin':'offline_hash_not_real_embedding',
        'real_api_requests':0,'metrics':metrics,'rows':rows,'answer_faithfulness':'not_evaluated_no_generation',
        'limits':'Development positives use document titles; not an independent accuracy benchmark. Vector/Hybrid use diagnostic hash vectors.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    evaluate(p.parse_args().out)
