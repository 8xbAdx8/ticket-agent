"""Explicit disabled, synthetic, and hash-pinned upstream query providers."""
import hashlib
import types
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import urlsplit
from http.cookiejar import DefaultCookiePolicy
import requests
from target.railway_protocol import Query, Train, Stop, Leg, Transfer, SYNTHETIC, UPSTREAM_COMMIT

UPSTREAM_SHA256 = '65dbb61a59efcadb51c0d79529eead54a0d0d1b08abcd66438b6640f628a2a00'
QUERY_PATHS = frozenset(('/otn/resources/js/framework/station_name.js', '/otn/leftTicket/init',
                         '/otn/leftTicket/queryG', '/otn/lcQuery/init', '/lcquery/queryG', '/otn/czxx/queryByTrainNo'))
SEATS = {'二等座': 'second_class', '一等座': 'first_class', '商务座': 'business'}


class DisabledProvider:
    source_type = 'DISABLED'
    name = 'disabled'
    def query(self, operation, query):
        raise PermissionError('LIVE_DISABLED')


class SyntheticProvider:
    """Explicit protocol test double. Not a real-data or fixture provider."""
    source_type = SYNTHETIC
    name = 'local_synthetic_test_service'
    def query(self, operation, q):
        def row(origin, destination):
            return Train(train_no=q.train_code or 'G9998', from_city=origin, to_city=destination,
                         date=q.train_date, depart='06:00', arrive='07:00', duration_min=60,
                         seat_type=q.seat_type or '二等座', price=None, seats_left=None, availability='UNKNOWN')
        if operation == 'left-ticket':
            return {'trains': [row(q.from_station, q.to_station)], 'stops': [], 'transfers': []}
        if operation == 'route':
            return {'trains': [], 'stops': [Stop(station_no=1, station_name=q.from_station, arrive_time=None, depart_time='06:00'),
                                          Stop(station_no=2, station_name=q.to_station, arrive_time='07:00', depart_time=None)], 'transfers': []}
        middle = q.middle_station or next(s for s in ['南京南', '合肥南', '武汉'] if s not in (q.from_station, q.to_station))
        def leg(a, b):
            data = row(a, b).model_dump();data.pop('kind');data.pop('duration_min')
            return Leg(**data)
        return {'trains': [], 'stops': [], 'transfers': [Transfer(middle_station=middle,
                legs=[leg(q.from_station, middle), leg(middle, q.to_station)])]}


class NoCookies(DefaultCookiePolicy):
    def set_ok(self, *args): return False
    def return_ok(self, *args): return False


class QuerySession(requests.Session):
    """A second capability boundary below the third-party query code."""
    def __init__(self, evidence, budget, deadline):
        super().__init__()
        self.trust_env = False
        self.cookies.set_policy(NoCookies())
        self.evidence, self.budget, self.deadline = evidence, budget, deadline
        self.calls = 0
        self.records = []

    def request(self, method, url, **kwargs):
        target = urlsplit(url)
        if (method.upper() != 'GET' or target.scheme != 'https' or target.hostname != 'kyfw.12306.cn'
                or target.port not in (None, 443) or target.username or target.password or target.query or target.fragment
                or target.path not in QUERY_PATHS):
            raise PermissionError('FORBIDDEN_UPSTREAM_CAPABILITY')
        if any(k.lower() in ('cookie', 'authorization', 'proxy-authorization') for k in kwargs.get('headers', {})):
            raise PermissionError('AUTHENTICATION_NOT_ALLOWED')
        if any(kwargs.get(k) for k in ('cookies', 'auth', 'proxies', 'hooks', 'cert')) or kwargs.get('verify') is False:
            raise PermissionError('AUTHENTICATION_OR_TLS_OVERRIDE_NOT_ALLOWED')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.calls >= 6:
            raise requests.Timeout('QUERY_DEADLINE')
        self.budget.take()
        self.calls += 1
        start = time.monotonic()
        record = {'method': 'GET', 'host': target.hostname, 'path': target.path,
                  'params': kwargs.get('params'), 'request_started_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
        try:
            kwargs.update(timeout=(min(2, remaining), min(2, remaining)), allow_redirects=False, stream=True)
            response = super().request('GET', url, **kwargs)
            record['http_status'] = response.status_code
            if 300 <= response.status_code < 400:
                response.close()
                raise requests.HTTPError('REDIRECT_REFUSED')
            response.raise_for_status()
            body = bytearray()
            # Check a total deadline even when the peer dribbles bytes indefinitely.
            for chunk in response.iter_content(chunk_size=1):
                if time.monotonic() > self.deadline or len(body) > 2_000_000:
                    response.close()
                    raise requests.Timeout('QUERY_DEADLINE_OR_RESPONSE_LIMIT')
                body.extend(chunk)
            response._content = bytes(body)
            response._content_consumed = True
            record['body_sha256'] = hashlib.sha256(body).hexdigest()
            record['body_bytes'] = len(body)
            record['response_date'] = response.headers.get('Date')
            response.close()
            return response
        except Exception as exc:
            record['error_class'] = type(exc).__name__
            raise
        finally:
            record['elapsed_ms'] = round((time.monotonic()-start)*1000)
            self.records.append(record)
            if self.evidence:
                with self.evidence.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False)+'\n')


