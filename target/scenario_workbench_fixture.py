"""Explicit local fixtures for the workbench. The executor still invokes Agent tools.

The offline generator publishes the *whole* seven-requirement scenario matrix,
not two token cases.  Every scenario is a real V3.10 candidate that the isolated
Agent actually executes; the UI reads the sealed results back.
"""
import json

from target.scenario_catalog import build_scenarios
from target.scenario_workbench import ModelReply


class MockWorkbenchModel:
    source = 'deterministic_model_fixture'

    def __call__(self, system, user, *, directory, run_id, step):
        packet = json.loads(user)
        if step == 'generate':
            turns = (packet.get('conversation') or {}).get('turns') or []
            payload = {'scenarios': build_scenarios(turns)}
            if not payload['scenarios']:
                raise ValueError('C_WORKBENCH_NO_MATCHING_MOCK_FIXTURE')
        else:
            payload = dict(status='indeterminate', reason='离线规则：语义质量需要独立评审。客观断言另列。',
                           evidence_refs=packet['refs'][-1:])
        return ModelReply(json.dumps(payload, ensure_ascii=False), 'workbench-fixture/2',
                          f'fixture-{run_id}-{step}', {'prompt': 0, 'completion': 0}, 0)

    @staticmethod
    def _candidates(turns):
        """Kept for callers that build fixtures directly (tests, probes)."""
        return build_scenarios(turns)
