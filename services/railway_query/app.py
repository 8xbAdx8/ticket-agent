"""Independent query service. Only four routes; disabled unless explicitly chosen."""
from collections import deque
from datetime import datetime, timezone
import threading
import time
import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from target.railway_protocol import Query, Response, Metadata, Error, OPERATIONS, train_status, transfer_status, utc_now, strict_json
from services.railway_query.providers import DisabledProvider

CLIENT_HEADER = 'ticket-agent-query-v1'


class Gate:
    def __init__(self, concurrency=2, per_minute=20, threshold=3, cooldown=30, clock=time.monotonic):
        if not 1 <= concurrency <= 4 or not 1 <= per_minute <= 60 or not 1 <= threshold <= 10 or not 1 <= cooldown <= 300:
            raise ValueError('INVALID_LIMITS')
        self.semaphore = threading.BoundedSemaphore(concurrency)
        self.lock, self.clock = threading.Lock(), clock
        self.times, self.failures, self.open_until = deque(), 0, 0
        self.per_minute, self.threshold, self.cooldown = per_minute, threshold, cooldown

    def enter(self):
        with self.lock:
            now = self.clock()
            if now < self.open_until:
                return 'CIRCUIT_OPEN'
            while self.times and self.times[0] <= now-60:
                self.times.popleft()
            if len(self.times) >= self.per_minute:
                return 'RATE_LIMITED'
            if not self.semaphore.acquire(blocking=False):
                return 'CONCURRENCY_LIMIT'
            self.times.append(now)
        return None

    def leave(self, failed):
        with self.lock:
            self.failures = self.failures+1 if failed else 0
            if self.failures >= self.threshold:
                self.open_until = self.clock()+self.cooldown
        self.semaphore.release()


def create_app(provider=None, gate=None):
    provider, gate = provider or DisabledProvider(), gate or Gate()
    app = FastAPI(title='Railway Query Service', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.state.provider, app.state.gate = provider, gate

    @app.middleware('http')
    async def boundaries(request: Request, call_next):
        if request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            return JSONResponse({'error': 'LOOPBACK_ONLY'}, status_code=403)
        if request.headers.get('origin') or request.headers.get('cookie') or request.headers.get('authorization'):
            return JSONResponse({'error': 'BROWSER_OR_AUTH_CONTEXT_REFUSED'}, status_code=403)
        if request.method == 'POST':
            if request.headers.get('x-ticket-railway-client') != CLIENT_HEADER:
                return JSONResponse({'error': 'QUERY_CLIENT_HEADER_REQUIRED'}, status_code=403)
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'error': 'JSON_REQUIRED'}, status_code=415)
            body = await request.body()
            if len(body) > 4096:
                return JSONResponse({'error': 'REQUEST_TOO_LARGE'}, status_code=413)
            try:
                strict_json(body)
            except (ValueError, UnicodeError):
                return JSONResponse({'error': 'INVALID_JSON'}, status_code=422)
        return await call_next(request)

    @app.get('/health')
    def health():
        return {'schema_version': '1.0', 'service': 'railway-query', 'capabilities': list(OPERATIONS),
                'provider': provider.name, 'source_type': provider.source_type,
                'upstream_commit': getattr(provider, 'upstream_commit', None),
                'origin_requests': getattr(getattr(provider, 'budget', None), 'count', 0),
                'transactions_enabled': False, 'cookie_persistence': False}

    def execute(operation, q):
        requested = utc_now();error = None;payload = {'trains': [], 'stops': [], 'transfers': []}
        status = 'SOURCE_UNAVAILABLE';block = gate.enter();acquired = block is None;attempted = False
        try:
            if block:
                raise RuntimeError(block)
            if operation == 'route' and q.train_code is None:
                raise ValueError('TRAIN_CODE_REQUIRED')
            attempted = True
            payload = provider.query(operation, q)
            status = train_status(payload['trains']) if operation == 'left-ticket' else (
                ('FOUND' if payload['stops'] else 'NO_MATCH') if operation == 'route' else transfer_status(payload['transfers']))
        except Exception as exc:
            import requests
            if provider.source_type == 'DISABLED':
                status, code = 'LIVE_DISABLED', 'LIVE_DISABLED'
            elif block:
                code = block
            elif isinstance(exc, requests.Timeout):
                code = 'UPSTREAM_TIMEOUT'
            elif isinstance(exc, PermissionError):
                code = 'UPSTREAM_CAPABILITY_BLOCKED'
            elif isinstance(exc, (ValueError, TypeError, KeyError, AttributeError)):
                code = 'INVALID_UPSTREAM_RESPONSE'
            else:
                code = 'UPSTREAM_UNAVAILABLE'
            error = Error(code=code, message='查询未完成；未使用Fixture或演示库存替代。')
            payload = {'trains': [], 'stops': [], 'transfers': []}
        try:
            result = Response(provider=provider.name, source_type=provider.source_type, operation=operation,
                query_id=uuid.uuid4().hex, requested_at=requested, data_as_of=None, query=q, status=status,
                source_metadata=Metadata(observed_at=utc_now(), upstream_commit=getattr(provider, 'upstream_commit', None),
                                         origin_requests=getattr(provider, 'last_calls', 0) if attempted else 0), error=error, **payload)
        except ValueError:
            result = Response(provider=provider.name, source_type=provider.source_type, operation=operation,
                query_id=uuid.uuid4().hex, requested_at=requested, data_as_of=None, query=q, status='SOURCE_UNAVAILABLE',
                trains=[], stops=[], transfers=[], source_metadata=Metadata(observed_at=utc_now(),
                upstream_commit=getattr(provider, 'upstream_commit', None)),
                error=Error(code='INVALID_UPSTREAM_RESPONSE', message='响应未通过协议校验。'))
        finally:
            if acquired:
                gate.leave(result.error is not None if 'result' in locals() else True)
        return JSONResponse(result.model_dump(mode='json'), status_code=503 if result.error else 200)

    @app.post('/v1/trains/search')
    def search(q: Query): return execute('left-ticket', q)

    @app.post('/v1/trains/route')
    def route(q: Query):
        if q.train_code is None:
            raise HTTPException(422, 'TRAIN_CODE_REQUIRED')
        return execute('route', q)

    @app.post('/v1/trains/transfer-search')
    def transfer(q: Query): return execute('transfer-ticket', q)

    return app
