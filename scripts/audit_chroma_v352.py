"""Instrument open/read/query/close on a copy only; never restore original files."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))


def audit(out):
    from target.rag_protection import BASELINE,copy_workspace,tree_hashes,hash_tree,logical_snapshot
    from target.rag_store import PolicyIndex
    from target.embeddings import EmbeddingProvider,EmbeddingSettings
    out.mkdir(parents=True,exist_ok=False);before=tree_hashes(BASELINE)
    destination,receipt=copy_workspace(BASELINE,out/'workspaces')
    state=json.loads((destination/'index/manifest.json').read_text(encoding='utf-8'))
    provider=EmbeddingProvider(EmbeddingSettings(base_url=state['endpoint'],dimensions=state['dimensions'],cache=destination/'unused-cache.db'))
    index=PolicyIndex(destination/'index',provider=provider);phases=[];last=tree_hashes(index.path)
    def capture(name):
        nonlocal last
        current=tree_hashes(index.path)
        phases.append({'phase':name,'changed_files':[p for p in sorted(set(last)|set(current)) if last.get(p)!=current.get(p)],
                       'tree_sha256':hash_tree(current),'wal_files':[p for p in current if p.endswith(('-wal','-shm'))]})
        last=current
    with patch.object(EmbeddingProvider,'_request',side_effect=AssertionError('No embedding authorization')),patch.object(PolicyIndex,'build',side_effect=AssertionError('No rebuild authorized')):
        client=index.client();capture('client_initialization')
        collection=client.get_collection(state['collection'],embedding_function=None);capture('get_collection')
        rows=collection.get(include=['documents','metadatas','embeddings']);capture('read_documents_metadata_vectors')
        first=logical_snapshot(index);capture('logical_validation')
        collection.query(query_embeddings=[[float(x) for x in rows['embeddings'][0]]],n_results=3,include=['documents','metadatas','distances'])
        capture('query_cached_vector')
        second=logical_snapshot(index);capture('second_logical_validation')
        client._system.stop();capture('client_close')
    db=index.path/'chroma.sqlite3'
    with sqlite3.connect(str(db)) as connection:
        sqlite={'journal_mode':connection.execute('PRAGMA journal_mode').fetchone()[0],
                'schema_version':connection.execute('PRAGMA schema_version').fetchone()[0],
                'user_version':connection.execute('PRAGMA user_version').fetchone()[0],
                'page_count':connection.execute('PRAGMA page_count').fetchone()[0],
                'wal_checkpoint_passive_result':list(connection.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone())}
    capture('explicit_checkpoint_copy_only')
    after=tree_hashes(BASELINE)
    result={'schema':'ticket-v352-chroma-forensics/1','source_unchanged':before==after,
        'source_tree_sha256':hash_tree(before),'source_files_before':before,'source_files_after':after,
        'copy_phases':phases,'copy_sqlite':sqlite,'logical_before':first,'logical_after':second,
        'logical_equal':first==second,'rebuild_calls':0,'real_embedding_requests':0,'real_generation_requests':0,
        'original_restored':False,'previous_incident':'docs/evidence/v351/chroma-retention-incident.json',
        'conclusion':'Observed phase writes concern only the copy. This does not retrospectively identify the exact historical writer.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('source_unchanged','logical_equal','rebuild_calls','real_embedding_requests')}))
    return 0 if result['source_unchanged'] and result['logical_equal'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts/runtime'):raise ValueError('isolated_output_required')
    return audit(out)


if __name__=='__main__':raise SystemExit(main())
