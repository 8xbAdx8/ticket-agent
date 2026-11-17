import unittest
from target.rag_service import citation_check

class MissingCitationLiveRegression(unittest.TestCase):
    def test_no_doc_id_never_crashes_or_fakes_valid_citation(self):
        reply='根据政策知识库（doc_id：43aea1ebf3c7b333）：模拟锁座有效期为 15 分钟。'
        hits=[{'title':'锁座与支付有效期','version':'43aea1ebf3c7b333','content':'模拟锁座有效期 15 分钟。'}]
        result=citation_check(reply,hits)
        self.assertEqual(result['allowed_doc_ids'],[])
        self.assertEqual(result['citation_status'],'failed')
        self.assertEqual(result['wrong_citations'],['43aea1ebf3c7b333'])
        self.assertEqual(result['faithfulness'],'indeterminate')
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from target.rag_service import attach_answer

class MissingCitationEndToEndRegression(unittest.TestCase):
    def test_policy_answer_with_missing_doc_id_keeps_unknown(self):
        trace=SimpleNamespace(trace_id='missing-citation',session_id='test',provider='deepseek',model='deepseek-flash',user_msg='锁座后多久支付？')
        events=[{'event':'tool_end','tool':'search_policy','ok':True,'result':{'hits':[{'title':'锁座与支付有效期','version':'43aea1ebf3c7b333','content':'模拟锁座有效期 15 分钟。'}]}}]
        with TemporaryDirectory() as temp, patch('config.TRACE_DIR',Path(temp)):
            result=attach_answer(trace,events,'根据政策知识库（doc_id：43aea1ebf3c7b333）：模拟锁座有效期为 15 分钟。')
        self.assertEqual(result['citation_status'],'failed')
        self.assertEqual(result['wrong_citations'],['43aea1ebf3c7b333'])
        self.assertNotEqual(result['faithfulness'],'pass')
from target.rag_faithfulness import check_answer

class OutOfScopeRefusalRegression(unittest.TestCase):
    def test_future_capability_list_is_not_a_policy_fact(self):
        reply='我没有检索到相关条目，无法给出天数答案。\n\n如果您有实际出行需求，我可以帮您：\n- 查询某日两地间的高铁/航班余票与票价；\n- 解答火车票政策问题。'
        result=check_answer(reply,[],question='火星需要几天隔离？')
        self.assertNotIn('no_evidence_positive_claim',[x['type'] for x in result['findings']])
        self.assertNotEqual(result['full_semantic_faithfulness'],'pass')
    def test_actual_unfounded_policy_fact_is_not_exempted(self):
        reply='我可以帮您：\n- 查询某日两地间的余票与票价，手续费必须收取 30 元。'
        result=check_answer(reply,[],question='火星政策？')
        self.assertIn('no_evidence_positive_claim',[x['type'] for x in result['findings']])
