"""Readback-only Web/CLI entries, intercepted HTTP, isolated evidence directories."""
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import config
try:
    import httpx
    HTTP=True
except ImportError:HTTP=False


@unittest.skipUnless(HTTP,'httpx optional in legacy environments')
class ReadbackEntryTests(unittest.TestCase):
    def setUp(self):
        from target.observability import export_payload
        from target.diagnostics import digest
        base=config.BASE_DIR/'artifacts/runtime';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'LANGCHAIN_API_KEY':'offline-entry-secret','LANGSMITH_API_KEY':'',
            'LANGCHAIN_PROJECT':'fixture','LANGSMITH_PROJECT':'','LANGCHAIN_ENDPOINT':'https://api.smith.langchain.com',
            'LANGSMITH_ENDPOINT':'','LANGCHAIN_WORKSPACE_ID':'','LANGSMITH_WORKSPACE_ID':'',
            'TICKET_LANGSMITH_EXPORT_ENABLED':'true','TICKET_DISABLE_LOCAL_SECRETS':'1',
            'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'})
        self.env.start()
        self.record={'trace_id':'entry-fixture','local_trace_saved':True,'local_sidecar_saved':True,
            'provider':'deepseek_live','reply':'模拟回复','user_msg':'模拟输入','events':[]}
        self.payload=export_payload(self.record)
        self.receipt={'remote_run_id':'00000000-0000-0000-0000-000000000001','post_http_status':202,
            'local_trace_id':'entry-fixture','project':'fixture','endpoint':'https://api.smith.langchain.com',
            'payload_sha256':digest(self.payload),'remote_status':'pending_verification','remote_verified':False,
            'timestamp':'2026-10-26T00:00:00+00:00'}
        self.calls=[]

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def respond(self,request):
        from target.diagnostics import digest
        self.calls.append(request.method);self.assertEqual(request.method,'GET')
        return httpx.Response(200,json={'id':self.receipt['remote_run_id'],'inputs':self.payload['inputs'],
            'outputs':self.payload['outputs'],'extra':{'metadata':{**self.payload['metadata'],'payload_sha256':digest(self.payload)}}})

    def session(self):
        from web.runtime import Conversation
        session=Conversation('user',engine='langchain',live=True,root=self.root/'session')
        session.agent=SimpleNamespace(langchain_engine=SimpleNamespace(last_live_run=copy.deepcopy(self.record)))
        session.remote_receipts=[copy.deepcopy(self.receipt)]
        return session

    def test_existing_export_cannot_be_reposted_from_runtime(self):
        session=self.session()
        with patch('target.observability.export_run',side_effect=AssertionError('no upload')) as upload:
            with self.assertRaisesRegex(ValueError,'read back'):session.export_last(consent=True)
            upload.assert_not_called()

    def test_runtime_readback_saves_new_receipt_without_mutating_original(self):
        session=self.session();original=copy.deepcopy(session.remote_receipts[0])
        result=session.recheck_export(consent=True,transport=httpx.MockTransport(self.respond))
        self.assertEqual(self.calls,['GET']);self.assertTrue(result['remote_verified'])
        self.assertEqual(session.remote_receipts[0],original)
        self.assertTrue((session.trace_dir/'langsmith_readbacks.jsonl').exists())
        self.assertFalse((session.trace_dir/'langsmith_exports.jsonl').exists())

    def test_frozen_export_prevents_prompt_or_projection_drift(self):
        session=self.session()
        relative='langsmith_payloads/'+self.receipt['remote_run_id']+'.json'
        path=session.trace_dir/relative;path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self.payload),encoding='utf-8')
        session.remote_receipts[0]['payload_file']=relative
        with patch('target.observability.export_payload',return_value={'inputs':{'changed':'projection drift'}}):
            result=session.recheck_export(consent=True,transport=httpx.MockTransport(self.respond))
        self.assertTrue(result['remote_verified']);self.assertEqual(self.calls,['GET'])

    def test_frozen_path_cannot_escape_trace_directory(self):
        session=self.session();session.remote_receipts[0]['payload_file']='../../.env'
        with self.assertRaisesRegex(ValueError,'Invalid frozen'):session.recheck_export(consent=True)
        self.assertFalse(self.calls)

    def test_saved_readback_is_available_after_page_rerender(self):
        session=self.session();session.trace_dir.mkdir(parents=True)
        result={**self.receipt,'remote_status':'verified','remote_verified':True,'timestamp':'2026-10-26T01:00:00+00:00'}
        (session.trace_dir/'langsmith_readbacks.jsonl').write_text(json.dumps(result)+'\n',encoding='utf-8')
        self.assertTrue(session.latest_remote_receipt()['remote_verified'])
        self.assertFalse(session.remote_receipts[0]['remote_verified'])

    def test_web_existing_id_shows_get_only_control_and_never_reposts(self):
        from streamlit.testing.v1 import AppTest
        session=self.session();app=AppTest.from_string(
            "import streamlit as st\nfrom web.conversation import show_remote_export\nshow_remote_export(st.session_state['session'])",
            default_timeout=30)
        app.session_state['session']=session
        original=session.recheck_export
        with patch.object(session,'recheck_export',side_effect=lambda **kw:original(**kw,transport=httpx.MockTransport(self.respond))):
            app.run();self.assertFalse(app.exception)
            self.assertFalse(any(b.label=='导出本轮并验证远端' for b in app.button))
            button=next(b for b in app.button if b.label=='重新核验现有远端记录（仅GET）')
            self.assertTrue(button.disabled);self.assertFalse(self.calls)
            app.checkbox[0].check().run()
            next(b for b in app.button if b.label=='重新核验现有远端记录（仅GET）').click().run()
            self.assertFalse(app.exception);self.assertTrue(session.remote_receipts[-1]['remote_verified'])
            app.run();self.assertEqual(self.calls,['GET'])

    def command(self,*,run=False,transport=None,extra=()):
        from scripts.check_langsmith_export import main
        receipt_path=self.root/'receipt.json';payload_path=self.root/'payload.json'
        receipt_path.write_text(json.dumps(self.receipt),encoding='utf-8')
        payload_path.write_text(json.dumps(self.payload),encoding='utf-8')
        args=['--receipt',str(receipt_path),'--payload',str(payload_path),'--run-id',self.receipt['remote_run_id'],*extra]
        if run:args+=['--run','--out',str(self.root/'out')]
        output=io.StringIO()
        with redirect_stdout(output):code=main(args,transport=transport)
        return code,json.loads(output.getvalue())

    def test_cli_default_is_zero_http_preflight(self):
        code,result=self.command(transport=httpx.MockTransport(lambda r:self.fail('no request')))
        self.assertEqual(code,0);self.assertEqual(result['http_requests'],0)
        self.assertFalse((self.root/'out').exists())

    def test_cli_run_is_exactly_one_get_and_preserves_old_receipt(self):
        code,result=self.command(run=True,transport=httpx.MockTransport(self.respond))
        self.assertEqual(code,0);self.assertEqual(self.calls,['GET']);self.assertTrue(result['remote_verified'])
        self.assertFalse(json.loads((self.root/'receipt.json').read_text())['remote_verified'])
        self.assertTrue((self.root/'out/result.json').is_file())

    def test_cli_404_preserves_pending_state_and_default_one_get_limit(self):
        code,result=self.command(run=True,transport=httpx.MockTransport(lambda r:httpx.Response(404,json={})))
        self.assertEqual(code,3);self.assertEqual(result['http_requests'],1)
        self.assertEqual(result['remote_status'],'pending_verification');self.assertFalse(result['remote_verified'])

    def test_cli_result_write_failure_never_reports_zero_http_after_get(self):
        original=Path.write_text
        def write(path,*args,**kw):
            if path.name=='result.json':raise OSError('unsafe path must not print')
            return original(path,*args,**kw)
        with patch.object(Path,'write_text',write):
            code,result=self.command(run=True,transport=httpx.MockTransport(self.respond))
        self.assertEqual(code,1);self.assertEqual(result['http_requests'],1)
        self.assertFalse(result['result_file_saved']);self.assertEqual(self.calls,['GET'])
