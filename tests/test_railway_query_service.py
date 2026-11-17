"""A engineering checks with explicit synthetic data; not B's 103 evaluator."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import threading
from unittest.mock import patch
import httpx
import pytest
import requests
from fastapi.testclient import TestClient
from services.railway_query.app import create_app, Gate, CLIENT_HEADER
from services.railway_query.providers import SyntheticProvider, DisabledProvider, TrainAssistantProvider, QuerySession, RequestBudget, quantity
from target.railway_protocol import Query, Response, Metadata, Error, OPERATIONS, SYNTHETIC, utc_now
from target.train_assistant_adapter import RailwayQueryClient, TrainAssistantAdapter, QueryFailure

FORBIDDEN = ['login', 'qr-login-create', 'passengers', 'orders', 'candidate-submit', 'candidate-cancel',
             'candidate-pay', 'book', 'transfer-book', 'order-pay']
HEADERS = {'X-Ticket-Railway-Client': CLIENT_HEADER}


def query(**kwargs):
    return Query(**({'from_station': '上海', 'to_station': '杭州', 'train_date': '2026-11-03', 'seat_type': '二等座'} | kwargs))


def wire(operation='left-ticket', provider=None):
    q = query(train_code='G9998' if operation == 'route' else None)
    c = TestClient(create_app(provider or SyntheticProvider()))
    return c.post(OPERATIONS[operation], json=q.model_dump(), headers=HEADERS).json()


def adapter_with(data=None, handler=None, **kwargs):
    transport = httpx.MockTransport(handler or (lambda r: httpx.Response(200, json=data)))
    return RailwayQueryClient(transport=transport, **kwargs)


@pytest.mark.parametrize('operation', list(OPERATIONS))
def test_three_query_interfaces_are_explicit_synthetic_not_live(operation):
    r = Response.model_validate(wire(operation))
    assert r.source_type == SYNTHETIC and r.provider == 'local_synthetic_test_service'
    assert r.source_metadata.source_verified_independently is False and r.source_metadata.real_time is False
    assert r.operation == operation and r.error is None


@pytest.mark.parametrize('scenario,status,count', [('normal', 'FOUND', 3), ('empty', 'NO_MATCH', None),
    ('sold', 'NO_AVAILABILITY', 0), ('unknown', 'AVAILABILITY_UNKNOWN', None)])
def test_adapter_business_states_and_unknown_price(scenario, status, count):
    data = wire()
    if scenario == 'empty': data['trains'] = []
    else:
        t = data['trains'][0];t['seats_left'] = count
        t['availability'] = 'UNKNOWN' if count is None else 'AVAILABLE' if count else 'SOLD_OUT'
    data['status'] = status
    r = TrainAssistantAdapter(adapter_with(data)).query_tickets('上海', '杭州', '2026-11-03', '二等座', '高铁')
    assert r['data_source']['status'] == status and r['data_source']['classification'] == SYNTHETIC
    if scenario != 'empty': assert r['trains'][0]['seats_left'] == count and r['trains'][0]['price'] is None


@pytest.mark.parametrize('bad', ['上海;book', '../orders', '--login', '上海\n北京', '', ' Shanghai', '沪/杭'])
def test_invalid_station_never_calls_network(bad):
    client = adapter_with(handler=lambda _: pytest.fail('network reached'))
    r = TrainAssistantAdapter(client).query_tickets(bad, '杭州', '2026-11-03')
    assert r['data_source']['status'] == 'SOURCE_UNAVAILABLE' and r['data_source']['error_code'] == 'INVALID_QUERY'


@pytest.mark.parametrize('bad', ['2026-02-30', '20261103', '2026-1-1', 'tomorrow', '2026-11-03;book'])
def test_invalid_date_never_calls_network(bad):
    r = TrainAssistantAdapter(adapter_with(handler=lambda _: pytest.fail('network reached'))).query_tickets('上海', '杭州', bad)
    assert r['data_source']['status'] == 'SOURCE_UNAVAILABLE'


@pytest.mark.parametrize('command', FORBIDDEN + ['left-ticket; book', '--help', 'short-ride-plan'])
def test_forbidden_commands_client_and_http(command):
    client = adapter_with(handler=lambda _: pytest.fail('network reached'))
    with pytest.raises(QueryFailure, match='FORBIDDEN_OPERATION'): client.request(command, query())
    service = TestClient(create_app(SyntheticProvider()))
    assert service.post('/v1/trains/'+command, json=query().model_dump(), headers=HEADERS).status_code == 404
    assert service.post('/v1/trains/search', json=query().model_dump() | {'command': command}, headers=HEADERS).status_code == 422


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'wrong_source', 'wrong_operation', 'wrong_query', 'future',
                                'naive', 'zero_for_unknown', 'wrong_status', 'secret', 'old_commit'])
def test_invalid_responses_fail_closed_without_stock_fallback(bad):
    data = wire()
    if bad == 'missing': del data['trains'][0]['price']
    if bad == 'duplicate': data['trains'] *= 2
    if bad == 'wrong_source': data['source_type'] = 'LIVE'
    if bad == 'wrong_operation': data['operation'] = 'route'
    if bad == 'wrong_query': data['query']['from_station'] = '北京'
    if bad == 'future': data['source_metadata']['observed_at'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    if bad == 'naive': data['requested_at'] = '2026-11-03T12:00:00'
    if bad == 'zero_for_unknown': data['trains'][0]['seats_left'] = 0
    if bad == 'wrong_status': data['status'] = 'NO_MATCH'
    if bad == 'secret': data['trains'][0]['secret_str'] = 'must-not-pass'
    if bad == 'old_commit':
        data.update(source_type='LIVE', provider='12306_train_assistant');data['source_metadata']['upstream_commit'] = '0'*40
    r = TrainAssistantAdapter(adapter_with(data)).query_tickets('上海', '杭州', '2026-11-03', '二等座')
    expected = 'QUERY_CORRELATION_MISMATCH' if bad == 'wrong_query' else 'INVALID_SERVICE_RESPONSE'
    assert r['data_source']['status'] == 'SOURCE_UNAVAILABLE' and r['data_source']['error_code'] == expected
    assert not r['trains']


@pytest.mark.parametrize('body', [b'bad', b'{"schema_version":"1.0","schema_version":"1.0"}', b'{"x":NaN}'])
def test_error_json_rejected(body):
    client = adapter_with(handler=lambda _: httpx.Response(200, content=body))
    with pytest.raises(QueryFailure, match='INVALID_SERVICE_RESPONSE'): client.left_ticket(query())


@pytest.mark.parametrize('failure,code', [(httpx.ConnectError, 'SERVICE_UNAVAILABLE'), (httpx.ReadTimeout, 'SERVICE_TIMEOUT')])
@pytest.mark.parametrize('retries', [0, 1])
def test_unavailable_timeout_and_bounded_retries(failure, code, retries):
    calls = []
    def handler(r): calls.append(r);raise failure('offline fault')
    with pytest.raises(QueryFailure, match=code): adapter_with(handler=handler, retries=retries).left_ticket(query())
    assert len(calls) == retries+1


@pytest.mark.parametrize('url', ['https://example.org', 'http://localhost:8540', 'http://127.0.0.1:8540/orders',
                               'http://user@127.0.0.1:8540', 'http://127.0.0.1:8540?cmd=book'])
def test_only_literal_loopback_service_url(url):
    with pytest.raises(ValueError): RailwayQueryClient(url)


def test_disabled_route_and_safe_defaults():
    client = TestClient(create_app())
    h = client.get('/health').json()
    assert h['provider'] == 'disabled' and h['transactions_enabled'] is False
    r = client.post('/v1/trains/search', json=query().model_dump(), headers=HEADERS)
    assert r.status_code == 503 and r.json()['status'] == 'LIVE_DISABLED'
    assert set((r.path, tuple(r.methods)) for r in client.app.routes) == {('/health', ('GET',)),
        ('/v1/trains/search', ('POST',)), ('/v1/trains/route', ('POST',)), ('/v1/trains/transfer-search', ('POST',))}
    assert client.post('/v1/trains/route', json=query().model_dump(), headers=HEADERS).status_code == 422


@pytest.mark.parametrize('extra', [{'Origin': 'https://evil.example'}, {'Cookie': 'session=not-used'}, {'Authorization': 'Bearer not-used'}])
def test_browser_and_auth_context_refused(extra):
    c = TestClient(create_app(SyntheticProvider()))
    assert c.post('/v1/trains/search', json=query().model_dump(), headers=HEADERS | extra).status_code == 403


def test_limits_circuit_recovery_and_busy():
    clock = [0.0];gate = Gate(concurrency=1, per_minute=2, threshold=2, cooldown=10, clock=lambda: clock[0])
    assert gate.enter() is None and gate.enter() == 'CONCURRENCY_LIMIT'
    gate.leave(True);assert gate.enter() is None;gate.leave(True)
    assert gate.enter() == 'CIRCUIT_OPEN'
    clock[0] = 11;assert gate.enter() == 'RATE_LIMITED'
    clock[0] = 61;assert gate.enter() is None;gate.leave(False)
    assert gate.failures == 0


def test_origin_gateway_rejects_transactions_redirects_credentials_and_bad_hash(tmp_path):
    session = QuerySession(None, RequestBudget(), __import__('time').monotonic()+8)
    for method, url in [('POST', 'https://kyfw.12306.cn/otn/leftTicket/queryG'), ('GET', 'https://kyfw.12306.cn/passport/web/login'),
                        ('GET', 'https://kyfw.12306.cn/otn/confirmPassenger/initDc'), ('GET', 'https://example.org/otn/leftTicket/queryG')]:
        with pytest.raises(PermissionError): session.request(method, url)
    assert session.calls == 0 and session.trust_env is False
    for k in ['auth', 'cookies', 'proxies']:
        with pytest.raises(PermissionError): session.get('https://kyfw.12306.cn/otn/leftTicket/queryG', **{k: {'x':'y'}})
    raw = tmp_path/'client.py';raw.write_text('raise RuntimeError("must never run")')
    with pytest.raises(PermissionError): TrainAssistantProvider(raw)
    with pytest.raises(ValueError): TrainAssistantProvider(raw, authorized=True)


@pytest.mark.parametrize('raw,expected', [('有', None), ('候补', None), ('--', None), ('', None), (None, None),
                                       ('无', 0), ('0', 0), ('7', 7), (True, None), (-1, None)])
def test_quantity_unknown_is_not_zero(raw, expected):
    assert quantity(raw) == expected


def test_adapter_source_audit_and_existing_write_isolation(tmp_path, monkeypatch):
    import config
    from data.seed import build_db
    from target.train_source import source_scope, SourceChoice, query_tickets
    from target import tools
    db = tmp_path/'business.db';build_db(db)
    monkeypatch.setattr(config, 'DB_PATH', db);monkeypatch.setattr(config, 'TRACE_DIR', tmp_path/'traces')
    monkeypatch.delenv('TICKET_TEST_MODE', raising=False)
    original = db.read_bytes()
    client = adapter_with(wire())
    with patch('target.train_assistant_adapter.configured_client', return_value=client), source_scope(SourceChoice('live')):
        r = query_tickets('上海', '杭州', '2026-11-03', '二等座', '高铁')
        assert r['data_source']['classification'] == SYNTHETIC and r['trains'][0]['seats_left'] is None
        _, ok, _ = tools.dispatch('lock_seat', {'train_no':'G9998','date':'2026-11-03','seat_type':'二等座','passengers':['演示乘客']})
        assert not ok
    assert db.read_bytes() == original
    events = list((tmp_path/'traces/train-data-events').glob('*.json'));assert events
    assert json.loads(events[0].read_text(encoding='utf-8'))['data_source']['service_query_id']


def test_baseline_never_connects_even_if_service_enabled(monkeypatch, tmp_path):
    import config
    from target.train_source import source_scope, SourceChoice, query_tickets
    monkeypatch.setenv('TICKET_TEST_MODE', '1');monkeypatch.setenv('TICKET_RAILWAY_QUERY_ENABLED', '1')
    monkeypatch.setattr(config, 'TRACE_DIR', tmp_path/'traces')
    with patch('target.train_assistant_adapter.configured_client', side_effect=AssertionError('must not connect')), source_scope(SourceChoice('live')):
        result = query_tickets('上海', '杭州', '2026-10-21')
    assert result['data_source']['mode'] == 'fixture'


def test_real_loopback_http_all_operations_stop_and_database_immutability(tmp_path):
    import time
    import uvicorn
    db = tmp_path/'business.db'
    with sqlite3.connect(db) as c:
        for table in ['orders', 'inventory', 'payments', 'refunds', 'reschedules']:
            c.execute('CREATE TABLE '+table+'(id INTEGER, state TEXT)')
            c.execute('INSERT INTO '+table+' VALUES(1,?)', (table+'-sentinel',))
    original = db.read_bytes()
    listener = socket.socket();listener.bind(('127.0.0.1', 0));port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(SyntheticProvider()), log_level='error', lifespan='off'))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True);thread.start()
    try:
        for _ in range(300):
            if server.started: break
            time.sleep(.01)
        assert server.started
        client = RailwayQueryClient('http://127.0.0.1:'+str(port), timeout=1)
        for operation in OPERATIONS:
            q = query(train_code='G9998' if operation == 'route' else None)
            r = client.request(operation, q)
            assert r.source_type == SYNTHETIC and r.source_metadata.origin_requests == 0
        with httpx.Client(trust_env=False) as h:
            r = h.post(f'http://127.0.0.1:{port}/v1/trains/search', json=query().model_dump() | {'db_path':str(db)}, headers=HEADERS)
            assert r.status_code == 422
        assert db.read_bytes() == original
    finally:
        server.should_exit = True;thread.join(5);listener.close()
    assert not thread.is_alive()
    result = TrainAssistantAdapter(client).query_tickets('上海', '杭州', '2026-11-03')
    assert result['data_source']['status'] == 'SOURCE_UNAVAILABLE'
    assert result['data_source']['error_code'] in ('SERVICE_UNAVAILABLE', 'SERVICE_TIMEOUT')
    assert db.read_bytes() == original


def test_response_oversize_redirect_and_request_json_boundaries():
    for status, body in [(302, b''), (200, b'x'*2_000_001)]:
        with pytest.raises(QueryFailure): adapter_with(handler=lambda _,s=status,b=body:httpx.Response(s,content=b)).left_ticket(query())
    c = TestClient(create_app(SyntheticProvider()))
    for raw in [b'{"x":1,"x":2}', b'{"x":NaN}']:
        assert c.post('/v1/trains/search', content=raw, headers=HEADERS | {'Content-Type':'application/json'}).status_code == 422
    assert c.post('/v1/trains/search',content='x'*4097,headers=HEADERS | {'Content-Type':'application/json'}).status_code == 413


def test_gateway_redirect_no_cookie_and_budget_evidence(tmp_path):
    import time
    session = QuerySession(tmp_path/'requests.jsonl', RequestBudget(1), time.monotonic()+8)
    response = requests.Response();response.status_code=302;response.url='https://kyfw.12306.cn/otn/leftTicket/queryG';response.headers['Location']='https://evil.example/'
    response._content=b'';response._content_consumed=True
    with patch.object(requests.Session,'request',return_value=response) as send:
        with pytest.raises(requests.HTTPError):session.get(response.url)
        assert send.call_args.kwargs['allow_redirects'] is False
        with pytest.raises(PermissionError):session.get(response.url)
        assert send.call_count == 1
    rows=[json.loads(line) for line in (tmp_path/'requests.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['http_status']==302 and 'cookies' not in rows[0]


def test_stale_replay_and_http_error_are_distinct():
    data=wire();data['requested_at']=(datetime.now(timezone.utc)-timedelta(seconds=8)).isoformat()
    client=adapter_with(data)
    with pytest.raises(QueryFailure,match='STALE_QUERY_RESPONSE'):client.left_ticket(query())
    data=wire();client=adapter_with(data);client.left_ticket(query())
    with pytest.raises(QueryFailure,match='QUERY_CORRELATION_MISMATCH'):client.left_ticket(query())


def test_service_circuit_counts_invalid_provider_payload():
    class Broken(SyntheticProvider):
        def query(self,*_):return {'trains':[{'invalid':'shape'}],'stops':[],'transfers':[]}
    gate=Gate(threshold=1)
    c=TestClient(create_app(Broken(),gate))
    assert c.post('/v1/trains/search',json=query().model_dump(),headers=HEADERS).status_code==503
    r=c.post('/v1/trains/search',json=query().model_dump(),headers=HEADERS)
    assert r.json()['error']['code']=='CIRCUIT_OPEN'


def test_wrong_row_route_rejected_separately_from_query_envelope():
    data=wire();data['trains'][0]['from_city']='北京'
    with pytest.raises(QueryFailure,match='ROW_QUERY_MISMATCH'):
        adapter_with(data).left_ticket(query())


@pytest.mark.parametrize('operation',list(OPERATIONS))
def test_pinned_provider_uses_only_fixed_query_methods_with_offline_upstream_double(operation):
    import requests
    calls=[]
    class FakeKyfw:
        def __init__(self,**kwargs):
            assert kwargs['cookie_file'] is None
            self.session=requests.Session()
        def query_left_ticket(self,**kwargs):
            calls.append('left-ticket')
            return {'raw':{'data':{'result':['opaque-row']}},'rows':[{'train_code':'G123','from_station':'上海','to_station':'杭州',
                'duration':'01:00','start_time':'06:00','arrive_time':'07:00','second_class':'有','first_class':'0','business':'--'}]}
        def resolve_train_no_by_train_code(self,**kwargs):calls.append('left-ticket-resolution');return {'train_no':'INTERNAL_QUERY_ID'}
        def query_route(self,**kwargs):
            calls.append('route');return {'rows':[{'station_no':'1','station_name':'上海','arrive_time':'----','start_time':'06:00'},
                                                 {'station_no':'2','station_name':'杭州','arrive_time':'07:00','start_time':'----'}]}
        def query_transfer_ticket(self,**kwargs):
            calls.append('transfer-ticket');return {'raw':{'data':{'middleList':[{}]}},'rows':[{'from_station':'上海','to_station':'杭州','middle_station':'南京南',
              'first_leg_train_code':'G123','first_leg_start_time':'23:00','first_leg_arrive_time':'00:30','first_leg_second_class':'有',
              'second_leg_train_code':'G456','second_leg_start_time':'01:00','second_leg_arrive_time':'03:00','second_leg_second_class':'无'}]}
    provider=TrainAssistantProvider.__new__(TrainAssistantProvider);provider.client_type=FakeKyfw;provider.budget=RequestBudget();provider.evidence=None;provider.local=threading.local()
    result=provider.query(operation,query(train_code='G123' if operation=='route' else None))
    assert calls=={'left-ticket':['left-ticket'],'route':['left-ticket-resolution','route'],'transfer-ticket':['transfer-ticket']}[operation]
    if operation=='left-ticket':assert result['trains'][0].seats_left is None and result['trains'][0].price is None
    if operation=='transfer-ticket':assert all(leg.date is None and leg.price is None for leg in result['transfers'][0].legs)


@pytest.mark.parametrize('classification,label',[('LIVE','独立只读查询'),('SYNTHETIC_TEST_FIXTURE','SYNTHETIC_TEST_FIXTURE')])
def test_live_ticket_source_label_and_unknown_values_are_not_demo_inventory(classification,label):
    from web.presentation import ticket_cards
    raw=wire();t=raw['trains'][0]
    html=ticket_cards({'trains':[t],'data_source':{'mode':'live','classification':classification}})
    assert label in html and '余票未提供' in html and '票价未提供' in html
    assert '演示数据 · 不真实出票' not in html and '余票 0 张' not in html


def test_rejected_request_never_reuses_previous_origin_request_count():
    class Counted(SyntheticProvider):
        last_calls=3
    c=TestClient(create_app(Counted(),Gate(per_minute=1)))
    first=c.post('/v1/trains/search',json=query().model_dump(),headers=HEADERS)
    assert first.json()['source_metadata']['origin_requests']==3
    blocked=c.post('/v1/trains/search',json=query().model_dump(),headers=HEADERS)
    assert blocked.json()['error']['code']=='RATE_LIMITED' and blocked.json()['source_metadata']['origin_requests']==0
