from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from api.app import app
from chat.deepseek import DeepSeekAdapter, ModelUnavailable
from config.settings import settings

def test_real_graph_and_hotel_invariants(tmp_path,monkeypatch):
    monkeypatch.setenv('CHAT_DB_PATH',str(tmp_path/'chat.sqlite3'))
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    def request(self,system,context):
        if 'estimate_scope' in context: return {}
        if 'message' in context:
            if '便宜' in context['message']: return {'patch':{},'action':'hotel_cheaper'}
            return {'patch':{'departure_city':'重庆','destination':'杭州','budget':8000,'num_travelers':2,'days':3,'start_date':'2026-12-01'},'action':'auto'}
        return {'days':[{'day':i,'title':'西湖漫步','description':'围绕西湖安排慢旅行。','source_ids':[context['sources'][0]['id']]} for i in range(1,4)]}
    monkeypatch.setattr(DeepSeekAdapter,'request',request)
    with TestClient(app) as c:
        s=c.post('/api/chat/sessions').json()
        s=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'去杭州','revision':0}).json()
        assert s['provider']=='deepseek' and s['plan']['mode']=='deepseek'
        old=deepcopy(s['plan'])
        s=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'酒店便宜一些','revision':1}).json()
        assert s['plan']['days']==old['days'] and s['plan']['flights']==old['flights']
        assert s['plan']['hotel']['price_cents'] < old['hotel']['price_cents']

def test_model_failure_does_not_commit(tmp_path,monkeypatch):
    monkeypatch.setenv('CHAT_DB_PATH',str(tmp_path/'chat.sqlite3'))
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    def failed(*args): raise ModelUnavailable('DeepSeek 账户余额不足（HTTP 402）。')
    monkeypatch.setattr(DeepSeekAdapter,'request',failed)
    with TestClient(app) as c:
        s=c.post('/api/chat/sessions').json()
        r=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'去杭州','revision':0})
        assert r.status_code==502 and '余额不足' in r.json()['detail']
        assert c.get(f"/api/chat/sessions/{s['id']}").json()==s

def test_fabricated_citation_rejected(monkeypatch):
    monkeypatch.setattr(DeepSeekAdapter,'request',lambda *args: {'days':[{'day':1,'title':'标题','description':'描述','source_ids':['invented']} ]})
    plan={'preferences':{},'days':[{'day':1}], 'sources':[{'id':'actual'}]}
    with pytest.raises(ModelUnavailable): DeepSeekAdapter().enrich(plan)
