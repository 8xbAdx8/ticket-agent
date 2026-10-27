"""A-owned regressions: immutable historical replies and SDK MockTransport only."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from target.reply_consistency import check

ROOT = Path(__file__).resolve().parent.parent
HISTORY = json.loads((ROOT / 'tests/fixtures/trace_quality_history.json').read_text(encoding='utf-8'))['records']


class HistoricalParserTests(unittest.TestCase):
    def test_both_real_clarifications_have_no_unverifiable_ticket_claim(self):
        for row in HISTORY:
            if row['user_msg'] != '妈妈':
                continue
            with self.subTest(trace_id=row['trace_id']):
                before = copy.deepcopy(row)
                verdict = check(row['raw_model_reply'], row['events'])
                self.assertEqual(verdict['status'], 'not_verified')
                self.assertEqual(verdict['indeterminate'], [])
                self.assertEqual(verdict['identity_checks'], 0)
                self.assertEqual(row, before)

    def test_original_train_response_25_fields_already_match_current_code(self):
        row = next(r for r in HISTORY if r['user_msg'] != '妈妈')
        verdict = check(row['raw_model_reply'], row['events'])
        self.assertEqual(verdict['status'], 'checked_fields_match')
        self.assertEqual(verdict['checked_fields'], 25)
        self.assertEqual(verdict['identity_checks'], 3)
        self.assertFalse(verdict['findings'])
        self.assertFalse(verdict['indeterminate'])

    def test_quoted_invented_ticket_fact_is_still_blocked(self):
        authority=next(r['events'] for r in HISTORY if r['user_msg'] != '妈妈')
        self.assertEqual(check('查询结果为“G9999 出发05:00”。', authority)['status'], 'failed')
        self.assertEqual(check('“G9999 出发05:00”', authority)['status'], 'indeterminate')

    def test_user_attribution_does_not_hide_a_later_quoted_result(self):
        authority=next(r['events'] for r in HISTORY if r['user_msg'] != '妈妈')
        verdict = check('您输入的“妈妈”，查询结果为“G9999 出发05:00”。', authority)
        self.assertEqual(verdict['status'], 'failed')
        self.assertEqual(verdict['findings'][0]['field'], 'train_no')

    def test_non_ticket_quotes_and_sample_questions_are_not_ticket_assertions(self):
        for reply in ('您发的“妈妈”是什么意思？', '请补充路线（如“下周三北京到上海的高铁”）。',
                      '您好，“谢谢”已收到，请补充出发地。'):
            self.assertEqual(check(reply, [])['status'], 'not_verified')


class QualityEvidenceTests(unittest.TestCase):
    def evaluate(self, *, error=None, executions=None, raw='请补充出发地和日期。'):
        from target.diagnostics import evaluate
        return evaluate({'session_id': 'S', 'user_msg': '妈妈', 'reply': '请求未完成。', 'finish_reason': 'stop'},
                        {'model_requests': [], 'executions': executions or []},
                        {'available': True, 'trains': ['G7301'], 'orders': []}, error=error, raw_model_reply=raw)

    def test_successful_zero_tool_clarification_is_not_failed_or_business_pass(self):
        result = self.evaluate()
        self.assertEqual(result['quality_verdict'], 'indeterminate')
        self.assertEqual(result['failure_reasons'], [])
        self.assertIsNone(result['dimensions']['business_correct'])

    def test_uncertain_reply_has_reason_and_is_not_a_confirmed_failure(self):
        result = self.evaluate(error={'category': 'reply_data_indeterminate', 'http_status': None})
        self.assertEqual(result['quality_verdict'], 'indeterminate')
        self.assertTrue(any('reply_data_indeterminate' in r for r in result['indeterminate_reasons']))
        self.assertEqual(result['failure_reasons'], [])

    def test_runtime_failure_always_has_an_explicit_reason(self):
        for category in ('timeout', 'authentication_failed', 'request_budget_exhausted', 'token_usage_unknown'):
            result = self.evaluate(error={'category': category, 'http_status': None})
            self.assertEqual(result['quality_verdict'], 'fail')
            self.assertTrue(any(category in r for r in result['failure_reasons']))

    def test_backend_error_is_not_an_empty_failure(self):
        result = self.evaluate(executions=[{'tool': 'query_tickets', 'ok': False, 'executed': False}])
        self.assertEqual(result['quality_verdict'], 'fail')
        self.assertTrue(any('query_tickets' in r for r in result['failure_reasons']))

    def test_raw_answer_is_checked_even_if_failure_placeholder_hides_it(self):
        result = self.evaluate(error={'category': 'reply_tool_mismatch'}, raw='查到G9999有票。')
        self.assertEqual(result['quality_verdict'], 'fail')
        self.assertTrue(result['hallucination']['hallucination_detected'])

    def test_historical_error_placeholder_is_not_labelled_a_returned_answer(self):
        from web.trace_view import timeline_items
        row = next(r for r in HISTORY if r['trace_id'] == 'cbe8c088462046d99e49f322136c47d1')
        audit = {'public_trace': row['original_public_trace'], 'contract_returned': False,
                 'raw_model_reply': row['raw_model_reply'], 'error': {'category': 'reply_data_indeterminate'}}
        timeline = timeline_items(audit)
        self.assertIn('模型原始回复', [r['kind'] for r in timeline])
        self.assertIn('错误占位记录', [r['kind'] for r in timeline])
        self.assertNotIn('最终回复', [r['kind'] for r in timeline])


class TokenEvidenceTests(unittest.TestCase):
    def test_complete_usage_is_independent_of_later_validation_failure(self):
        from target.live_evidence import token_summary
        events=[{'event':'http_request'}, {'event':'model_response','usage':{'input_tokens':1412,'output_tokens':81}},
                {'event':'agent_error','category':'reply_data_indeterminate'}]
        result=token_summary(events)
        self.assertEqual(result['token_usage_status'],'complete')
        self.assertEqual(result['tokens'],{'prompt':1412,'completion':81})

    def test_second_request_timeout_preserves_partial_usage_without_fabricated_total(self):
        from target.live_evidence import token_summary
        events=[{'event':'http_request'}, {'event':'model_response','usage':{'input_tokens':13,'output_tokens':5}},
                {'event':'http_request'}, {'event':'http_error','category':'timeout'}]
        result=token_summary(events)
        self.assertEqual(result['token_usage_status'],'partial')
        self.assertIsNone(result['tokens'])
        self.assertEqual(result['observed_tokens'],{'prompt':13,'completion':5})

    def test_missing_second_usage_does_not_claim_complete(self):
        from target.live_evidence import token_summary
        result=token_summary([{'event':'model_response','usage':{'input_tokens':13,'output_tokens':5}},
                              {'event':'model_response','usage':{}}])
        self.assertEqual(result['token_usage_status'],'partial')
        self.assertIsNone(result['tokens'])

    def test_no_response_is_unknown_and_explicitly_reported_zero_is_preserved(self):
        from target.live_evidence import token_summary
        self.assertEqual(token_summary([])['token_usage_status'],'unknown')
        result=token_summary([{'event':'model_response','usage':{'input_tokens':0,'output_tokens':0}}])
        self.assertEqual(result['token_usage_status'],'complete')
        self.assertEqual(result['tokens'],{'prompt':0,'completion':0})


try:
    import test_deepseek_agent as deep_fixture
    import test_live_providers as bailian_fixture
    SDK = deep_fixture.AVAILABLE and bailian_fixture.AVAILABLE
except ImportError:
    SDK = False


@unittest.skipUnless(SDK, 'full SDK environment required; all requests use offline MockTransport')
class ProviderReplyTests(unittest.TestCase):
    def run_scenario(self, provider, scenario):
        import contextlib
        import io
        import config
        from target.deepseek_runtime import DeepSeekError
        cls = deep_fixture.DeepSeekAgentTests if provider == 'deepseek' else bailian_fixture.LiveProviderTests
        fixture = cls()
        with contextlib.redirect_stdout(io.StringIO()):
            fixture.setUp()
        try:
            historical = next(r for r in HISTORY if r['trace_id'] == 'cbe8c088462046d99e49f322136c47d1')
            reply = historical['raw_model_reply']
            if scenario == 'uncertain':
                reply = 'G7301 和 G7303 出发06:00。'
            elif scenario == 'mismatch':
                reply = '查询结果为“G9999 出发05:00”。'
            elif scenario == 'timeout':
                import httpx
                reply = None
                response = httpx.ReadTimeout('offline-timeout')
            elif scenario == 'bad_usage':
                reply = '请补充出发地。'
            if scenario != 'timeout':
                response = fixture.response({'content': reply}, usage=scenario != 'bad_usage')
            responses=[response]
            if scenario == 'mismatch':
                from datetime import timedelta
                args={'from_city':'上海','to_city':'杭州','date':(config.today()+timedelta(days=1)).isoformat(),
                      'kind':'高铁','seat_type':'二等座'}
                responses.insert(0,fixture.response({'content':None,'tool_calls':[fixture.call('query_tickets',args)]}))
            agent = fixture.agent(responses)
            if scenario in ('clarification','web'):
                if scenario=='web':
                    from web.runtime import Conversation
                    from streamlit.testing.v1 import AppTest
                    import uuid
                    session=Conversation('user',engine='langchain',live=True,live_provider=provider,
                                         root=ROOT/'artifacts/runtime'/('trace-ui-'+uuid.uuid4().hex),sid='mom')
                    session.agent=agent
                    with patch('web.runtime.live_ready',return_value=True),patch.object(session,'_values',return_value={}):
                        result=session.send('妈妈','isolated-web-request')
                    self.assertIsNone(session.error)
                    self.assertEqual(session.history,[result])
                    app=AppTest.from_string('from web.conversation import user_page\nuser_page()')
                    for name,value in {'user_sessions':[session],'default_engine':'langchain','default_live':True,
                                       'default_provider':provider,'default_live_model':None,
                                       'user_provider_signature':('langchain',True,provider,None,'manual-live-v1')}.items():
                        app.session_state[name]=value
                    with patch.dict('os.environ',{'TICKET_LANGSMITH_EXPORT_ENABLED':'false'}):
                        app.run(timeout=15)
                    self.assertFalse(app.exception)
                    self.assertFalse(app.error)
                    self.assertTrue(any(reply in item.value for item in app.markdown))
                else:
                    result = agent.chat('mom', '妈妈')
                self.assertEqual(result['reply'], reply)
                self.assertEqual(result['tool_sequence'], [])
                self.assertEqual(result['finish_reason'], 'stop')
                self.assertEqual(len(result), 10)
                self.assertEqual(agent.last_audit_report['judgement']['quality_verdict'], 'indeterminate')
                self.assertTrue(agent.last_audit_report['contract_returned'])
                self.assertTrue((config.TRACE_DIR / 'traces.jsonl').exists())
            else:
                category = {'uncertain': 'reply_data_indeterminate', 'mismatch': 'reply_tool_mismatch',
                            'timeout': 'timeout', 'bad_usage': 'token_usage_unknown'}[scenario]
                with self.assertRaisesRegex(DeepSeekError, category):
                    agent.chat('error', '查高铁')
                audit = agent.last_audit_report
                self.assertEqual(audit['error']['category'], category)
                self.assertFalse(audit['contract_returned'])
                self.assertFalse((config.TRACE_DIR / 'traces.jsonl').exists())
                self.assertTrue(any(e.get('event') == 'agent_error' and e['category'] == category
                                    for e in audit['framework_events']))
                self.assertIn(category, audit['public_trace']['reply'] if scenario in ('timeout', 'bad_usage')
                              else json.dumps(audit['error']))
                if scenario in ('uncertain', 'mismatch'):
                    self.assertEqual(audit['token_usage_evidence']['status'], 'reported')
                    self.assertEqual(audit['token_usage_evidence']['completeness'], 'complete')
                    self.assertNotIn('Token 用量可能未知', audit['public_trace']['reply'])
                    self.assertEqual(audit['raw_model_reply'], reply)
                    if provider=='deepseek':
                        saved=json.loads((config.TRACE_DIR/'deepseek_runs.jsonl').read_text(encoding='utf-8').splitlines()[-1])
                        self.assertEqual(saved['token_usage_status'],'complete')
                        self.assertEqual(saved['tokens'],agent.langchain_engine.last_live_run['tokens'])
                else:
                    self.assertEqual(audit['token_usage_evidence']['status'], 'unknown_or_partial')
                    self.assertIsNone(audit['token_usage_evidence']['reported'])
                quality = audit['judgement']
                self.assertEqual(quality['quality_verdict'], 'indeterminate' if scenario == 'uncertain' else 'fail')
                self.assertTrue(quality['indeterminate_reasons'] if scenario == 'uncertain' else quality['failure_reasons'])
            self.assertEqual(len(fixture.payloads), 2 if scenario == 'mismatch' else 1)  # No automatic retries.
            live = agent.langchain_engine.last_live_run
            if scenario == 'mismatch':
                self.assertTrue(live['tool_execution_success'])
            else:
                self.assertIsNone(live['tool_execution_success'])  # No request is not a failed tool call.
            self.assertEqual(live['token_usage_status'], 'complete' if scenario not in ('timeout', 'bad_usage') else 'unknown')
        finally:
            fixture.tearDown()


def provider_test(provider, scenario):
    def run(self):
        self.run_scenario(provider, scenario)
    return run


for _provider in ('deepseek', 'bailian'):
    for _scenario in ('clarification', 'web', 'uncertain', 'mismatch', 'timeout', 'bad_usage'):
        setattr(ProviderReplyTests, 'test_' + _provider + '_' + _scenario, provider_test(_provider, _scenario))
