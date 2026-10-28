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
 def test_selection_across_user_turns_and_auto_order(self):
  history=[Msg('human','自动下单'), Msg('human','北京到广州，后天，高铁，二等座，乘客张三'), query(), Msg('human','G702')]
  self.assertIsNone(denial('lock_seat', self.args, ctx('G702'), history))
  self.assertIsNotNone(denial('lock_seat',dict(self.args,passengers=['李四']),ctx('G702'),history))
  from web.runtime import operation_kind
  self.assertEqual(operation_kind('G702',[{'user_msg':'自动下单'},{'user_msg':'二等座，乘客张三'}]),'模拟锁座')
 def test_multiturn_rejects_cancel_ambiguous_or_assistant_data(self):
  cases=[
   [Msg('human','我要买票'),Msg('human','二等座，乘客张三'),query(),Msg('human','算了'),Msg('human','G702')],
   [Msg('human','我要买票'),Msg('ai','二等座，乘客张三'),query(),Msg('human','G702')],
   [Msg('human','我要买票'),Msg('human','二等座，一等座，乘客张三'),query(),Msg('human','G702')],
  ]
  for history in cases:
   self.assertIsNotNone(denial('lock_seat',self.args,ctx('G702'),history))
  self.assertIsNotNone(denial('pay_order',{'order_id':'ODfake'},ctx('G702'),cases[0]))
 def test_context_confirmation_binds_exact_lock_and_query(self):
  history=[Msg('human','我要买票'),query(),Msg('human',self.text),Msg('ai','是否锁座 G702 二等座，乘客张三，日期 2026-10-30？'),Msg('human','确认')]
  self.assertIsNone(denial('lock_seat',self.args,ctx('确认'),history))
  self.assertIsNotNone(denial('lock_seat',dict(self.args,train_no='G703'),ctx('确认'),history))
  self.assertIsNotNone(denial('pay_order',{'order_id':'ODfake'},ctx('确认'),history))
  from web.runtime import operation_kind
  self.assertEqual(operation_kind('确认',[{'reply':history[-2].content}]),'模拟业务操作')
 def test_confirmation_cannot_invent_or_accept_ambiguous_or_stale_prompt(self):
  base=[Msg('human','我要买票'),query(),Msg('human',self.text)]
  for prompt in ('是否锁座 G702 二等座？','是否锁座 G702 二等座，乘客李四，日期 2026-10-30？','是否锁座 G702 二等座，乘客张三，日期 2026-10-30，并支付？','是否查询 G702？'):
   self.assertIsNotNone(denial('lock_seat',self.args,ctx('确认'),base+[Msg('ai',prompt),Msg('human','确认')]))
  self.assertIsNotNone(denial('lock_seat',self.args,ctx('确认'),base+[Msg('ai','是否锁座 G702 二等座，乘客张三，日期 2026-10-30？'),Msg('human','不买了'),Msg('human','确认')]))
 def test_confirm_order_and_payment_are_separate(self):
  lock=Msg('tool',json.dumps({'lock_id':'LK123','passengers':['张三']}),'lock_seat')
  order=Msg('tool',json.dumps({'order_id':'OD123'}),'create_order')
  lock_args={'lock_id':'LK123','passenger_ids':['张三']}
  order_question=[lock,Msg('ai','是否创建模拟订单，锁座 LK123？'),Msg('human','确认')]
  self.assertIsNone(denial('create_order',lock_args,ctx('确认'),order_question))
  self.assertIsNotNone(denial('pay_order',{'order_id':'OD123'},ctx('确认'),order_question))
  pay_question=[order,Msg('ai','是否支付订单 OD123？'),Msg('human','确认')]
  self.assertIsNone(denial('pay_order',{'order_id':'OD123'},ctx('确认'),pay_question))
  self.assertIsNotNone(denial('pay_order',{'order_id':'OD456'},ctx('确认'),pay_question))
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
