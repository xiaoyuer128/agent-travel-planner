"""Read-only tool registry. Model-selected names and arguments are always validated."""
import json,os,time,hashlib,threading
from datetime import date,datetime,timezone,timedelta
from uuid import uuid4
import httpx
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .runtime import check,progress,CURRENT
from rag.library import search

class Arguments(BaseModel):model_config=ConfigDict(extra='forbid')
class Places(Arguments):
    query:str=Field(min_length=1,max_length=80)
    city:str=Field(default='',max_length=30)
class Weather(Arguments):
    city:str=Field(min_length=1,max_length=30)
    date:str=Field(default='',max_length=10)
class Route(Arguments):
    origin:str=Field(pattern=r'^\d{2,3}\.\d+,\d{1,2}\.\d+$')
    destination:str=Field(pattern=r'^\d{2,3}\.\d+,\d{1,2}\.\d+$')
    mode:str=Field(default='walking',pattern='^(walking|driving)$')
class Knowledge(Arguments):
    query:str=Field(min_length=1,max_length=300)
    city:str=Field(default='',max_length=30)

DEFINITIONS={
 'search_places':(Places,'搜索中国城市中的真实景点，返回地点、地址、坐标及可用的开放信息'),
 'get_weather':(Weather,'查询城市近期天气预报，date 可选，格式 YYYY-MM-DD，超出预报日期必须说明未知'),
 'get_route':(Route,'已知起终点高德坐标时查询步行或驾车距离与耗时；不能猜测坐标'),
 'search_knowledge':(Knowledge,'从旅行知识库检索资料和引用，用于景点建议及一般旅行问题'),
}
SCHEMAS=[{'type':'function','function':{'name':name,'description':description,'parameters':model.model_json_schema()}} for name,(model,description) in DEFINITIONS.items()]
_CACHE={};_LOCK=threading.RLock()

def amap(path,params,ttl=600):
    check();key=os.getenv('AMAP_API_KEY','')
    if not key:return {'status':'0','info':'not_configured'}
    cachekey=(path,json.dumps(params,sort_keys=True),hashlib.sha256(key.encode()).hexdigest()[:10])
    with _LOCK:cached=_CACHE.get(cachekey)
    if cached and time.monotonic()-cached[0]<ttl:return {**cached[1],'_cached':True}
    try:
        with httpx.Client(timeout=httpx.Timeout(8,connect=4)) as client:
            run=CURRENT.get()
            if run:
                with run.closing(client.close):response=client.get('https://restapi.amap.com/v3/'+path,params={**params,'key':key})
            else:response=client.get('https://restapi.amap.com/v3/'+path,params={**params,'key':key})
            check();response.raise_for_status();value=response.json()
        if value.get('status')=='1':
            value['_fetched_at']=datetime.now(timezone.utc).isoformat()
            with _LOCK:
                if len(_CACHE)>256:_CACHE.clear()
                _CACHE[cachekey]=(time.monotonic(),value)
        return value
    except (httpx.HTTPError,ValueError,RuntimeError):
        check();return {'status':'0','info':'network_or_permission_error'}

def places(data):
    params={'keywords':data.query,'extensions':'all','offset':6,'page':1}
    if data.city:params.update(city=data.city,citylimit='true')
    result=amap('place/text',params,3600)
    if result.get('status')!='1':return {'available':False,'message':'景点查询暂不可用，不能确认实时信息'}
    items=[]
    for poi in result.get('pois',[]):
        business=poi.get('business') or {};ext=poi.get('biz_ext') or {}
        items.append({'id':poi.get('id'),'name':poi.get('name'),'city':poi.get('cityname'),
            'location':poi.get('location'),'address':poi.get('address'),
            'opening_hours':business.get('opentime') or ext.get('open_time') or None})
    return {'available':True,'places':items,'source':'高德地图','fetched_at':result.get('_fetched_at'),'cached':result.get('_cached',False)}

