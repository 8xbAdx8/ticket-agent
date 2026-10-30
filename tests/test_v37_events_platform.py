import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import config
from target.run_events import capture,bind
from target.trace import Trace
from target.tools import dispatch

class V37Tests(unittest.TestCase):
    def test_invalid_tool_never_gets_execution_start(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.jsonl'; seen=[]
            with capture(path,seen.append):
                t=Trace('s','test');bind(t)
                result,ok,_=dispatch('pay_order',{})
            self.assertFalse(ok)
            rows=[json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
            self.assertEqual(seen,rows)
            self.assertTrue(all(r['run_id']==t.trace_id for r in rows))
            self.assertNotIn('tool_start',[r['event_type'] for r in rows])
            self.assertEqual(rows[-1]['status'],'blocked');self.assertFalse(rows[-1]['executed'])
            for prior,row in zip(rows,rows[1:]):self.assertEqual(row['previous_event_id'],prior['event_id'])

    def test_ui_agent_events_share_trace_identity(self):
        from web.runtime import Conversation
        with patch.dict(os.environ,{'TICKET_DISABLE_LOCAL_SECRETS':'1'}):
            s=Conversation('user',engine='legacy',live=False)
            r=s.send('查明天上海到杭州的高铁二等座','run')
            rows=[json.loads(x) for x in (s.trace_dir/'run_events.jsonl').read_text(encoding='utf8').splitlines()]
            self.assertEqual({x['run_id'] for x in rows},{s.audits[-1]['trace_id']})
            self.assertIn('tool_start',[x['event_type'] for x in rows]);self.assertEqual(rows[-1]['event_type'],'agent_returned')
            self.assertEqual(r['tool_sequence'],['query_tickets'])

    def test_corpus_preserves_originals_and_excludes_attack_samples(self):
        from target.rag_store import documents
        root=Path(__file__).resolve().parent.parent
        rows=json.loads((root/'data/v37/policies.json').read_text(encoding='utf8'))
        self.assertEqual(len(rows),60);self.assertEqual(len({r['doc_id'] for r in rows}),60)
        old={r['doc_id']:r for r in documents(root/'data/policies.md')}
        for r in rows[:15]:self.assertEqual(r['content'],old[r['doc_id']]['content'])
        self.assertEqual(sum(r['status']=='active' for r in rows),57)
