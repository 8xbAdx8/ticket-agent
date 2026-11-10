"""V3.11-R1 test-side lifecycle driver.

Adds business-boundary turns and append-only checkpoints around the existing
AgentRun. It does not modify Agent, Registry, Service, D9/P01 or the historical
V311 batch. Each write still requires the original trusted test_user confirm.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import hashlib
import json
import uuid

from target.scenario_live_agent import AgentRun, save
from target.scenario_r1_budget import R1Batch


def _sha(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


class R1Run:
    """One isolated chain. Same-process continuation only; no secret recovery."""

    def __init__(self, root, provider, *, transport=None, scenario='default'):
        self.root = Path(root).resolve()
        self.batch = R1Batch(self.root)
        # The caller must initialize_authorized before constructing a run.
        self.provider = provider
        self.run = AgentRun(self.root, provider, transport=transport, scenario=scenario, batch=self.batch)
        self.execution_id = self.run.id
        self.checkpoint_dir = self.root / 'checkpoints' / self.execution_id
        self.checkpoint_dir.mkdir(parents=True, exist_ok=False)
        self.phase = 'PREPARE'
        self.completed = []
        self.sequence = 0
        self._checkpoint('PREPARE', note='run initialized')

    @property
    def session_id(self):
        return self.run.session.sid

    def _checkpoint(self, phase, *, note=None, extra=None):
        view = self.run.read()
        proposals = [p for p in view['tables']['proposals'] if p['state'] == 'PENDING']
        payload = {
            'schema': 'v311-r1-checkpoint/1',
            'sequence': self.sequence,
            'run_id': self.execution_id,
            'conversation_id': self.session_id,
            'provider': self.provider,
            'phase': phase,
            'completed_ops': list(self.completed),
            'pending_proposals': [p['proposal_id'] for p in proposals],
            'order_ids': [o['order_id'] for o in view['tables']['orders']],
            'state_sha256': view['state_sha256'],
            'db_path': str(self.run.service.store.path),
            'db_sha256': _sha(Path(self.run.service.store.path).read_bytes()),
            'http_requests': self.batch.status()['http_requests'],
            'providers': self.batch.status()['providers'],
            'note': note,
            'extra': extra or {},
        }
        path = self.checkpoint_dir / f'{self.sequence:03d}-{phase}.json'
        save(path, payload)
        self.sequence += 1
        self.phase = phase
        return payload

    def state_preface(self):
        view=self.run.read();tables=view['tables']
        orders=[{k:o[k] for k in ('order_id','order_status','total_fen','paid_total_fen','refunded_total_fen','fee_total_fen','active_item_count','change_count')} for o in tables['orders']]
        items=[{k:i[k] for k in ('order_id','item_id','passenger_name','item_status','fare_fen')} for i in tables['order_items']]
        pending=[{k:p[k] for k in ('proposal_id','action','state','payload_json')} for p in tables['proposals'] if p['state']=='PENDING']
        return ('测试驱动只读状态（来自当前独立SQLite，不是模型推断；必须以此为准）：\n'
                + json.dumps({'orders':orders,'items':items,'pending_proposals':pending},ensure_ascii=False)
                + '\n\n业务指令：')

    def turn(self, message, *, expectations=None, phase=None, readback=True):
        """One user turn = one business boundary; no automatic retry."""
        if readback:message=self.state_preface()+message
        row = self.run.turn(message, expectations=expectations)
        if not row.get('passed'):
            self._checkpoint('STOPPED', note='turn failed', extra={'row_index': row.get('index'), 'task_status': row.get('task_status'), 'error': row.get('error')})
            raise RuntimeError('R1_TURN_FAILED')
        self.completed.append(phase or 'TURN')
        self._checkpoint(phase or 'TURN', extra={'row_index': row.get('index'), 'executed_tools': [e.get('tool') for e in row.get('executed_tools', [])]})
        return row

    def confirm(self, action, *, approved=True, expected_outcome=None):
        proposals = [p for p in self.run.pending() if p['action'] == action]
        if len(proposals) != 1:
            raise ValueError('R1_ONE_MATCHING_PROPOSAL_REQUIRED')
        preview = self.run.decision_preview(proposals[0]['proposal_id'])
        row = self.run.confirm(preview, approved, actor='test_user', expected_outcome=expected_outcome)
        if not row.get('passed'):
            self._checkpoint('STOPPED', note='confirmation failed', extra={'action': action, 'row_index': row.get('index')})
            raise RuntimeError('R1_CONFIRM_FAILED')
        self.completed.append(action)
        self._checkpoint(action, extra={'proposal_id': preview['proposal_id'], 'row_index': row.get('index'), 'business_outcome': row.get('business_outcome')})
        return row

    def pending(self):
        return self.run.pending()

    def read(self):
        return self.run.read()

    def finalize(self, status='VERIFIED'):
        payload = self._checkpoint(status)
        save(self.checkpoint_dir / 'summary.json', {
            'schema': 'v311-r1-run-summary/1',
            'execution_id': self.execution_id,
            'session_id': self.session_id,
            'provider': self.provider,
            'phase': status,
            'completed_ops': self.completed,
            'final_state_sha256': payload['state_sha256'],
            'db_path': payload['db_path'],
            'http_requests': payload['http_requests'],
            'checkpoints': sorted(p.name for p in self.checkpoint_dir.glob('*.json')),
        })
        return payload
