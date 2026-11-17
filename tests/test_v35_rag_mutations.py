"""Eight real isolated Chroma experiments with explicit offline embedding stubs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from target.rag_faults import NAMES,run_experiment,evidence_risks
from target.rag_store import ROOT


@unittest.skipUnless(importlib.util.find_spec('chromadb') is not None,'Chroma experiments require .venv-v35')
class MutationTests(unittest.TestCase):
    pass


def mutation_test(name):
    def run(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/runtime',prefix='v35-fault-',ignore_cleanup_errors=True) as folder:
            r=run_experiment(name,Path(folder)/'experiment')
            self.assertTrue(r['executed']);self.assertTrue(r['passed'],r['judgement'])
            self.assertEqual(r['embedding_origin'],'offline_stub');self.assertEqual(r['real_api_requests'],0)
            self.assertFalse(r['normal_index_modified']);self.assertTrue(r['before']['hits'])
            self.assertEqual(json.loads((Path(folder)/'experiment/record.json').read_text(encoding='utf-8'))['mutation'],name)
    return run


for _name in NAMES:setattr(MutationTests,'test_'+_name,mutation_test(_name))


class EvidenceRiskTests(unittest.TestCase):
    def test_normal_policy_not_flagged_and_tests_are_detectable(self):
        normal=[{'doc_id':'P11','content':'模拟锁座有效期15分钟。'}]
        self.assertEqual(evidence_risks(normal),[])
        self.assertTrue(evidence_risks(normal+[{'doc_id':'P90','content':'锁座有效期60分钟。'}]))
