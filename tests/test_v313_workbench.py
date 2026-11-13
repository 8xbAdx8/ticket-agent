import json

from streamlit.testing.v1 import AppTest

from target.scenario_workbench import LiveWorkbenchModel, ModelReply, RUN_ROOT, Workbench
from target.scenario_workbench_gaps import inspect_run
from test_scenario_workbench import FixtureModel, candidate, source_session


def test_supplement_ui_keeps_live_candidate_behind_review(monkeypatch, tmp_path):
    monkeypatch.setenv('TICKET_WEB_OFFLINE_ONLY', '0')
    session = source_session(tmp_path / 'source')
    parent = Workbench(session.sid)
    assert parent.execute(session, FixtureModel([candidate()]))['status'] == 'COMPLETED'
    gap = next(row for row in inspect_run(parent.run_id, session.sid, root=RUN_ROOT)['gaps']
               if row['feature'] == 'RAG 引用')
    calls = []

    def fake_model(self, system, user, *, directory, run_id, step):
        calls.append((directory, step))
        payload = json.loads(user)
        assert [row['gap_id'] for row in payload['selected_gaps']] == [gap['gap_id']]
        message = '查询发车超过 48 小时退票手续费，并引用 P01。'
        item = dict(candidate(), title='核对 P01 引用', objective='查阅退票费规则后引用 P01',
                    dimension='RAG', gap_id=gap['gap_id'], turns=[message], integration_steps=[
                        dict(kind='chat', message=message, checks=[
                            dict(path='result.public_result.tool_sequence', op='contains', value='search_policy'),
                            dict(path='result.reply', op='contains', value='P01')])])
        return ModelReply(json.dumps({'scenarios': [item]}), 'offline-model-fixture', 'fixture',
                          {'prompt': None, 'completion': None}, 1)

    monkeypatch.setattr(LiveWorkbenchModel, '__call__', fake_model)
    app = AppTest.from_string('''
import streamlit as st
from web.consistency_audit_view import quality_page
quality_page(st.session_state.source_sessions)
''')
    app.session_state['source_sessions'] = [session]
    app.session_state['c_workbench_pointer'] = {'run_id': parent.run_id, 'session_id': session.sid}
    app.run()
    app.button(key='c_gap_plan_' + parent.run_id).click().run()
    app.selectbox(key='c_gap_dimension_' + parent.run_id).set_value('RAG').run()
    app.multiselect(key=f'c_gap_selection_{parent.run_id}_RAG').set_value([gap['gap_id']]).run()
    assert app.button(key='c_gap_generate_' + parent.run_id).disabled
    assert not calls
    app.checkbox(key='c_gap_consent_' + parent.run_id).set_value(True).run()
    app.button(key='c_gap_generate_' + parent.run_id).click().run()
    assert not app.exception
    [(directory, step)] = calls
    assert step == 'generate'
    manifest = json.loads((directory / 'manifest.json').read_text('utf8'))
    assert manifest['status'] == 'AWAITING_REVIEW'
    assert [row['status'] for row in manifest['stages']][2:] == ['WAITING'] * 3
    assert not (directory / 'review.json').exists()
    assert not list((directory / 'executions').iterdir())