class RequestBudget:
    def __init__(self, maximum=12):
        if type(maximum) is not int or not 1 <= maximum <= 1000:
            raise ValueError('INVALID_ORIGIN_BUDGET')
        self.maximum, self.count, self.lock = maximum, 0, threading.Lock()
    def take(self):
        with self.lock:
            if self.count >= self.maximum:
                raise PermissionError('ORIGIN_BUDGET_EXHAUSTED')
            self.count += 1


def quantity(value):
    if type(value) is int and 0 <= value <= 100000:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) <= 100000:
        return int(value)
    if value == '无':
        return 0
    return None


class TrainAssistantProvider:
    source_type = 'LIVE'
    name = '12306_train_assistant'
    upstream_commit = UPSTREAM_COMMIT
    def __init__(self, client_file, *, authorized=False, evidence=None, origin_budget=12):
        if not authorized:
            raise PermissionError('EXPLICIT_READ_QUERY_AUTHORIZATION_REQUIRED')
        path = Path(client_file)
        if path.is_symlink() or not path.is_file():
            raise ValueError('UPSTREAM_SOURCE_HASH_MISMATCH')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != UPSTREAM_SHA256:
            raise ValueError('UPSTREAM_SOURCE_HASH_MISMATCH')
        module = types.ModuleType('ticket_query_only_upstream')
        module.__file__ = str(path.resolve())
        # Execute exactly the hash-verified bytes; never use a stale .pyc or reread
        # the path after validation. The __main__ CLI branch is not entered.
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        self.client_type = module.KyfwClient
        self.budget = RequestBudget(origin_budget)
        self.evidence = Path(evidence) if evidence else None
        if self.evidence:
            self.evidence.parent.mkdir(parents=True, exist_ok=True)
        self.local = threading.local()

    @property
    def last_calls(self):
        return getattr(self.local, 'calls', 0)

    def query(self, operation, q):
        self.local.calls = 0
        if operation not in ('left-ticket', 'route', 'transfer-ticket'):
            raise PermissionError('FORBIDDEN_OPERATION')
        session = QuerySession(self.evidence, self.budget, time.monotonic()+8)
        client = self.client_type(cookie_file=None, timeout=2)
        session.headers.update(client.session.headers)
        client.session.close()
        client.session = session
        common = dict(train_date=q.train_date, from_station=q.from_station, to_station=q.to_station)
        try:
            with tempfile.TemporaryDirectory(prefix='railway-query-stations-') as cache:
                client._station_cache_file = Path(cache)/'stations.json'
                if operation == 'left-ticket':
                    data = client.query_left_ticket(**common)
                    if not isinstance(data.get('raw', {}).get('data', {}).get('result'), list):
                        raise ValueError('INVALID_ORIGIN_ROWS')
                    rows = []
                    for t in data['rows']:
                        for seat in ([q.seat_type] if q.seat_type else list(SEATS)):
                            count = quantity(t.get(SEATS[seat]))
                            duration = t['duration'].split(':')
                            rows.append(Train(train_no=t['train_code'], from_city=t['from_station'], to_city=t['to_station'],
                                              date=q.train_date, depart=t['start_time'], arrive=t['arrive_time'],
                                              kind='高铁' if t['train_code'][0] in 'GCD' else '普速',
                                              duration_min=int(duration[0])*60+int(duration[1]), seat_type=seat,
                                              price=None, seats_left=count, availability='UNKNOWN' if count is None else 'AVAILABLE' if count else 'SOLD_OUT'))
                    if len(data['raw']['data']['result']) != len(data['rows']):
                        raise ValueError('PARTIAL_ORIGIN_ROWS')
                    return {'trains': rows, 'stops': [], 'transfers': []}
                if operation == 'route':
                    if q.train_code is None:
                        raise ValueError('TRAIN_CODE_REQUIRED')
                    internal = client.resolve_train_no_by_train_code(**common, train_code=q.train_code)
                    data = client.query_route(**common, train_no=internal['train_no'])
                    stops = [Stop(station_no=int(t['station_no']), station_name=t['station_name'],
                                  arrive_time=t['arrive_time'] if t['arrive_time'] not in ('----', '--', '') else None,
                                  depart_time=t['start_time'] if t['start_time'] not in ('----', '--', '') else None) for t in data['rows']]
                    return {'trains': [], 'stops': stops, 'transfers': []}
                data = client.query_transfer_ticket(**common, middle_station=q.middle_station or '')
                raw = data.get('raw', {}).get('data', {}).get('middleList')
                if not isinstance(raw, list) or len(raw) != len(data['rows']):
                    raise ValueError('INVALID_TRANSFER_ROWS')
                transfers = []
                for t in data['rows']:
                    middle = t['middle_station'];legs = []
                    for prefix, origin, dest in [('first', t['from_station'], middle), ('second', middle, t['to_station'])]:
                        depart, arrive = t[prefix+'_leg_start_time'], t[prefix+'_leg_arrive_time']
                        h,m = map(int, depart.split(':'));ah,am = map(int, arrive.split(':'))
                        count = quantity(t.get(prefix+'_leg_'+SEATS[q.seat_type or '二等座']))
                        legs.append(Leg(train_no=t[prefix+'_leg_train_code'], from_city=origin, to_city=dest,
                                          date=None, depart=depart, arrive=arrive,
                                          seat_type=q.seat_type or '二等座', price=None, seats_left=count,
                                          availability='UNKNOWN' if count is None else 'AVAILABLE' if count else 'SOLD_OUT'))
                    transfers.append(Transfer(middle_station=middle, legs=legs))
                return {'trains': [], 'stops': [], 'transfers': transfers}
        finally:
            self.local.calls = session.calls
            session.close()
