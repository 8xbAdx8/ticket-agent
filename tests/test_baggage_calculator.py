import unittest
from decimal import Decimal
from target.baggage import calculate_baggage

class BaggageTests(unittest.TestCase):
 def test_policy_boundaries(self):
  self.assertEqual(Decimal(calculate_baggage('成人',20,50,50,60)['weight_fee_yuan']),0)
  self.assertEqual(Decimal(calculate_baggage('成人','20.5',50,50,60)['weight_fee_yuan']),Decimal('2.5'))
  self.assertEqual(Decimal(calculate_baggage('儿童',12,50,50,60)['weight_fee_yuan']),10)
  self.assertEqual(calculate_baggage('成人',20,50,50,60)['size_status'],'符合')
  self.assertIn('未说明',calculate_baggage('成人',20,51,50,60)['size_status'])
 def test_invalid_input(self):
  for v in ('-1','NaN','Infinity','abc'):
   with self.assertRaises(ValueError):calculate_baggage('成人',v,10,10,10)
  with self.assertRaises(ValueError):calculate_baggage('成人',10,0,10,10)

 def test_web_calculator_displays_weight_and_size(self):
  from streamlit.testing.v1 import AppTest
  app=AppTest.from_string('from web.conversation import user_page\nuser_page()')
  for key,value in {'default_engine':'legacy','default_live':False,'default_provider':'deepseek','default_live_model':None}.items():app.session_state[key]=value
  app.run(timeout=15)
  for key,value in {'baggage_weight':'22','baggage_length':'60','baggage_width':'60','baggage_height':'50'}.items():app.text_input(key=key).set_value(value)
  next(b for b in app.button if b.label=='计算模拟行李费用').click().run(timeout=15)
  self.assertFalse(app.exception)
  self.assertTrue(any('¥10' in x.value for x in app.markdown))
  self.assertTrue(any('未说明' in x.value for x in app.markdown))
