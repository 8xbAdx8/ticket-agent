"""Phase2 local demo only: real PNGs, atomic ownership checks, no model/API."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import json
import sqlite3
from unittest.mock import patch

from PIL import Image
import pytest
import qrcode

import config
from target import mock_core
from target.demo_payment import confirm
from target.payment_qr import payment_payload, render_qr
from web.runtime import Conversation


@pytest.fixture
def order(tmp_path):
    database = tmp_path/'tickets.db'
    with mock_core.database_scope(database):
        day = (config.today()+timedelta(days=1)).isoformat()
        train = next(t for t in mock_core.query_tickets('上海','杭州',day)['trains'] if t['seats_left']>0)
        lock = mock_core.lock_seat(train['train_no'],day,train['seat_type'],['张三'])
        result = mock_core.create_order(lock['lock_id'],['张三'],config.CURRENT_USER_PHONE)
    return database, result


def state(database, order_id):
    with mock_core.database_scope(database):
        return mock_core.query_order(order_id)


def payment_count(database):
    with sqlite3.connect(database) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='demo_payments'").fetchone():
            return 0
        return c.execute('SELECT COUNT(*) FROM demo_payments').fetchone()[0]


def test_png_is_readable_and_encodes_exact_non_sensitive_payload():
    encoded = []
    original = qrcode.QRCode.add_data
    def capture(self, data, *args, **kwargs):
        encoded.append(data)
        return original(self,data,*args,**kwargs)
    with patch.object(qrcode.QRCode,'add_data',capture):
        raw = render_qr('ODactual123',55.5,'55.50')
    assert raw.startswith(b'\x89PNG\r\n\x1a\n')
    image = Image.open(io.BytesIO(raw))
    image.load()
    assert image.format == 'PNG' and image.width == image.height
    payload = json.loads(encoded[0])
    assert payload == json.loads(image.info['ticket_demo_payment'])
    assert payload == {'order_id':'ODactual123','amount':55.5,'amount_yuan':'55.50',
                       'currency':'CNY','amount_unit':'yuan','demo':True}


def test_distinct_orders_have_distinct_qr_bytes():
    assert render_qr('ODone',55,55) != render_qr('ODtwo',55,55)


def test_order_amount_is_yuan_not_fen(order):
    _, o = order
    p = payment_payload(o['order_id'],o['amount'],o['amount'])
    assert p['amount'] == o['amount'] and p['amount_unit']=='yuan'


@pytest.mark.parametrize('value',[True,None,'NaN','Infinity',-1,0,'1.001'])
def test_bad_amount_never_generates_a_qr(value):
    with pytest.raises(ValueError):
        render_qr('OD1',value,value)


def test_yuan_and_fen_mismatch_rejected():
    with pytest.raises(ValueError):
        render_qr('OD1',5500,55)


@pytest.mark.parametrize('method',['alipay','wechat'])
def test_pending_to_paid_and_method_survives_fresh_read(order,method):
    db,o = order
    result = confirm(db,o['order_id'],o['amount'],method,confirmed=True)
    assert result['status']=='paid' and result['duplicate_pay'] is False
    current = state(db,o['order_id'])
    assert current['status']=='paid' and current['pay_type']==method
    assert current['amount']==o['amount'] and current['paid_at']
    assert payment_count(db)==1


def test_duplicate_confirmation_is_idempotent_and_preserves_first_method(order):
    db,o = order
    confirm(db,o['order_id'],o['amount'],'alipay',confirmed=True)
    for _ in range(3):
        result = confirm(db,o['order_id'],o['amount'],'wechat',confirmed=True)
        assert result['duplicate_pay'] is True
    assert state(db,o['order_id'])['pay_type']=='alipay'
    assert payment_count(db)==1


def test_concurrent_confirmations_write_one_record(order):
    db,o = order
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(db,o['order_id'],o['amount'],'wechat',confirmed=True), range(2)))
    assert sorted(r['duplicate_pay'] for r in results)==[False,True]
    assert payment_count(db)==1


def test_cancelled_order_cannot_be_paid(order):
    db,o = order
    with mock_core.database_scope(db):
        assert mock_core.cancel_order(o['order_id'])['status']=='cancelled'
    assert 'error' in confirm(db,o['order_id'],o['amount'],'alipay',confirmed=True)
    assert state(db,o['order_id'])['status']=='cancelled' and payment_count(db)==0


def test_expired_order_cannot_be_paid(order):
    db,o = order
    with sqlite3.connect(db) as c:
        c.execute("UPDATE locks SET expire_at='2000-01-01T00:00:00' WHERE lock_id=?",(o['lock_id'],))
    assert 'error' in confirm(db,o['order_id'],o['amount'],'alipay',confirmed=True)
    assert state(db,o['order_id'])['status']=='expired' and payment_count(db)==0


def test_other_user_cannot_pay_order(order):
    db,o = order
    with patch.object(config,'CURRENT_USER_PHONE',config.OTHER_USER_PHONE):
        assert confirm(db,o['order_id'],o['amount'],'wechat',confirmed=True)=={'error':'订单不存在'}
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_wrong_amount_rejected_before_business_write(order):
    db,o = order
    result = confirm(db,o['order_id'],o['amount']+1,'alipay',confirmed=True)
    assert 'error' in result
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


@pytest.mark.parametrize('decision',[False,None,'true',1])
def test_explicit_boolean_confirmation_required(order,decision):
    db,o = order
    with pytest.raises(ValueError):
        confirm(db,o['order_id'],o['amount'],'alipay',confirmed=decision)
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_payment_record_failure_rolls_back_status(order):
    db,o = order
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE demo_payments (order_id TEXT PRIMARY KEY,pay_type TEXT,amount REAL,paid_at TEXT)')
        c.execute('INSERT INTO demo_payments VALUES (?,?,?,?)',(o['order_id'],'alipay',o['amount'],'prior-inconsistent'))
    with pytest.raises(sqlite3.IntegrityError):
        confirm(db,o['order_id'],o['amount'],'alipay',confirmed=True)
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==1


def test_render_and_qr_failure_do_not_pay(order):
    from web.payment import controls
    from streamlit.testing.v1 import AppTest
    db,o = order
    from types import SimpleNamespace
    session = SimpleNamespace(sid='qr-failure',read_only=False,pending_action=lambda:None,
                              confirm_demo_payment=lambda *a,**k:pytest.fail('render paid an order'))
    app = AppTest.from_string("import streamlit as st\nfrom web.payment import controls\ncontrols(st.session_state.s,st.session_state.o,verified=True)")
    app.session_state.s=session;app.session_state.o=o
    with patch('web.payment.render_qr',side_effect=RuntimeError('private detail')):
        app.run();app.run()
    assert not app.exception
    assert any('暂时无法生成' in x.value for x in app.warning)
    assert not any('private detail' in x.value for x in app.warning)
    assert all(b.disabled for b in app.button)
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_conversation_read_only_denies_payment():
    s = Conversation('user',read_only=True)
    with pytest.raises(ValueError):
        s.confirm_demo_payment('OD1',55,'alipay',confirmed=True)


def test_order_card_escapes_payment_fields_and_does_not_guess_old_method():
    from web.presentation import order_card
    card = order_card({'order_id':'OD1','status':'paid','amount':55,'pay_type':'<script>'})
    assert '未记录' in card and '<script>' not in card


def test_browser_like_controls_require_consent_and_hide_after_payment(order):
    from streamlit.testing.v1 import AppTest
    from types import SimpleNamespace
    db,o = order
    s = SimpleNamespace(sid='controls',read_only=False,pending_action=lambda:None,
                        confirm_demo_payment=lambda oid,amount,method,**kw:confirm(db,oid,amount,method,**kw))
    app = AppTest.from_string("import streamlit as st\nfrom web.payment import controls\ncontrols(st.session_state.s,st.session_state.o,verified=True)")
    app.session_state.s=s;app.session_state.o=o
    app.run()
    assert all(b.disabled for b in app.button)
    app.checkbox[0].check().run()
    assert all(not b.disabled for b in app.button)
    app.button[1].click().run()
    assert not app.exception
    assert state(db,o['order_id'])['status']=='paid' and payment_count(db)==1
    app.session_state.o=state(db,o['order_id']);app.run()
    assert not app.button and not app.checkbox
    assert len(app.success)==1


def test_paid_render_never_pay():
    from streamlit.testing.v1 import AppTest
    from types import SimpleNamespace
    s=SimpleNamespace(read_only=False)
    app=AppTest.from_string("import streamlit as st\nfrom web.payment import controls\ncontrols(st.session_state.s,{'order_id':'OD1','status':'paid'},verified=True)")
    app.session_state.s=s
    with patch('target.mock_core.pay_order') as pay:
        app.run();app.run()
        pay.assert_not_called()
    assert not app.exception and not app.button


def test_provider_selection_and_settings_do_not_pay():
    from streamlit.testing.v1 import AppTest
    import os
    with patch.dict(os.environ,{'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1'}), \
            patch.multiple(config,PROVIDER='mock',ENGINE='legacy'):
        app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()
        app.text_input(key='user_message').set_value('订明天上海到杭州的高铁')
        next(b for b in app.button if b.label=='发送').click().run()
        next(b for b in app.button if b.label=='确认执行模拟操作').click().run()
        s=app.session_state['user_sessions'][0]
        o=s.results[-1][-1]['result'];db=s.root/'tickets.db'
        with patch('target.mock_core.pay_order') as pay:
            app.run()
            app.selectbox(key='provider_selection').select('LangChain Mock').run()
            app.run()
            pay.assert_not_called()
        assert not app.exception
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_other_session_database_cannot_pay_order(order,tmp_path):
    db,o=order
    other=tmp_path/'other.db'
    assert confirm(other,o['order_id'],o['amount'],'alipay',confirmed=True)=={'error':'订单不存在'}
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_scan_confirmation_uses_selected_method_and_checks_order_amount(order):
    from streamlit.testing.v1 import AppTest
    from types import SimpleNamespace
    db,o=order
    s=SimpleNamespace(sid='scan',read_only=False,pending_action=lambda:None,
        confirm_demo_payment=lambda oid,amount,method,**kw:confirm(db,oid,amount,method,**kw))
    app=AppTest.from_string("import streamlit as st\nfrom web.payment import controls\ncontrols(st.session_state.s,st.session_state.o,verified=True)")
    app.session_state.s=s;app.session_state.o=o
    app.run();app.checkbox[0].check().run()
    app.selectbox[0].select('wechat').run()
    next(b for b in app.button if b.label=='我已扫码，确认演示支付').click().run()
    assert not app.exception
    assert state(db,o['order_id'])['pay_type']=='wechat' and payment_count(db)==1


def test_invalid_method_cannot_pay(order):
    db,o=order
    with pytest.raises(ValueError):
        confirm(db,o['order_id'],o['amount'],'external',confirmed=True)
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_read_only_reload_uses_separate_receipt_without_db_or_payment(order):
    from web.payment import current_order, save_receipt
    from types import SimpleNamespace
    db,o=order
    confirm(db,o['order_id'],o['amount'],'wechat',confirmed=True)
    s=SimpleNamespace(root=db.parent,sid='reload',read_only=True)
    save_receipt(s,state(db,o['order_id']))
    with patch('target.mock_core.pay_order') as pay,patch('target.mock_core.query_order') as query:
        restored,can_pay=current_order(s,o)
        assert restored['status']=='paid' and restored['pay_type']=='wechat' and can_pay is False
        pay.assert_not_called();query.assert_not_called()
    assert o['status']=='pending'
    cancelled={**o,'status':'cancelled'}
    assert current_order(s,cancelled)==(cancelled,False)


def test_read_only_receipt_cannot_cross_session(order):
    from web.payment import current_order, save_receipt
    from types import SimpleNamespace
    db,o=order
    confirm(db,o['order_id'],o['amount'],'alipay',confirmed=True)
    save_receipt(SimpleNamespace(root=db.parent,sid='owner'),state(db,o['order_id']))
    assert current_order(SimpleNamespace(root=db.parent,sid='other',read_only=True),o)==(o,False)


@pytest.mark.parametrize('bad',[[],{'schema':'ticket-demo-payments/1','session_id':'bad','orders':[]},
                              {'schema':'ticket-demo-payments/1','session_id':'bad','orders':{'OD1':None}}])
def test_corrupt_display_receipt_does_not_crash_or_authorize_payment(order,bad):
    from web.payment import current_order
    from types import SimpleNamespace
    db,o=order
    (db.parent/'demo-payment-receipts.json').write_text(json.dumps(bad),encoding='utf-8')
    assert current_order(SimpleNamespace(root=db.parent,sid='bad',read_only=True),o)==(o,False)
    assert state(db,o['order_id'])['status']=='pending' and payment_count(db)==0


def test_live_read_only_toolset_cannot_bypass_permission_via_demo_payment():
    s=Conversation('user',engine='langchain',live=True,full_tools=False)
    with patch('target.demo_payment.confirm') as payment,pytest.raises(ValueError,match='仅支持查询'):
        s.confirm_demo_payment('OD1',55,'alipay',confirmed=True)
    payment.assert_not_called()


def test_live_read_only_toolset_has_no_payment_controls():
    from streamlit.testing.v1 import AppTest
    from types import SimpleNamespace
    app=AppTest.from_string("import streamlit as st\nfrom web.payment import controls\ncontrols(st.session_state.s,{'order_id':'OD1','status':'pending','amount':55},verified=True)")
    app.session_state.s=SimpleNamespace(read_only=False,live=True,full_tools=False)
    app.run()
    assert not app.exception and not app.button and not app.checkbox
    assert any('仅支持查询' in x.value for x in app.info)
