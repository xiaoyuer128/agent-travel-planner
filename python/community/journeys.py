import json,time,secrets,html,os
import httpx
from datetime import date
from urllib.parse import urlencode,quote
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import HTMLResponse,Response
from pydantic import BaseModel,Field
from .auth import identity,require_user,digest
from .db import database
from chat.api import get_session,store
from chat.store import Conflict
from api.discover import spots
from domestic import PLACES,GUIDES
from copy import deepcopy

router=APIRouter(prefix='/api',tags=['行程管理'])
_maps={}

class Rename(BaseModel):
    title:str=Field(min_length=1,max_length=60)
    revision:int=Field(ge=0)

class ApplyRepair(BaseModel):revision:int=Field(ge=0)

@router.post('/chat/sessions/{sid}/apply-repair')
def apply_repair(sid:str,data:ApplyRepair,who=Depends(identity)):
    session=get_session(sid,who);plan=session.get('plan')
    proposal=(plan or {}).get('repair_proposal')
    if not proposal or proposal.get('base_version')!=plan['version']:raise HTTPException(409,'当前版本没有可应用的调整建议')
    if data.revision!=session['revision']:raise HTTPException(409,'会话已更新，请刷新后重试')
    updated=deepcopy(plan);updated['days']=deepcopy(proposal['days']);updated['feasibility']=deepcopy(proposal['feasibility'])
    updated.pop('repair_proposal',None);updated['changed_sections']=['days','feasibility'];updated['version']=len(session['versions'])+1
    session['plan']=updated;session['versions'].append(deepcopy(updated))
    session['messages'].append({'role':'assistant','content':'已按你的确认应用路线调整，保存为新版本；待核实信息仍需出行前确认。'})
    try:return store(who).save(session,data.revision)
    except Conflict as exc:raise HTTPException(409,str(exc))

@router.patch('/chat/sessions/{sid}')
def rename(sid:str,data:Rename,who=Depends(identity)):
    session=get_session(sid,who);session['title']=data.title.strip()
    try:return store(who).save(session,data.revision)
    except Conflict as exc:raise HTTPException(409,str(exc))

@router.delete('/chat/sessions/{sid}')
def delete(sid:str,who=Depends(identity)):
    get_session(sid,who)
    with database() as db:
        db.execute('DELETE FROM chat_sessions WHERE id=? AND owner=?',(sid,who['owner']))
        db.execute('DELETE FROM shares WHERE session_id=? AND owner=?',(sid,who['owner']))
        db.execute('DELETE FROM checklists WHERE session_id=? AND owner=?',(sid,who['owner']))
    return {'ok':True}

@router.get('/chat/sessions/{sid}/compare')
def compare(sid:str,a:int,b:int,who=Depends(identity)):
    session=get_session(sid,who)
    versions=session['versions']
    if not (1<=a<=len(versions) and 1<=b<=len(versions)):raise HTTPException(404,'版本不存在')
    left,right=versions[a-1],versions[b-1]
    return {'a':a,'b':b,'cost_delta_cents':right['cost']['total_cents']-left['cost']['total_cents'],
        'changes':[{'section':key,'before':left.get(key),'after':right.get(key)} for key in ['preferences','hotel','days','flights'] if left.get(key)!=right.get(key)]}

@router.post('/chat/sessions/{sid}/share')
def share(sid:str,who=Depends(require_user)):
    session=get_session(sid,who)
    if not session.get('plan'):raise HTTPException(422,'请先生成方案')
    token=secrets.token_urlsafe(24);expires=time.time()+7*86400
    snapshot={'title':session['title'],'plan':session['plan']}
    with database() as db:
        db.execute('DELETE FROM shares WHERE session_id=? AND owner=?',(sid,who['owner']))
        db.execute('INSERT INTO shares VALUES(?,?,?,?,?)',(digest(token),who['owner'],sid,json.dumps(snapshot,ensure_ascii=False),expires))
    return {'path':'/#/share/'+token,'expires':expires}

@router.delete('/chat/sessions/{sid}/share')
def revoke(sid:str,who=Depends(require_user)):
    get_session(sid,who)
    with database() as db:db.execute('DELETE FROM shares WHERE session_id=? AND owner=?',(sid,who['owner']))
    return {'ok':True}

@router.get('/shares/{token}')
def shared(token:str):
    with database() as db:row=db.execute('SELECT snapshot FROM shares WHERE token=? AND expires>?',(digest(token),time.time())).fetchone()
    if not row:raise HTTPException(404,'分享已失效或被撤销')
    return json.loads(row['snapshot'])

