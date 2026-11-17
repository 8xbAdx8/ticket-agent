from pathlib import Path

import pytest

import config
from target.railway_policy_evidence import public_answer, select
from target.rag_service import citation_check, retrieve
from target.v39.context import Context, scope
from web.runtime import Conversation


CONTEXT = Context('synthetic', '13800000001', 'railway-demo', enabled=True)
COMBINATION = '请结合 P01、P03 说明退票和改签政策。'
UNSUPPORTED = '请查询铁路政策，能不能用时光机退回上周再退票？'


@pytest.mark.parametrize('engine', ['legacy', 'langchain'])
@pytest.mark.parametrize('question,required', [(COMBINATION, {'P01', 'P03'}), (UNSUPPORTED, set())])
def test_policy_dialogue_uses_current_evidence_without_writes(monkeypatch, engine, question, required):
    from contextlib import closing
    import sqlite3
    from uuid import uuid4
    from web.evidence import session_execution_events

    for key, value in {'RAILWAY_SIMULATION_ENABLED':'1', 'RAILWAY_SIM_CLOCK_MODE':'demo',
                       'TICKET_TEST_MODE':'1', 'TICKET_DATA_MODE':'fixture', 'RAG_ALLOW_NETWORK':'0'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('RAILWAY_SIM_DB_PATH', raising=False)
    session = Conversation('user', engine=engine, live=False, full_tools=True, rag_mode='keyword')
    result = session.send(question, uuid4().hex, defer_followups=True)
    events, _ = session_execution_events(session.trace_dir, session.sid)
    retrieval, = [event for event in events if event['event_type'] == 'rag_result']
    assert result['tool_sequence'] == ['search_policy']
    assert {hit['doc_id'] for hit in retrieval['documents']} == required
    answer = result['reply']
    assert set(citation_check(answer, retrieval['documents'])['cited_doc_ids']) == required
    if required:
        assert '5%' in answer and '发车后不办理退票或改签' in answer
    else:
        assert '证据不足，无法确认' in answer
        assert retrieval['sufficiency']['reason'] == 'unsupported_request'
        assert '5%' not in answer
    db = Path(session.railway_state_reference['path'])
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro', uri=True)) as connection:
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        for name in ('orders', 'holds', 'transactions', 'proposals'):
            assert connection.execute('SELECT count(*) FROM v39_'+name).fetchone()[0] == 0


def test_missing_or_low_ranked_evidence_is_not_fabricated():
    p01 = {'doc_id':'P01','content':'policy one','score':0.6}
    p03 = {'doc_id':'P03','content':'policy three','score':0.1}
    raw = dict(mode='vector',hits=[p01],candidate_hits=[p01,p03])
    result = select(COMBINATION, raw, k=3)
    assert result['hits'] == []
    assert result['candidate_hits'] == [p01,p03]
    assert result['answerability']['missing_policy_ids'] == ['P03']
    assert select(COMBINATION, dict(raw, mode='hybrid'), k=3)['hits'] == []
    assert raw['hits'] == [p01]


def test_answer_requires_executed_receipts_and_respects_transaction_turns():
    receipt = dict(event='tool_end', tool='search_policy', ok=True, executed=True,
                   args={'question':UNSUPPORTED}, result={'hits':[]})
    with scope(CONTEXT):
        assert public_answer(UNSUPPORTED, [dict(receipt, executed=False)]) is None
        assert public_answer(UNSUPPORTED, [receipt, dict(event='tool_end', tool='create_order', executed=True)]) is None
        assert public_answer(UNSUPPORTED, [receipt]).startswith('当前政策证据不足')


def test_positive_query_and_original_corpus_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'TRACE_DIR', tmp_path)
    original = config.POLICY_PATH.read_bytes()
    with scope(CONTEXT):
        assert [row['doc_id'] for row in retrieve('查询高铁成人行李政策', mode='keyword')['hits']] == ['P06']
        assert not retrieve(COMBINATION, mode='keyword', k=1)['hits']
    assert config.POLICY_PATH.read_bytes() == original
