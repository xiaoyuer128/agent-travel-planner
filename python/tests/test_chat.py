from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.app import app
from chat.store import SessionStore

PROMPT = "两个人，预算8000，重庆出发，去杭州，2026-12-01出发，玩5天"

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))
    return TestClient(app)

def new(client):
    r = client.post('/api/chat/sessions')
    assert r.status_code == 201
    return r.json()

def turn(client, session, text, **extra):
    r = client.post(f"/api/chat/sessions/{session['id']}/messages",
                    json={"message": text, "revision": session['revision'], **extra})
    assert r.status_code == 200, r.text
    return r.json()

def test_collect_then_plan(client):
    s = turn(client, new(client), "两个人，预算8000，重庆出发")
    assert s['plan'] is None
    assert s['preferences']['num_travelers'] == 2
    assert '目的地' in s['messages'][-1]['content']
    s = turn(client, s, '去杭州，2026-12-01出发，玩5天')
    assert s['plan']['preferences']['departure_city'] == '重庆'
    assert s['trace'] == ['understand','collect','retrieve','plan','validate','respond']
    assert len(s['plan']['days']) == 5
    assert s['plan']['cost']['nights'] == 4

def test_hotel_edit_preserves_others_and_prices(client):
    s = turn(client, new(client), PROMPT)
    old = deepcopy(s['plan'])
    s = turn(client, s, '酒店换便宜一些，其他不变')
    p = s['plan']
    assert p['flights'] == old['flights'] and p['days'] == old['days']
    assert p['hotel']['id'] != old['hotel']['id']
    assert p['cost']['total_cents'] < old['cost']['total_cents']
    assert s['versions'][0] == old
    s = turn(client, s, '酒店换便宜一些')
    assert s['plan']['hotel']['price_cents'] == p['hotel']['price_cents']

def test_budget_change_no_fake_discount(client):
    s = turn(client, new(client), PROMPT)
    old = deepcopy(s['plan'])
    s = turn(client, s, '预算改成100')
    assert s['plan']['flights'] == old['flights']
    assert s['plan']['hotel'] == old['hotel']
    assert not s['plan']['cost']['within_budget']
    assert '超预算' in s['messages'][-1]['content']

def test_activity_edit_preserves_hotel_and_flights(client):
    s = turn(client, new(client), PROMPT)
    old = deepcopy(s['plan'])
    s = turn(client, s, '增加美食活动')
    assert s['plan']['hotel'] == old['hotel']
    assert s['plan']['flights'] == old['flights']
    assert s['preferences']['interests'] == ['美食']

def test_grounding_and_unknown_city(client):
    s = turn(client, new(client), PROMPT)
    sources = {x['id']:x for x in s['plan']['sources']}
    assert sources
    for day in s['plan']['days']:
        assert day['description'] == sources[day['source_ids'][0]]['text']
    s = turn(client, s, '更换目的地', patch={'destination':'火星城'})
    assert s['plan']['sources'] == []
    assert all(not day['source_ids'] for day in s['plan']['days'])

def test_restore_is_new_version(client):
    s = turn(client, new(client), PROMPT)
    old = deepcopy(s['plan'])
    s = turn(client, s, '酒店换便宜一些')
    r = client.post(f"/api/chat/sessions/{s['id']}/restore/1",json={'message':'恢复','revision':s['revision']})
    assert r.status_code == 200
    updated = r.json()
    assert updated['plan']['hotel'] == old['hotel']
    assert updated['plan']['version'] == 3

def test_persistence_and_isolation(client):
    s = turn(client, new(client), PROMPT)
    second = new(client)
    restored = client.get(f"/api/chat/sessions/{s['id']}").json()
    assert restored == s
    assert client.get(f"/api/chat/sessions/{second['id']}").json()['messages'] == []
    assert len(client.get('/api/chat/sessions').json()) == 2

def test_conflicting_revision_and_missing_session(client):
    s = new(client)
    turn(client,s,PROMPT)
    r=client.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'酒店换便宜','revision':0})
    assert r.status_code == 409
    assert client.get('/api/chat/sessions/not-found').status_code == 404

@pytest.mark.parametrize('text', ['2026-02-30出发','人数99人','玩100天'])
def test_invalid_turn_keeps_plan(client, text):
    s=turn(client,new(client),PROMPT)
    changed=turn(client,s,text)
    assert changed['plan'] == s['plan']
    assert changed['preferences'] == s['preferences']
    assert '无效' in changed['messages'][-1]['content']

def test_blank_and_invalid_patch(client):
    s=new(client)
    url=f"/api/chat/sessions/{s['id']}/messages"
    assert client.post(url,json={'message':'  ','revision':0}).status_code == 422
    assert client.post(url,json={'message':'修改','revision':0,'patch':{'budget':-1}}).status_code == 422

def test_budget_components(client):
    s=turn(client,new(client),PROMPT)
    cost=s['plan']['cost']
    assert cost['total_cents'] == cost['flight_cents']+cost['hotel_cents']+cost['activity_cents']

def test_store_restart(tmp_path):
    path=tmp_path/'persist.sqlite3'
    first=SessionStore(path)
    s=first.create();s['preferences']={'destination':'杭州'}
    saved=first.save(s,0)
    assert SessionStore(path).get(s['id']) == saved
