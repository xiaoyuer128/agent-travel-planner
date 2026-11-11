"""Product flows and trust boundaries; no external calls or fake throughput numbers."""
import io,json,time
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from api.app import app
from community.db import database
from chat.graph import run_turn

PROMPT='两个人，预算8000，重庆出发，去杭州，2026-12-01出发，玩3天'

@pytest.fixture
def clients(tmp_path,monkeypatch):
    monkeypatch.setenv('CHAT_DB_PATH',str(tmp_path/'chat.sqlite3'))
    monkeypatch.setenv('ADMIN_EMAILS','admin@example.com')
    from config.settings import settings
    monkeypatch.setattr(settings,'LLM_PROVIDER','mock')
    with TestClient(app) as a,TestClient(app) as b,TestClient(app) as admin:
        yield a,b,admin

def signup(c,email):
    r=c.post('/api/account/register',json={'email':email,'password':'testing-password','name':'测试旅行者'})
    assert r.status_code==201,r.text
    return r.json()

def plan(c):
    s=c.post('/api/chat/sessions').json()
    r=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':s['revision'],'message':PROMPT})
    assert r.status_code==200,r.text
    return r.json()

def picture(c):
    output=io.BytesIO();image=Image.new('RGB',(80,60),'green')
    exif=Image.Exif();exif[0x010E]='private camera metadata';image.save(output,'JPEG',exif=exif)
    r=c.post('/api/uploads',content=output.getvalue(),headers={'Content-Type':'application/octet-stream'})
    assert r.status_code==201,r.text
    return r.json()['id']

def test_guest_claim_and_user_isolation(clients):
    a,b,_=clients
    s=plan(a)
    assert b.get('/api/chat/sessions').json()==[]
    assert b.get('/api/chat/sessions/'+s['id']).status_code==404
    signup(a,'a@example.com');signup(b,'b@example.com')
    assert a.get('/api/chat/sessions/'+s['id']).status_code==200
    assert b.get('/api/chat/sessions/'+s['id']).status_code==404
    assert b.delete('/api/chat/sessions/'+s['id']).status_code==404
    token=a.cookies.get('travel_auth');a.post('/api/account/logout')
    assert a.get('/api/chat/sessions').json()==[]
    a.cookies.set('travel_auth',token)
    assert a.get('/api/account/me').json()['user'] is None

def test_password_and_origin_boundary(clients):
    a,_,_=clients
    signup(a,'a@example.com')
    with database() as db:
        row=db.execute('SELECT password FROM users').fetchone()
        assert 'testing-password' not in row['password'] and ':' in row['password']
    assert a.post('/api/account/login',json={'email':'a@example.com','password':'incorrect-password'}).status_code==401
    assert a.post('/api/account/logout',headers={'Origin':'https://untrusted.example'}).status_code==403
    assert a.get('/api/account/me').json()['user']['email']=='a@example.com'
    assert 'HttpOnly' in a.post('/api/account/login',json={'email':'a@example.com','password':'testing-password'}).headers['set-cookie']

def test_profile_defaults_and_override(clients):
    a,_,_=clients;signup(a,'a@example.com')
    r=a.put('/api/account/profile',json={'name':'小旅','departure_city':'上海','budget':3000,'pace':'轻松','transport':'高铁优先','interests':['文化']})
    assert r.status_code==200,r.text
    s=a.post('/api/chat/sessions').json()
    assert s['preferences']['departure_city']=='上海' and s['preferences']['budget']==3000
    changed=a.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':s['revision'],'message':'预算改成5000','generate':False}).json()
    assert changed['preferences']['budget']==5000
    assert a.get('/api/account/me').json()['user']['profile']['budget']==3000

def test_favorites_folders_and_feedback(clients):
    a,b,_=clients;signup(a,'a@example.com');signup(b,'b@example.com')
    folder=a.post('/api/folders',json={'name':'秋天想去'}).json()
    value={'folder_id':folder['id'],'kind':'spot','city':'杭州','name':'西湖','target':'spot:西湖'}
    assert a.post('/api/favorites',json=value).status_code==200
    assert a.post('/api/favorites',json=value).status_code==200
    assert len(a.get('/api/favorites').json())==1
    assert b.post('/api/favorites',json=value).status_code==404
    assert b.get('/api/favorites').json()==[]
    assert a.post('/api/feedback',json={'target':'city:杭州','value':'hide'}).status_code==200
    assert a.get('/api/feedback').json()['city:杭州']=='hide'
    a.delete('/api/folders/'+folder['id'])
    assert a.get('/api/favorites').json()==[]

