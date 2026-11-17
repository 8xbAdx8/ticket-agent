"""Offline MockTransport verification, not real DeepSeek/Qwen validation."""
import copy
from dataclasses import replace
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
from web.runtime import Conversation, scoped


ROWS = [dict(train_no='G7301', from_city='上海', to_city='杭州', date='2026-11-01',
             depart='06:00', arrive='07:00', seat_type='二等座', price=73.0, seats_left=35),
        dict(train_no='G7302', from_city='上海', to_city='杭州', date='2026-11-01',
             depart='09:17', arrive='10:17', seat_type='二等座', price=73.0, seats_left=47)]


class FollowupMVPTests(unittest.TestCase):
    def setUp(self):
        base=config.BASE_DIR/'artifacts/runtime';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='followups-offline-',dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.calls=[];self.clients=[]
        self.env=patch.dict(os.environ,{'TICKET_DISABLE_LOCAL_SECRETS':'1','LANGCHAIN_TRACING_V2':'false',
            'LANGSMITH_TRACING':'false','DEEPSEEK_API_KEY':'offline-fixture','DASHSCOPE_API_KEY':'offline-fixture',
            'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'DASHSCOPE_MODEL':'qwen3.8-flash','TICKET_API_USAGE_DIR':str(self.root/'usage'),
            'TICKET_FROZEN_RAG_EVIDENCE':'','AGENT_RAG_MODE':'','TICKET_API_VALIDATION_PROFILE':'interactive'})
        self.env.start();self.addCleanup(self.env.stop)

    def sdk(self,provider='deepseek',output='valid',error=None):
        module=bailian_runtime if provider=='bailian' else deepseek_runtime
        settings=module.Settings(ledger_path=self.root/'historical-budget.db')
        # A sentinel old ledger must never be opened, reset or used as a new quota.
        settings.ledger_path.write_bytes(b'historical-budget-must-remain-unchanged')
        def response(request):
            body=json.loads(request.content);self.calls.append(body)
            self.assertNotIn('tools',body)
            self.assertEqual({'type':'json_object'},body['response_format'])
            if isinstance(error,Exception):raise error
            if isinstance(error,int):return httpx.Response(error,json={'error':{'message':'private error body'}})
            payload=json.loads(body['messages'][-1]['content'])
            rows=payload['candidates'][:2]
            content=json.dumps({'suggestions':[{'id':r['id'],'question':r['question']} for r in reversed(rows)]},ensure_ascii=False)
            if output!='valid':content=output
            return httpx.Response(200,json={'id':'offline-followups','object':'chat.completion','created':1,
                'model':config.MODEL_NAME,'choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})
        address='https://dashscope.aliyuncs.com/compatible-mode/v1' if provider=='bailian' else 'https://api.deepseek.com'
        model_name='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash'
        with scoped({'PROVIDER':provider,'BASE_URL':address,'MODEL_NAME':model_name,'API_KEY':'offline-fixture'}):
            model=module.make_model(settings,transport=httpx.MockTransport(response))
        self.clients.append(model.http_client)
        self.addCleanup(model.http_client.close)
        return model,settings

    def run_generation(self,provider='deepseek',*,authorized=True,model=None,settings=None,source='tickets',live=True):
        trace=Trace('fixture-session','明天上海到杭州有哪些高铁？' if source=='tickets' else '退票手续费怎么算？')
        trace.provider=provider+'_live';trace.model='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash'
        trace.finish('已查询模拟票务数据。')
        record=trace.to_dict();audit={'trace_id':trace.trace_id,'public_trace':record}
        before=copy.deepcopy(record)
        directory=self.root/trace.trace_id
        address='https://dashscope.aliyuncs.com/compatible-mode/v1' if provider=='bailian' else 'https://api.deepseek.com'
        with scoped({'PROVIDER':provider,'MODEL_NAME':trace.model,'BASE_URL':address,'API_KEY':'offline-fixture'}), capture(directory/'run_events.jsonl'):
            bind(trace)
            if source=='tickets':
                emit('tool_result','succeeded',tool='query_tickets',executed=True,output={'trains':ROWS})
            elif source=='unrelated':
                emit('tool_result','succeeded',tool='query_tickets',executed=True,output={'trains':ROWS},session_id='someone-else')
            result=followups.generate_and_save(record,audit,directory,live=live,authorized=authorized,
                model=model,settings=settings,network_ready=True)
        self.assertEqual(before,record)
        return result,directory,record,audit

    def success(self,provider):
        model,settings=self.sdk(provider)
        result,directory,record,audit=self.run_generation(provider,model=model,settings=settings)
        self.assertEqual('model',result['generation_source'])
        self.assertIsNone(result['fallback_reason'])
        self.assertEqual(2,len(result['suggestions']))
        self.assertEqual(1,len(self.calls));self.assertEqual(1,result['http_requests'])
        self.assertEqual({'prompt':20,'completion':10},result['tokens'])
        self.assertEqual(b'historical-budget-must-remain-unchanged',settings.ledger_path.read_bytes())
        self.assertIn('ticket_results',json.loads(self.calls[0]['messages'][-1]['content'])['evidence'])
        events=[json.loads(s) for s in (directory/'run_events.jsonl').read_text(encoding='utf8').splitlines()]
        self.assertEqual({result['run_id']},{e['run_id'] for e in events})
        self.assertTrue(set(result['source_event_ids']) <= {e['event_id'] for e in events})
        self.assertIn('followup_success',[e['event_type'] for e in events])
        self.assertEqual(result,followups.read_record(directory,record['session_id'],audit['trace_id'],record))
        return result

    def test_deepseek_model_json_success_via_mock_transport(self):self.success('deepseek')
    def test_qwen_model_json_success_via_mock_transport(self):self.success('bailian')

    def test_timeout_falls_back_without_retry_or_private_error_text(self):
        model,settings=self.sdk(error=httpx.ReadTimeout('do-not-save-private-error-text'))
        row,path,_,_=self.run_generation(model=model,settings=settings)
        self.assertEqual('timeout',row['fallback_reason']);self.assertEqual(1,len(self.calls))
        self.assertEqual('rule_fallback',row['generation_source']);self.assertEqual(2,len(row['suggestions']))
        self.assertNotIn('do-not-save-private-error-text',(path/'followups.jsonl').read_text(encoding='utf8'))

    def test_api_error_falls_back(self):
        model,settings=self.sdk(error=401)
        row,*_=self.run_generation(model=model,settings=settings)
        self.assertEqual('authentication_failed',row['fallback_reason']);self.assertEqual(1,len(self.calls))

    def test_provider_balance_error_falls_back(self):
        model,settings=self.sdk(error=402)
        row,*_=self.run_generation(model=model,settings=settings)
        self.assertEqual('insufficient_balance',row['fallback_reason']);self.assertEqual(1,len(self.calls))

    def test_bad_json_falls_back(self):
        model,settings=self.sdk(output='not JSON')
        row,*_=self.run_generation(model=model,settings=settings)
        self.assertEqual('invalid_json',row['fallback_reason']);self.assertEqual(2,len(row['suggestions']))

    def test_empty_model_result_falls_back(self):
        model,settings=self.sdk(output='{"suggestions":[]}')
        row,*_=self.run_generation(model=model,settings=settings)
        self.assertEqual('empty_result',row['fallback_reason'])
        self.assertEqual('rule_fallback',row['generation_source'])

    def test_unsupported_policy_question_is_rejected(self):
        output=json.dumps({'suggestions':[{'id':'tickets_earliest','question':'退款多久能到账？'},
                                         {'id':'tickets_most_seats','question':'哪班余票最多？'}]},ensure_ascii=False)
        model,settings=self.sdk(output=output)
        row,*_=self.run_generation(model=model,settings=settings)
        self.assertEqual('ungrounded_or_duplicate_question',row['fallback_reason'])
        self.assertFalse(any('退款' in q for q in row['suggestions']))

    def test_no_authorization_never_invokes_model(self):
        model,settings=self.sdk()
        row,*_=self.run_generation(authorized=False,model=model,settings=settings)
        self.assertEqual('not_authorized',row['fallback_reason']);self.assertEqual([],self.calls)

    def test_token_budget_exhausted_before_http_falls_back(self):
        model,settings=self.sdk()
        row,*_=self.run_generation(model=model,settings=replace(settings,turn_token_budget=512))
        self.assertEqual('token_budget_insufficient',row['fallback_reason'])
        self.assertEqual(0,row['model_invocations']);self.assertEqual([],self.calls)

    def test_no_rag_evidence_does_not_invent_policy_suggestions(self):
        model,settings=self.sdk()
        row,*_=self.run_generation(model=model,settings=settings,source='policy-without-evidence')
        self.assertEqual('insufficient_evidence',row['fallback_reason'])
        self.assertEqual([],row['suggestions']);self.assertEqual([],row['doc_ids']);self.assertEqual([],self.calls)

    def test_other_session_evidence_is_not_used(self):
        row,*_=self.run_generation(source='unrelated')
        self.assertEqual([],row['suggestions'])

    def test_fallback_is_deterministic_for_same_input_and_version(self):
        a,*_=self.run_generation(authorized=False)
        b,*_=self.run_generation(authorized=False)
        self.assertEqual(a['input_hash'],b['input_hash']);self.assertEqual(a['suggestions'],b['suggestions'])

    def test_history_replay_uses_saved_version_without_regeneration(self):
        row,path,record,audit=self.run_generation(authorized=False)
        with patch.object(followups,'PROMPT_VERSION','future-version'),patch.object(followups,'_invoke',side_effect=AssertionError('no replay calls')):
            self.assertEqual(row,followups.read_record(path,record['session_id'],audit['trace_id'],record))
        self.assertIsNone(followups.read_record(path,'other-session',audit['trace_id'],record))

    def test_answer_changes_cannot_borrow_saved_questions(self):
        _,path,record,audit=self.run_generation(authorized=False)
        changed={**record,'reply':'changed answer'}
        self.assertIsNone(followups.read_record(path,record['session_id'],audit['trace_id'],changed))

    def test_asking_for_earliest_does_not_recommend_it_again(self):
        row,path,record,audit=self.run_generation(authorized=False)
        events=[json.loads(s) for s in (path/'run_events.jsonl').read_text(encoding='utf8').splitlines()]
        record['user_msg']='哪一班最早出发？'
        available,_=followups.candidates(record,events,audit)
        self.assertNotIn('tickets_earliest',[r['id'] for r in available])

    def test_mock_mode_ignores_extra_model_authorization(self):
        model,settings=self.sdk()
        row,*_=self.run_generation(model=model,settings=settings,live=False)
        self.assertEqual('mock_mode',row['fallback_reason']);self.assertEqual([],self.calls)

    def test_unknown_usage_stays_unknown_and_does_not_issue_auxiliary_http(self):
        model,settings=self.sdk()
        row,path,record,audit=self.run_generation(authorized=False)
        record['tokens']={'prompt':None,'completion':None}
        trace=Trace(record['session_id'],record['user_msg']);trace.trace_id=audit['trace_id']
        trace.provider=record['provider'];trace.model=record['model']
        with capture(path/'run_events.jsonl'):
            bind(trace)
            result=followups.generate_and_save(record,audit,path,live=True,authorized=True,
                model=model,settings=settings,network_ready=True)
        self.assertEqual('token_usage_unknown',result['fallback_reason'])
        self.assertEqual({'prompt':None,'completion':None},result['tokens'])
        self.assertEqual(0,result['model_invocations']);self.assertEqual([],self.calls)


class FollowupRuntimeTests(unittest.TestCase):
    def live_round_trip(self,provider,ui=False):
        base=config.BASE_DIR/'artifacts/runtime';base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='followups-sdk-',dir=base) as directory:
            root=Path(directory);calls=[];clients=[]
            date=(config.today()+timedelta(days=1)).isoformat()
            def respond(request):
                body=json.loads(request.content);calls.append(body)
                if body.get('response_format')=={'type':'json_object'}:
                    self.assertNotIn('tools',body)
                    payload=json.loads(body['messages'][-1]['content'])
                    message={'content':json.dumps({'suggestions':[{'id':r['id'],'question':r['question']}
                        for r in payload['candidates'][:2]]},ensure_ascii=False)}
                elif body['messages'][-1]['role']=='user':
                    args={'from_city':'上海','to_city':'杭州','date':date,'kind':'高铁','seat_type':'二等座'}
                    message={'content':None,'tool_calls':[{'id':'fixture-query-'+str(len(calls)),
                        'type':'function','function':{'name':'query_tickets','arguments':json.dumps(args,ensure_ascii=False)}}]}
                else:
                    result=json.loads(body['messages'][-1]['content'])
                    lines=[f"车次{r['train_no']}，{r['from_city']}到{r['to_city']}，日期{r['date']}，出发{r['depart']}，到达{r['arrive']}，{r['seat_type']}，票价{r['price']}元，余票{r['seats_left']}张。"
                           for r in result['trains']]
                    message={'content':'模拟查询结果：\n'+'\n'.join(lines)}
                return httpx.Response(200,json={'id':'offline-sdk-round-trip','object':'chat.completion','created':1,
                    'model':body['model'],'choices':[{'index':0,'message':{'role':'assistant',**message},
                    'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
                    'usage':{'prompt_tokens':13,'completion_tokens':5,'total_tokens':18}})
            module=bailian_runtime if provider=='bailian' else deepseek_runtime
            original=module.make_model
            def factory(settings):
                model=original(settings,transport=httpx.MockTransport(respond));clients.append(model.http_client);return model
            env={'TICKET_DISABLE_LOCAL_SECRETS':'1','TICKET_WEB_OFFLINE_ONLY':'0',
                 'DEEPSEEK_API_KEY':'offline-test','DASHSCOPE_API_KEY':'offline-test',
                 'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
                 'DASHSCOPE_MODEL':'qwen3.8-flash','TICKET_API_USAGE_DIR':str(root/'usage'),
                 'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
            session=Conversation('user',engine='langchain',live=True,live_provider=provider,
                live_model='qwen3.8-flash' if provider=='bailian' else None,root=root,full_tools=True)
            try:
                with patch.dict(os.environ,env),patch('web.runtime.live_ready',return_value=True),patch('web.conversation.live_ready',return_value=True),patch.object(module,'make_model',side_effect=factory):
                    if ui:
                        from streamlit.testing.v1 import AppTest
                        script="""import streamlit as st
from web.conversation import user_page
st.session_state.update(default_engine='langchain',default_live=True,
    default_provider=st.session_state['fixture_provider'],default_live_model=st.session_state['fixture_model'])
user_page()
"""
                        app=AppTest.from_string(script,default_timeout=30)
                        for key,value in dict(fixture_provider=provider,fixture_model=session.live_model,
                                user_sessions=[session],user_provider_signature=('langchain',True,provider,session.live_model,'manual-live-v1')).items():
                            app.session_state[key]=value
                        app.run();self.assertEqual([],list(app.exception));self.assertEqual([],calls)
                        self.assertNotIn('user_followup_model',[b.key for b in app.checkbox])
                        if provider=='deepseek':
                            self.assertNotIn('user_allow_live',[b.key for b in app.checkbox])
                            app.run();self.assertEqual([],calls)  # Rendering never dispatches.
                        else:
                            self.assertFalse(app.checkbox(key='user_allow_live').value)
                            app.text_input(key='user_message').set_value('查明天上海到杭州的高铁二等座')
                            next(b for b in app.button if b.label=='发送').click().run()
                            self.assertEqual([],calls)  # Qwen still requires Live consent.
                            app.checkbox(key='user_allow_live').check().run()
                            self.assertEqual([],calls)
                        app.text_input(key='user_message').set_value('查明天上海到杭州的高铁二等座')
                        next(b for b in app.button if b.label=='发送').click().run()
                        self.assertEqual([],list(app.exception))
                        record=session.history[-1]
                        self.assertEqual(2,len([b for b in app.button if (b.key or '').startswith('policy_followup_')]))
                        app.run();self.assertEqual(3,len(calls))
                    else:
                        record=session.send('查明天上海到杭州的高铁二等座','one',followup_authorized=True)
                    saved=session.followups_for(record)
                    self.assertEqual('model',saved['generation_source'],saved.get('fallback_reason'))
                    self.assertEqual(3,len(calls));self.assertEqual(1,saved['http_requests'])
                    self.assertEqual({'prompt':26,'completion':10},record['tokens'])
                    self.assertEqual(['query_tickets'],record['tool_sequence'])
                    self.assertEqual(10,len(record))
                    self.assertEqual(5,len(record['steps'][0]['calls'][0]))
                    # The same request ID and subsequent history reads never regenerate.
                    request_id=next(iter(session.receipts))
                    self.assertEqual(record,session.send(record['user_msg'],request_id,followup_authorized=True))
                    self.assertEqual(saved,session.followups_for(record));self.assertEqual(3,len(calls))
            finally:
                for client in clients:client.close()

    def test_deepseek_full_agent_then_auxiliary_generation_offline(self):self.live_round_trip('deepseek')
    def test_qwen_full_agent_then_auxiliary_generation_offline(self):self.live_round_trip('bailian')

    def test_deepseek_ui_consent_automatically_includes_followups_offline(self):self.live_round_trip('deepseek',ui=True)
    def test_qwen_ui_consent_automatically_includes_followups_offline(self):self.live_round_trip('bailian',ui=True)

    def test_click_saved_ticket_question_uses_same_session_and_normal_flow(self):
        from streamlit.testing.v1 import AppTest
        env={'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1',
             'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','AGENT_RAG_MODE':''}
        script="""import streamlit as st
from web.conversation import user_page
st.session_state.update(default_engine='legacy',default_live=False,default_provider='deepseek',default_live_model=None)
user_page()
"""
        with patch.dict(os.environ,env),patch.multiple(config,PROVIDER='mock',ENGINE='legacy',MAX_STEPS=8):
            app=AppTest.from_string(script,default_timeout=30).run()
            app.text_input(key='user_message').set_value('查明天上海到杭州的高铁二等座')
            next(b for b in app.button if b.label=='发送').click().run()
            self.assertEqual([],list(app.exception))
            session=app.session_state['user_sessions'][0];sid=session.sid
            buttons=[b for b in app.button if (b.key or '').startswith('policy_followup_')]
            self.assertEqual(2,len(buttons));question=buttons[0].label
            buttons[0].click().run()
            self.assertEqual([],list(app.exception));self.assertEqual(sid,session.sid)
            self.assertEqual(question,session.history[-1]['user_msg'])
            self.assertEqual(2,len(session.history))
            with patch.object(followups,'generate_and_save',side_effect=AssertionError('history must not generate')):
                app.run();self.assertEqual([],list(app.exception))


if __name__=='__main__':unittest.main()