@router.get('/chat/sessions/{sid}/map')
async def route_map(sid:str,day:int=1,who=Depends(identity)):
    session=get_session(sid,who);plan=session.get('plan')
    if not plan or not 1<=day<=len(plan['days']):raise HTTPException(404,'行程不存在')
    city=plan['preferences']['destination']
    info=await spots(city)
    current=plan['days'][day-1]
    docs={s['id']:s for s in plan['sources']}
    source_text=' '.join(docs[x]['title'] for x in current['source_ids'] if x in docs)
    points=[]
    for spot in info['spots']:
        names=[x[0] for x in PLACES.get(city,[]) if x[0] in spot['name']]
        if not names or not any(n in source_text for n in names):continue
        location=spot.get('location')
        if location and isinstance(location,str) and ',' in location:
            try:lng,lat=map(float,location.split(','))
            except ValueError:continue
            points.append({'name':spot['name'],'lng':lng,'lat':lat,'url':'https://uri.amap.com/marker?'+urlencode({'position':location,'name':spot['name'],'src':'roam','coordinate':'gaode','callnative':0})})
    route_url=None
    if len(points)>=2:
        a,b=points[0],points[-1]
        route_url='https://uri.amap.com/navigation?'+urlencode({'from':f"{a['lng']},{a['lat']},{a['name']}",'to':f"{b['lng']},{b['lat']},{b['name']}",'mode':'walk','coordinate':'gaode','src':'roam','callnative':0})
    return {'day':day,'city':city,'points':points,'route_url':route_url,'note':'高德地点坐标；连线为位置示意，实际路线请打开高德导航。'}

@router.get('/chat/sessions/{sid}/map-image')
async def static_map(sid:str,day:int=1,who=Depends(identity)):
    info=await route_map(sid,day,who)
    points=info['points']
    if not points:raise HTTPException(404,'当天暂无可匹配坐标')
    key=os.getenv('AMAP_API_KEY','')
    cache_key=tuple((p['lng'],p['lat']) for p in points)
    cached=_maps.get(cache_key)
    if cached and time.monotonic()-cached[0]<3600:
        return Response(cached[1],media_type=cached[2])
    markers='|'.join(f"mid,0x2d6045,{i+1}:{p['lng']},{p['lat']}" for i,p in enumerate(points))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response=await client.get('https://restapi.amap.com/v3/staticmap',params={'key':key,'size':'600*320','zoom':13,'markers':markers})
        media=response.headers.get('content-type','').split(';')[0]
        if response.status_code!=200 or media not in {'image/png','image/jpeg'}:raise ValueError()
        if len(_maps)>100:_maps.clear()
        _maps[cache_key]=(time.monotonic(),response.content,media)
        return Response(response.content,media_type=media)
    except (httpx.HTTPError,ValueError):raise HTTPException(503,'静态地图暂不可用，已提供坐标示意与高德入口') from None

class Checklist(BaseModel):
    items:list[dict]=Field(max_length=40)

@router.get('/chat/sessions/{sid}/checklist')
def checklist(sid:str,who=Depends(identity)):
    session=get_session(sid,who)
    with database() as db:row=db.execute('SELECT items FROM checklists WHERE session_id=? AND owner=?',(sid,who['owner'])).fetchone()
    if row:return json.loads(row['items'])
    pref=session['preferences']
    labels=['身份证件与必要证件','确认景点开放及预约','核实交通与住宿订单','充电器与充电宝','常用药品与饮水']
    if pref.get('transport')=='自驾':labels+=['驾驶证与车辆检查']
    if '自然' in pref.get('interests',[]):labels+=['舒适步行鞋与防晒用品']
    if pref.get('needs'):labels+=['确认饮食及无障碍需求：'+pref['needs']]
    return [{'text':t,'done':False} for t in labels]

@router.put('/chat/sessions/{sid}/checklist')
def save_checklist(sid:str,data:Checklist,who=Depends(identity)):
    get_session(sid,who)
    if any(set(x)!= {'text','done'} or not isinstance(x['text'],str) or not 1<=len(x['text'])<=400 or not isinstance(x['done'],bool) for x in data.items):raise HTTPException(422,'清单格式不正确')
    with database() as db:db.execute('INSERT INTO checklists VALUES(?,?,?) ON CONFLICT(session_id,owner) DO UPDATE SET items=excluded.items',(sid,who['owner'],json.dumps(data.items,ensure_ascii=False)))
    return data.items

@router.get('/chat/sessions/{sid}/export',response_class=HTMLResponse)
def export(sid:str,who=Depends(identity)):
    session=get_session(sid,who);plan=session.get('plan')
    if not plan:raise HTTPException(422,'请先生成行程')
    esc=lambda s:html.escape(str(s))
    days=''.join(f"<article><small>第{d['day']}天 · {esc(d['date'])}</small><h2>{esc(d['title'])}</h2><p>{esc(d['description'])}</p></article>" for d in plan['days'])
    sources=''.join(f"<li>{esc(s['title'])} — {esc(s['source'])}</li>" for s in plan['sources'])
    return HTMLResponse(f'''<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8"><title>{esc(session['title'])}</title><style>body{{max-width:800px;margin:40px auto;padding:24px;font-family:system-ui;line-height:1.8;color:#24443d}}article{{break-inside:avoid;border-bottom:1px solid #ddd;padding:20px 0}}small{{color:#777}}button{{padding:12px}}@media print{{button{{display:none}}body{{margin:0}}}}@page{{size:A4;margin:18mm}}</style><button onclick="window.print()">打印 / 保存为 PDF</button><h1>{esc(session['title'])}</h1><p>{esc(plan['preferences']['start_date'])} · {esc(plan['preferences']['num_travelers'])}人 · 示例总费用 ¥{plan['cost']['total_cents']/100:,.2f}</p>{days}<h2>资料来源</h2><ul>{sources}</ul><p>航班、酒店与费用为示例，非实时报价；开放与预约请自行核实。</p></html>''')
