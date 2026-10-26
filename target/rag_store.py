"""Persistent Chroma policy index. All embedding calls are explicit and receipted."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

ROOT=Path(__file__).resolve().parent.parent


class RagError(RuntimeError):pass


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def documents(path,chunk_size=450,overlap=50):
    path=Path(path)
    if chunk_size<80 or not 0<=overlap<chunk_size:raise RagError('invalid_chunk_settings')
    text=path.read_text(encoding='utf-8-sig');parts=re.split(r'^## \[(P\d+)\]\s*(.*?)\n',text,flags=re.M)
    source=path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
    chunks=[];seen=set()
    for i in range(1,len(parts),3):
        doc_id,title,body=parts[i],parts[i+1],parts[i+2].strip()
        if doc_id in seen:raise RagError('duplicate_document_id')
        seen.add(doc_id);version=digest([title,body])[:16]
        for n,start in enumerate(range(0,len(body),chunk_size-overlap)):
            content=body[start:start+chunk_size]
            chunk_id=f'{doc_id}-{n:04}-{digest(content)[:12]}'
            chunks.append({'doc_id':doc_id,'title':title,'source':source+'#'+doc_id,'version':version,
                           'chunk_id':chunk_id,'content':content})
            if start+chunk_size>=len(body):break
    if not chunks:raise RagError('empty_policy_corpus')
    return chunks


def keyword(chunks,question,k=3,threshold=0):
    tokenize=lambda s:[c for c in s if '\u4e00'<=c<='\u9fff']+re.findall(r'[a-zA-Z0-9]+',s)
    terms=set(tokenize(question));hits=[]
    for c in chunks:
        words=tokenize(c['title']+c['content'])
        score=sum(w in terms for w in words)/math.sqrt(len(words)) if words else 0
        if score>threshold:hits.append({**c,'score':score,'keyword_score':score})
    hits.sort(key=lambda h:(-h['score'],h['chunk_id']))
    return dedup(hits,k)


def dedup(hits,k):
    out=[];seen=set()
    for h in hits:
        if h['doc_id'] not in seen:
            seen.add(h['doc_id']);out.append({**h,'rank':len(out)+1})
        if len(out)>=k:break
    return out


class PolicyIndex:
    def __init__(self,path,policy=None,provider=None,chunk_size=450,overlap=50):
        from target.embeddings import EmbeddingProvider
        self.path=Path(path);self.policy=Path(policy or ROOT/'data/policies.md')
        self.provider=provider or EmbeddingProvider();self.chunk_size,self.overlap=chunk_size,overlap

    def expected(self):
        chunks=documents(self.policy,self.chunk_size,self.overlap);s=self.provider.settings
        identity={'model':s.model,'dimensions':s.dimensions,'endpoint':s.base_url,
                  'corpus_hash':hashlib.sha256(self.policy.read_bytes()).hexdigest(),
                  'chunk_size':self.chunk_size,'overlap':self.overlap,'schema':'ticket-policy-index/1'}
        return {**identity,'index_version':digest(identity)[:24]},chunks

    def client(self):
        from target.rag_protection import is_baseline
        if is_baseline(self.path):raise RagError('immutable_chroma_baseline_open_forbidden')
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:raise RagError('chromadb_dependency_missing') from None
        return chromadb.PersistentClient(path=str(self.path),settings=Settings(anonymized_telemetry=False,allow_reset=False))

    def load(self,*,require_real=False):
        manifest=self.path/'manifest.json'
        if not manifest.exists():raise RagError('empty_or_missing_index')
        try:
            state=json.loads(manifest.read_text(encoding='utf-8'));expected,chunks=self.expected()
            if any(state.get(k)!=v for k,v in expected.items()):raise RagError('stale_or_incompatible_index_rebuild_required')
            if require_real and state.get('embedding_origin')!='real_api':raise RagError('test_index_forbidden_in_live')
            collection=self.client().get_collection(state['collection'],embedding_function=None)
            got=collection.get(include=['documents','metadatas','embeddings'])
            if set(got['ids'])!={c['chunk_id'] for c in chunks} or len(got['ids'])!=state['chunk_count']:
                raise RagError('index_content_mismatch')
            for uid,body,meta,vector in zip(got['ids'],got['documents'],got['metadatas'],got['embeddings']):
                if len(vector)!=state['dimensions'] or digest([float(v) for v in vector])!=state['stored_vector_hashes'][uid]:
                    raise RagError('corrupt_or_incompatible_vectors')
                expected_row=next(c for c in chunks if c['chunk_id']==uid)
                if body!=expected_row['content'] or any(meta.get(k)!=expected_row[k] for k in ('doc_id','title','source','version','chunk_id')):
                    raise RagError('index_metadata_mismatch')
            return state,collection
        except RagError:raise
        except Exception:raise RagError('corrupt_index') from None

    def status(self):
        try:
            state,_=self.load()
            return {**state,'state':'ready','network_requests':0}
        except Exception as exc:
            return {'state':'unavailable','category':str(exc) if isinstance(exc,RagError) else 'configuration_error','network_requests':0}

    def build(self,*,allow_network=False,rebuild=False):
        from target.rag_protection import is_baseline
        if is_baseline(self.path):raise RagError('immutable_chroma_baseline_rebuild_forbidden')
        expected,chunks=self.expected()
        if (self.path/'manifest.json').exists() and not rebuild:
            state,_=self.load();return {**state,'reused':True,'new_embedding_requests':0}
        before=self.provider.budget.snapshot()['used']
        vectors=self.provider.embed_many([c['title']+'\n'+c['content'] for c in chunks],allow_network=allow_network)
        receipts=self.provider.last_receipts
        if not receipts or any(r['origin']!=self.provider.origin for r in receipts):raise RagError('embedding_provenance_missing')
        self.path.mkdir(parents=True,exist_ok=True)
        name='policy-'+expected['index_version']+'-'+uuid.uuid4().hex[:8]
        collection=self.client().create_collection(name,metadata={'hnsw:space':'cosine'},embedding_function=None)
        collection.add(ids=[c['chunk_id'] for c in chunks],documents=[c['content'] for c in chunks],embeddings=vectors,
                       metadatas=[{k:c[k] for k in ('doc_id','title','source','version','chunk_id')} for c in chunks])
        stored=collection.get(include=['embeddings'])
        state={**expected,'collection':name,'chunk_count':len(chunks),'document_count':len({c['doc_id'] for c in chunks}),
               'embedding_origin':self.provider.origin,'embedding_receipts':receipts,
               'stored_vector_hashes':{uid:digest([float(v) for v in emb]) for uid,emb in zip(stored['ids'],stored['embeddings'])}}
        # Preserve previous manifests/collections; rebuilding never deletes evidence.
        if (self.path/'manifest.json').exists():
            archive=self.path/'manifests';archive.mkdir(exist_ok=True)
            (archive/(uuid.uuid4().hex+'.json')).write_bytes((self.path/'manifest.json').read_bytes())
        temp=self.path/'manifest.pending';temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.path/'manifest.json');self.load()
        return {**state,'reused':False,'new_embedding_requests':self.provider.budget.snapshot()['used']-before}

    def retrieve(self,question,mode='hybrid',k=3,threshold=0.35,*,allow_network=False,require_real=False,quality_profile='v35'):
        if mode not in ('keyword','vector','hybrid') or not 1<=k<=20 or not -1<=threshold<=1:raise RagError('invalid_retrieval_configuration')
        started=time.perf_counter();_,chunks=self.expected();state=None;vector_hits=[];embedding_ms=0
        lexical=keyword(chunks,question,k=20)
        if mode!='keyword':
            state,collection=self.load(require_real=require_real)
            begin=time.perf_counter();q=self.provider.embed_many([question],allow_network=allow_network)[0]
            embedding_ms=round((time.perf_counter()-begin)*1000)
            got=collection.query(query_embeddings=[q],n_results=min(20,state['chunk_count']),include=['documents','metadatas','distances'])
            for text,meta,distance in zip(got['documents'][0],got['metadatas'][0],got['distances'][0]):
                score=1-float(distance)
                if score>=threshold:vector_hits.append({**meta,'content':text,'score':score,'vector_score':score})
            vector_hits=dedup(vector_hits,20)
        if mode=='keyword':hits=dedup(lexical,k)
        elif mode=='vector':hits=dedup(vector_hits,k)
        else:
            # RRF(60): deterministic rank fusion, never concatenate two result lists.
            fused={}
            for label,items in (('keyword',lexical),('vector',vector_hits)):
                for rank,item in enumerate(items,1):
                    target=fused.setdefault(item['doc_id'],{**item,'score':0,'fusion_ranks':{}})
                    target['score']+=1/(60+rank);target['fusion_ranks'][label]=rank
            hits=dedup(sorted(fused.values(),key=lambda h:(-h['score'],h['doc_id'])),k)
        quality={}
        if quality_profile=='v351':
            from target.rag_relevance import apply_quality
            quality=apply_quality(question,lexical,vector_hits,mode,k)
            hits=quality['hits']
        elif quality_profile!='v35':raise RagError('invalid_quality_profile')
        evidence={'schema':'ticket-rag-retrieval/1','question':question,'mode':mode,'top_k':k,'vector_threshold':threshold,
                  'embedding_model':self.provider.settings.model if mode!='keyword' else None,
                  'embedding_origin':state['embedding_origin'] if state else 'not_used','index_version':state['index_version'] if state else None,
                  'fusion':'reciprocal_rank_fusion_k60' if mode=='hybrid' else None,'hits':hits,
                  'embedding_latency_ms':embedding_ms,'total_latency_ms':round((time.perf_counter()-started)*1000),
                  'embedding_receipts':list(self.provider.last_receipts) if mode!='keyword' else [],**quality}
        return evidence
