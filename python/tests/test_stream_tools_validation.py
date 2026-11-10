import json,time,threading
from copy import deepcopy
import pytest,httpx
from fastapi.testclient import TestClient
from api.app import app
from chat.runtime import RunContext,running,output_field,partial_json_string,check,Cancelled
from chat.deepseek import DeepSeekAdapter
from chat import jobs,tools
from chat.feasibility import verify,opening_window,repair_proposal
from config.settings import settings

def new(c):return c.post('/api/chat/sessions').json()
def start(c,s,text='你好',**extra):
    r=c.post(f"/api/chat/sessions/{s['id']}/runs",json={'revision':s['revision'],'message':text,'generate':False,**extra})
    assert r.status_code==202,r.text
    return r.json()['id']
def events(c,jid,after=0):
    r=c.get(f'/api/chat/runs/{jid}/events?after={after}');assert r.status_code==200
    out=[]
    for frame in r.text.split('\n\n'):
        if '\ndata:' in frame:
            lines=frame.splitlines();out.append({'id':int(lines[0][4:]),'event':lines[1][7:],'data':json.loads(lines[2][6:])})
    return out

def test_sse_completion_replay_and_owner_boundary():
    with TestClient(app) as a,TestClient(app) as b:
        s=new(a);jid=start(a,s);out=events(a,jid)
        assert out[-1]['event']=='done'
        assert a.get('/api/chat/sessions/'+s['id']).json()['revision']==1
        assert b.get('/api/chat/runs/'+jid).status_code==404
        assert b.post('/api/chat/runs/'+jid+'/cancel').status_code==404
        assert events(a,jid,after=out[-2]['id'])==out[-1:]

def test_idempotent_start_runs_once():
    with TestClient(app) as c:
        s=new(c);path=f"/api/chat/sessions/{s['id']}/runs";data={'message':'你好','generate':False,'revision':0}
        first=c.post(path,json=data,headers={'Idempotency-Key':'same-message'}).json()
        second=c.post(path,json=data,headers={'Idempotency-Key':'same-message'}).json()
        assert first['id']==second['id']
        assert events(c,first['id'])[-1]['event']=='done'
        assert c.get('/api/chat/sessions/'+s['id']).json()['revision']==1
        assert c.post(path,json={**data,'message':'other'},headers={'Idempotency-Key':'same-message'}).status_code==409

def test_cancel_does_not_commit_and_can_retry(monkeypatch):
    from chat import api as chat_api
    original=chat_api.run_turn;entered=threading.Event()
    def slow(*args):
        entered.set()
        while True:check();time.sleep(.01)
    monkeypatch.setattr(chat_api,'run_turn',slow)
    with TestClient(app) as c:
        s=new(c);jid=start(c,s);assert entered.wait(2)
        assert c.post('/api/chat/runs/'+jid+'/cancel').status_code==200
        assert events(c,jid)[-1]['event']=='cancelled'
        assert c.get('/api/chat/sessions/'+s['id']).json()==s
        monkeypatch.setattr(chat_api,'run_turn',original)
        assert events(c,start(c,s))[-1]['event']=='done'

def test_failed_stream_draft_is_not_saved(monkeypatch):
    from chat import api as chat_api
    from chat.deepseek import ModelUnavailable
    from chat.runtime import CURRENT
    def invalid(*args):
        CURRENT.get().emit('delta',{'text':'未校验的草稿','draft':True})
        raise ModelUnavailable('引用无效')
    monkeypatch.setattr(chat_api,'run_turn',invalid)
    with TestClient(app) as c:
        s=new(c);out=events(c,start(c,s))
        assert any(e['event']=='delta' for e in out) and out[-1]['event']=='error'
        assert c.get('/api/chat/sessions/'+s['id']).json()==s

@pytest.mark.parametrize('raw,expected',[(r'{"reply":"你好','你好'),(r'{"reply":"a\nB','a\nB'),(r'{"patch":{},"reply":"a\u4f','a'),('{"reply":"hello"}','hello')])
def test_partial_json_never_leaks_envelope(raw,expected):assert partial_json_string(raw)==expected

