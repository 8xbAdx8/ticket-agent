"""HTTP usage accounting without cumulative admission limits or old-ledger writes."""
import contextvars
import json
import os
import sqlite3
import uuid
import hashlib
import time
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from target.api_usage import UsageLog, origin_for

ACTIVE = contextvars.ContextVar('ticket_http_audit', default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


def error(category):
    from target.deepseek_runtime import DeepSeekError
    return DeepSeekError(category)


@contextmanager
def capture(events, trace_id, model_step):
    token = ACTIVE.set((events, trace_id, model_step))
    try:
        yield
    finally:
        ACTIVE.reset(token)


def emit(event):
    active = ACTIVE.get()
    if active:
        active[0].append({**event, 'model_step': active[2], 'timestamp': now()})


class CoordinatedBudget(UsageLog):
    """Import compatibility only; shared_path/total_limit are no longer gates.

    No transactions, schema migration, policy update or reservation is performed
    in either of the historical SQLite files.
    """
    def __init__(self, settings, provider, shared_path=None, total_limit=None):
        self.settings = settings
        self.historical_shared_path = shared_path or os.getenv('TICKET_INITIAL_LIVE_BUDGET')
        super().__init__(provider, settings.ledger_path)


def snapshot(path, limit=None):
    """Read-only history viewer. Its output must never decide HTTP admission."""
    path = Path(path)
    if not path.exists():
        return {'reserved_requests': 0, 'limit': limit, 'requests': [], 'unsettled_ids': [], 'historical': True}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(r) for r in connection.execute('SELECT * FROM requests ORDER BY rowid')]
        return {'reserved_requests': len(rows), 'limit': limit, 'requests': rows, 'historical': True,
                'unsettled_ids': [r.get('request_id', f"legacy-row:{r.get('id')}") for r in rows if r.get('status') is None],
                'historical_unlinked': bool(rows and 'request_id' not in rows[0])}
    except (OSError, sqlite3.Error):
        return {'reserved_requests': None, 'limit': limit, 'requests': [], 'unsettled_ids': [],
                'historical': True, 'history_status': 'unreadable'}


def budget_for(settings, provider, *, transport=None):
    # Deprecated name retained for SDK entry compatibility. No legacy account
    # state, request count, total limit or verification-batch marker is consulted.
    return UsageLog(provider, settings.ledger_path, origin=origin_for(transport))


def dispatch_snapshot(body, permitted):
    """Hash the actual outgoing payload without retaining prompt or tool schemas.

    This is dispatch intent, not evidence of a successful HTTP response. The
    list passed by the transport guard is the permission effective on this
    request, which can differ from a configured or historical toolset.
    """
    def hashed(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                         separators=(',', ':')).encode('utf-8')).hexdigest()
    supplied_tools = body.get('tools')
    valid_tools = isinstance(supplied_tools, list) and all(
        isinstance(t, dict) and isinstance(t.get('function'), dict)
        and isinstance(t['function'].get('name'), str) for t in supplied_tools)
    messages = body.get('messages')
    system_messages = [m for m in messages if isinstance(m, dict) and m.get('role') == 'system'] if isinstance(messages, list) else []
    return {'bound_tools': [t['function']['name'] for t in supplied_tools] if valid_tools else None,
            'tool_schemas_sha256': hashed(supplied_tools) if valid_tools else None,
            'tool_schema_sha256': {t['function']['name']: hashed(t) for t in supplied_tools} if valid_tools else None,
            'system_prompt_sha256': hashed(system_messages) if system_messages else None,
            'tool_permission': sorted(permitted) if permitted is not None else None,
            'scope': 'HTTP dispatch intent; not evidence of response or tool execution'}


