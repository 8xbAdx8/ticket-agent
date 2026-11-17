import hashlib
import json

import pytest

from web.workbench_evidence_view import approved_case_ids, case_evidence


def test_approval_requires_receipt_and_never_counts_all_generated(tmp_path):
    run = {'run_id': 'run-a', 'session_id': 'session-a', 'status': 'AWAITING_REVIEW'}
    assert approved_case_ids(tmp_path, run) == set()
    run['status'] = 'COMPLETED'
    assert approved_case_ids(tmp_path, run) is None
    path = tmp_path / 'review.json'
    path.write_text(json.dumps({**run, 'case_ids': ['case-002']}), encoding='utf8')
    run['review_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert approved_case_ids(tmp_path, run) == {'case-002'}
    with pytest.raises(ValueError, match='OWNER'):
        approved_case_ids(tmp_path, {**run, 'session_id': 'session-b'})
    path.write_text('{}', encoding='utf8')
    with pytest.raises(ValueError, match='HASH'):
        approved_case_ids(tmp_path, run)


def test_case_details_use_only_linked_execution_and_judge_evidence(tmp_path):
    case = {'case_id': 'case-002', 'execution_ref': None, 'judge_ref': None}
    assert case_evidence(tmp_path, case) == (None, None)
    folder = tmp_path / 'executions'
    folder.mkdir()
    execution = {'case_id': 'case-002', 'executed': True, 'steps': [{'checks': [{'ok': False, 'actual': 0}]}]}
    (folder / 'case-002.json').write_text(json.dumps(execution), encoding='utf8')
    judgement = {'case_id': 'case-002', 'status': 'indeterminate', 'evidence_refs': ['executions/case-002.json']}
    (tmp_path / 'judgements-revision-2.jsonl').write_text(json.dumps(judgement), encoding='utf8')
    case.update(execution_ref='executions/case-002.json', judge_ref='judgements-revision-2.jsonl#line=1')
    assert case_evidence(tmp_path, case) == (execution, judgement)
    with pytest.raises(ValueError, match='EXECUTION_REFERENCE'):
        case_evidence(tmp_path, {**case, 'execution_ref': '../case-002.json'})
    (tmp_path / 'judgements-revision-2.jsonl').write_text(json.dumps({**judgement, 'case_id': 'case-001'}), encoding='utf8')
    with pytest.raises(ValueError, match='JUDGE_CASE'):
        case_evidence(tmp_path, case)
