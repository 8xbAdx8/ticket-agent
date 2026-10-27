"""Immutable Chroma source: hash/copy first, open only an isolated working copy."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import uuid

ROOT=Path(__file__).resolve().parent.parent
BASELINE=ROOT/'artifacts/runtime/v35-rag/index'
WORK=ROOT/'artifacts/runtime/v352-chroma-work'


def tree_hashes(path):
    path=Path(path)
    if not path.is_dir():raise ValueError('missing_chroma_source')
    result={}
    for p in sorted(path.rglob('*')):
        if p.is_symlink():raise ValueError('symlink_in_chroma_source')
        if p.is_file():result[p.relative_to(path).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def hash_tree(hashes):
    return hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def is_baseline(path):
    return Path(path).resolve()==BASELINE.resolve()


def copy_workspace(source,parent=WORK):
    source=Path(source).resolve();parent=Path(parent).resolve()
    if parent==source or parent.is_relative_to(source):raise ValueError('workspace_inside_immutable_source')
    before=tree_hashes(source)
    destination=parent/uuid.uuid4().hex;destination.mkdir(parents=True,exist_ok=False)
    shutil.copytree(source,destination/'index')
    copied=tree_hashes(destination/'index');after=tree_hashes(source)
    if before!=after or before!=copied:raise ValueError('source_changed_during_chroma_copy')
    receipt={'schema':'ticket-chroma-copy/1','source_tree_sha256':hash_tree(before),
             'source_files':before,'copy_files_match':True,'workspace_id':destination.name}
    (destination/'copy-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return destination,receipt


@contextmanager
def working_index(source,provider,*,policy=None,parent=WORK):
    from target.rag_store import PolicyIndex
    from target.embeddings import EmbeddingProvider
    destination,receipt=copy_workspace(source,parent)
    cache=destination/'embedding-cache.db'
    if provider.settings.cache.is_file():shutil.copyfile(provider.settings.cache,cache)
    local=EmbeddingProvider(replace(provider.settings,cache=cache),transport=provider.transport)
    index=PolicyIndex(destination/'index',provider=local,policy=policy)
    try:yield index,receipt
    finally:
        # Stop only this UUID's system, never a client shared with another test.
        try:index.client()._system.stop()
        except Exception:pass
        after=tree_hashes(source)
        receipt.update(source_unchanged=after==receipt['source_files'],
                       working_files_changed=tree_hashes(destination/'index')!=receipt['source_files'])
        (destination/'copy-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        if not receipt['source_unchanged']:raise ValueError('immutable_chroma_source_changed')


def logical_snapshot(index,*,require_real=True):
    state,collection=index.load(require_real=require_real)
    got=collection.get(include=['documents','metadatas','embeddings'])
    rows=[]
    for uid,text,meta,vector in zip(got['ids'],got['documents'],got['metadatas'],got['embeddings']):
        rows.append({'chunk_id':uid,'content':text,'metadata':meta,'dimensions':len(vector),
                     'vector_sha256':hashlib.sha256(json.dumps([float(x) for x in vector],separators=(',',':')).encode()).hexdigest()})
    rows.sort(key=lambda r:r['chunk_id'])
    return {'index_version':state['index_version'],'chunks':len(rows),'documents':len({r['metadata']['doc_id'] for r in rows}),
            'rows':rows,'logical_sha256':hash_tree({'rows':json.dumps(rows,ensure_ascii=False,sort_keys=True)})}


class ProtectedPolicyIndex:
    """Read-through source; status/retrieve cannot give Chroma its source path."""
    def __init__(self,path,provider=None,policy=None,parent=WORK):
        from target.embeddings import EmbeddingProvider
        self.path=Path(path);self.provider=provider or EmbeddingProvider();self.policy=policy;self.parent=parent

    def status(self):
        try:
            with working_index(self.path,self.provider,policy=self.policy,parent=self.parent) as (index,receipt):
                state=index.status()
                state.update(immutable_baseline=True,source_tree_sha256=receipt['source_tree_sha256'],
                             source_unchanged=True,opened_working_copy_only=True)
                return state
        except Exception as exc:
            return {'state':'unavailable','category':getattr(exc,'category',type(exc).__name__),
                    'network_requests':0,'immutable_baseline':True}

    def retrieve(self,*args,**kwargs):
        # Query embedding may use explicitly authorized network on the COPY.
        # This never permits rebuilding or opening the immutable source in place.
        with working_index(self.path,self.provider,policy=self.policy,parent=self.parent) as (index,receipt):
            result=index.retrieve(*args,**kwargs)
            result['index_protection']={'source_tree_sha256':receipt['source_tree_sha256'],'opened_working_copy_only':True}
            return result

    def build(self,*args,**kwargs):
        from target.rag_store import RagError
        raise RagError('immutable_chroma_baseline_rebuild_forbidden')

    def load(self,*args,**kwargs):
        from target.rag_store import RagError
        raise RagError('immutable_index_explicit_workspace_required')
