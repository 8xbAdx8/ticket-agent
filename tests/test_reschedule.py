import json,sqlite3,tempfile,unittest
from datetime import datetime
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from target.reschedule import preview,confirm
from target import mock_core

class RescheduleTests(unittest.TestCase):
 def setUp(self):
  root=Path('artifacts/runtime');root.mkdir(parents=True,exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=root);self.path=Path(self.tmp.name)/'tickets.db'
  with closing(sqlite3.connect(self.path)) as c, c:
   c.executescript("CREATE TABLE inventory(kind,train_no,date,seat_type,depart,price,seats_left); CREATE TABLE orders(order_id,phone,train_no,date,seat_type,passengers,amount,status,created_at,lock_id); CREATE TABLE locks(lock_id,train_no,date,seat_type,passengers,created_at,expire_at,used);")
   c.execute('INSERT INTO inventory VALUES (?,?,?,?,?,?,?)',('高铁','G101','2026-10-30','二等座','12:00',100,5))
   c.execute('INSERT INTO inventory VALUES (?,?,?,?,?,?,?)',('高铁','G102','2026-10-31','二等座','12:00',120,5))
   c.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)',('OD1','13800000001','G101','2026-10-30','二等座',json.dumps(['张三']),100,'paid','2026-10-01','LK1'))
 def tearDown(self):self.tmp.cleanup()
 def test_48_hour_boundary_atomic_and_no_refund(self):
  with patch('config.now',return_value=datetime(2026,10,28,12)):
   p=preview(self.path,'OD1','G102','2026-10-31','二等座')
   self.assertEqual(p['difference'],'20')
   r=confirm(self.path,p);self.assertTrue(r['record_id'].startswith('RS'))
   with closing(sqlite3.connect(self.path)) as db:
    self.assertEqual(db.execute('SELECT seats_left FROM inventory ORDER BY train_no').fetchall(),[(6,),(4,)])
   with self.assertRaisesRegex(ValueError,'已改签'):preview(self.path,'OD1','G101','2026-10-30','二等座')
   with mock_core.database_scope(self.path):self.assertIn('已改签',mock_core.cancel_order('OD1')['error'])
 def test_less_than_48_hours_rejects_next_day_without_mutation(self):
  with patch('config.now',return_value=datetime(2026,10,28,12,0,1)):
   with self.assertRaises(ValueError):preview(self.path,'OD1','G102','2026-10-31','二等座')
  with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('SELECT seats_left FROM inventory ORDER BY train_no').fetchall(),[(5,),(5,)])
 def test_changed_price_rejects_stale_confirmation(self):
  with patch('config.now',return_value=datetime(2026,10,28,12)):
   p=preview(self.path,'OD1','G102','2026-10-31','二等座')
   with closing(sqlite3.connect(self.path)) as c, c:c.execute("UPDATE inventory SET price=200 WHERE train_no='G102'")
   with self.assertRaisesRegex(ValueError,'变化'):confirm(self.path,p)

 def test_after_departure_two_hour_boundary(self):
  with closing(sqlite3.connect(self.path)) as c, c:
   c.execute("UPDATE inventory SET date='2026-10-30',depart='18:00' WHERE train_no='G102'")
  with patch('config.now',return_value=datetime(2026,10,30,14,0)):
   self.assertEqual(preview(self.path,'OD1','G102','2026-10-30','二等座')['new_train'],'G102')
  with patch('config.now',return_value=datetime(2026,10,30,14,0,1)):
   with self.assertRaises(ValueError):preview(self.path,'OD1','G102','2026-10-30','二等座')
 def test_unavailable_target_does_not_mutate_order(self):
  with closing(sqlite3.connect(self.path)) as c,c:c.execute("UPDATE inventory SET seats_left=0 WHERE train_no='G102'")
  with patch('config.now',return_value=datetime(2026,10,28,12)):
   with self.assertRaises(ValueError):preview(self.path,'OD1','G102','2026-10-31','二等座')
  with closing(sqlite3.connect(self.path)) as c:
   self.assertEqual(c.execute('SELECT train_no FROM orders').fetchone()[0],'G101')

 def test_after_departure_rejects_same_train_other_seat(self):
  with closing(sqlite3.connect(self.path)) as c,c:
   c.execute('INSERT INTO inventory VALUES (?,?,?,?,?,?,?)',('高铁','G101','2026-10-30','一等座','18:00',150,5))
  with patch('config.now',return_value=datetime(2026,10,30,13,0)):
   with self.assertRaisesRegex(ValueError,'其他车次'):
    preview(self.path,'OD1','G101','2026-10-30','一等座')
