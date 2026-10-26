"""Frozen deterministic cases; no provider client, credentials, or network needed."""
import copy
import json
from pathlib import Path
import unittest

from target.rag_faithfulness import check_answer

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=json.loads((ROOT/'cases/rag_faithfulness_v351.json').read_text(encoding='utf-8'))['cases']


class FaithfulnessCases(unittest.TestCase):
    def run_case(self,case):
        preserved=copy.deepcopy(case)
        result=check_answer(case['reply'],case['hits'],events=case['events'],question=case['input'])
        self.assertEqual(result['status']=='failed',case['expected']['failed'],case['id']+': '+json.dumps(result,ensure_ascii=False))
        self.assertEqual(result['original_model_reply'],case['reply'])
        self.assertEqual(result['full_semantic_faithfulness'],'indeterminate')
        actual={f['type'] for f in result['findings']}
        self.assertTrue(set(case['expected']['finding_types'])<=actual,(case['id'],actual))
        self.assertEqual(case,preserved)


def fixture_test(case):
    def run(self):self.run_case(case)
    return run


for _case in FIXTURES:
    setattr(FaithfulnessCases,'test_'+_case['id'],fixture_test(_case))


class FaithfulnessScopes(unittest.TestCase):
    def test_full_semantics_never_inferred_from_valid_ids(self):
        result=check_answer('提前付款更稳妥 [P11]。',[{'doc_id':'P11','content':'锁座有效期15分钟。'}])
        self.assertEqual(result['status'],'indeterminate')
        self.assertEqual(result['full_semantic_faithfulness'],'indeterminate')

    def test_unknown_conditions_remain_manual(self):
        case=next(c for c in FIXTURES if c['id']=='F08')
        result=check_answer(case['reply'],case['hits'])
        self.assertEqual(result['status'],'indeterminate')
        self.assertTrue(result['manual_review'])

    def test_same_evidence_same_rules_across_provider_labels(self):
        case=next(c for c in FIXTURES if c['id']=='F05')
        # Provider is deliberately absent from the API. Compare deep copies,
        # rather than treating model identity as an accuracy shortcut.
        deep=check_answer(case['reply'],copy.deepcopy(case['hits']))
        qwen=check_answer(case['reply'],copy.deepcopy(case['hits']))
        self.assertEqual(deep,qwen)


if __name__=='__main__':unittest.main()
