"""Check that the advanced UI presents the original plans and evidence."""
import json
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from target.scenario_generator import ROOT, Store
from target.scenario_plans import candidate, plans
from target.scenario_quality import coverage, model_comparison, quality
from web.scenario_advanced import PLAN_COPY, _metric_card


@pytest.fixture
def desk(monkeypatch):
    root = ROOT / 'artifacts/runtime' / ('scenario-advanced-test-' + uuid4().hex)
    monkeypatch.setenv('TICKET_AI_SCENARIO_ROOT', str(root))
    monkeypatch.setenv('TICKET_DISABLE_LOCAL_SECRETS', '1')
    monkeypatch.setenv('TICKET_WEB_OFFLINE_ONLY', '1')
    return AppTest.from_string('from web.scenario_generator import page\npage()'), Store(root)


def report_cards(app):
    return ''.join(node.proto.body for node in app.get('html') if '<article class="ta-advanced-metric"' in node.proto.body)


def test_preset_choices_and_import_keep_original_plan_and_review_gate(desk):
    app, store = desk
    app.run()
    assert not app.exception
    references = {plan['title']: plan for plan in plans()}
    select = app.selectbox(key='scenario_reference_plan')
    assert set(references) == set(PLAN_COPY)
    assert select.options == [PLAN_COPY[key][0] for key in references]
    select.select('lifecycle').run()
    assert any('部分退款、改签及退清后取消订单' in element.value for element in app.markdown)
    app.selectbox(key='scenario_reference_plan').select('railway_queries').run()
    assert any('车站搜索、区间车次和指定车次的经停查询' in element.value for element in app.markdown)
    app.button(key='scenario_import_reference').click().run()
    assert not app.exception
    row, = store.list()
    assert row['status'] == 'PENDING'
    assert row['body']['generation_model'] == 'deterministic_reference_plan'
    assert row['body']['integration_steps'] == references['railway_queries']['integration_steps']
    assert not store.runs() and not store.generations()
    assert not (store.root / 'generation-budget.sqlite').exists()
    with pytest.raises(ValueError, match='approved current revision required'):
        store.run(row['id'], row['revision'])


def test_empty_report_shows_no_evidence_and_keeps_help_and_raw_json(desk):
    app, store = desk
    app.run()
    assert not app.exception
    cards = report_cards(app)
    assert cards.count('尚无执行证据') == 7
    assert '不适用' in cards and '<progress' not in cards and '0%' not in cards
    html = [node.proto.body for node in app.get('html') if '<summary>这是什么？</summary>' in node.proto.body]
    assert len(html) == 2 and all('容易误解什么？' in node for node in html)
    assert any(block.label == '查看技术详情' for block in app.expander)
    assert [json.loads(node.value) for node in app.json[:3]] == [
        quality([], []), coverage([]), model_comparison([], [])]
    assert not store.runs()


def test_report_cards_match_actual_execution_and_preserve_failed_history(desk):
    app, store = desk
    case = candidate(plans()[0])
    store.save(case, 'reference-plan-import')
    store.decide([(case['case_id'], 1)], 'APPROVED', 'offline-test-reviewer')
    result = store.run(case['case_id'], 2)
    assert result['status'] == 'passed' and result['model_requests'] == 0
    with store.connect() as connection:
        connection.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)', ('fixture-previous-fail', case['case_id'], 2,
                           'failed', json.dumps({'status': 'failed', 'fault': 'ui_drift', 'mode': 'deterministic_v310_integration'}),
                           '2000-01-01T00:00:00Z'))
    before_rows, before_runs = store.list(), store.runs()
    original = quality(before_rows, before_runs)
    measured = coverage([run['body'] for run in before_runs])
    models = model_comparison(store.original_candidates(), store.generations())
    app.run()
    assert not app.exception
    assert [json.loads(node.value) for node in app.json[:3]] == [original, measured, models]
    cards = report_cards(app)
    for ratio in (original['execution'], original['parameters'], measured['tools'], measured['trace']):
        assert f'<strong>{ratio["display"]}</strong>' in cards
        assert f'value="{ratio["numerator"]}" max="{ratio["denominator"]}"' in cards
    assert '<strong>1/2</strong>' in cards
    assert store.list() == before_rows and store.runs() == before_runs


@pytest.mark.parametrize('metric,available,text', [
    ({}, True, '未知'),
    ({'numerator': 0, 'denominator': 0, 'value': None}, True, '不适用'),
    ({'numerator': 0, 'denominator': 11, 'value': 0}, False, '尚无执行证据'),
])
def test_unavailable_metrics_have_no_percentage(metric, available, text):
    card = _metric_card('工具覆盖', metric, '统计说明', available=available)
    assert text in card and '<progress' not in card and '%' not in card
