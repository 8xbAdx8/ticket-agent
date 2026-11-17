import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from target.deepseek_runtime import Settings
from target.bailian_runtime import Settings as BailianSettings

class MutationPresetsTests(unittest.TestCase):
 def test_live_tool_cap_default_is_eight(self):
  with patch.dict('os.environ',{'DEEPSEEK_LIVE_TEST_PROFILE':'read_only','DEEPSEEK_MAX_TOOL_CALLS':'8'},clear=False):
   self.assertEqual(Settings.from_env().max_tool_calls,8)
   self.assertEqual(BailianSettings.from_env().max_tool_calls,8)
 def test_examples_are_selectable_and_do_not_enable_fault(self):
  app=AppTest.from_string('from web.laboratory import lab_page\nlab_page()').run(timeout=20)
  scene=next(x for x in app.selectbox if x.label=='测试场景')
  scene.select('M3 重复调用').run(timeout=20)
  self.assertFalse(app.exception)
  self.assertFalse(app.checkbox(key='lab_mutation_repeat_call').value)
  self.assertIn('上海到杭州',app.text_input(key='lab_message_M3 重复调用').value)
  self.assertTrue(any('配套开关' in c.value for c in app.caption))
  next(x for x in app.selectbox if x.label=='测试场景').select('M8 并发重复订单（离线）').run(timeout=20)
  self.assertFalse(app.exception)
