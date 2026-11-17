"""A-owned answer-integrity regression. Every SDK request uses MockTransport."""
import copy
import json
from pathlib import Path
import unittest

from target.reply_consistency import check, failure_notice

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT/'tests/fixtures/v341_reply_cases.json').read_text(encoding='utf-8'))['cases']


def assert_case(test, case):
    before = copy.deepcopy(case['authority_events'])
    result = check(case['model_output'], case['authority_events'])
    test.assertEqual(result['status'], case['assertion']['status'])
    test.assertEqual(sorted(f['field'] for f in result['findings']), sorted(case['assertion']['finding_fields']))
    reason = case['assertion'].get('indeterminate_reason')
    if reason:
        test.assertIn(reason, [r['reason'] for r in result['indeterminate']])
    test.assertEqual(before, case['authority_events'])
    for f in result['findings']:
        for key in ('field','claimed','tool_values','error_type','line','text','authority_sources'):
            test.assertIn(key, f)
    return result


class FieldCases(unittest.TestCase):
    pass


def fixture_test(case):
    def run(self):
        assert_case(self, case)
    return run


for _case in CASES:
    setattr(FieldCases, 'test_'+_case['id'], fixture_test(_case))


class IntegrityProperties(unittest.TestCase):
    def test_matching_does_not_depend_on_authority_order(self):
        case = copy.deepcopy(next(c for c in CASES if c['id']=='nonpositional_reverse'))
        a = check(case['model_output'],case['authority_events'])
        case['authority_events'][0]['result']['trains'].reverse()
        b = check(case['model_output'],case['authority_events'])
        self.assertEqual(a,b)

    def test_original_four_mismatch_values_and_types(self):
        case = next(c for c in CASES if c['id']=='history_bailian')
        r = assert_case(self,case)
        self.assertEqual([(f['train_no'],f['field'],f['claimed'],f['tool_value']) for f in r['findings']],
                         [('G7303','depart','06:00','12:34'),('G7303','arrive','07:00','13:34'),
                          ('G7301','depart','12:34','06:00'),('G7301','arrive','13:34','07:00')])
        self.assertEqual([f['error_type'] for f in r['findings']],
                         ['departure_time_mismatch','arrival_time_mismatch']*2)

    def test_all_nine_fields_have_explicit_check_evidence(self):
        r=assert_case(self,next(c for c in CASES if c['id']=='all_nine_fields'))
        self.assertEqual({c['field'] for c in r['field_checks']},
                         {'train_no','from_city','to_city','date','depart','arrive','seat_type','price','seats_left'})
        self.assertEqual(r['checked_fields'],8)
        self.assertEqual(r['identity_checks'],1)

    def test_clear_safe_fallback_without_rewriting_reply(self):
        self.assertIn('不一致',failure_notice('reply_tool_mismatch'))
        self.assertIn('无法可靠核验',failure_notice('reply_data_indeterminate'))
        self.assertIsNone(failure_notice('other_error'))


try:
    import test_deepseek_agent as deep_fixtures
    import test_live_providers as bailian_fixtures
    SDK = deep_fixtures.AVAILABLE and bailian_fixtures.AVAILABLE
except ImportError:
    SDK=False


@unittest.skipUnless(SDK,'full Live SDK environment required; offline stubs only')
class ProviderIntegration(unittest.TestCase):
    def run_provider(self, provider, mode):
        import contextlib
        import io
        from datetime import timedelta
        import config
        from target.deepseek_runtime import DeepSeekError
        cls = deep_fixtures.DeepSeekAgentTests if provider=='deepseek' else bailian_fixtures.LiveProviderTests
        fixture=cls()
        with contextlib.redirect_stdout(io.StringIO()):
            fixture.setUp()
        try:
            args={'from_city':'上海','to_city':'杭州','date':(config.today()+timedelta(days=1)).isoformat(),
                  'kind':'高铁','seat_type':'二等座'}
            reply={'match':'G7301 出发06:00，到达07:00，票价73元。',
                   'mismatch':'G7301 出发05:01，票价9999元。',
                   'uncertain':'G7301 和 G7303 出发06:00。'}[mode]
            agent=fixture.agent([fixture.response({'content':None,'tool_calls':[fixture.call('query_tickets',args)]}),
                                 fixture.response({'content':reply})])
            if mode=='match':
                result=agent.chat('isolated-v341','请查询模拟高铁。')
                self.assertEqual(result['reply'],reply)
                self.assertEqual(len(result),10)
                self.assertEqual(len(result['steps'][0]['calls'][0]),5)
            else:
                category='reply_tool_mismatch' if mode=='mismatch' else 'reply_data_indeterminate'
                with self.assertRaisesRegex(DeepSeekError,category):
                    agent.chat('isolated-v341','请查询模拟高铁。')
                self.assertEqual(agent.langchain_engine.last_live_run['error']['category'],category)
                self.assertFalse((config.TRACE_DIR/'traces.jsonl').exists())
            final=next(e for e in agent.langchain_engine.last_events if e['event']=='model_final')
            self.assertEqual(final['text'],reply)  # Original words preserved on both failure paths.
            self.assertIn('reply_consistency',final)
            self.assertEqual(final['reply_consistency']['status'],
                             {'match':'checked_fields_match','mismatch':'failed','uncertain':'indeterminate'}[mode])
            self.assertEqual(len(fixture.payloads),2)
            tool=next(e for e in agent.langchain_engine.last_events if e['event']=='tool_end')
            self.assertTrue(tool['executed']);self.assertTrue(tool['ok'])
            self.assertEqual(tool['tool'],'query_tickets')
            self.assertEqual(len(fixture.payloads[0]['tools']),2)
            self.assertNotIn('lock_seat',[t['function']['name'] for t in fixture.payloads[0]['tools']])
        finally:
            fixture.tearDown()


def provider_test(provider, mode):
    def run(self): self.run_provider(provider, mode)
    return run


for _provider in ('deepseek','bailian'):
    for _mode in ('match','mismatch','uncertain'):
        setattr(ProviderIntegration,'test_'+_provider+'_'+_mode,provider_test(_provider,_mode))
