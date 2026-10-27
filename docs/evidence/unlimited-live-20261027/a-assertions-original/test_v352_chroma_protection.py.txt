"""Actual local Chroma on UUID copies; no remote model or embedding calls."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

CHROMA=importlib.util.find_spec('chromadb') is not None


@unittest.skipUnless(CHROMA,'Chroma installed in V3.5 environment only')
class ChromaProtectionTests(unittest.TestCase):
    def setUp(self):
        import httpx
        from target.embeddings import EmbeddingProvider,EmbeddingSettings
        from target.rag_store import PolicyIndex
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.root=Path(self.tmp.name)
        self.source=self.root/'immutable';self.env=patch.dict(os.environ,{'DASHSCOPE_API_KEY':'offline-v352-chroma-stub'})
        self.env.start()
        def response(request):
            body=json.loads(request.content);rows=[]
            for n,text in enumerate(body['input']):
                v=[0.0]*64;v[0 if '锁座' in text else 1]=1.0;rows.append({'index':n,'embedding':v})
            return httpx.Response(200,json={'data':rows,'model':'text-embedding-v4','usage':{'total_tokens':1}})
        self.provider=EmbeddingProvider(EmbeddingSettings(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',dimensions=64,
            cache=self.root/'cache.db',ledger=self.root/'stub.db'),transport=httpx.MockTransport(response))
        self.index=PolicyIndex(self.source,provider=self.provider);self.index.build(allow_network=True)
        self.provider.embed_many(['锁座支付'],allow_network=True);self.index.client()._system.stop()

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def test_direct_baseline_open_and_rebuild_rejected_before_embedding(self):
        from target.rag_store import RagError
        with patch('target.rag_protection.BASELINE',self.source),patch.object(self.provider,'embed_many') as embed:
            with self.assertRaisesRegex(RagError,'immutable_chroma_baseline_open_forbidden'):self.index.client()
            with self.assertRaisesRegex(RagError,'immutable_chroma_baseline_rebuild_forbidden'):self.index.build(allow_network=True,rebuild=True)
            embed.assert_not_called()

    def test_query_status_and_close_leave_source_bytes_unchanged(self):
        from target.rag_protection import ProtectedPolicyIndex,tree_hashes
        before=tree_hashes(self.source);cache=self.provider.settings.cache.read_bytes()
        safe=ProtectedPolicyIndex(self.source,provider=self.provider,parent=self.root/'work')
        status=safe.status();self.assertEqual(status['state'],'ready')
        result=safe.retrieve('锁座支付','vector',require_real=False,allow_network=False,quality_profile='v351')
        self.assertEqual(result['hits'][0]['doc_id'],'P11');self.assertTrue(result['index_protection']['opened_working_copy_only'])
        self.assertEqual(tree_hashes(self.source),before);self.assertEqual(self.provider.settings.cache.read_bytes(),cache)
        self.assertEqual(len(list((self.root/'work').iterdir())),2)

    def test_parallel_tasks_have_distinct_workspaces_and_same_logical_data(self):
        from target.rag_protection import working_index,logical_snapshot,tree_hashes
        before=tree_hashes(self.source)
        def task(_):
            with working_index(self.source,self.provider,parent=self.root/'parallel') as (index,receipt):
                result=logical_snapshot(index,require_real=False)
                return receipt['workspace_id'],result['logical_sha256']
        with ThreadPoolExecutor(max_workers=2) as executor:rows=list(executor.map(task,range(2)))
        self.assertNotEqual(rows[0][0],rows[1][0]);self.assertEqual(rows[0][1],rows[1][1])
        self.assertEqual(tree_hashes(self.source),before)

    def test_baseline_wrapper_does_not_allow_network_or_rebuild(self):
        from target.rag_protection import ProtectedPolicyIndex
        from target.rag_store import RagError
        safe=ProtectedPolicyIndex(self.source,provider=self.provider,parent=self.root/'blocked')
        with self.assertRaisesRegex(RagError,'cache_only'):safe.retrieve('uncached',allow_network=True)
        with self.assertRaisesRegex(RagError,'rebuild_forbidden'):safe.build(allow_network=True)
        self.assertFalse((self.root/'blocked').exists())

    def test_modification_of_working_index_is_not_source_modification(self):
        from target.rag_protection import working_index,tree_hashes
        before=tree_hashes(self.source)
        with working_index(self.source,self.provider,parent=self.root/'modified') as (index,receipt):
            (index.path/'test-working-only').write_text('isolated',encoding='utf-8')
        self.assertTrue(receipt['source_unchanged']);self.assertTrue(receipt['working_files_changed'])
        self.assertEqual(tree_hashes(self.source),before)


class CopyRulesTests(unittest.TestCase):
    def test_reject_destination_inside_source(self):
        from target.rag_protection import copy_workspace
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            with self.assertRaisesRegex(ValueError,'inside_immutable'):copy_workspace(p,p/'nested')
