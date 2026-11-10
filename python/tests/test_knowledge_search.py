import pytest,httpx
from fastapi.testclient import TestClient
from api.app import app
from rag.library import ingest,search,remove
from config.settings import settings
from chat.deepseek import DeepSeekAdapter

def test_persistent_chinese_chunks_and_delete():
    body='泉州开元寺适合人文步行探索。西街可以安排街区漫步与休息。' * 40
    did=ingest('泉州人文路线','泉州','测试资料','https://example.com/guide',body)
    hits=search('泉州开元寺西街','泉州')
    assert hits and any(h['id'].startswith(did) for h in hits)
    assert all(h['city'] in ('泉州','') for h in hits)
    assert max(len(h['text']) for h in hits)<=650
    assert search('泉州开元寺','北京')==[]
    remove(did)
    assert not any(h['id'].startswith(did) for h in search('泉州开元寺'))

def test_casual_chat_does_not_require_trip_fields(monkeypatch):
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    def request(self,system,context):
        assert 'sources' in context
        return {'reply':'你好！可以先聊聊喜欢的风景，不必填写预算。','patch':{},'source_ids':[]}
    monkeypatch.setattr(DeepSeekAdapter,'request',request)
    with TestClient(app) as c:
        s=c.post('/api/chat/sessions').json()
        r=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'你好，先聊聊','revision':s['revision'],'generate':False})
        assert r.status_code==200,r.text
        value=r.json()
        assert not value['plan'] and not value['versions']
        assert '还需要' not in value['messages'][-1]['content']
        assert value['trace']==['retrieve_knowledge','tools','chat']

def test_casual_answer_uses_imported_knowledge(monkeypatch):
    did=ingest('泉州开元寺步行','泉州','文旅参考','https://example.com/qz','泉州开元寺与西街可以结合步行探索，预留休息时间，不要安排过密。')
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    def request(self,system,context):
        source=next(s for s in context['sources'] if s['id'].startswith(did))
        return {'reply':'可围绕开元寺与西街慢慢走。','patch':{'destination':'泉州'},'source_ids':[source['id']]}
    monkeypatch.setattr(DeepSeekAdapter,'request',request)
    with TestClient(app) as c:
        s=c.post('/api/chat/sessions').json()
        r=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'泉州开元寺西街怎么逛','revision':0,'generate':False})
        assert r.status_code==200,r.text
        assert r.json()['messages'][-1]['sources'][0]['source']=='文旅参考'
        assert r.json()['preferences']['destination']=='泉州'

def test_fabricated_chat_citation_does_not_commit(monkeypatch):
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    monkeypatch.setattr(DeepSeekAdapter,'request',lambda *args:{'reply':'回答','patch':{},'source_ids':['not-retrieved']})
    with TestClient(app) as c:
        s=c.post('/api/chat/sessions').json()
        r=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':'你好','revision':0,'generate':False})
        assert r.status_code==502
        assert c.get('/api/chat/sessions/'+s['id']).json()==s

def test_knowledge_write_requires_admin(monkeypatch):
    monkeypatch.setenv('ADMIN_EMAILS','admin@example.com')
    with TestClient(app) as c:
        doc={'title':'测试知识','city':'厦门','source':'测试来源','body':'厦门旅行可以结合园林与海边步行，具体开放以景区公告为准。'}
        assert c.post('/api/knowledge/documents',json=doc).status_code==401
        c.post('/api/account/register',json={'email':'reader@example.com','password':'testing-password'})
        assert c.post('/api/knowledge/documents',json=doc).status_code==403
        c.post('/api/account/logout')
        c.post('/api/account/register',json={'email':'admin@example.com','password':'testing-password'})
        r=c.post('/api/knowledge/documents',json=doc)
        assert r.status_code==201,r.text
        assert any(d['id']==r.json()['id'] for d in c.get('/api/knowledge/documents').json())

def test_nationwide_live_search_and_pagination(monkeypatch):
    from api import discover
    discover._search_cache.clear();monkeypatch.setenv('AMAP_API_KEY','test-key')
    calls=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,params):
            calls.append(params)
            return httpx.Response(200,json={'status':'1','count':'25','pois':[{'id':'QZ-1','name':'泉州开元寺','cityname':'泉州市','address':'西街','type':'风景名胜;寺庙','location':'118.5,24.9','photos':[]}]})
    monkeypatch.setattr(discover.httpx,'AsyncClient',Client)
    with TestClient(app) as c:
        r=c.get('/api/discover/search',params={'q':'泉州开元寺','page':2})
        assert r.status_code==200,r.text
        assert r.json()['spots'][0]['city']=='泉州' and r.json()['has_more']
        assert calls[0]['page']==2 and 'citylimit' not in calls[0]
    discover._search_cache.clear()
