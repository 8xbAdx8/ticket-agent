"""Non-factual follow-up invitations must not masquerade as ticket assertions."""
import copy
import json
from pathlib import Path
import unittest
from target.reply_consistency import check


class TicketFollowUpTests(unittest.TestCase):
    def setUp(self):
        self.events=[{'event':'tool_end','tool':'query_tickets','ok':True,'executed':True,
            'call_id':'offline-follow-up','args':{},'result':{'trains':[
                {'train_no':'G7301','date':'2026-10-27','from_city':'上海','to_city':'杭州',
                 'kind':'高铁','seat_type':'二等座','depart':'06:00','arrive':'07:00','price':73,'seats_left':35}]}}]
        self.table='车次 | 出发 | 到达 | 席别 | 票价 | 余票\n---|---|---|---|---|---\nG7301 | 06:00 | 07:00 | 二等座 | ¥73 | 35 张\n\n'

    def test_generic_follow_up_is_non_factual_and_never_changes_authority(self):
        original=copy.deepcopy(self.events)
        report=check(self.table+'如果您需要改查其他席别或返程车次，可以告诉我。',self.events)
        self.assertEqual(report['status'],'checked_fields_match')
        self.assertTrue(any(i['reason']=='non_factual_follow_up' for i in report['ignored']))
        self.assertEqual(self.events,original)

    def test_missing_condition_question_has_no_ticket_assertion(self):
        report=check('请提供出发地、目的地和日期。',[])
        self.assertEqual(report['status'],'not_verified');self.assertFalse(report['findings'])

    def test_follow_up_cannot_exempt_invented_identity_or_bad_time(self):
        for suffix in ('如果要G9999请告诉我。','如果G7301在99:99出发，请告诉我。'):
            with self.subTest(suffix=suffix):
                self.assertEqual(check(self.table+suffix,self.events)['status'],'indeterminate')

    def test_follow_up_cannot_hide_an_actual_mismatch(self):
        report=check(self.table.replace('06:00','08:00')+'如需其他席别，请告诉我。',self.events)
        self.assertEqual(report['status'],'failed')
        self.assertTrue(any(f['field']=='depart' for f in report['findings']))

    def test_preserved_manual_live_reply_offline_replay(self):
        path=Path(__file__).resolve().parent.parent/'docs/evidence/live-web-repair-20261026/user-manual-deepseek-query.json'
        fixture=json.loads(path.read_text(encoding='utf-8'))
        original=copy.deepcopy(fixture)
        self.assertEqual(fixture['original_reply_consistency']['status'],'indeterminate')
        replay=check(fixture['original_model_reply'],fixture['tool_events'])
        self.assertEqual(replay['status'],'checked_fields_match')
        self.assertEqual(replay['checked_fields'],25);self.assertEqual(replay['identity_checks'],3)
        self.assertEqual(fixture,original)
