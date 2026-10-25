"""Both actual SDK adapters + real Agent/search_policy; model HTTP is MockTransport."""
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
try:
    import test_deepseek_agent as deep
    import test_live_providers as qwen
    SDK=deep.AVAILABLE and qwen.AVAILABLE
except ImportError:SDK=False


@unittest.skipUnless(SDK,'full SDK environment required; zero paid requests')
class AgentRagTests(unittest.TestCase):
    def run_case(self,provider,wrong):
        import config
        from target.deepseek_runtime import DeepSeekError
        fixture=(deep.DeepSeekAgentTests if provider=='deepseek' else qwen.LiveProviderTests)()
        with contextlib.redirect_stdout(io.StringIO()):fixture.setUp()
        try:
            reply='模拟锁座有效期15分钟，来源 '+('P99' if wrong else 'P11')+'。'
            with patch.dict(os.environ,{'AGENT_RAG_MODE':'keyword','RAG_ALLOW_NETWORK':'0'}),patch('target.embeddings.EmbeddingProvider._request') as embedding:
                agent=fixture.agent([fixture.response({'content':None,'tool_calls':[fixture.call('search_policy',{'question':'锁座后多久必须完成支付？'})]}),
                                     fixture.response({'content':reply})])
                if wrong:
                    with self.assertRaisesRegex(DeepSeekError,'rag_wrong_citation'):agent.chat('v35-policy','解释锁座有效期')
                else:
                    result=agent.chat('v35-policy','解释锁座有效期')
                    self.assertEqual(result['tool_sequence'],['search_policy']);self.assertEqual(len(result),10)
                    self.assertEqual(len(result['steps'][0]['calls'][0]),5)
                records=[json.loads(s) for s in (config.TRACE_DIR/'rag_runs.jsonl').read_text(encoding='utf-8').splitlines()]
                retrieval=next(r for r in records if r['schema']=='ticket-rag-retrieval/1')
                answer=next(r for r in records if r['schema']=='ticket-rag-answer/1')
                self.assertEqual(retrieval['trace_id'],agent.langchain_engine.last_live_run['trace_id'])
                self.assertEqual(answer['original_model_reply'],reply)
                self.assertIn('P11',[h['doc_id'] for h in retrieval['hits']])
                self.assertEqual(answer['wrong_citations'],['P99'] if wrong else [])
                embedding.assert_not_called();self.assertEqual(len(fixture.payloads),2)
        finally:fixture.tearDown()


def case(provider,wrong):
    def run(self):self.run_case(provider,wrong)
    return run


for _p in ('deepseek','qwen'):
    for _w in (False,True):setattr(AgentRagTests,'test_'+_p+('_wrong_citation' if _w else '_rag_trace_contract'),case(_p,_w))
