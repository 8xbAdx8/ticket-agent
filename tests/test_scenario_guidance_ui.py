"""Exercise the original generation form with the new guidance rendered."""
from pathlib import Path
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from target.scenario_generator import Store
from web.scenario_examples import CONSTRAINTS_PLACEHOLDER, OBJECTIVE_PLACEHOLDER


@pytest.fixture
def desk(monkeypatch):
    root = Path(__file__).resolve().parents[1] / 'artifacts/runtime' / ('scenario-guidance-test-' + uuid4().hex)
    monkeypatch.setenv('TICKET_AI_SCENARIO_ROOT', str(root))
    monkeypatch.setenv('TICKET_DISABLE_LOCAL_SECRETS', '1')
    monkeypatch.setenv('TICKET_WEB_OFFLINE_ONLY', '1')
    calls = []
    generate = Store.generate

    def record(store, objective, category, difficulty, count, provider, constraints='', adapter='p2'):
        calls.append((objective, category, difficulty, count, provider, constraints, adapter))
        assert provider == 'Mock'
        return generate(store, objective, category, difficulty, count, provider, constraints, adapter=adapter)

    monkeypatch.setattr(Store, 'generate', record)
    app = AppTest.from_string('from web.scenario_generator import page\npage()').run()
    assert not app.exception
    return app, root, calls


def widget(items, label):
    return next(item for item in items if item.label == label)


def test_guidance_is_rendered_without_default_input(desk):
    app, root, calls = desk
    objective, constraints = app.text_area
    assert objective.value == constraints.value == ''
    assert objective.proto.placeholder == OBJECTIVE_PLACEHOLDER
    assert constraints.proto.placeholder == CONSTRAINTS_PLACEHOLDER
    html = [node.proto.body for node in app.get('html') if 'data-scenario-target=' in node.proto.body]
    assert len(html) == 2
    assert '示例目标' in html[0] and 'railway_query_trips' in html[0] and 'trip_short_name' in html[0]
    assert '示例约束' in html[1] and 'result.data.stops' in html[1] and 'enabled' in html[1]
    assert all(card.count('type="button"') == 2 for card in html)
    assert not calls and not Store(root).generations()
    assert not (root / 'generation-budget.sqlite').exists()


def test_blank_objective_still_uses_existing_validation(desk):
    app, root, calls = desk
    widget(app.button, '生成候选场景').click().run()
    assert calls[0][0] == calls[0][5] == ''
    assert app.error[0].value == 'invalid generation requirements'
    assert not Store(root).generations()


def test_custom_submission_retains_settings_and_pending_gate(desk):
    app, root, calls = desk
    app.text_area(key='ai_scenario_objective').set_value('验证工具调用')
    app.text_area(key='ai_scenario_constraints').set_value('仅用项目工具')
    widget(app.selectbox, '测试领域').select('工具调用')
    widget(app.selectbox, '测试难度').select('hard')
    widget(app.number_input, '生成数量').set_value(2)
    widget(app.selectbox, '生成目标适配器').select('Legacy P2')
    widget(app.button, '生成候选场景').click().run()
    assert not app.exception
    assert calls == [('验证工具调用', '工具调用', 'hard', 2, 'Mock', '仅用项目工具', 'p2')]
    store = Store(root)
    assert len(store.list()) == 2 and all(row['status'] == 'PENDING' for row in store.list())
    assert all(row['body']['generation_model'] == 'deterministic_mock' for row in store.list())
    assert not store.runs() and not (root / 'generation-budget.sqlite').exists()


def test_online_submission_without_consent_never_reaches_generator(desk):
    app, root, calls = desk
    app.text_area(key='ai_scenario_objective').set_value('验证 G7331')
    widget(app.selectbox, '生成模型').select('deepseek')
    widget(app.button, '生成候选场景').click().run()
    assert any(warning.value == '请先授权本次在线生成。' for warning in app.warning)
    assert not calls and not Store(root).generations()
    assert not (root / 'generation-budget.sqlite').exists()
