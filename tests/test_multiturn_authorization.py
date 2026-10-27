"""Multiturn simulated-operation authorization; no network or real identity data."""
import json, unittest
import importlib.util, uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from target.write_authorization import denial, selection_details

class Msg:
 def __init__(self, kind, content, name=None):self.type=kind;self.content=content;self.name=name

def query():
 return Msg('tool',json.dumps({'trains':[{'train_no':'G702','seat_type':'二等座','date':'2026-10-30'}]}),'query_tickets')

def ctx(message):return SimpleNamespace(user_message=message,lock_ids=set())

class MultiturnAuthorizationTests(unittest.TestCase):
 def setUp(self):
  self.text='G702 二等座，乘客张三'
  self.args={'train_no':'G702','date':'2026-10-30','seat_type':'二等座','passengers':['张三']}
  self.history=[Msg('human','我要买票'),query(),Msg('human','G702'),Msg('ai','请提供席别和乘客姓名'),Msg('human',self.text)]
 def test_selected_train_locks_only_after_earlier_purchase_and_matching_query(self):
  self.assertIsNone(denial('lock_seat',self.args,ctx(self.text),self.history))
  self.assertIsNotNone(denial('create_order',{'lock_id':'LKfake','passenger_ids':['张三']},ctx(self.text),self.history))
  self.assertIsNotNone(denial('pay_order',{'order_id':'ODfake'},ctx(self.text),self.history))
 def test_does_not_infer_from_assistant_or_no_query_or_cancelled_intent(self):
  for history in ([Msg('ai','我要买票'),query(),Msg('human',self.text)], [Msg('human','我要买票'),Msg('human',self.text)], [Msg('human','我要买票'),query(),Msg('human','不买了'),Msg('human',self.text)], [Msg('human','我要买票'),query(),Msg('human','不需要买票了'),Msg('human',self.text)]):
   self.assertIsNotNone(denial('lock_seat',self.args,ctx(self.text),history))
 def test_does_not_invent_passenger_train_or_date(self):
  for field,value in [('train_no','G703'),('date','2026-10-31'),('seat_type','一等座'),('passengers',['李四'])]:
   args=dict(self.args);args[field]=value
   self.assertIsNotNone(denial('lock_seat',args,ctx(self.text),self.history))
  for text in ('如果要G702二等座，乘客张三','G702 二等座，乘客张三吗？','不要订G702 二等座，乘客张三'):
   self.assertIsNone(selection_details(text))
 def test_explicit_confirm_order_reuses_only_latest_matching_real_lock(self):
  lock=Msg('tool',json.dumps({'lock_id':'LK123','passengers':['张三']}),'lock_seat')
  args={'lock_id':'LK123','passenger_ids':['张三']}
  self.assertIsNone(denial('create_order',args,ctx('确认下单'),self.history+[lock]))
  self.assertIsNotNone(denial('create_order',dict(args,lock_id='LKother'),ctx('确认下单'),self.history+[lock]))
  self.assertIsNotNone(denial('create_order',dict(args,passenger_ids=['李四']),ctx('确认下单'),self.history+[lock]))
  self.assertIsNotNone(denial('create_order',args,ctx('确认下单'),self.history))
  self.assertIsNotNone(denial('pay_order',{'order_id':'ODfake'},ctx('确认下单'),self.history+[lock]))
 def test_ui_selection_requires_confirmation(self):
  from web.runtime import operation_kind
  self.assertEqual(operation_kind(self.text),'模拟锁座')
  self.assertIsNone(operation_kind('G702还有余票吗？'))
 def test_error_hint_is_safe_and_specific(self):
  from web.runtime import tool_failure_hint
  reason='当前消息未明确授权该操作，请明确说明订票、支付、退票或候补请求。'
  session=SimpleNamespace(error={'category':'tool_execution_failed'},audits=[{'fault_report':{'executions':[{'result':{'error':reason}}]}}])
  self.assertIn(reason,tool_failure_hint(session))
  session.audits[0]['fault_report']['executions'][0]['result']['error']='arbitrary-credential-like-text'
  self.assertIsNone(tool_failure_hint(session))

 @unittest.skipUnless(importlib.util.find_spec('streamlit') is not None,'Streamlit required')
 def test_ui_prompts_before_selection_without_executing(self):
  from streamlit.testing.v1 import AppTest
  from web.runtime import Conversation
  s=Conversation('user',engine='langchain',live=True,live_provider='deepseek',full_tools=True,
                 root=Path('artifacts/runtime')/('multiturn-ui-'+uuid.uuid4().hex))
  s.history=[{'user_msg':'我要买票','reply':'请提供车次、席别和乘客。','tool_sequence':[],
              'finish_reason':'stop','total_latency_ms':0,'steps':[]}];s.results=[[]]
  app=AppTest.from_string('from web.conversation import user_page\nuser_page()')
  for key,value in {'user_sessions':[s],'default_engine':'langchain','default_live':True,'default_provider':'deepseek',
                    'default_live_model':None,'user_provider_signature':('langchain',True,'deepseek',None,'manual-live-v1')}.items():
   app.session_state[key]=value
  with patch('web.conversation.live_ready',return_value=True),patch.object(s,'send') as send:
   app.run(timeout=15)
   app.checkbox(key='user_allow_live').check()
   app.text_input(key='user_message').set_value(self.text)
   next(b for b in app.button if b.label=='发送').click().run(timeout=15)
   self.assertFalse(app.exception)
   self.assertTrue(any(b.label=='确认执行模拟操作' for b in app.button))
   send.assert_not_called()
