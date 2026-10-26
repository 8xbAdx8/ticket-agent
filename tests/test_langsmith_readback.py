"""LangSmith asynchronous ingestion tests. MockTransport only; no paid or remote calls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
try:
    import httpx
    HTTP=True
except ImportError:HTTP=False
from target import observability as obs
from target.diagnostics import digest


@unittest.skipUnless(HTTP,'httpx optional in legacy environments; all requests are fixtures')
class LangSmithReadbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'LANGCHAIN_API_KEY':'offline-readback-secret','LANGSMITH_API_KEY':'',
            'LANGCHAIN_PROJECT':'fixture','LANGSMITH_PROJECT':'','LANGCHAIN_ENDPOINT':'https://api.smith.langchain.com',
            'LANGSMITH_ENDPOINT':'','LANGCHAIN_WORKSPACE_ID':'','LANGSMITH_WORKSPACE_ID':'',
            'TICKET_LANGSMITH_EXPORT_ENABLED':'true','LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'})
        self.env.start();self.sleep=patch.object(obs.time,'sleep');self.sleeper=self.sleep.start()
        self.record={'trace_id':'offline-local','provider':'deepseek_live','mode':'live','user_msg':'模拟问题',
            'reply':'模拟回答','tokens':None,'local_trace_saved':True,'local_sidecar_saved':True,'events':[]}
        self.calls=[];self.body={}

    def tearDown(self):self.sleep.stop();self.env.stop();self.tmp.cleanup()

    def export(self,respond,**kwargs):
        def handle(request):
            self.calls.append((request.method,request.url.path))
            if request.method=='POST':self.body.update(json.loads(request.content))
            return respond(request)
        return obs.export_run(self.record,consent=True,trace_dir=self.root,transport=httpx.MockTransport(handle),**kwargs)

    def matching(self):return httpx.Response(200,json=copy.deepcopy(self.body),headers={'x-request-id':'fixture-readback-200'})

    def receipt(self,payload):
        return {'remote_run_id':'00000000-0000-0000-0000-000000000001','post_http_status':202,
            'endpoint':'https://api.smith.langchain.com','project':'fixture','payload_sha256':digest(payload),
            'local_trace_id':'offline-local'}

    def test_202_acknowledgement_needs_no_response_id_and_get_checks_payload(self):
        result=self.export(lambda r:httpx.Response(202,json={'message':'accepted'}) if r.method=='POST' else self.matching())
        self.assertTrue(result['remote_verified']);self.assertEqual(result['id_source'],'client_supplied')
        self.assertEqual(result['remote_run_id'],self.body['id']);self.assertEqual(len(self.calls),2)
        self.assertTrue(all(result['readback_matches'].values()));self.sleeper.assert_not_called()

    def test_202_then_temporary_404_then_200_only_polls_get(self):
        def respond(r):
            if r.method=='POST':return httpx.Response(202,json={})
            return httpx.Response(404,json={'detail':'not found'}) if len(self.calls)==2 else self.matching()
        result=self.export(respond)
        self.assertTrue(result['remote_verified']);self.assertNotIn('error',result)
        self.assertEqual([m for m,_ in self.calls],['POST','GET','GET']);self.sleeper.assert_called_once_with(1)
        self.assertEqual([r['http_status'] for r in result['http_attempts']],[202,404,200])

    def test_persistent_404_is_pending_and_stops_after_three_gets(self):
        result=self.export(lambda r:httpx.Response(202 if r.method=='POST' else 404,json={}))
        self.assertEqual(result['remote_status'],'pending_verification');self.assertFalse(result['remote_verified'])
        self.assertEqual([m for m,_ in self.calls],['POST','GET','GET','GET'])
        self.assertEqual([c.args[0] for c in self.sleeper.call_args_list],[1,2])

    def test_legacy_201_missing_run_stops_without_assuming_async(self):
        result=self.export(lambda r:httpx.Response(201 if r.method=='POST' else 404,json={}))
        self.assertEqual(result['remote_status'],'failed');self.assertEqual(len(self.calls),2)
        self.sleeper.assert_not_called()

    def test_get_401_stops_as_authentication_failed(self):self.check_get_error(401,'failed','authentication_failed')
    def test_get_403_stops_as_permission_denied(self):self.check_get_error(403,'failed','permission_denied')
    def test_get_429_is_pending_without_retry(self):self.check_get_error(429,'pending_verification','rate_limited')
    def test_get_500_is_pending_without_retry(self):self.check_get_error(500,'pending_verification','remote_server_error')
    def test_get_503_is_pending_without_retry(self):self.check_get_error(503,'pending_verification','remote_server_error')

    def check_get_error(self,status,state,category):
        result=self.export(lambda r:httpx.Response(202 if r.method=='POST' else status,json={}))
        self.assertEqual(result['remote_status'],state);self.assertEqual(result['error']['category'],category)
        self.assertEqual(result['get_http_status'],status);self.assertEqual(len(self.calls),2)
        self.sleeper.assert_not_called();self.assertFalse(result['remote_verified'])

    def test_wrong_remote_id_is_not_verified(self):
        def respond(r):
            if r.method=='POST':return httpx.Response(202,json={})
            data=copy.deepcopy(self.body);data['id']='other';return httpx.Response(200,json=data)
        result=self.export(respond)
        self.assertFalse(result['remote_verified']);self.assertFalse(result['readback_matches']['id'])

    def test_wrong_outputs_are_not_verified(self):
        def respond(r):
            if r.method=='POST':return httpx.Response(202,json={})
            data=copy.deepcopy(self.body);data['outputs']['reply']='wrong';return httpx.Response(200,json=data)
        result=self.export(respond)
        self.assertFalse(result['remote_verified']);self.assertFalse(result['readback_matches']['outputs'])

    def test_same_hash_but_tampered_metadata_is_not_verified(self):
        def respond(r):
            if r.method=='POST':return httpx.Response(202,json={})
            data=copy.deepcopy(self.body);data['extra']['metadata']['provider']='wrong';return httpx.Response(200,json=data)
        result=self.export(respond)
        self.assertFalse(result['remote_verified']);self.assertFalse(result['readback_matches']['metadata'])

    def test_wrong_post_response_id_is_not_adopted(self):
        result=self.export(lambda r:httpx.Response(202,json={'id':'00000000-0000-0000-0000-000000000999'}))
        self.assertEqual(len(self.calls),1);self.assertEqual(result['error']['category'],'post_response_id_mismatch')
        self.assertEqual(result['remote_run_id'],self.body['id']);self.assertFalse(result['remote_verified'])

    def test_post_timeout_has_unknown_outcome_and_never_reposts(self):
        def respond(r):raise httpx.ReadTimeout('offline-readback-secret Authorization: unsafe')
        result=self.export(respond)
        self.assertEqual(result['remote_status'],'upload_outcome_unknown');self.assertEqual(result['error']['category'],'timeout')
        self.assertEqual(len(self.calls),1);self.assertNotIn('offline-readback-secret',json.dumps(result))

    def test_get_timeout_is_pending_and_never_retries(self):
        def respond(r):
            if r.method=='POST':return httpx.Response(202,json={})
            raise httpx.ReadTimeout('unsafe')
        result=self.export(respond)
        self.assertEqual(result['remote_status'],'pending_verification');self.assertEqual(result['error']['category'],'timeout')
        self.assertEqual(len(self.calls),2);self.sleeper.assert_not_called()

    def test_invalid_readback_json_fails_without_raw_response_log(self):
        result=self.export(lambda r:httpx.Response(202,json={}) if r.method=='POST' else httpx.Response(200,content=b'offline-readback-secret'))
        self.assertFalse(result['remote_verified']);self.assertEqual(result['error']['category'],'invalid_readback_response')
        self.assertNotIn('offline-readback-secret',(self.root/'langsmith_exports.jsonl').read_text())

    def test_invalid_readback_shape_fails(self):
        result=self.export(lambda r:httpx.Response(202,json={}) if r.method=='POST' else httpx.Response(200,json=[]))
        self.assertEqual(result['error']['category'],'invalid_readback_response')

    def test_post_permission_failure_does_not_get_or_retry(self):
        result=self.export(lambda r:httpx.Response(403,json={'detail':'offline-readback-secret'}))
        self.assertEqual(len(self.calls),1);self.assertEqual(result['error']['category'],'permission_denied')
        self.assertNotIn('offline-readback-secret',json.dumps(result))

    def test_frozen_payload_and_original_record_are_preserved(self):
        original=copy.deepcopy(self.record)
        result=self.export(lambda r:httpx.Response(202,json={}) if r.method=='POST' else self.matching())
        self.assertEqual(self.record,original)
        frozen=json.loads((self.root/result['payload_file']).read_text(encoding='utf-8'))
        self.assertEqual(digest(frozen),result['payload_sha256'])
        self.assertEqual(result['generation_requests'],0);self.assertTrue(result['receipt_saved'])

    def test_existing_run_default_is_one_get_and_no_post(self):
        payload=obs.export_payload(self.record);receipt=self.receipt(payload);original=copy.deepcopy(receipt)
        def respond(r):
            self.calls.append(r.method)
            return httpx.Response(200,json={'id':receipt['remote_run_id'],'inputs':payload['inputs'],
                'outputs':payload['outputs'],'extra':{'metadata':{**payload['metadata'],'payload_sha256':digest(payload)}}})
        result=obs.verify_existing(receipt,payload,consent=True,transport=httpx.MockTransport(respond),trace_dir=self.root)
        self.assertTrue(result['remote_verified']);self.assertEqual(self.calls,['GET'])
        self.assertEqual(result['upload_attempts'],0);self.assertEqual(receipt,original)
        self.assertTrue((self.root/'langsmith_readbacks.jsonl').is_file())
        self.assertFalse((self.root/'langsmith_exports.jsonl').exists())

    def test_existing_run_404_is_pending_without_implicit_polling(self):
        payload=obs.export_payload(self.record)
        result=obs.verify_existing(self.receipt(payload),payload,consent=True,transport=httpx.MockTransport(lambda r:httpx.Response(404,json={})))
        self.assertEqual(result['remote_status'],'pending_verification');self.assertEqual(result['http_requests'],1)

    def test_existing_run_explicit_polling_has_same_id_and_zero_post(self):
        payload=obs.export_payload(self.record);receipt=self.receipt(payload)
        def respond(r):
            self.calls.append(r.method);self.assertTrue(r.url.path.endswith(receipt['remote_run_id']))
            if len(self.calls)==1:return httpx.Response(404,json={})
            return httpx.Response(200,json={'id':receipt['remote_run_id'],'inputs':payload['inputs'],'outputs':payload['outputs'],
                'extra':{'metadata':{**payload['metadata'],'payload_sha256':digest(payload)}}})
        result=obs.verify_existing(receipt,payload,consent=True,max_read_attempts=3,transport=httpx.MockTransport(respond))
        self.assertTrue(result['remote_verified']);self.assertEqual(self.calls,['GET','GET'])

    def test_missing_consent_never_sends(self):
        payload=obs.export_payload(self.record)
        result=obs.verify_existing(self.receipt(payload),payload,transport=httpx.MockTransport(lambda r:self.fail('must not send')))
        self.assertEqual(result['http_requests'],0)

    def test_changed_workspace_never_sends(self):
        payload=obs.export_payload(self.record);receipt={**self.receipt(payload),'workspace_sha256':hashlib.sha256(b'original').hexdigest()}
        result=obs.verify_existing(receipt,payload,consent=True,transport=httpx.MockTransport(lambda r:self.fail('must not send')))
        self.assertEqual(result['http_requests'],0);self.assertEqual(result['error']['category'],'original_workspace_required')

    def test_changed_payload_never_sends(self):
        payload=obs.export_payload(self.record);receipt=self.receipt(payload);payload['outputs']['reply']='changed'
        result=obs.verify_existing(receipt,payload,consent=True,transport=httpx.MockTransport(lambda r:self.fail('must not send')))
        self.assertEqual(result['http_requests'],0);self.assertFalse(result['remote_verified'])

    def test_invalid_attempt_budget_never_sends(self):
        for limit in (0,4,False):
            with self.subTest(limit=limit):
                result=self.export(lambda r:self.fail('must not send'),max_read_attempts=limit)
                self.assertEqual(result['http_requests'],0)

    def test_unknown_post_outcome_can_be_rechecked_without_new_upload(self):
        payload=obs.export_payload(self.record);receipt=self.receipt(payload)
        receipt.pop('post_http_status');receipt['remote_status']='upload_outcome_unknown'
        result=obs.verify_existing(receipt,payload,consent=True,transport=httpx.MockTransport(lambda r:httpx.Response(404,json={})))
        self.assertEqual(result['remote_status'],'pending_verification');self.assertEqual(result['upload_attempts'],0)
