"""Offline HTTP fixtures: model proposes, user approves exact simulated calls."""
import json, os, uuid, unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import httpx
import config
from target import deepseek_runtime
from web.runtime import Conversation

class ConfirmationFlowTests(unittest.TestCase):
 def test_proposal_approve_and_cancel_are_isolated(self):
  root=Path('artifacts/runtime')/('model-confirm-'+uuid.uuid4().hex)
  day=(config.today()+timedelta(days=1)).isoformat()
  requests=[]; clients=[]
  def respond(req):
   body=json.loads(req.content); requests.append(body)
   last=body['messages'][-1]
   if last['role']=='user' and last['content']=='付款':
    order=next(json.loads(m['content'])['order_id'] for m in reversed(body['messages']) if m['role']=='tool' and 'order_id' in json.loads(m['content']))
    tool='pay_order';args={'order_id':order}
   elif last['role']=='user':
    tool='lock_seat';args={'train_no':'G7301','date':day,'seat_type':'二等座','passengers':['张三']}
   elif last['role']=='tool' and 'lock_id' in json.loads(last['content']) and 'order_id' not in json.loads(last['content']):
    tool='create_order';args={'lock_id':json.loads(last['content'])['lock_id'],'passenger_ids':['张三'],'contact':config.CURRENT_USER_PHONE}
   else: tool=None
   msg={'content':'模拟处理结束。'} if not tool else {'content':None,'tool_calls':[{'id':'tc'+str(len(requests)),'type':'function','function':{'name':tool,'arguments':json.dumps(args,ensure_ascii=False)}}]}
   return httpx.Response(200,json={'id':'fixture','object':'chat.completion','created':1,'model':'deepseek-flash','choices':[{'index':0,'message':{'role':'assistant',**msg},'finish_reason':'tool_calls' if tool else 'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}})
  original=deepseek_runtime.make_model
  def factory(settings):
   model=original(settings,transport=httpx.MockTransport(respond));clients.append(model);return model
  env={'DEEPSEEK_API_KEY':'offline-test','TICKET_API_USAGE_DIR':str(root/'usage'),'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','TICKET_DISABLE_LOCAL_SECRETS':'1'}
  s=Conversation('user',engine='langchain',live=True,live_provider='deepseek',root=root,full_tools=True,interactive=True)
  with patch.dict(os.environ,env),patch('web.runtime.live_ready',return_value=True),patch.object(deepseek_runtime,'make_model',side_effect=factory):
   first=s.send('就这班，帮我办了','one')
   self.assertEqual(first['tool_sequence'],[])
   self.assertEqual(s.pending_action()['tool'],'lock_seat')
   self.assertEqual(len(requests),1)
   import sqlite3
   with sqlite3.connect(root/'tickets.db') as db:self.assertEqual(db.execute('select count(*) from locks').fetchone()[0],0)
   second=s.confirm_action(True,'two')
   self.assertEqual(second['tool_sequence'],['lock_seat'])
   self.assertEqual(s.pending_action()['tool'],'create_order')
   with sqlite3.connect(root/'tickets.db') as db:self.assertEqual(db.execute('select count(*) from orders').fetchone()[0],0)
   third=s.confirm_action(True,'three')
   self.assertEqual(third['tool_sequence'],['create_order'])
   self.assertIsNone(s.pending_action())
   with sqlite3.connect(root/'tickets.db') as db:self.assertEqual(db.execute('select count(*) from orders').fetchone()[0],1)
   s.send('付款','pay-start')
   self.assertEqual(s.pending_action()['tool'],'pay_order')
   with sqlite3.connect(root/'tickets.db') as db:self.assertEqual(db.execute('select status from orders').fetchone()[0],'pending')
   paid=s.confirm_action(True,'pay-confirm')
   self.assertEqual(paid['tool_sequence'],['pay_order'])
   with sqlite3.connect(root/'tickets.db') as db:self.assertEqual(db.execute('select status from orders').fetchone()[0],'paid')
   other=Conversation('user',engine='langchain',live=True,live_provider='deepseek',root=Path('artifacts/runtime')/('model-cancel-'+uuid.uuid4().hex),full_tools=True,interactive=True)
   other.send('就这班','cancel-start')
   self.assertEqual(other.pending_action()['tool'],'lock_seat')
   cancelled=other.confirm_action(False,'cancel-end')
   self.assertEqual(cancelled['tool_sequence'],[])
   with sqlite3.connect(other.root/'tickets.db') as db:self.assertEqual(db.execute('select count(*) from locks').fetchone()[0],0)
  for model in clients:model.client._client.close()

 def test_confirmation_error_is_kept_for_ui(self):
  from types import SimpleNamespace
  s=Conversation('user',engine='langchain',live=True,full_tools=True,interactive=True)
  s.agent=SimpleNamespace(langchain_engine=SimpleNamespace(pending_actions={s.sid:{'tool':'lock_seat','args':{},'call_id':'x'}}))
  with patch.object(s,'_send',side_effect=RuntimeError('fixture')):
   with self.assertRaises(RuntimeError):s.confirm_action(True,'request')
  self.assertIsNotNone(s.error)
