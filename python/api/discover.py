"""高德景点搜索；密钥仅用于后端，失败明确回退到国内示例。"""
import asyncio
import os
import time
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel,Field
from community.auth import identity,limit
from domestic import PLACES

router = APIRouter(prefix='/api/discover', tags=['国内景点'])
_cache = {}
_lock = asyncio.Lock()
_search_cache={}

def poi_card(poi,fallback_city=''):
    photos=poi.get('photos') or []
    photo=next((p.get('url').replace('http://','https://',1) for p in photos if isinstance(p,dict) and str(p.get('url','')).startswith(('http://','https://'))),None)
    city=poi.get('cityname') or fallback_city or poi.get('pname','')
    city=city if isinstance(city,str) else fallback_city
    return {'name':poi.get('name',''),'city':city.removesuffix('市'),'subtitle':poi.get('address') if isinstance(poi.get('address'),str) else '',
            'tag':(poi.get('type') or '景点').split(';')[-1],'image':photo,'source':'高德地图','location':poi.get('location'),'poi_id':poi.get('id'),'seasonal':False}

@router.get('/search')
async def search_places(q:str=Query(min_length=1,max_length=80),city:str=Query(default='',max_length=30),page:int=Query(default=1,ge=1,le=20),who=Depends(identity)):
    limit('place-search:'+who['owner'],120,3600)
    q=q.strip()
    if not q:return {'spots':[],'page':page,'has_more':False,'message':'请输入城市或景点名称'}
    cache_key=(q,city,page)
    cached=_search_cache.get(cache_key)
    if cached and time.monotonic()-cached[0]<600:return cached[1]
    key=os.getenv('AMAP_API_KEY','')
    if not key:raise HTTPException(503,'未配置高德接口，暂时无法实时搜索')
    normalized=q.removesuffix('市')
    params={'key':key,'keywords':'风景名胜' if normalized in PLACES else q,'types':'110000','extensions':'all','offset':12,'page':page}
    if city or normalized in PLACES:params.update(city=city or normalized,citylimit='true')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data=(await client.get('https://restapi.amap.com/v3/place/text',params=params)).json()
            # A generic city keyword can return city suggestions rather than POIs.
            if data.get('status')=='1' and not data.get('pois') and data.get('cities'):
                candidate=data['cities'][0].get('name','')
                params.update(city=candidate,citylimit='true',keywords='风景名胜')
                data=(await client.get('https://restapi.amap.com/v3/place/text',params=params)).json()
        if data.get('status')!='1':raise ValueError()
        items=[poi_card(p,city or normalized) for p in data.get('pois',[]) if isinstance(p,dict)]
        result={'spots':items,'page':page,'has_more':int(data.get('count') or 0)>page*12,'message':'高德实时检索结果；照片非当前实景'}
        if len(_search_cache)>200:_search_cache.clear()
        _search_cache[cache_key]=(time.monotonic(),result)
        return result
    except (httpx.HTTPError,ValueError,TypeError,KeyError):raise HTTPException(503,'地点搜索暂不可用，请稍后重试') from None

async def query_amap(city, name, key):
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get('https://restapi.amap.com/v3/place/text', params={
            'key': key, 'keywords': name, 'city': city, 'citylimit': 'true',
            'extensions': 'all', 'offset': 3, 'page': 1})
        r.raise_for_status()
        data = r.json()
    if data.get('status') != '1':
        return None, str(data.get('infocode', 'unknown'))
    pois = data.get('pois', [])
    # Do not use an unrelated first result as the attraction.
    poi = next((p for p in pois if name in p.get('name','')), None)
    return poi, None

