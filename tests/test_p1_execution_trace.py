"""P1 isolated execution/replay checks. All model HTTP uses local test transports."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from streamlit.testing.v1 import AppTest
from web.runtime import Conversation, scoped
from web.run_view import execution_stages, load_events
from web.session_store import restore_session


class ExecutionTraceTests(unittest.TestCase):
    def setUp(self):
        base=config.BASE_DIR/'artifacts/runtime';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base)
        self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'AGENT_RAG_MODE':'','RAG_ALLOW_NETWORK':'0',
            'TICKET_DISABLE_LOCAL_SECRETS':'1','LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'})
        self.env.start()
        self.settings=patch.multiple(config,PROVIDER='mock',ENGINE='legacy',USE_VECTOR_RAG=False,USE_HTTP_MOCK=False)
        self.settings.start()

    def tearDown(self):
        self.settings.stop();self.env.stop();self.tmp.cleanup()

    def session(self,engine='legacy',mode='user'):
        return Conversation(mode,engine=engine,root=self.root/engine,interactive=True)

    def events(self,s,index=-1):
        return load_events(s.trace_dir,s.audits[index]['trace_id'],s.sid)[0]

    def assert_links(self,rows):
        ids={r['event_id'] for r in rows}
        self.assertEqual(len(ids),len(rows))
        self.assertTrue(all(r.get('parent_event_id') is None or r['parent_event_id'] in ids for r in rows))
        for previous,current in zip(rows,rows[1:]):
            self.assertEqual(previous['event_id'],current['previous_event_id'])

    def test_both_mock_engines_link_model_rag_tool_and_reply(self):
        for engine in ('legacy','langchain'):
            with self.subTest(engine=engine):
                s=self.session(engine);result=s.send('锁座后多久必须完成支付？','first')
                rows=self.events(s);self.assert_links(rows)
                self.assertEqual({r['run_id'] for r in rows},{s.audits[-1]['trace_id']})
                self.assertEqual({r['session_id'] for r in rows},{s.sid})
                kinds=[r['event_type'] for r in rows]
                for kind in ('user_input','agent_start','model_start','model_end','model_tool_proposed',
                    'rag_start','rag_result','tool_start','tool_result','tool_message_created',
                    'tool_result_in_model_request','run_finished','agent_returned'):
                    self.assertIn(kind,kinds)
                retrieval=next(r for r in rows if r['event_type']=='rag_result')
                start=next(r for r in rows if r['event_type']=='rag_start')
                self.assertEqual(retrieval['parent_event_id'],start['event_id'])
                self.assertEqual(retrieval['retrieval_id'],start['retrieval_id'])
                proposal=next(r for r in rows if r['event_type']=='model_tool_proposed')
                self.assertEqual(retrieval['call_id'],proposal['call_id'])
                execution=next(e for e in rows if e['event_type']=='tool_result')
                self.assertEqual(execution['args'],proposal['args'])
                self.assertTrue(execution['started_at'])
                self.assertIn('requires_confirmation',execution)
                self.assertIn('P11',[h['doc_id'] for h in retrieval['documents']])
                self.assertIn('P11',result['reply'])
                self.assertTrue(retrieval['corpus_version'])
                self.assertIsNone(retrieval['index_version'])
                self.assertEqual(len(result),10)
                self.assertTrue(all(len(c)==5 for step in result['steps'] for c in step['calls']))

    def test_multiple_runs_keep_session_but_never_mix_events(self):
        s=self.session()
        s.send('查明天上海到杭州的高铁二等座','one')
        s.send('锁座后多久必须完成支付？','two')
        first,second=self.events(s,0),self.events(s,1)
        self.assertNotEqual(first[0]['run_id'],second[0]['run_id'])
        self.assertEqual(first[0]['session_id'],second[0]['session_id'])
        self.assertFalse({e['event_id'] for e in first}&{e['event_id'] for e in second})
        self.assert_links(first);self.assert_links(second)

    def test_matching_run_id_from_another_session_is_excluded(self):
        s=self.session();s.send('查明天上海到杭州的高铁','one')
        rows=self.events(s)
        with (s.trace_dir/'run_events.jsonl').open('a',encoding='utf8') as f:
            f.write(json.dumps(dict(rows[0],session_id='other',event_id='foreign'))+'\n')
        self.assertEqual(self.events(s),rows)

    def test_previous_policy_in_model_context_is_not_current_retrieval(self):
        s=self.session();s.send('锁座后多久必须完成支付？','policy')
        s.send('查明天上海到杭州的高铁','query')
        rows=self.events(s)
        self.assertTrue(any(e['event_type']=='tool_result_in_model_request' and e.get('tool')=='search_policy' for e in rows))
        self.assertFalse(any(e['event_type']=='rag_result' for e in rows))
        self.assertEqual(next(p['status'] for p in execution_stages(rows) if p['stage']=='RAG 检索'),'未发生')

    def test_failure_absence_and_missing_are_different(self):
        s=self.session();s.send('查明天上海到杭州的高铁','one')
        states={r['stage']:r['status'] for r in execution_stages(self.events(s))}
        self.assertEqual(states['RAG 检索'],'未发生')
        self.assertEqual(states['用户确认'],'未发生')
        self.assertTrue(all(r['status']=='未记录' for r in execution_stages([])))
        failed=execution_stages([{'event_type':'rag_error','status':'failed'}])
        self.assertEqual(next(r for r in failed if r['stage']=='RAG 检索')['status'],'失败')
        partial=execution_stages([{'event_type':'user_input','status':'recorded'}])
        self.assertEqual(next(r for r in partial if r['stage']=='RAG 检索')['status'],'未记录')

    def test_invalid_tool_has_no_success_or_execution_start(self):
        from target.run_events import bind,capture,finish
        from target.trace import Trace
        from target.tools import dispatch
        path=self.root/'blocked.jsonl'
        with capture(path):
            bind(Trace('blocked','支付'))
            _,ok,_=dispatch('pay_order',{})
            finish()
        self.assertFalse(ok)
        rows=[json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
        self.assertNotIn('tool_start',[e['event_type'] for e in rows])
        result=next(r for r in rows if r['event_type']=='tool_result')
        self.assertEqual(result['status'],'blocked');self.assertIs(result['executed'],False)
        self.assertFalse(any(r['event_type']=='tool_result' and r['status']=='succeeded' for r in rows))

    def test_policy_citations_join_only_current_retrieval_and_delivery(self):
        from web.policy_interaction import policy_view
        s=self.session();record=s.send('锁座后多久必须完成支付？','one')
        view=policy_view(s.sid,s.audits[-1]['trace_id'],events=self.events(s),audit=s.audits[-1])
        p11=next(r for r in view['evidence'] if r['doc_id']=='P11')
        self.assertTrue(p11['entered_context']);self.assertTrue(p11['content'])
        self.assertTrue(p11['event_ids']);self.assertEqual(p11['run_id'],s.audits[-1]['trace_id'])
        self.assertEqual(p11['support_status'],'尚未验证')
        self.assertIn('P11',record['reply'])

    def test_restore_reads_original_audits_without_constructing_agent_or_writing(self):
        s=self.session();s.send('查明天上海到杭州的高铁','one');s.send('锁座后多久必须完成支付？','two')
        files={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in s.root.rglob('*') if p.is_file()}
        with patch('web.runtime.Agent') as model:
            recovered=restore_session(s.root,expected_sid=s.sid)
            self.assertTrue(recovered.read_only);self.assertIsNone(recovered.agent)
            self.assertEqual(recovered.history,s.history)
            self.assertEqual([a['trace_id'] for a in recovered.audits],[a['trace_id'] for a in s.audits])
            self.assertEqual(recovered.results,s.results)
            with self.assertRaises(ValueError):recovered.send('支付订单','no')
            with self.assertRaises(ValueError):recovered.confirm_action(True,'no')
            model.assert_not_called()
        self.assertEqual(files,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

    def test_restore_rejects_other_session_and_does_not_copy_foreign_audit(self):
        s=self.session();s.send('查明天上海到杭州的高铁','one')
        with self.assertRaises(ValueError):restore_session(s.root,expected_sid='web-000000000000')
        path=s.trace_dir/'audit_runs.jsonl'
        with path.open('a',encoding='utf8') as f:
            f.write(json.dumps(dict(s.audits[0],trace_id='foreign',public_trace={'session_id':'other'}))+'\n')
        recovered=restore_session(s.root,expected_sid=s.sid)
        self.assertEqual(len(recovered.audits),1)

    def test_direct_agent_entry_also_records_and_save_false_stays_opt_out(self):
        from target.agent import Agent
        s=self.session();s.send('查明天上海到杭州的高铁','seed')
        with scoped(s._values()):
            agent=Agent();result=agent.chat('direct','锁座后多久必须完成支付？')
            rid=agent.last_audit_report['trace_id']
            rows=load_events(s.trace_dir,rid,'direct')[0]
            self.assertEqual(rows[-1]['event_type'],'agent_returned')
            self.assertIn('run_finished',[e['event_type'] for e in rows])
            before=(s.trace_dir/'run_events.jsonl').read_bytes()
            agent.chat('direct','查明天上海到杭州的高铁',save_trace=False)
            self.assertEqual((s.trace_dir/'run_events.jsonl').read_bytes(),before)

    def test_provider_exception_is_recorded_without_false_answer(self):
        s=self.session();s.send('查明天上海到杭州的高铁','one')
        with patch.object(s.agent.provider,'chat',side_effect=TimeoutError('private-error-do-not-log')):
            with self.assertRaises(RuntimeError):s.send('锁座后多久必须完成支付？','two')
        rows=self.events(s)
        self.assertIn('model_error',[e['event_type'] for e in rows])
        self.assertEqual(rows[-1]['event_type'],'agent_error')
        self.assertEqual(next(e for e in rows if e['event_type']=='run_finished')['status'],'failed')
        self.assertNotIn('private-error-do-not-log',json.dumps(rows))
        self.assertEqual(len(s.history),1)

    def test_actual_mock_purchase_records_confirmation_in_same_run(self):
        s=self.session();s.send('订明天上海到杭州的高铁','one',confirmation={'approved':True,'proposal':{'message':'订票'}})
        rows=self.events(s);confirmation=next(e for e in rows if e['event_type']=='user_confirmation')
        self.assertTrue(confirmation['approved'])
        self.assertEqual(confirmation['run_id'],s.audits[-1]['trace_id'])
        self.assertLess(rows.index(confirmation),next(i for i,e in enumerate(rows) if e['event_type']=='tool_start'))
        self.assertIn('create_order',s.history[-1]['tool_sequence'])

    def test_failed_current_run_does_not_reuse_previous_success_trace(self):
        s=Conversation('user',engine='legacy');s.send('查明天上海到杭州的高铁','one')
        with patch.object(s.agent.provider,'chat',side_effect=TimeoutError()):
            with self.assertRaises(RuntimeError):s.send('锁座后多久必须完成支付？','two')
        app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30)
        app.session_state['user_sessions']=[s]
        app.session_state['user_provider_signature']=('legacy',False,'deepseek',None,'manual-live-v1')
        app.run();self.assertFalse(app.exception)
        self.assertTrue(any('不复用上一条成功 Trace' in c.value for c in app.caption))
        self.assertNotIn('执行记录与 Trace 证据',[e.label for e in app.expander])

    def test_refresh_by_session_url_is_read_only_and_does_not_reexecute(self):
        s=Conversation('user',engine='legacy');s.send('锁座后多久必须完成支付？','one')
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in s.root.rglob('*') if p.is_file()}
        app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30)
        app.query_params['session_id']=s.sid
        with patch('web.runtime.Agent') as model:
            app.run();self.assertFalse(app.exception)
            recovered=app.session_state['user_sessions'][0]
            self.assertEqual(recovered.sid,s.sid);self.assertEqual(len(recovered.history),1)
            self.assertTrue(next(b for b in app.button if b.label=='发送').disabled)
            app.run();model.assert_not_called()
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_selected_run_opens_correct_developer_evidence(self):
        s=Conversation('user',engine='legacy');s.send('查明天上海到杭州的高铁','one');s.send('锁座后多久必须完成支付？','two')
        app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30)
        app.session_state['user_sessions']=[s]
        app.session_state['user_provider_signature']=('legacy',False,'deepseek',None,'manual-live-v1')
        app.run();self.assertFalse(app.exception)
        app.selectbox(key='user_run_'+s.sid).select(0).run()
        summary=next(m.value for m in app.markdown if 'class="ta-summary"' in m.value)
        self.assertIn(s.audits[0]['trace_id'],summary)
        app.button(key='user_to_trace_'+s.sid).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='workspace_mode').value,'开发者工作台')
        self.assertEqual(app.selectbox(key='dev_run_index').value,0)

    def test_deepseek_and_qwen_sdk_paths_use_same_events_with_offline_http_only(self):
        import httpx
        from target.agent import Agent
        from target import deepseek_runtime,bailian_runtime
        from data.seed import build_db
        import contextlib,io
        for provider,runtime,model_name,address in (
            ('deepseek',deepseek_runtime,'deepseek-flash','https://api.deepseek.com'),
            ('bailian',bailian_runtime,'qwen3.8-flash','https://dashscope.aliyuncs.com/compatible-mode/v1')):
            with self.subTest(provider=provider):
                folder=self.root/provider;folder.mkdir()
                requests=[]
                def respond(request):
                    body=json.loads(request.content);requests.append(body)
                    message=({'role':'assistant','content':None,'tool_calls':[{'id':'p1-policy-call','type':'function',
                        'function':{'name':'search_policy','arguments':json.dumps({'question':'锁座后多久必须完成支付？'},ensure_ascii=False)}}]}
                        if len(requests)==1 else {'role':'assistant','content':'根据 P11（本地模拟政策），锁座有效期15分钟，过期未支付自动释放库存。'})
                    return httpx.Response(200,json={'id':'offline-p1-only','object':'chat.completion','created':1,
                        'model':model_name,'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if len(requests)==1 else 'stop'}],
                        'usage':{'prompt_tokens':12,'completion_tokens':8,'total_tokens':20}})
                env={'DEEPSEEK_API_KEY':'offline-p1-fixture','DASHSCOPE_API_KEY':'offline-p1-fixture',
                    'DASHSCOPE_MODEL':model_name,'DASHSCOPE_BASE_URL':address,
                    'DEEPSEEK_LIVE_TEST_PROFILE':'read_only','DEEPSEEK_THINKING':'disabled',
                    'DEEPSEEK_BUDGET_PATH':str(folder/'generation.db'),'BAILIAN_BUDGET_PATH':str(folder/'generation.db'),
                    'TICKET_API_USAGE_DIR':str(folder/'usage')}
                values={'PROVIDER':provider,'ENGINE':'langchain','LC_TOOLSET':'read_only',
                    'MODEL_NAME':model_name,'BASE_URL':address,'API_KEY':'offline-p1-fixture',
                    'DB_PATH':folder/'tickets.db','TRACE_DIR':folder/'traces'}
                with scoped(values,env):
                    with contextlib.redirect_stdout(io.StringIO()):build_db(config.DB_PATH)
                    model=runtime.make_model(runtime.Settings.from_env(),transport=httpx.MockTransport(respond))
                    try:
                        agent=Agent(model=model)
                        result=agent.chat('offline-p1-'+provider,'锁座后多久必须完成支付？')
                        rows=load_events(config.TRACE_DIR,agent.last_audit_report['trace_id'],result['session_id'])[0]
                    finally:model.root_client.close()
                self.assertEqual(len(requests),2)
                self.assertEqual(result['tool_sequence'],['search_policy'])
                self.assertIn('P11',result['reply']);self.assert_links(rows)
                self.assertIn('rag_result',[r['event_type'] for r in rows])
                self.assertIn('tool_result_in_model_request',[r['event_type'] for r in rows])
                self.assertTrue(all(e.get('execution_mode')=='live_configured' for e in rows if e['event_type']=='model_end'))
                self.assertNotIn('offline-p1-fixture',json.dumps(rows))


if __name__=='__main__':unittest.main()