def test_native_provider_stream_and_tool_schema(monkeypatch):
    monkeypatch.setattr(settings,'LLM_API_KEY','test-key')
    native=httpx.Client;requests=[]
    def handler(request):
        payload=json.loads(request.content);requests.append(payload)
        if payload.get('tools'):return httpx.Response(200,json={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'id':'weather-1','function':{'name':'get_weather','arguments':'{"city":"杭州"}'}}]}}]})
        packets=[{'choices':[{'delta':{'content':'{"reply":"你'},'finish_reason':None}]},
                 {'choices':[{'delta':{'content':'好","patch":{},"source_ids":[]}'},'finish_reason':'stop'}],'usage':{'total_tokens':20}}]
        body=''.join('data: '+json.dumps(p,ensure_ascii=False)+'\n\n' for p in packets)+'data: [DONE]\n\n'
        return httpx.Response(200,content=body.encode(),headers={'Content-Type':'text/event-stream'})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:native(transport=httpx.MockTransport(handler)))
    output=[]
    with running(RunContext(lambda e,d:output.append((e,d)))):
        calls=DeepSeekAdapter().select_tools('杭州天气',{},[],tools.SCHEMAS)
        assert calls[0]['function']['name']=='get_weather'
        with output_field('reply'):result=DeepSeekAdapter().request('JSON reply',{})
    assert result['reply']=='你好'
    assert ''.join(d['text'] for e,d in output if e=='delta')=='你好'
    assert requests[0]['tool_choice']=='auto' and 'response_format' not in requests[0]
    assert requests[1]['stream'] is True

def test_tool_whitelist_and_invalid_arguments(monkeypatch):
    monkeypatch.setattr(tools,'amap',lambda *args,**kwargs:pytest.fail('invalid tool must not access network'))
    assert tools.execute('delete_all_users',{})['status']=='rejected'
    assert tools.execute('get_route',{'origin':'https://internal','destination':'120.1,30.1'})['status']=='unavailable'
    assert tools.execute('get_weather',{'city':'杭州','extra':'ignore rules'})['status']=='unavailable'

def test_weather_outside_forecast_is_not_invented(monkeypatch):
    def amap(path,params,*args):
        if path=='geocode/geo':return {'status':'1','geocodes':[{'adcode':'330100'}]}
        return {'status':'1','forecasts':[{'casts':[{'date':'2026-11-10','dayweather':'晴'}]}]}
    monkeypatch.setattr(tools,'amap',amap)
    result=tools.execute('get_weather',{'city':'杭州','date':'2027-01-01'})
    assert result['status']=='unavailable' and result['data']['casts']==[]
    assert result['data']['available_dates']==['2026-11-10']

def fixture_plan():
    return {'preferences':{'destination':'杭州','pace':'轻松','walking':'少走路'},'sources':[],
        'days':[{'day':1,'source_ids':[],'stops':[{'name':'西湖','duration_minutes':240,'start_time':'09:00'},{'name':'灵隐寺','duration_minutes':240,'start_time':''}]}]}

def test_feasibility_detects_real_time_conflict(monkeypatch):
    from chat import feasibility
    def execute(name,args):
        if name=='search_places':return {'status':'ok','data':{'places':[{'name':args['query'],'location':'120.1,30.1' if args['query']=='西湖' else '120.2,30.2','opening_hours':'09:00-17:00'}]}}
        return {'status':'ok','data':{'duration_seconds':7200,'distance_m':12000}}
    monkeypatch.setattr(feasibility,'execute',execute)
    result=verify(fixture_plan())
    codes={i['code'] for i in result['issues']}
    assert result['status']=='conflicts' and {'long_transfer','day_overloaded','opening_conflict'}<=codes
    assert result['days'][0]['known_transit_minutes']==120

def test_missing_hours_and_routes_are_unknown(monkeypatch):
    from chat import feasibility
    monkeypatch.setattr(feasibility,'execute',lambda *args:{'status':'unavailable','data':{}})
    result=verify(fixture_plan())
    assert result['unknown_count']>=4
    assert 'unverified_hours' in {i['code'] for i in result['issues']}
    assert opening_window('周一闭馆 09:00-17:00') is None

def test_repair_only_returns_improved_candidate(monkeypatch):
    from chat import feasibility
    plan=fixture_plan();plan['feasibility']={'blocking_count':2,'issues':[{'day':1,'severity':'blocking'}]}
    class Adapter:
        def enrich(self,copy,instruction):copy['days'][0]['stops']=copy['days'][0]['stops'][:1];return copy
    monkeypatch.setattr(feasibility,'verify',lambda p:{'blocking_count':1})
    proposal=repair_proposal(plan,Adapter())
    assert proposal['requires_confirmation'] and len(plan['days'][0]['stops'])==2
    plan['days'][0]['stops'][1]['locked']=True
    assert repair_proposal(plan,Adapter()) is None