@router.get('/spots')
async def spots(city: str = Query('杭州', max_length=30)):
    if city not in PLACES:
        key=os.getenv('AMAP_API_KEY','')
        if not key:return {'city':city,'mode':'unavailable','message':'未配置高德，暂无该城市本地资料','spots':[]}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                data=(await client.get('https://restapi.amap.com/v3/place/text',params={'key':key,'keywords':'风景名胜','types':'110000','city':city,'citylimit':'true','extensions':'all','offset':12})).json()
            if data.get('status')!='1':raise ValueError()
            return {'city':city,'mode':'live','message':'高德地点查询结果，非实时热门榜','spots':[poi_card(p,city) for p in data.get('pois',[])]}
        except (httpx.HTTPError,ValueError,TypeError):return {'city':city,'mode':'unavailable','message':'景点查询暂不可用，请重试','spots':[]}
    async with _lock:
        cached = _cache.get(city)
        if cached and time.monotonic() - cached[0] < 3600:
            return cached[1]
        key = os.getenv('AMAP_API_KEY', '')
        month = datetime.now(timezone(timedelta(hours=8))).month
        result, errors = [], []
        for name, tag, months in sorted(PLACES[city], key=lambda s: month not in s[2]):
            poi, code = None, None
            if key:
                try:
                    poi, code = await query_amap(city, name, key)
                except (httpx.HTTPError, ValueError, TypeError):
                    code = 'network_error'
            if code: errors.append(code)
            photos = (poi or {}).get('photos') or []
            photo = next((p.get('url').replace('http://','https://',1) for p in photos if isinstance(p,dict) and str(p.get('url','')).startswith(('https://','http://'))), None)
            result.append({'name': (poi or {}).get('name',name), 'subtitle': (poi or {}).get('address') or f'{city} · {tag}',
                'tag': tag, 'theme': 'garden', 'image': photo, 'poi_id': (poi or {}).get('id'),
                'source': '高德地图' if poi else '本地示例', 'seasonal': month in months,
                'location':(poi or {}).get('location'), 'months':months})
        count = sum(x['source'] == '高德地图' for x in result)
        mode = 'live' if count == len(result) else 'mixed' if count else 'mock'
        message = '高德地点资料；季节排序为本地规则，非实时热度。' if count else ('高德暂不可用，展示国内示例。' if key else '未配置高德，展示国内示例。')
        value = {'city': city, 'mode': mode, 'message': message, 'errors': sorted(set(errors)), 'spots': result}
        _cache[city] = (time.monotonic(), value)
        return value

@router.get('/catalog')
def catalog():
    month=datetime.now(timezone(timedelta(hours=8))).month
    return [{'city':city,'spots':[name for name,tag,months in rows],
             'tags':list(dict.fromkeys(tag for name,tag,months in rows)),
             'seasonal':any(month in months for name,tag,months in rows),
             'description': ' · '.join(name for name,_,_ in rows)} for city,rows in PLACES.items()]

class Position(BaseModel):
    longitude:float=Field(ge=-180,le=180)
    latitude:float=Field(ge=-90,le=90)

@router.post('/location')
async def locate(data:Position,who=Depends(identity)):
    limit('locate:'+who['owner'],20,3600)
    key=os.getenv('AMAP_API_KEY','')
    if not key:raise HTTPException(503,'未配置定位服务，请手动选择城市')
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            coordinates=(await client.get('https://restapi.amap.com/v3/assistant/coordinate/convert',params={'key':key,'locations':f'{data.longitude},{data.latitude}','coordsys':'gps'})).json()
            if coordinates.get('status')!='1':raise ValueError()
            result=(await client.get('https://restapi.amap.com/v3/geocode/regeo',params={'key':key,'location':coordinates['locations'],'extensions':'base'})).json()
            if result.get('status')!='1':raise ValueError()
            address=result['regeocode']['addressComponent']
            city=address.get('city') or address.get('province')
            if not isinstance(city,str) or not city:raise ValueError()
            return {'city':city.removesuffix('市'),'source':'高德地图'}
    except (httpx.HTTPError,ValueError,KeyError,TypeError):raise HTTPException(503,'暂时无法识别所在城市，请手动选择') from None
