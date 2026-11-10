"""Deterministic itinerary checks; missing evidence is never treated as a pass."""
from copy import deepcopy
from datetime import datetime,timezone
import math,re
from .tools import execute
from .runtime import progress,check

def distance(a,b):
    x1,y1=map(math.radians,a);x2,y2=map(math.radians,b)
    return 6371000*2*math.asin(min(1,math.sqrt(math.sin((y2-y1)/2)**2+math.cos(y1)*math.cos(y2)*math.sin((x2-x1)/2)**2)))

def opening_window(text):
    if not isinstance(text,str) or any(word in text for word in ['周','节假','闭馆','次日']):return None
    if text.strip() in {'全天','24小时','00:00-24:00'}:return (0,1440)
    match=re.fullmatch(r'\s*(\d{1,2}):(\d{2})\s*[-—~至]\s*(\d{1,2}):(\d{2})\s*',text)
    if not match:return None
    h,m,h2,m2=map(int,match.groups())
    if h>23 or h2>24 or m>59 or m2>59 or (h2==24 and m2):return None
    start,end=h*60+m,h2*60+m2
    return (start,end) if end>start else None

def day_stops(day,sources):
    if day.get('stops'):return deepcopy(day['stops'])
    docs={s['id']:s for s in sources}
    return [{'name':docs[s]['title'].split('·')[0].strip(),'duration_minutes':90,'locked':False,'start_time':''}
            for s in day.get('source_ids',[]) if s in docs and docs[s].get('city')]

