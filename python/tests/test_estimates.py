"""Offline regression for generated budgets, omissions and partial edits."""
import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from api.app import app
from chat.deepseek import DeepSeekAdapter, ModelUnavailable
from chat.estimates import BudgetEstimate, apply_estimate
from chat.planner import build_plan
from config.settings import settings


PREFERENCES = {
    'departure_city': '重庆', 'destination': '杭州', 'budget': 8000,
    'num_travelers': 2, 'days': 3, 'start_date': '2026-12-01',
}


def estimate_payload():
    return {
        'flights': [{'price_cents': 50000}, {'price_cents': 60000}],
        'hotels': [{'price_cents': 10000}, {'price_cents': 18000}, {'price_cents': 30000}],
        'daily_costs': [
            {'day': day, 'tickets_cents': 6000, 'meals_cents': 9000, 'local_transport_cents': 3000}
            for day in range(1, 4)
        ],
    }


def plan():
    return build_plan(PREFERENCES, [
        {'id': 'guide', 'title': '西湖', 'text': '围绕西湖慢行。'}
    ])[0]


def test_estimate_totals_and_missing_fields():
    result = apply_estimate(plan(), BudgetEstimate.model_validate(estimate_payload()))
    # Independent arithmetic: flights 2200 + hotel 360 + daily expenses 1080 yuan.
    assert result['cost']['total_cents'] == 364000
    assert result['cost']['meals_cents'] == 54000
    assert result['price_metadata']['fallback_fields'] == []
    assert 'AI预算估算' in result['warnings'][0]
    missing = apply_estimate(plan(), BudgetEstimate())
    assert len(missing['flights']) == 2 and len(missing['hotel_options']) == 3
    assert len(missing['price_metadata']['fallback_fields']) == 14
    assert missing['hotel']['source_kind'] == 'planning_assumption'
    assert missing['cost']['total_cents'] > 0
    assert any('未查询历史价格数据库' in warning for warning in missing['warnings'])


@pytest.mark.parametrize('value', [-1, 1.5, True, 9_000_000])
def test_invalid_money_rejects_instead_of_inventing_a_value(monkeypatch, value):
    monkeypatch.setattr(DeepSeekAdapter, 'request', lambda *args: {'flights': [{'price_cents': value}]})
    original = plan()
    before = deepcopy(original)
    with pytest.raises(ModelUnavailable):
        DeepSeekAdapter().estimate(original)
    assert original == before


@pytest.mark.parametrize('days', [[{'day': 1}, {'day': 1}], [{'day': 4}]])
def test_duplicate_or_out_of_range_days_fail(monkeypatch, days):
    monkeypatch.setattr(DeepSeekAdapter, 'request', lambda *args: {'daily_costs': days})
    with pytest.raises(ModelUnavailable):
        DeepSeekAdapter().estimate(plan())


def test_estimate_uses_json_mode_and_existing_http_adapter(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_API_KEY', 'test-only')
    native_client = httpx.Client

    def respond(request):
        payload = json.loads(request.content)
        assert payload['response_format'] == {'type': 'json_object'}
        context = json.loads(payload['messages'][1]['content'])
        assert context['estimate_scope'] == 'full'
        assert 'schema' in context
        return httpx.Response(200, json={'choices': [{
            'finish_reason': 'stop', 'message': {'content': json.dumps(estimate_payload())}
        }]})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: native_client(transport=httpx.MockTransport(respond)))
    assert DeepSeekAdapter().estimate(plan())['cost']['total_cents'] == 364000


def test_partial_edits_and_export_keep_estimates_consistent(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'deepseek')
    calls = []

    def request(self, system, context):
        if 'estimate_scope' in context:
            calls.append(context['estimate_scope'])
            result = estimate_payload()
            if context['estimate_scope'] == 'daily':
                result['daily_costs'][1]['meals_cents'] = 12000
            return result
        if 'message' in context:
            text = context['message']
            if '便宜' in text:
                return {'patch': {}, 'action': 'hotel_cheaper'}
            if '预算' in text:
                return {'patch': {'budget': 6000}, 'action': 'auto'}
            if '第二天' in text:
                return {'patch': {}, 'action': 'activity'}
            return {'patch': PREFERENCES, 'action': 'auto'}
        return {'days': [
            {'day': day, 'title': '路线调整', 'description': '慢游西湖',
             'source_ids': [context['sources'][0]['id']]}
            for day in range(1, 4)
        ]}

    monkeypatch.setattr(DeepSeekAdapter, 'request', request)
    with TestClient(app) as client:
        session = client.post('/api/chat/sessions').json()

        def turn(text):
            response = client.post(f'/api/chat/sessions/{session["id"]}/messages',
                                   json={'message': text, 'revision': session['revision']})
            assert response.status_code == 200, response.text
            session.update(response.json())

        turn('生成杭州行程')
        before = deepcopy(session['plan'])
        turn('酒店便宜一些')
        assert session['plan']['hotel']['price_cents'] == 10000
        assert session['plan']['flights'] == before['flights']
        assert session['plan']['days'] == before['days']
        turn('预算改6000')
        assert calls == ['full']
        before = deepcopy(session['plan'])
        turn('只修改第二天，其他不变')
        assert calls == ['full', 'daily']
        after = session['plan']
        assert after['days'][0] == before['days'][0]
        assert after['days'][2] == before['days'][2]
        assert after['hotel'] == before['hotel'] and after['flights'] == before['flights']
        assert after['cost']['total_cents'] - before['cost']['total_cents'] == 6000
        exported = client.get(f'/api/chat/sessions/{session["id"]}/export')
        assert 'AI估算总费用' in exported.text and '以预订平台为准' in exported.text


def test_bad_estimate_does_not_save_session(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'deepseek')

    def request(self, system, context):
        if 'estimate_scope' in context:
            return {'hotels': [{'price_cents': -100}]}
        if 'message' in context:
            return {'patch': PREFERENCES, 'action': 'auto'}
        return {'days': [
            {'day': day, 'title': '西湖', 'description': '慢行', 'source_ids': [context['sources'][0]['id']]}
            for day in range(1, 4)
        ]}

    monkeypatch.setattr(DeepSeekAdapter, 'request', request)
    with TestClient(app) as client:
        session = client.post('/api/chat/sessions').json()
        response = client.post(f'/api/chat/sessions/{session["id"]}/messages',
                               json={'message': '生成行程', 'revision': 0})
        assert response.status_code == 502
        assert client.get(f'/api/chat/sessions/{session["id"]}').json() == session
