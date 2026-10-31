"""QwenCloud (sk-ws-) endpoint acceptance and explicit mismatch diagnosis."""
import os
import unittest
from unittest.mock import patch

import config
from target import bailian_runtime
from target.bailian_runtime import BailianError

QWENCLOUD = "https://ap-southeast-1.maas.qwencloudapi.com/compatible-mode/v1"


class QwenCloudEndpointTests(unittest.TestCase):
    def test_qwencloud_region_endpoint_is_accepted(self):
        with patch.object(config, "BASE_URL", QWENCLOUD), \
             patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-ws-test-key"}, clear=False):
            self.assertEqual(bailian_runtime.endpoint().hostname, "ap-southeast-1.maas.qwencloudapi.com")
            bailian_runtime.validate_configuration()

    def test_qwencloud_singapore_alias_is_accepted(self):
        with patch.object(config, "BASE_URL", "https://maas.qwencloudapi.com/compatible-mode/v1"), \
             patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-ws-test-key"}, clear=False):
            bailian_runtime.validate_configuration()

    def test_ws_key_with_dashscope_endpoint_fails_fast_with_clear_category(self):
        with patch.object(config, "BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"), \
             patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-ws-test-key"}, clear=False):
            with self.assertRaises(BailianError) as caught:
                bailian_runtime.validate_configuration()
            self.assertEqual(caught.exception.category, "qwencloud_key_requires_qwencloud_endpoint")

    def test_legacy_dashscope_key_still_works_on_dashscope_endpoint(self):
        with patch.object(config, "BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"), \
             patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-legacy-dashscope"}, clear=False):
            bailian_runtime.validate_configuration()


if __name__ == "__main__":
    unittest.main()