def weather(data):
    if data.date:
        try:date.fromisoformat(data.date)
        except ValueError:return {'available':False,'message':'日期格式无效'}
    geo=amap('geocode/geo',{'address':data.city},86400)
    geocodes=geo.get('geocodes') or []
    if geo.get('status')!='1' or not geocodes:return {'available':False,'message':'无法确认城市，天气未查询'}
    result=amap('weather/weatherInfo',{'city':geocodes[0]['adcode'],'extensions':'all'},900)
    forecast=(result.get('forecasts') or [{}])[0];casts=forecast.get('casts') or []
    selected=[c for c in casts if not data.date or c.get('date')==data.date]
    return {'available':bool(selected),'city':data.city,'requested_date':data.date,'casts':selected,
        'available_dates':[c.get('date') for c in casts], 'report_time':forecast.get('reporttime'),
        'source':'高德天气','fetched_at':result.get('_fetched_at'),
        'message':'预报仅覆盖列出的日期；超出范围不能当作实时预报' if not selected else '天气预报可能变化，请临近出行核实'}

def route(data):
    for point in [data.origin,data.destination]:
        lng,lat=map(float,point.split(','))
        if not (73<=lng<=136 and 3<=lat<=55):return {'available':False,'message':'坐标超出支持范围'}
    result=amap('direction/'+data.mode,{'origin':data.origin,'destination':data.destination},1800)
    paths=(result.get('route') or {}).get('paths') or []
    if result.get('status')!='1' or not paths:return {'available':False,'message':'路线查询暂不可用，耗时未知'}
    try:distance=int(paths[0]['distance']);duration=int(paths[0]['duration'])
    except (ValueError,KeyError,TypeError):return {'available':False,'message':'路线结果缺少距离或耗时'}
    return {'available':True,'distance_m':distance,'duration_seconds':duration,'mode':data.mode,'source':'高德路径规划','fetched_at':result.get('_fetched_at')}

def execute(name,arguments,call_id=None):
    check();started=time.monotonic();call_id=call_id or uuid4().hex
    if name not in DEFINITIONS:return {'id':call_id,'name':name,'status':'rejected','data':{'message':'工具不在只读白名单中'}}
    progress('tool_start','正在查询：'+{'search_places':'景点资料','get_weather':'天气','get_route':'路线','search_knowledge':'知识库'}[name],tool=name)
    validated={}
    try:
        data=DEFINITIONS[name][0].model_validate(json.loads(arguments) if isinstance(arguments,str) else arguments)
        validated=data.model_dump(mode='json')
        if name=='search_places':result=places(data)
        elif name=='get_weather':result=weather(data)
        elif name=='get_route':result=route(data)
        else:result={'available':True,'sources':search(data.query,data.city)}
    except (ValidationError,ValueError,TypeError):result={'available':False,'message':'工具参数校验失败，未执行查询'}
    check();status='ok' if result.get('available') else 'unavailable'
    item={'id':call_id,'name':name,'arguments':validated,'status':status,'data':result,'elapsed_ms':round((time.monotonic()-started)*1000)}
    progress('tool_done','查询完成' if status=='ok' else '查询未取得可靠结果',tool=name,status=status)
    return item

def dispatch(calls):
    results=[];seen=set()
    for call in calls[:4]:
        if not isinstance(call,dict):continue
        function=call.get('function') or {};name=function.get('name','')
        args=function.get('arguments','{}');signature=(name,str(args))
        if signature in seen:continue
        seen.add(signature);results.append(execute(name,args,call.get('id')))
    return results

def tool_sources(results):
    output=[]
    for item in results:
        if item['status']!='ok':continue
        data=item['data']
        if item['name']=='search_knowledge':output.extend(data['sources']);continue
        output.append({'id':'tool:'+item['id'],'city':data.get('city',''),'title':{'get_weather':'天气查询结果','search_places':'景点查询结果','get_route':'路线查询结果'}[item['name']],
            'text':json.dumps(data,ensure_ascii=False)[:2200],'source':data.get('source','高德地图'),'uri':'https://www.amap.com/',
            'version':data.get('fetched_at') or 'live','score':1.0})
    return output