def reserve(request, budget, provider, body, *, permitted=None):
    if 'ticket_reservation' in request.extensions:
        raise error('duplicate_request_dispatch')
    summary = {'model': body.get('model'), 'message_roles': [m.get('role') for m in body.get('messages', [])],
               'returned_tool_call_ids': [m.get('tool_call_id') for m in body.get('messages', []) if m.get('role') == 'tool']}
    from target.acceptance_budget import active
    batch=active()
    if batch:
        identity=uuid.uuid4().hex
        scope=ACTIVE.get()
        try:batch.reserve(identity,provider,body,request.content,trace_id=scope[1] if scope else None,model_step=scope[2] if scope else None)
        except Exception as exc:
            from target.deepseek_runtime import DeepSeekError
            if isinstance(exc,DeepSeekError):raise
            raise error('acceptance_budget_unavailable') from None
        request.extensions['ticket_acceptance_reservation']=(batch,identity)
    try:
        identity = budget.reserve(summary,request_id=identity) if batch else budget.reserve(summary)
    except Exception:
        identity = uuid.uuid4().hex
        emit({'event': 'usage_recording_warning', 'provider': provider, 'category': 'usage_log_write_failed'})
    request.extensions['ticket_reservation'] = (budget, identity, identity, provider)
    request.extensions['ticket_budget_id'] = identity  # Compatibility, not a budget reservation.
    request.extensions['ticket_usage_started'] = time.perf_counter()
    emit({'event': 'http_request', 'request_id': identity, 'provider': provider, 'summary': summary,
          'dispatch_snapshot': dispatch_snapshot(body, permitted)})
    if os.getenv('TICKET_API_VALIDATION_PROFILE') == 'v352':
        from target.v352_validation import canonical_hash
        payloads = []
        for message in body.get('messages', []):
            if message.get('role') != 'tool':
                continue
            content = message.get('content')
            try:
                parsed = json.loads(content) if isinstance(content, str) else None
            except ValueError:
                parsed = None
            payloads.append({'tool_call_id': message.get('tool_call_id'),
                             'content_sha256': hashlib.sha256(str(content).encode()).hexdigest(),
                             'parsed_result_sha256': canonical_hash(parsed) if isinstance(parsed, dict) else None,
                             'tool_result': parsed if isinstance(parsed, dict) else None})
        emit({'event': 'http_dispatch_evidence', 'request_id': identity, 'provider': provider, 'tool_payloads': payloads,
              'system_prompt_sha256': canonical_hash([m for m in body.get('messages', []) if m.get('role') == 'system']),
              'scope': 'Dispatch intent; successful HTTP/model response must be checked separately'})


def _record(request, **values):
    entry=request.extensions.get('ticket_acceptance_reservation')
    if entry:
        batch,request_id=entry
        try:batch.settle(request_id,values.get('usage'),values.get('category','outcome_unknown'))
        except Exception:
            # Its durable reservation remains charged. A broken batch cannot
            # grant the next HTTP request, even if usage logging remains usable.
            emit({'event':'acceptance_settlement_warning','request_id':request_id})
    budget, identity, _, provider = request.extensions['ticket_reservation']
    started = request.extensions.get('ticket_usage_started')
    if started is not None:
        values['latency_ms'] = round((time.perf_counter() - started) * 1000)
    try:
        budget.record(identity, **values)
    except Exception:
        emit({'event': 'usage_recording_warning', 'provider': provider, 'category': 'usage_log_write_failed'})


def settle(response, category, body):
    entry = response.request.extensions.get('ticket_reservation')
    if not entry:
        return
    _, _, uid, provider = entry
    _record(response.request, status=response.status_code, category=category,
            usage=body.get('usage') if isinstance(body, dict) else None,
            model=body.get('model') if isinstance(body, dict) else None,
            server_request_id=response.headers.get('x-request-id') or (body.get('id') if isinstance(body, dict) else None))
    response.request.extensions['ticket_response_settled'] = True
    emit({'event': 'http_response', 'request_id': uid, 'provider': provider, 'http_status': response.status_code,
          'category': category, 'usage': body.get('usage') if isinstance(body, dict) else None})


def client_class():
    import httpx
    class AuditedClient(httpx.Client):
        def send(self, request, *args, **kwargs):
            try:
                return super().send(request, *args, **kwargs)
            except Exception as exc:
                entry = request.extensions.get('ticket_reservation')
                if entry:
                    from target.deepseek_runtime import safe_error
                    _, _, uid, provider = entry
                    if not request.extensions.get('ticket_response_settled'):
                        _record(request, category=safe_error(exc)['category'] + '_outcome_unknown')
                    emit({'event': 'http_error', 'request_id': uid, 'provider': provider, 'error': safe_error(exc)})
                raise
    return AuditedClient

