"""Offline UI smoke tests for the workspaces and real simulated booking path."""
import os
import unittest
from unittest.mock import patch
from pathlib import Path

from streamlit.testing.v1 import AppTest


class WorkspacesTests(unittest.TestCase):
    def test_navigation_and_offline_demo(self):
        env={'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1',
             'DEEPSEEK_API_KEY':'','DASHSCOPE_API_KEY':'',
             'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
        with patch.dict(os.environ,env):
            app=AppTest.from_file(str(Path(__file__).resolve().parent.parent/'web/app.py'),default_timeout=30).run()
            for key in ('demo_start','demo_query','demo_order','demo_pay','demo_order_query'):
                app.button(key=key).click().run()
                self.assertEqual([e.message for e in app.exception],[])
            demo=app.session_state['guided_demo']
            self.assertEqual(demo['stage'],4)
            session=demo['session']
            sequences=[r['tool_sequence'] for r in session.history]
            self.assertIn('query_tickets',sequences[0])
            self.assertIn('lock_seat',sequences[1]);self.assertIn('create_order',sequences[1])
            self.assertIn('pay_order',sequences[2]);self.assertIn('query_order',sequences[3])
            self.assertTrue(any(o.get('order_id')==demo['order_id'] and o.get('status')=='paid'
                for result in session.results[-1] if result['tool']=='query_order'
                for o in result['result']['orders']))
            app.radio(key='workspace_mode').set_value('开发者工作台').run()
            self.assertEqual([e.message for e in app.exception],[])
            self.assertIn('工具配置',[tab.label for tab in app.tabs])
            app.radio(key='workspace_mode').set_value('测试工作台').run()
            self.assertEqual([e.message for e in app.exception],[])


if __name__=='__main__':unittest.main()