def test_upload_privacy_and_validation(clients):
    a,b,_=clients
    assert a.post('/api/uploads',content=b'not-image').status_code==401
    signup(a,'a@example.com')
    uid=picture(a)
    response=a.get('/api/media/'+uid)
    assert response.status_code==200
    with Image.open(io.BytesIO(response.content)) as image: assert not image.getexif()
    assert b.get('/api/media/'+uid).status_code==404
    assert a.post('/api/uploads',content=b'<svg>evil</svg>').status_code==422
    assert a.post('/api/uploads',content=b'x'*(8*1024*1024+1)).status_code==413

def test_moderation_publication_report_and_reedit(clients):
    a,b,admin=clients;signup(a,'a@example.com');signup(b,'b@example.com');signup(admin,'admin@example.com')
    uid=picture(a)
    data={'title':'我的西湖旅行','body':'沿湖慢慢走，记录风景。','city':'杭州','visibility':'public','submit':True,'images':[uid]}
    r=a.post('/api/posts',json=data);assert r.status_code==201
    pid=r.json()['id']
    assert a.get('/api/posts?mine=true').json()[0]['status']=='pending'
    assert b.get('/api/posts').json()==[] and b.get('/api/media/'+uid).status_code==404
    assert b.post('/api/admin/posts/'+pid+'/review',json={'decision':'approved'}).status_code==403
    assert admin.get('/api/media/'+uid).status_code==200
    assert admin.post('/api/admin/posts/'+pid+'/review',json={'decision':'approved'}).status_code==200
    assert b.get('/api/posts').json()[0]['id']==pid and b.get('/api/media/'+uid).status_code==200
    assert b.post('/api/posts/'+pid+'/report',json={'reason':'需要管理员核实'}).status_code==200
    assert len(admin.get('/api/admin/queue').json()['reports'])==1
    assert admin.post('/api/admin/posts/'+pid+'/review',json={'decision':'hidden'}).status_code==200
    assert b.get('/api/media/'+uid).status_code==404
    assert a.put('/api/posts/'+pid,json=data).json()['status']=='pending'
    data['visibility']='private';data['submit']=False
    assert a.put('/api/posts/'+pid,json=data).json()['status']=='draft'
    assert b.get('/api/posts/'+pid).status_code==404
    assert b.put('/api/posts/'+pid,json=data).status_code==404

def test_cannot_attach_another_users_image(clients):
    a,b,_=clients;signup(a,'a@example.com');signup(b,'b@example.com');uid=picture(a)
    assert b.post('/api/posts',json={'title':'test','body':'test','city':'杭州','images':[uid]}).status_code==422

def test_share_snapshot_revocation_and_private_messages(clients):
    a,b,_=clients;signup(a,'a@example.com');s=plan(a)
    share=a.post(f"/api/chat/sessions/{s['id']}/share").json();token=share['path'].split('/')[-1]
    value=b.get('/api/shares/'+token).json()
    assert 'messages' not in value and value['plan']['version']==1
    a.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':s['revision'],'message':'酒店换便宜一些'})
    assert b.get('/api/shares/'+token).json()['plan']['version']==1
    a.delete(f"/api/chat/sessions/{s['id']}/share")
    assert b.get('/api/shares/'+token).status_code==404

def test_share_expiration(clients):
    a,b,_=clients;signup(a,'a@example.com');s=plan(a)
    token=a.post(f"/api/chat/sessions/{s['id']}/share").json()['path'].split('/')[-1]
    with database() as db:db.execute('UPDATE shares SET expires=?',(time.time()-1,))
    assert b.get('/api/shares/'+token).status_code==404

