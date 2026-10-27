"""Regression for an actual Qwen clarification without fabricating stock."""
import unittest
import json
from pathlib import Path
import contextlib
import io
import os
import socket
import tempfile
import importlib.util
from unittest.mock import patch

from target.reply_consistency import check
from target.rag_faithfulness import check_answer

RECORDED = json.loads((Path(__file__).parent / 'fixtures/ticket_buy_clarification.json').read_text(encoding='utf-8'))
PURCHASE_ADVICE = json.loads((Path(__file__).parent / 'fixtures/ticket_purchase_advice.json').read_text(encoding='utf-8'))


class ClarificationOfferTests(unittest.TestCase):
    def test_recorded_official_channel_advice_is_not_a_ticket_claim(self):
        result = check(PURCHASE_ADVICE['reply'], [])
        self.assertEqual(result['status'], 'not_verified', result)
        self.assertFalse(result['indeterminate'])

    def test_purchase_advice_does_not_hide_unverified_ticket_claims(self):
        advice = '如果您想购买明天（2026-10-28）上海到杭州的高铁二等座，建议通过 12306 官方 App 或网站办理'
        for claim in ('，目前有23张余票', '，G9999有余票', '，票价73元', '，已经下单成功'):
            with self.subTest(claim=claim):
                self.assertEqual(check(advice + claim, [])['status'], 'indeterminate')
        self.assertEqual(check('G9999有余票。' + advice, [])['status'], 'indeterminate')

    def test_actual_reply_passes_both_scoped_guards_without_claiming_full_fidelity(self):
        reply, events = RECORDED['reply'], RECORDED['events']
        self.assertEqual(check(reply, events)['status'], 'not_verified')
        rag = check_answer(reply, [], events=events, question='我要怎么买票')
        self.assertNotEqual(rag['status'], 'failed', rag['findings'])
        self.assertNotEqual(rag['full_semantic_faithfulness'], 'pass')

    def test_date_example_cannot_hide_policy_numbers(self):
        reply = '2. 乘车/乘机日期（如"11月3日"），手续费必须收取30元。'
        result = check_answer(reply, [], question='我要怎么买票')
        self.assertEqual(result['status'], 'failed')

    def test_future_simulated_query_is_not_a_stock_assertion(self):
        reply = '如果您愿意，可以告诉我以下信息，我先帮您模拟查一下有没有余票，供您参考：'
        result = check(reply, [])
        self.assertNotEqual(result['status'], 'indeterminate', result)
        self.assertEqual(result['status'], 'not_verified')

    def test_offer_never_hides_concrete_or_completed_claims(self):
        offer = '如果您愿意，可以告诉我以下信息，我先帮您模拟查一下有没有余票，供您参考'
        for extra in ('，目前有23张余票', '，G9999有余票', '，已经查询成功', '，二等座有余票'):
            with self.subTest(extra=extra):
                self.assertEqual(check(offer + extra, [])['status'], 'indeterminate')
        self.assertEqual(check('G9999有余票。' + offer, [])['status'], 'indeterminate')

    @unittest.skipUnless(all(importlib.util.find_spec(x) for x in ('httpx', 'langchain_openai', 'langchain_deepseek')),
                         'Full model SDK dependencies required for offline transport test')
    def test_agent_policy_round_trip_with_offline_http_stub(self):
        import config
        import httpx
        from data.seed import build_db
        from target import bailian_runtime
        from target.agent import Agent
        sent = []
        call = {'id': 'policy-test', 'type': 'function', 'function': {
            'name': 'search_policy', 'arguments': json.dumps({'question': '怎么买票？'})}}
        def respond(request):
            sent.append(json.loads(request.content))
            if len(sent) > 2:
                raise AssertionError('unexpected extra request')
            msg = {'content': None, 'tool_calls': [call]} if len(sent) == 1 else {'content': RECORDED['reply']}
            return httpx.Response(200, json={'id': 'offline-fixture', 'object': 'chat.completion',
                'created': 1, 'model': 'qwen3.8-flash', 'choices': [{'index': 0,
                'message': {'role': 'assistant', **msg}, 'finish_reason': 'tool_calls' if len(sent) == 1 else 'stop'}],
                'usage': {'prompt_tokens': 13, 'completion_tokens': 5, 'total_tokens': 18}})
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            env = {'DASHSCOPE_API_KEY': 'offline-fixture', 'DASHSCOPE_MODEL': 'qwen3.8-flash',
                'DASHSCOPE_BASE_URL': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'BAILIAN_MAX_MODEL_CALLS': '2',
                'AGENT_RAG_MODE': 'keyword', 'RAG_ALLOW_NETWORK': '0', 'RAG_QUALITY_PROFILE': 'v351',
                'LANGCHAIN_TRACING_V2': 'false', 'LANGSMITH_TRACING': 'false',
                'TICKET_DISABLE_LOCAL_SECRETS': '1', 'TICKET_API_USAGE_DIR': str(folder / 'usage')}
            cfg = {'PROVIDER': 'bailian', 'ENGINE': 'langchain', 'LC_TOOLSET': 'read_only',
                'MODEL_NAME': 'qwen3.8-flash', 'BASE_URL': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'API_KEY': 'offline-fixture', 'DB_PATH': folder / 'tickets.db',
                'TRACE_DIR': folder / 'traces', 'USE_HTTP_MOCK': False, 'USE_VECTOR_RAG': False, 'MAX_STEPS': 2}
            with patch.dict(os.environ, env), patch.multiple(config, **cfg), \
                    patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')):
                with contextlib.redirect_stdout(io.StringIO()):
                    build_db()
                model = bailian_runtime.make_model(bailian_runtime.Settings.from_env(), transport=httpx.MockTransport(respond))
                try:
                    agent = Agent(model=model)
                    result = agent.chat('clarification-offline', '我要怎么买票')
                    self.assertEqual(result['reply'], RECORDED['reply'])
                    self.assertEqual(result['tool_sequence'], ['search_policy'])
                    self.assertEqual(len(sent), 2)
                    self.assertTrue(agent.last_audit_report['contract_returned'])
                finally:
                    model.client._client.close()


if __name__ == '__main__':
    unittest.main()
