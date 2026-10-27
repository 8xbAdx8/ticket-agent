"""Append-only API usage evidence. Recording never grants or denies a request.

Historical SQLite budgets are not opened or modified. Old ledger paths are only
hashed namespace labels; new evidence goes to a separate usage directory.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
LOCK = threading.RLock()
RECORDING_ERRORS = set()


def usage_root():
    return Path(os.getenv('TICKET_API_USAGE_DIR', str(ROOT / 'artifacts/runtime/api-usage')))


def origin_for(transport):
    if transport is None:
        return 'real_api'
    import httpx
    return 'offline_stub' if isinstance(transport, httpx.MockTransport) else 'custom_transport_unverified'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _tokens(value):
    return value if type(value) is int and value >= 0 else None


class UsageLog:
    def __init__(self, provider, namespace, *, origin='local_audit_only'):
        self.provider, self.origin = provider, origin
        # abspath is lexical: no access to the old ledger, its schema or status.
        self.namespace = hashlib.sha256(os.path.abspath(str(namespace)).encode()).hexdigest()[:20]
        self.path = usage_root() / provider / self.namespace / 'requests.jsonl'
        self.recording_error = None

    def _append(self, event):
        try:
            from target.diagnostics import sanitize
            event = sanitize({'schema': 'ticket-api-usage/1', 'provider': self.provider,
                              'origin': self.origin, 'timestamp': _now(), **event})
            payload = (json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            with LOCK:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_BINARY', 0), 0o600)
                try:
                    # Bounded, cross-process logging lock. Failure only loses
                    # statistics, never admission to the model/Embedding API.
                    for attempt in range(6):
                        try:
                            if os.name == 'nt':
                                import msvcrt
                                os.lseek(fd, 0, os.SEEK_SET)
                                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                            else:
                                import fcntl
                                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except OSError:
                            if attempt == 5:raise
                            time.sleep(.01)
                    if os.write(fd, payload) != len(payload):
                        raise OSError('partial_usage_write')
                finally:
                    os.close(fd)
            return True
        except Exception:
            self.recording_error = 'usage_log_write_failed'
            RECORDING_ERRORS.add((str(self.path.absolute()), self.provider, self.origin))
            # Trace still contains HTTP/model events even if the statistics disk
            # is unavailable. Do not turn logging failure into an API rejection.
            try:
                from target.request_accounting import emit
                emit({'event': 'usage_recording_warning', 'provider': self.provider,
                      'category': self.recording_error})
            except Exception:
                pass
            return False

    def reserve(self, summary=None, request_id=None):
        identity = request_id or uuid.uuid4().hex
        from target.request_accounting import ACTIVE
        active = ACTIVE.get()
        self._append({'event': 'request_started', 'request_id': identity,
                      'trace_id': active[1] if active else None,
                      'model_step': active[2] if active else None, 'summary': summary or {},
                      'category': 'dispatched_outcome_unknown'})
        return identity

    def record(self, identity, *, status=None, category='response_received', usage=None,
               model=None, phase='settled', **metadata):
        usage = usage if isinstance(usage, dict) else {}
        self._append({'event': 'request_finished', 'request_id': identity, 'status': status,
                      'category': category, 'phase': phase, 'model': model,
                      'prompt': _tokens(usage.get('prompt_tokens')),
                      'completion': _tokens(usage.get('completion_tokens')),
                      'cost': None, 'cost_basis': 'unknown_without_provider_billing_evidence', **metadata})

    def snapshot(self):
        result=read_usage(self.path)
        if (str(self.path.absolute()),self.provider,self.origin) in RECORDING_ERRORS:
            result.update(request_count=None,reserved_requests=None,used=None,recording_status='partial_or_unavailable',error='usage_log_write_failed')
        return result


def read_usage(path):
    rows = {}
    invalid = 0
    try:
        path = Path(path)
        if path.exists():
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                        uid = event['request_id']
                        if event['event'] == 'request_started':
                            rows.setdefault(uid, {'request_id': uid, 'provider': event['provider'],
                                'origin': event['origin'], 'created': event['timestamp'],
                                'trace_id': event.get('trace_id'), 'model_step': event.get('model_step'),
                                'model': event.get('summary', {}).get('model'), 'request_summary': event.get('summary'),
                                'status': None, 'category': event.get('category'), 'prompt': None,
                                'completion': None, 'tokens': None, 'cost': None, 'phase': 'dispatched',
                                **event.get('summary', {})})
                        elif event['event'] == 'request_finished':
                            row = rows.get(uid)
                            if row is None:
                                invalid += 1
                                continue
                            # Retain the first observed HTTP result. Later SDK or
                            # tool exceptions must not replace it with unknown.
                            if row.get('status') is not None:
                                continue
                            row.update({k: v for k, v in event.items() if k not in ('event', 'schema', 'request_id', 'origin', 'provider')})
                    except (ValueError, TypeError, KeyError):
                        invalid += 1
    except OSError:
        return {'request_count': None, 'reserved_requests': None, 'used': None, 'limit': None,
                'policy': 'unlimited_usage_only', 'requests': [], 'unsettled_ids': [],
                'recording_status': 'unavailable', 'error': 'usage_log_unreadable'}
    records = [dict(row, id=i + 1) for i, row in enumerate(rows.values())]
    count = len(records) if not invalid else None
    return {'request_count': count, 'reserved_requests': count, 'used': count, 'limit': None,
            'policy': 'unlimited_usage_only', 'requests': records,
            'unsettled_ids': [r['request_id'] for r in records if r['status'] is None],
            'recording_status': 'partial' if invalid else 'available', 'invalid_lines': invalid,
            'real_api_attempts': sum(r['origin'] == 'real_api' for r in records),
            'offline_stub_attempts': sum(r['origin'] == 'offline_stub' for r in records)}


def provider_usage(provider):
    """Read-only integration/UI totals. Unknown usage stays unknown, never zero."""
    root=usage_root().absolute()
    records, errors = [], sum(p==provider and origin!='offline_stub' and Path(path).is_relative_to(root)
                             for path,p,origin in RECORDING_ERRORS)
    try:
        for path in (usage_root() / provider).glob('*/requests.jsonl'):
            result = read_usage(path)
            records.extend(result['requests'])
            errors += result['recording_status'] != 'available'
    except OSError:
        errors += 1
    live = [r for r in records if r['origin'] == 'real_api']
    total = lambda field: (sum(r[field] for r in live) if live and all(type(r.get(field)) is int for r in live) else None)
    return {'provider': provider, 'policy': 'unlimited_usage_only', 'local_request_limit': None,
            'request_count': None if errors else len(live), 'prompt_tokens': total('prompt'),
            'completion_tokens': total('completion'), 'embedding_tokens': total('tokens'),
            'offline_stub_requests': sum(r['origin'] == 'offline_stub' for r in records),
            'recording_status': 'partial_or_unavailable' if errors else 'available',
            'actual_cost': None, 'cost_basis': 'unknown_without_provider_billing_evidence',
            'recent_requests': live[-20:]}
