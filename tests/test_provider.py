"""真实 Provider 的适配器自测：模拟 SDK 响应，不是联网模型验证。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import config
from target.providers import OpenAIProvider, _to_api


class ProviderTests(unittest.TestCase):
    def test_ids_usage_and_malformed_json(self):
        with patch.object(config, "API_KEY", "local-adapter-test-placeholder"):
            provider = OpenAIProvider()
        response = NS(choices=[NS(message=NS(content=None, tool_calls=[NS(id="server_call_1", function=NS(name="query_tickets", arguments="{invalid"))]))], usage=NS(prompt_tokens=12, completion_tokens=7))
        with patch.object(provider.client.chat.completions, "create", return_value=response):
            msg = provider.chat([], [])
        self.assertEqual(msg["tool_calls"][0]["id"], "server_call_1")
        self.assertEqual(provider.last_usage, {"prompt":12, "completion":7})
        self.assertEqual(_to_api([msg])[0]["tool_calls"][0]["function"]["arguments"], "{invalid")
        provider.client.close()

    def test_missing_key(self):
        with patch.object(config, "API_KEY", ""):
            with self.assertRaises(ValueError):
                OpenAIProvider()


if __name__ == "__main__":
    unittest.main()
