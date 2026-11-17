"""Explicit DashScope embedding HTTP client and durable, independent request ledger."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
import uuid
from urllib.parse import urlsplit
from target.api_usage import UsageLog

ROOT=Path(__file__).resolve().parent.parent
AUTH=ROOT/'artifacts/runtime/v35-qwen38-rag/authorization-20261026'


class EmbeddingError(RuntimeError):
    def __init__(self,category,status=None):
        self.category,self.status=category,status
        super().__init__('Embedding 请求未完成：'+category)


@dataclass(frozen=True)
class EmbeddingSettings:
    model: str='text-embedding-v4'
    dimensions: int=1024
    batch_size: int=10
    timeout: float=25
    limit: int=0  # Deprecated: cumulative request caps have been removed.
    ledger: Path=AUTH/'embedding.db'
    cache: Path=ROOT/'artifacts/runtime/v35-rag/embedding-cache.db'
    base_url: str=''

    @classmethod
    def from_env(cls):
        return cls(model=os.getenv('RAG_EMBEDDING_MODEL','text-embedding-v4'),
                   dimensions=int(os.getenv('RAG_EMBEDDING_DIMENSIONS','1024')),
                   base_url=os.getenv('DASHSCOPE_EMBEDDING_BASE_URL',os.getenv('DASHSCOPE_BASE_URL','')),
                   cache=Path(os.getenv('RAG_EMBEDDING_CACHE',str(cls.cache))))


def endpoint(base):
    try:
        u=urlsplit(base);port=u.port
    except ValueError:raise EmbeddingError('invalid_endpoint') from None
    hosts={'dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com','cn-hongkong.dashscope.aliyuncs.com'}
    import re
    workspace=bool(re.fullmatch(r'[a-z0-9-]+\.[a-z]{2}-[a-z0-9-]+\.maas\.aliyuncs\.com',u.hostname or ''))
    if (u.scheme!='https' or (u.hostname not in hosts and not workspace) or u.username or u.password or
            port not in (None,443) or u.query or u.fragment or u.path.rstrip('/')!='/compatible-mode/v1'):
        raise EmbeddingError('invalid_endpoint')
    return base.rstrip('/')+'/embeddings'


class EmbeddingBudget(UsageLog):
    """Compatibility name: independent append-only usage, never a request gate."""
    def __init__(self, path, limit=0):
        self.historical_path = Path(path)
        super().__init__('embedding', path)

    def reserve(self, settings, texts, origin):
        self.origin = origin
        return super().reserve({'model': settings.model, 'dimension': settings.dimensions,
            'input_hashes': [hashlib.sha256(t.encode()).hexdigest() for t in texts], 'batch_size': len(texts)})

    def settle(self, uid, **values):
        self.record(uid, status=values.pop('status', None), category=values.pop('category', 'response_received'),
                    model=values.get('actual_model'), **values)


class EmbeddingProvider:
    def __init__(self,settings=None,*,transport=None):
        self.settings=settings or EmbeddingSettings.from_env();s=self.settings
        if s.model!='text-embedding-v4' or s.dimensions not in (64,128,256,512,768,1024,1536,2048) or not 1<=s.batch_size<=10:
            raise EmbeddingError('unsupported_embedding_configuration')
        self.url=endpoint(s.base_url);self.transport=transport
        self.origin='offline_stub' if transport is not None else 'real_api'
        self.budget=EmbeddingBudget(s.ledger,s.limit);self.last_receipts=[];self.request_ids=[]

    def cache_key(self,text):
        s=self.settings
        return hashlib.sha256(json.dumps([s.model,s.dimensions,s.base_url,text,self.origin],ensure_ascii=False).encode()).hexdigest()

    def _cache(self):
        self.settings.cache.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(self.settings.cache)
        c.execute('CREATE TABLE IF NOT EXISTS vectors(cache_key TEXT PRIMARY KEY,vector TEXT,receipt TEXT)');c.commit();return c

    def embed_many(self,texts,*,allow_network=False):
        if not isinstance(texts,list) or any(not isinstance(t,str) or not t.strip() or len(t)>8000 for t in texts):
            raise EmbeddingError('invalid_embedding_input')
        self.last_receipts=[];self.request_ids=[];result=[None]*len(texts);missing={}
        with closing(self._cache()) as c:
            for i,text in enumerate(texts):
                row=c.execute('SELECT vector,receipt FROM vectors WHERE cache_key=?',(self.cache_key(text),)).fetchone()
                if row:
                    result[i]=json.loads(row[0]);self.last_receipts.append(json.loads(row[1]))
                else:missing.setdefault(text,[]).append(i)
        if missing and not allow_network:raise EmbeddingError('query_embedding_not_cached_explicit_network_required')
        unique=list(missing)
        for start in range(0,len(unique),self.settings.batch_size):
            batch=unique[start:start+self.settings.batch_size];vectors,receipt=self._request(batch)
            with closing(self._cache()) as c:
                for text,vector in zip(batch,vectors):
                    c.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?)',(self.cache_key(text),json.dumps(vector),json.dumps(receipt)))
                    for i in missing[text]:result[i]=vector
                c.commit()
            self.last_receipts.append(receipt)
        return result

    def _request(self,texts):
        import httpx
        key=os.getenv('DASHSCOPE_API_KEY','').strip()
        if not key:raise EmbeddingError('missing_DASHSCOPE_API_KEY')
        uid=self.budget.reserve(self.settings,texts,self.origin);started=time.perf_counter();status=None
        self.request_ids.append(uid)
        try:
            from target.model_network import client_kwargs
            kw=client_kwargs(timeout=self.settings.timeout,follow_redirects=False,transport=self.transport)
            if self.transport is not None: kw.pop('proxy',None); kw['trust_env']=False
            with httpx.Client(**kw) as c:
                r=c.post(self.url,headers={'Authorization':'Bearer '+key},json={'model':self.settings.model,'input':texts,
                    'dimensions':self.settings.dimensions,'encoding_format':'float'})
            status=r.status_code
            if not r.is_success:
                category={400:'invalid_parameters',401:'authentication_failed',402:'insufficient_balance',403:'permission_denied',
                          404:'model_or_endpoint_not_found',422:'invalid_parameters',429:'rate_limited',500:'server_error',503:'service_unavailable'}.get(status,'http_error')
                try:code=str(r.json().get('error',{}).get('code','')).lower()
                except (ValueError,AttributeError):code=''
                if any(x in code for x in ('arrearage','balance','insufficient')):category='insufficient_balance'
                raise EmbeddingError(category,status)
            body=r.json();data=body.get('data',[])
            if len(data)!=len(texts) or {d.get('index') for d in data}!=set(range(len(texts))):raise EmbeddingError('invalid_embedding_response',status)
            vectors=[d['embedding'] for d in sorted(data,key=lambda d:d['index'])]
            if any(not isinstance(v,list) or len(v)!=self.settings.dimensions or
                   any(type(x) not in (int,float) or not math.isfinite(x) for x in v) or sum(x*x for x in v)==0 for v in vectors):
                raise EmbeddingError('invalid_embedding_vectors',status)
            usage=body.get('usage') or {};tokens=usage.get('total_tokens')
            tokens=tokens if type(tokens) is int and tokens>=0 else None
            hashes=[hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest() for v in vectors]
            receipt={'request_id':uid,'origin':self.origin,'model':self.settings.model,'actual_model':body.get('model'),
                     'dimensions':self.settings.dimensions,'tokens':tokens,'status':status,
                     'latency_ms':round((time.perf_counter()-started)*1000),'server_request_id':r.headers.get('x-request-id') or body.get('id'),
                     'response_sha256':hashlib.sha256(r.content).hexdigest(),'vector_hashes':hashes}
            from target.diagnostics import sanitize
            receipt=sanitize(receipt)
            self.budget.settle(uid,**{k:v for k,v in receipt.items() if k in ('status','server_request_id','actual_model','tokens','latency_ms','response_sha256')},
                               category='response_received',vector_hashes=json.dumps(hashes))
            return vectors,receipt
        except Exception as exc:
            category=exc.category if isinstance(exc,EmbeddingError) else 'timeout' if isinstance(exc,httpx.TimeoutException) else 'network_connection' if isinstance(exc,httpx.TransportError) else 'invalid_embedding_response'
            self.budget.settle(uid,status=status,latency_ms=round((time.perf_counter()-started)*1000),category=category)
            raise EmbeddingError(category,status) from None
