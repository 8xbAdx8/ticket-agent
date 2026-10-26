"""Regression must not open original writable Chroma/cache paths."""
from pathlib import Path
import tempfile
import unittest
from scripts.verify_v351_offline import isolated_rag_inputs


class RegressionIsolationTests(unittest.TestCase):
    def test_copies_index_and_cache_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);normal=root/'artifacts/runtime/v35-rag';index=normal/'index';index.mkdir(parents=True)
            (index/'chroma.sqlite3').write_bytes(b'original-index');(normal/'embedding-cache.db').write_bytes(b'original-cache')
            env=isolated_rag_inputs(root,root/'evidence')
            Path(env['RAG_INDEX_DIR'],'chroma.sqlite3').write_bytes(b'read-persistence')
            Path(env['RAG_EMBEDDING_CACHE']).write_bytes(b'new-cache')
            self.assertEqual((index/'chroma.sqlite3').read_bytes(),b'original-index')
            self.assertEqual((normal/'embedding-cache.db').read_bytes(),b'original-cache')

    def test_clean_clone_missing_index_is_not_replaced_by_fake_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env=isolated_rag_inputs(root,root/'new-evidence')
            self.assertFalse(Path(env['RAG_INDEX_DIR']).exists())
            self.assertFalse(Path(env['RAG_EMBEDDING_CACHE']).exists())
