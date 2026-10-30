"""Ten-turn UI/SDK replay using isolated HTTP substitutes, never real APIs."""
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
import config
from target import followups, deepseek_runtime, bailian_runtime
from target.run_events import capture, bind, emit
from target.trace import Trace
from web.runtime import Conversation


class ContinuousFollowupsTests(unittest.TestCase):
    def chain(self, provider):
        from streamlit.testing.v1 import AppTest
        calls=[]; clients=[]; saved=[]; clicked=[]; evidence=[]
        base=config.BASE_DIR/'artifacts/runtime';base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='continuous-',dir=base) as directory:
            root=Path(directory);date=(config.today()+timedelta(days=1)).isoformat()
            def respond(request):
                body=json.loads(request.content);calls.append(body)
                if body.get('response_format')=={'type':'json_object'}:
                    self.assertNotIn('tools',body)
                    auxiliary=sum('response_format' in p for p in calls)
                    if provider=='bailian' and auxiliary==5:
                        raise httpx.ReadTimeout('offline-followup-timeout')
                    payload=json.loads(body['messages'][-1]['content'])
                    self.assertLessEqual(len(payload['candidates']),6)
                    message={'content':json.dumps({'suggestions':[
                        {'id':r['id'],'question':r['question']} for r in payload['candidates'][:3]]},ensure_ascii=False)}
                elif body['messages'][-1]['role']=='user':
                    args={'from_city':'上海','to_city':'杭州','date':date,'kind':'高铁','seat_type':'二等座'}
                    message={'content':None,'tool_calls':[{'id':'offline-'+str(len(calls)),'type':'function',
                        'function':{'name':'query_tickets','arguments':json.dumps(args,ensure_ascii=False)}}]}
                else:
                    result=json.loads(body['messages'][-1]['content'])
                    message={'content':'模拟查询：\n'+'\n'.join(
                        f"{r['train_no']}，{r['from_city']}到{r['to_city']}，日期{r['date']}，出发{r['depart']}，到达{r['arrive']}，{r['seat_type']}，票价{r['price']}元，余票{r['seats_left']}张。"
                        for r in result['trains'])}
                return httpx.Response(200,json={'id':'offline-continuous','object':'chat.completion','created':1,
                    'model':body['model'],'choices':[{'index':0,'message':{'role':'assistant',**message},
                    'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
                    'usage':{'prompt_tokens':13,'completion_tokens':5,'total_tokens':18}})
            module=bailian_runtime if provider=='bailian' else deepseek_runtime
            original=module.make_model
            def factory(settings):
                model=original(settings,transport=httpx.MockTransport(respond));clients.append(model.http_client);return model
            env={'TICKET_DISABLE_LOCAL_SECRETS':'1','TICKET_WEB_OFFLINE_ONLY':'0',
                 'DEEPSEEK_API_KEY':'offline-fixture','DASHSCOPE_API_KEY':'offline-fixture',
                 'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
                 'DASHSCOPE_MODEL':'qwen3.8-flash','TICKET_API_USAGE_DIR':str(root/'usage'),
                 'LANGSMITH_TRACING':'false','LANGCHAIN_TRACING_V2':'false'}
            session=Conversation('user',engine='langchain',live=True,live_provider=provider,
                live_model='qwen3.8-flash' if provider=='bailian' else None,root=root,full_tools=True)
            script="""import streamlit as st
from web.conversation import user_page
st.session_state.update(default_engine='langchain',default_live=True,
 default_provider=st.session_state['fixture_provider'],default_live_model=st.session_state['fixture_model'])
user_page()
"""
            try:
                with patch.dict(os.environ,env),patch('web.runtime.live_ready',return_value=True),\
                     patch('web.conversation.live_ready',return_value=True),patch.object(module,'make_model',side_effect=factory):
                    app=AppTest.from_string(script,default_timeout=30)
                    for k,v in dict(fixture_provider=provider,fixture_model=session.live_model,user_sessions=[session],
                            user_provider_signature=('langchain',True,provider,session.live_model,'manual-live-v1')).items():
                        app.session_state[k]=v
                    app.run();app.checkbox(key='user_allow_live').check().run()
                    self.assertEqual([],calls)
                    app.text_input(key='user_message').set_value('查明天上海到杭州的高铁二等座')
                    next(b for b in app.button if b.label=='发送').click().run()
                    for turn in range(1,11):
                        with self.subTest(provider=provider,turn=turn):
                            self.assertEqual([],list(app.exception));self.assertIsNone(session.error)
                            self.assertEqual(turn,len(session.history))
                            record=session.history[-1];row=session.followups_for(record)
                            self.assertIn(len(row['suggestions']),(2,3));self.assertEqual(1,row['http_requests'])
                            self.assertFalse({followups.normal(q) for q in row['suggestions']} &
                                             {followups.normal(r['user_msg']) for r in session.history})
                            self.assertEqual('rule_fallback' if provider=='bailian' and turn==5 else 'model',row['generation_source'])
                            if turn==5 and provider=='bailian':self.assertEqual('timeout',row['fallback_reason'])
                            self.assertEqual(10,len(record))
                            self.assertTrue(all(len(c)==5 for s in record['steps'] for c in s['calls']))
                            saved.append(copy.deepcopy(row))
                            on_disk=[json.loads(s) for s in (session.trace_dir/'followups.jsonl').read_text(encoding='utf8').splitlines()]
                            self.assertEqual(saved,on_disk)  # New turns append, never overwrite old ones.
                            prefix='policy_followup_'+session.sid+'_'+row['run_id']+'_'
                            buttons=[b for b in app.button if (b.key or '').startswith(prefix)]
                            self.assertEqual(len(row['suggestions']),len(buttons))
                            evidence.append({'turn':turn,'session_id':session.sid,'run_id':row['run_id'],
                                'question':record['user_msg'],'reply':record['reply'],'suggestions':row['suggestions'],
                                'generation_source':row['generation_source'],'fallback_reason':row['fallback_reason'],
                                'source_event_ids':row['source_event_ids'],'mock_http_total':len(calls)})
                            before=len(calls);app.run();self.assertEqual(before,len(calls))
                            if turn<10:
                                button=next(b for b in app.button if (b.key or '').startswith(prefix))
                                question=button.label;clicked.append(question)
                                button.click().run()
                                self.assertEqual(question,session.history[-1]['user_msg'])
                    self.assertEqual(9,len(set(clicked)))
                    self.assertEqual(30,len(calls))  # 20 main + 10 auxiliary, including the one timeout; no retry.
                    reopened=Conversation('user',root=root)
                    reopened.sid=session.sid;reopened.audits=copy.deepcopy(session.audits)
                    before=len(calls)
                    for record,row in zip(session.history,saved):self.assertEqual(row,reopened.followups_for(record))
                    self.assertEqual(before,len(calls))
                    if os.getenv('FOLLOWUP_CONTINUOUS_EVIDENCE_DIR'):
                        out=Path(os.environ['FOLLOWUP_CONTINUOUS_EVIDENCE_DIR']);out.mkdir(parents=True,exist_ok=True)
                        with (out/(provider+'.json')).open('x',encoding='utf8') as stream:
                            json.dump({'real_api_requests':0,'http_origin':'httpx.MockTransport','rows':evidence},stream,ensure_ascii=False,indent=2)
            finally:
                for client in clients:client.close()

    def test_deepseek_ten_clicks_and_independent_saved_replay(self):self.chain('deepseek')
    def test_qwen_ten_clicks_survive_timeout_and_saved_replay(self):self.chain('bailian')

    def test_context_evidence_is_bound_and_new_empty_results_do_not_reuse_old_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);events=path/'run_events.jsonl'
            first=Trace('same','查票');first.finish('已查询模拟班次。')
            rows=[dict(train_no='G'+str(n),date='2026-11-01',seat_type='二等座',depart=f'0{n}:00',
                       arrive=f'0{n+1}:00',price=73,seats_left=n*10) for n in (1,2,3)]
            with capture(events):
                bind(first);source=emit('tool_result','succeeded',tool='query_tickets',executed=True,output={'trains':rows})
            for case,sid,empty,allowed in (('carry','same',False,True),('empty','same',True,False),('other','other',False,False)):
                with self.subTest(case=case):
                    current=Trace(sid,'这些班次哪班出发更早？');current.finish('可以继续对比已查询的模拟班次。')
                    with capture(events):
                        bind(current)
                        if empty:emit('tool_result','succeeded',tool='query_tickets',executed=True,output={'trains':[]})
                        row=followups.generate_and_save(current.to_dict(),{'trace_id':current.trace_id},path,
                            prior_run_ids=[first.trace_id],asked=[current.user_msg],authorized=False)
                    self.assertEqual(allowed,bool(row['suggestions']))
                    if allowed:
                        self.assertEqual([first.trace_id],row['source_run_ids'])
                        self.assertIn(source['event_id'],row['source_event_ids'])
                        self.assertNotEqual(first.trace_id,row['run_id'])


if __name__=='__main__':unittest.main()