def test_prepare_confirmation_version_compare_and_checklist(clients):
    a,b,_=clients;s=a.post('/api/chat/sessions').json()
    s=a.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':0,'message':PROMPT,'generate':False}).json()
    assert not s['plan'] and not s['versions']
    s=a.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':s['revision'],'message':'生成方案'}).json()
    assert s['plan']['preferences']['destination']=='杭州'
    sid=s['id'];s=a.post(f'/api/chat/sessions/{sid}/messages',json={'revision':s['revision'],'message':'酒店换便宜一些'}).json()
    diff=a.get(f'/api/chat/sessions/{sid}/compare?a=1&b=2').json()
    assert diff['cost_delta_cents']<0 and [c['section'] for c in diff['changes']]==['hotel']
    items=a.get(f'/api/chat/sessions/{sid}/checklist').json();items[0]['done']=True
    assert a.put(f'/api/chat/sessions/{sid}/checklist',json={'items':items}).status_code==200
    assert a.get(f'/api/chat/sessions/{sid}/checklist').json()[0]['done']
    assert b.get(f'/api/chat/sessions/{sid}/checklist').status_code==404
    assert '保存为 PDF' in a.get(f'/api/chat/sessions/{sid}/export').text

def test_prepared_destination_change_is_applied(clients):
    a,_,_=clients;s=plan(a);sid=s['id']
    s=a.post(f'/api/chat/sessions/{sid}/messages',json={'revision':s['revision'],'message':'去南京','patch':{'destination':'南京'},'generate':False}).json()
    assert s['plan']['preferences']['destination']=='杭州'
    s=a.post(f'/api/chat/sessions/{sid}/messages',json={'revision':s['revision'],'message':'确认生成'}).json()
    assert s['plan']['preferences']['destination']=='南京' and '栖霞' in s['plan']['days'][0]['description']

def test_rename_and_delete_revoke_share(clients):
    a,b,_=clients;signup(a,'a@example.com');s=plan(a);sid=s['id']
    token=a.post(f'/api/chat/sessions/{sid}/share').json()['path'].split('/')[-1]
    r=a.patch('/api/chat/sessions/'+sid,json={'title':'秋日漫游','revision':s['revision']})
    assert r.status_code==200 and r.json()['title']=='秋日漫游'
    assert a.patch('/api/chat/sessions/'+sid,json={'title':'旧修改','revision':0}).status_code==409
    assert a.delete('/api/chat/sessions/'+sid).status_code==200
    assert b.get('/api/shares/'+token).status_code==404

def test_map_day_link_and_private_static_map(clients,monkeypatch):
    from community import journeys
    import httpx
    a,b,_=clients;s=plan(a);sid=s['id']
    async def spots(city):
        return {'spots':[{'name':'西湖','location':'120.14,30.25'},{'name':'灵隐飞来峰','location':'120.10,30.24'}]}
    monkeypatch.setattr(journeys,'spots',spots)
    result=a.get(f'/api/chat/sessions/{sid}/map?day=1').json()
    assert result['points'] and result['points'][0]['url'].startswith('https://uri.amap.com/')
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):return httpx.Response(200,content=b'PNG',headers={'content-type':'image/png'})
    monkeypatch.setattr(journeys.httpx,'AsyncClient',Client)
    journeys._maps.clear()
    assert a.get(f'/api/chat/sessions/{sid}/map-image?day=1').content==b'PNG'
    assert b.get(f'/api/chat/sessions/{sid}/map-image?day=1').status_code==404

def test_model_second_day_edit_preserves_other_days(clients,monkeypatch):
    from config.settings import settings
    from chat.deepseek import DeepSeekAdapter
    a,_,_=clients;s=plan(a);sid=s['id'];old=s['plan']['days']
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    def request(self,system,context):
        if 'estimate_scope' in context:return {}
        if 'message' in context:return {'patch':{},'action':'activity'}
        return {'days':[{'day':i,'title':'修改后的路线','description':'调整后的安排','source_ids':[context['sources'][0]['id']]} for i in range(1,4)]}
    monkeypatch.setattr(DeepSeekAdapter,'request',request)
    r=a.post(f'/api/chat/sessions/{sid}/messages',json={'revision':s['revision'],'message':'只修改第二天，安排轻松一点'})
    assert r.status_code==200,r.text
    days=r.json()['plan']['days']
    assert days[0]==old[0] and days[2]==old[2] and days[1]['title']=='修改后的路线'
