"""Offline HTTP transport evidence; no network or provider credentials."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import httpx
except ImportError:
    httpx = None
import config
from target.request_accounting import capture
from target.deepseek_runtime import Settings as DeepSettings, guarded_client as deep_client
from target.bailian_runtime import Settings as BailianSettings, guarded_client as bailian_client


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


@unittest.skipUnless(httpx is not None, 'HTTP transport dependency required')
class ActualDispatchSnapshot(unittest.TestCase):
    def test_real_payload_snapshot_for_each_provider_is_hashed_and_no_prompt_or_key_is_saved(self):
        tools = [{'type':'function','function':{'name':'query_tickets','parameters':{'type':'object','properties':{'date':{'type':'string'}}}}},
                 {'type':'function','function':{'name':'search_policy','parameters':{'type':'object','properties':{'question':{'type':'string'}}}}}]
        for name in ('deepseek','bailian'):
            with self.subTest(provider=name), tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'TICKET_API_USAGE_DIR':str(Path(temp)/'usage')}):
                is_deep = name == 'deepseek'
                model = 'deepseek-flash' if is_deep else 'qwen3.8-flash'
                base = 'https://api.deepseek.com' if is_deep else 'https://dashscope.aliyuncs.com/compatible-mode/v1'
                body={'model':model,'messages':[{'role':'system','content':'SENSITIVE_PROMPT_MARKER'}, {'role':'user','content':'hello'}], 'tools':tools,'max_tokens':16}
                if is_deep:body['thinking']={'type':'disabled'}
                settings = (DeepSettings if is_deep else BailianSettings)(ledger_path=Path(temp)/'unused.db')
                events=[]
                with patch.multiple(config,BASE_URL=base,MODEL_NAME=model):
                    factory=deep_client if is_deep else bailian_client
                    with factory(settings,transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'model':model}))) as client, capture(events,'trace-offline',1):
                        client.post(base+'/chat/completions',json=body,headers={'Authorization':'Bearer SENSITIVE_CREDENTIAL_MARKER'})
                event=next(e for e in events if e['event']=='http_request')
                snap=event['dispatch_snapshot']
                self.assertEqual(snap['bound_tools'],['query_tickets','search_policy'])
                self.assertEqual(snap['tool_schemas_sha256'],digest(tools))
                self.assertEqual(snap['tool_schema_sha256'],{t['function']['name']:digest(t) for t in tools})
                self.assertEqual(snap['system_prompt_sha256'],digest([body['messages'][0]]))
                self.assertEqual(snap['tool_permission'],['query_tickets','search_policy'])
                self.assertNotIn('SENSITIVE_PROMPT_MARKER',json.dumps(events))
                self.assertNotIn('SENSITIVE_CREDENTIAL_MARKER',json.dumps(events))
                self.assertIn('dispatch intent',snap['scope'])

    def test_absent_optional_fields_are_not_fabricated(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'TICKET_API_USAGE_DIR':str(Path(temp)/'usage')}):
            body={'model':'deepseek-flash','messages':[{'role':'user','content':'hello'}],'max_tokens':16,'thinking':{'type':'disabled'}}
            events=[]
            with deep_client(DeepSettings(ledger_path=Path(temp)/'unused.db'),transport=httpx.MockTransport(lambda req:httpx.Response(200,json={}))) as client, capture(events,'trace-offline',1):
                client.post('https://api.deepseek.com/chat/completions',json=body)
            snap=next(e for e in events if e['event']=='http_request')['dispatch_snapshot']
            self.assertIsNone(snap['bound_tools']);self.assertIsNone(snap['tool_schemas_sha256']);self.assertIsNone(snap['system_prompt_sha256'])

if __name__=='__main__':unittest.main()