def verify(plan,live=True):
    progress('validate','正在检查每日时长、地点距离与开放信息')
    issues=[];days=[];resolved={};routes={};seen={};live_calls=0;unknown=0
    pref=plan['preferences'];city=pref['destination']
    daily_limit={'轻松':360,'适中':480,'紧凑':600}.get(pref.get('pace'),480)
    def issue(code,severity,day,message):issues.append({'code':code,'severity':severity,'day':day,'message':message})
    for day in plan['days']:
        check();stops=day_stops(day,plan['sources']);items=[];legs=[];cursor=9*60;visit=0;transit=0;walking=0
        if not stops:issue('missing_stops','unknown',day['day'],'缺少结构化景点，无法检查位置与时间');unknown+=1
        for index,stop in enumerate(stops):
            name=stop['name'];planned=stop.get('duration_minutes',90);visit+=planned
            if name in seen:issue('repeated_stop','warning',day['day'],f"{name}已在第{seen[name]}天出现，请确认是否需要重复游览")
            seen[name]=day['day']
            if name not in resolved:
                poi=None
                if live and live_calls<20:
                    live_calls+=1;result=execute('search_places',{'query':name,'city':city})
                    if result['status']=='ok':poi=next((p for p in result['data'].get('places',[]) if name in p.get('name','') or p.get('name','') in name),None)
                resolved[name]=poi
            poi=resolved[name];coordinates=None
            if poi and poi.get('location'):
                try:coordinates=tuple(map(float,poi['location'].split(',')))
                except (ValueError,TypeError):pass
            if not coordinates:issue('unverified_location','unknown',day['day'],f'{name}的位置未核实');unknown+=1
            if index and items[-1].get('coordinates') and coordinates:
                previous=items[-1];origin=previous['coordinates'];straight=distance(origin,coordinates)
                mode='walking' if straight<=2000 and pref.get('walking')!='少走路' else 'driving'
                key=(tuple(origin),tuple(coordinates),mode)
                if key not in routes:
                    result=execute('get_route',{'origin':','.join(map(str,origin)),'destination':','.join(map(str,coordinates)),'mode':mode}) if live and len(routes)<12 else {'status':'unavailable'}
                    routes[key]=result
                result=routes[key];data=result.get('data',{})
                leg={'from':previous['name'],'to':name,'mode':mode,'available':result['status']=='ok'}
                if leg['available']:
                    minutes=math.ceil(data['duration_seconds']/60);transit+=minutes;cursor+=minutes
                    if mode=='walking':walking+=data['distance_m']
                    leg.update(duration_minutes=minutes,distance_m=data['distance_m'],source='高德路径规划')
                    if minutes>90:issue('long_transfer','blocking',day['day'],f"{previous['name']}到{name}单段参考耗时{minutes}分钟，建议拆分或换景点")
                else:unknown+=1;issue('unverified_route','unknown',day['day'],f"{previous['name']}到{name}的交通耗时未知")
                legs.append(leg)
            start=stop.get('start_time') or ''
            if re.fullmatch(r'\d{2}:\d{2}',start):cursor=max(cursor,int(start[:2])*60+int(start[-2:]))
            window=opening_window((poi or {}).get('opening_hours'))
            if not window:unknown+=1;issue('unverified_hours','unknown',day['day'],f'{name}开放时间缺少可靠资料，出行前需核实')
            elif cursor<window[0] or cursor+planned>window[1]:issue('opening_conflict','blocking',day['day'],f'{name}计划游览时间与已获取的开放时间冲突')
            items.append({**stop,'coordinates':coordinates,'arrival_minutes':cursor,'opening_hours':(poi or {}).get('opening_hours'),
                'location_verified':coordinates is not None,'duration_basis':'规划估计，非场馆官方建议时长'})
            cursor+=planned
        total=max(visit+transit,cursor-9*60)
        if total>daily_limit:issue('day_overloaded','blocking',day['day'],f'已知游览与交通合计{total}分钟，超过当前节奏参考上限{daily_limit}分钟')
        if pref.get('walking')=='少走路' and walking>3000:issue('walking_excess','blocking',day['day'],f'已知步行距离{walking}米，超过少走路模式的3000米设计阈值')
        days.append({'day':day['day'],'stops':items,'legs':legs,'visit_minutes':visit,'known_transit_minutes':transit,'known_total_minutes':total,'walking_m':walking,'daily_limit_minutes':daily_limit})
    blocking=sum(i['severity']=='blocking' for i in issues)
    status='conflicts' if blocking else 'needs_verification' if unknown else 'checked'
    return {'status':status,'blocking_count':blocking,'unknown_count':unknown,'issues':issues,'days':days,'checked_at':datetime.now(timezone.utc).isoformat(),
        'note':'这是基于已获取资料的约束检查，不保证实际可出行。未知开放时间与交通不会计为通过；游览时长、节奏阈值是规划假设。'}

def repair_proposal(plan,adapter=None):
    report=plan['feasibility']
    if not report['blocking_count']:return None
    progress('repair','正在生成一次有界调整建议，确认后才应用')
    if adapter is None:return None
    original=deepcopy(plan);candidate=deepcopy(plan)
    candidate=adapter.enrich(candidate,'仅修复以下检查中有 blocking 冲突的天，减少折返或过密安排。保留所有 locked 景点的位置与时长，其他天不变。不能编造开放时间。检查：'+str(report['issues'])[:3500])
    bad={i['day'] for i in report['issues'] if i['severity']=='blocking'}
    for i,day in enumerate(candidate['days']):
        if day['day'] not in bad:candidate['days'][i]=original['days'][i]
        else:
            old_stops=day_stops(original['days'][i],plan['sources']);new_stops=day_stops(day,plan['sources'])
            if any(stop.get('locked') and (j>=len(new_stops) or new_stops[j]!=stop) for j,stop in enumerate(old_stops)):return None
    checked=verify(candidate)
    if checked['blocking_count']>=report['blocking_count']:return None
    return {'days':candidate['days'],'feasibility':checked,'reason':'已减少检测到的冲突；其他天保留。未知信息仍需核实。',
        'before_blocking':report['blocking_count'],'after_blocking':checked['blocking_count'],'requires_confirmation':True}
