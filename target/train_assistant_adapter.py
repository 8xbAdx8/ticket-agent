"""Loopback-only railway query adapter; no shell, credentials or business DB."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from urllib.parse import urlsplit
import uuid
import httpx
from target.railway_protocol import Query, Response, OPERATIONS, strict_json, utc_now


class QueryFailure(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RailwayQueryClient:
    def __init__(self, base_url='http://127.0.0.1:8540', *, timeout=12, retries=0, transport=None):
        target = urlsplit(base_url)
        if (target.scheme != 'http' or target.hostname != '127.0.0.1' or target.port is None
                or target.username or target.password or target.path not in ('', '/') or target.query or target.fragment):
            raise ValueError('LOOPBACK_URL_REQUIRED')
        if type(retries) is not int or retries not in (0, 1) or not 0.05 <= timeout <= 30:
            raise ValueError('INVALID_CLIENT_LIMITS')
        self.base_url, self.timeout, self.retries, self.transport = base_url.rstrip('/'), timeout, retries, transport
        self.seen = set()

    def request(self, operation, query):
        if operation not in OPERATIONS:
            raise QueryFailure('FORBIDDEN_OPERATION')
        q = query if isinstance(query, Query) else Query.model_validate(query)
        started = datetime.now(timezone.utc)
        for attempt in range(self.retries+1):
            try:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout, trust_env=False,
                                  follow_redirects=False, transport=self.transport) as client:
                    with client.stream('POST', OPERATIONS[operation], json=q.model_dump(),
                            headers={'X-Ticket-Railway-Client': 'ticket-agent-query-v1'}) as response:
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 2_000_000:
                                raise QueryFailure('RESPONSE_TOO_LARGE')
                        if response.status_code not in (200, 503):
                            raise QueryFailure('HTTP_RESPONSE_REJECTED')
                        result = Response.model_validate(strict_json(raw))
                        if result.query != q or result.operation != operation or result.query_id in self.seen:
                            raise QueryFailure('QUERY_CORRELATION_MISMATCH')
                        def matches(actual, requested):
                            return actual == requested or bool(re.fullmatch('[A-Za-z]{3}', requested))
                        for t in result.trains:
                            if not matches(t.from_city, q.from_station) or not matches(t.to_city, q.to_station) or q.seat_type is not None and t.seat_type != q.seat_type:
                                raise QueryFailure('ROW_QUERY_MISMATCH')
                        for item in result.transfers:
                            if not matches(item.legs[0].from_city, q.from_station) or not matches(item.legs[-1].to_city, q.to_station):
                                raise QueryFailure('ROW_QUERY_MISMATCH')
                        stamp = datetime.fromisoformat(result.requested_at)
                        if (stamp-started).total_seconds() < -5 or (stamp-datetime.now(timezone.utc)).total_seconds() > 5:
                            raise QueryFailure('STALE_QUERY_RESPONSE')
                        if (response.status_code == 200) != (result.error is None):
                            raise QueryFailure('HTTP_STATUS_MISMATCH')
                        self.seen.add(result.query_id)
                        return result
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == self.retries:
                    raise QueryFailure('SERVICE_TIMEOUT' if isinstance(exc, httpx.TimeoutException) else 'SERVICE_UNAVAILABLE') from exc
            except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                if isinstance(exc, QueryFailure):
                    raise
                raise QueryFailure('INVALID_SERVICE_RESPONSE') from exc

    def left_ticket(self, query): return self.request('left-ticket', query)
    def route(self, query): return self.request('route', query)
    def transfer_search(self, query): return self.request('transfer-ticket', query)


class TrainAssistantAdapter:
    def __init__(self, client=None):
        self.client = client

    def query_tickets(self, from_city, to_city, date, seat_type=None, kind=None):
        from target.train_source import _result, _status
        if self.client is None:
            return _result('LIVE_DISABLED', [], {'mode': 'live', 'blocker': 'LIVE_SOURCE_BLOCKED_PENDING_AUTHORIZATION'})
        meta = {'mode': 'live', 'provider': 'independent_railway_query_service', 'requested_at': utc_now()}
        try:
            if kind not in (None, '高铁'):
                raise QueryFailure('UNSUPPORTED_TRANSPORT')
            q = Query(from_station=from_city, to_station=to_city, train_date=date, seat_type=seat_type)
            result = self.client.left_ticket(q)
            raw = result.model_dump(mode='json')
            meta.update(provider=result.provider, classification=result.source_type,
                        source={'LIVE':'12306独立只读查询服务','SYNTHETIC_TEST_FIXTURE':'合成协议测试服务 · 非真实数据','DISABLED':'独立查询服务已关闭'}[result.source_type],
                        fetched_at=result.source_metadata.observed_at, requested_at=result.requested_at,
                        data_as_of=result.data_as_of, service_query_id=result.query_id,
                        source_verified_independently=False, upstream_commit=result.source_metadata.upstream_commit,
                        response_sha256=hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                        error_code=result.error.code if result.error else None)
            rows = [t.model_dump(exclude={'availability'}) for t in result.trains if kind is None or t.kind == kind]
            return _result(result.status if result.error else _status(rows), rows, meta)
        except (ValueError, TypeError) as exc:
            meta['error_code'] = exc.code if isinstance(exc, QueryFailure) else 'INVALID_QUERY'
            return _result('SOURCE_UNAVAILABLE', [], meta)

    def get_train_detail(self, train_no, date):
        # TrainSource detail is an inventory authority API, not a request to book.
        return []


def configured_client():
    if os.getenv('TICKET_RAILWAY_QUERY_ENABLED') != '1' or os.getenv('TICKET_TEST_MODE') == '1':
        return None
    return RailwayQueryClient(os.getenv('TICKET_RAILWAY_QUERY_URL', 'http://127.0.0.1:8540'))
