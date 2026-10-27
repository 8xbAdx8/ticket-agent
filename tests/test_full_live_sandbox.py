import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
try:
 import httpx
 import config
 from web.runtime import Conversation
 from target import deepseek_runtime, bailian_runtime
 AVAILABLE=True
except ImportError:
 AVAILABLE=False

@unittest.skipUnless(AVAILABLE,'Live SDK and Streamlit required for offline sandbox test')
class LiveSandboxRoundTrip(unittest.TestCase):
 def test_payment_requires_explicit_current_turn_authorization(self):
  from target.write_authorization import permissions,denial
  from types import SimpleNamespace
  context=SimpleNamespace(user_message='帮我查一下票',lock_ids=set())
  self.assertNotIn('pay_order',permissions(context.user_message))
  self.assertIsNotNone(denial('pay_order',{'order_id':'ODfake'},context,[]))
  self.assertNotIn('pay_order',permissions('帮我订明天的高铁'))
 def run_provider(self, provider):
  root=Path('artifacts/runtime')/('full-sandbox-offline-'+__import__('uuid').uuid4().hex)
  today=(config.today()+timedelta(days=1)).isoformat()
  calls=[]; clients=[]
  def respond(req):
   body=json.loads(req.content); calls.append(body); messages=body['messages']
   assert {x['function']['name'] for x in body['tools']}=={'query_tickets','monitor_seat','lock_seat','create_order','pay_order','cancel_order','query_order','search_policy'}
   user=next(m['content'] for m in reversed(messages) if m['role']=='user')
   tail=messages[-1]
   if tail['role']=='user':
    if '查明天' in user: tool='query_tickets';args={'from_city':'上海','to_city':'杭州','date':today,'kind':'高铁','seat_type':'二等座'}
    elif '订明天' in user: tool='lock_seat';args={'train_no':'G7301','date':today,'seat_type':'二等座','passengers':['张三']}
    else:
     tool='pay_order'; order=next(json.loads(m['content'])['order_id'] for m in reversed(messages) if m['role']=='tool' and 'order_id' in json.loads(m['content']))
     args={'order_id':order,'pay_type':'alipay'}
   else:
    result=json.loads(tail['content'])
    if 'lock_id' in result and 'order_id' not in result:
     tool='create_order';args={'lock_id':result['lock_id'],'passenger_ids':['张三'],'contact':config.CURRENT_USER_PHONE}
    else:tool=None
   msg={'content':'模拟操作完成，详情以工具结果为准。'} if not tool else {'content':None,'tool_calls':[{'id':'id-'+str(len(calls)),'type':'function','function':{'name':tool,'arguments':json.dumps(args,ensure_ascii=False)}}]}
   return httpx.Response(200,json={'id':'offline-fixture','object':'chat.completion','created':1,'model':config.MODEL_NAME,'choices':[{'index':0,'message':{'role':'assistant',**msg},'finish_reason':'tool_calls' if tool else 'stop'}],'usage':{'prompt_tokens':13,'completion_tokens':5,'total_tokens':18}})
  module=bailian_runtime if provider=='bailian' else deepseek_runtime; original=module.make_model
  def factory(settings):
   model=original(settings,transport=httpx.MockTransport(respond));clients.append(model);return model
  env={'DEEPSEEK_API_KEY':'offline-test','DASHSCOPE_API_KEY':'offline-test','DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1','DASHSCOPE_MODEL':'qwen3.8-flash','TICKET_API_USAGE_DIR':str(root/'usage'),'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','TICKET_DISABLE_LOCAL_SECRETS':'1'}
  s=Conversation('user',engine='langchain',live=True,live_provider=provider,live_model='qwen3.8-flash' if provider=='bailian' else None,root=root,full_tools=True)
  with patch.dict(os.environ,env),patch('web.runtime.live_ready',return_value=True),patch.object(module,'make_model',side_effect=factory):
   a=s.send('查明天上海到杭州的高铁二等座','query')
   b=s.send('帮我订明天上海到杭州G7301二等座，乘客张三','order')
   self.assertEqual(b['tool_sequence'],['lock_seat','create_order'])
   self.assertEqual(s.results[-1][-1]['result']['status'],'pending')
   c=s.send('支付刚才的订单','pay')
   self.assertEqual(c['tool_sequence'],['pay_order']); self.assertEqual(s.results[-1][-1]['result']['status'],'paid')
   self.assertEqual(len(calls),7)
  for m in clients:m.client._client.close()
 def test_deepseek(self):self.run_provider('deepseek')
 def test_qwen(self):self.run_provider('bailian')
 def test_multiturn_selection_then_explicit_order_and_payment(self):
  root=Path('artifacts/runtime')/('multiturn-offline-'+__import__('uuid').uuid4().hex)
  day=(config.today()+timedelta(days=2)).isoformat()
  calls=[];clients=[]
  def respond(req):
   body=json.loads(req.content);calls.append(body);messages=body['messages'];last=messages[-1]
   user=next(m['content'] for m in reversed(messages) if m['role']=='user')
   tool=None;args={}
   if last['role']=='user':
    if user=='查后天北京到广州的高铁':
     tool='query_tickets';args={'from_city':'北京','to_city':'广州','date':day,'kind':'高铁','seat_type':'二等座'}
    elif user=='G702 二等座，乘客张三':
     tool='lock_seat';args={'train_no':'G702','date':day,'seat_type':'二等座','passengers':['张三']}
    elif user=='确认下单':
     lock=next(json.loads(m['content'])['lock_id'] for m in reversed(messages) if m['role']=='tool' and 'lock_id' in json.loads(m['content']))
     tool='create_order';args={'lock_id':lock,'passenger_ids':['张三'],'contact':config.CURRENT_USER_PHONE}
    elif user=='支付刚才的订单':
     order=next(json.loads(m['content'])['order_id'] for m in reversed(messages) if m['role']=='tool' and 'order_id' in json.loads(m['content']))
     tool='pay_order';args={'order_id':order}
   msg={'content':'请确认下一步，具体状态以模拟工具结果为准。'} if not tool else {'content':None,'tool_calls':[{'id':'mt-'+str(len(calls)),'type':'function','function':{'name':tool,'arguments':json.dumps(args,ensure_ascii=False)}}]}
   return httpx.Response(200,json={'id':'offline-fixture','object':'chat.completion','created':1,'model':config.MODEL_NAME,'choices':[{'index':0,'message':{'role':'assistant',**msg},'finish_reason':'tool_calls' if tool else 'stop'}],'usage':{'prompt_tokens':13,'completion_tokens':5,'total_tokens':18}})
  original=deepseek_runtime.make_model
  def factory(settings):
   model=original(settings,transport=httpx.MockTransport(respond));clients.append(model);return model
  env={'DEEPSEEK_API_KEY':'offline-test','TICKET_API_USAGE_DIR':str(root/'usage'),'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','TICKET_DISABLE_LOCAL_SECRETS':'1'}
  s=Conversation('user',engine='langchain',live=True,live_provider='deepseek',root=root,full_tools=True)
  with patch.dict(os.environ,env),patch('web.runtime.live_ready',return_value=True),patch.object(deepseek_runtime,'make_model',side_effect=factory):
   self.assertEqual(s.send('我要买票','intent')['tool_sequence'],[])
   self.assertEqual(s.send('查后天北京到广州的高铁','query')['tool_sequence'],['query_tickets'])
   self.assertEqual(s.send('G702 二等座，乘客张三','select')['tool_sequence'],['lock_seat'])
   self.assertEqual(s.send('确认下单','order')['tool_sequence'],['create_order'])
   self.assertEqual(s.results[-1][-1]['result']['status'],'pending')
   self.assertEqual(s.send('支付刚才的订单','pay')['tool_sequence'],['pay_order'])
   self.assertEqual(s.results[-1][-1]['result']['status'],'paid')
  for model in clients:model.client._client.close()