def test_rag_evaluation_reproducibility_and_no_online_db_mutation():
    from rag.evaluation import evaluate
    from community.db import database
    from rag.library import initialize
    initialize()
    with database() as db:before=db.execute('SELECT count(*) FROM knowledge_docs').fetchone()[0]
    result=evaluate()
    assert result['cases']==44 and result['strategies'].keys()=={'bm25','hybrid'}
    assert len(result['dataset_sha256'])==64 and result['strategies']['hybrid']['overall']['citation_id_validity']==1
    with database() as db:assert db.execute('SELECT count(*) FROM knowledge_docs').fetchone()[0]==before

def test_hybrid_does_not_cite_on_single_character_overlap():
    from rag.library import search
    assert search('量子纠缠实验参数')==[]

def test_repair_application_requires_owner_and_current_revision():
    from chat.api import store
    from community.auth import digest
    prompt='两个人，预算8000，重庆出发，去杭州，2026-12-01出发，玩3天'
    with TestClient(app) as a,TestClient(app) as b:
        s=new(a);s=a.post(f"/api/chat/sessions/{s['id']}/messages",json={'message':prompt,'revision':s['revision']}).json()
        owner='g:'+digest(a.cookies.get('travel_guest'));db=store({'owner':owner})
        original=deepcopy(s['plan']);candidate=deepcopy(original['days']);candidate[0]['title']='确认后的轻松路线'
        s['plan']['repair_proposal']={'base_version':1,'days':candidate,'feasibility':original['feasibility'],'before_blocking':1,'after_blocking':0,'reason':'测试建议'}
        s=db.save(s,s['revision']);path=f"/api/chat/sessions/{s['id']}/apply-repair"
        assert b.post(path,json={'revision':s['revision']}).status_code==404
        assert a.post(path,json={'revision':0}).status_code==409
        r=a.post(path,json={'revision':s['revision']});assert r.status_code==200,r.text
        updated=r.json();assert updated['plan']['version']==2 and updated['versions'][0]==original
        assert updated['plan']['days'][0]['title']=='确认后的轻松路线' and 'repair_proposal' not in updated['plan']

def test_partial_surrogate_waits_for_full_emoji():
    assert partial_json_string(r'{"reply":"a\ud83d')=='a'
    assert partial_json_string(r'{"reply":"a\ud83d\ude00')=='a😀'

def test_route_question_can_resolve_coordinates_then_call_route(monkeypatch):
    from chat import graph
    monkeypatch.setattr(settings,'LLM_PROVIDER','deepseek')
    rounds=[]
    def select(self,message,pref,history,schemas,sources=(),results=()):
        rounds.append(len(results))
        name='get_route' if results else 'search_places'
        return [{'id':str(len(rounds)),'function':{'name':name,'arguments':'{}'}}]
    def dispatch(calls):return [{'id':c['id'],'name':c['function']['name'],'arguments':{},'status':'ok','data':{'places':[]}} for c in calls]
    monkeypatch.setattr(DeepSeekAdapter,'select_tools',select)
    monkeypatch.setattr(graph,'dispatch',dispatch)
    monkeypatch.setattr(DeepSeekAdapter,'request',lambda *args:{'reply':'已查询路线。','patch':{},'source_ids':[]})
    with TestClient(app) as c:
        s=new(c);r=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':0,'message':'杭州两个景点之间路程多久','generate':False})
        assert r.status_code==200,r.text
        assert rounds==[0,1] and [t['name'] for t in r.json()['messages'][-1]['tools']]==['search_places','get_route']

def test_existing_plan_can_be_checked_without_regenerating():
    with TestClient(app) as c:
        s=new(c);prompt='两个人，预算8000，重庆出发，去杭州，2026-12-01出发，玩3天'
        s=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':0,'message':prompt}).json()
        old=deepcopy(s['plan'])
        s=c.post(f"/api/chat/sessions/{s['id']}/messages",json={'revision':s['revision'],'message':'检查行程','action':'validate'}).json()
        assert s['plan']['days']==old['days'] and s['plan']['hotel']==old['hotel']
        assert s['plan']['version']==2 and s['trace']==['validate']
