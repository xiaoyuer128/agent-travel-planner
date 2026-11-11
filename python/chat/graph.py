from copy import deepcopy
from typing import TypedDict
from pydantic import ValidationError
from langgraph.graph import StateGraph, START, END
from .models import Preferences, REQUIRED
from .provider import MockExtractor,number
from .planner import retrieve, build_plan
from config.settings import settings
from .deepseek import DeepSeekAdapter,ModelUnavailable
import re
from rag.library import search as knowledge_search
from .runtime import progress,check
from .tools import SCHEMAS,dispatch,tool_sources,execute
from .feasibility import verify,repair_proposal
from domestic import PLACES


class GraphState(TypedDict, total=False):
    session: dict
    message: str
    patch: dict
    action: str
    preferences: dict
    changed: list
    missing: list
    sources: list
    plan: dict | None
    reply: str
    trace: list
    error: str
    generate: bool
    citations: list
    tool_results: list
    place_context: list


def build_graph(extractor=None):
    extractor = extractor or MockExtractor()

    def conversation(s):
        progress('retrieve','正在检索旅行知识')
        previous=s['session']['preferences']
        city=next((c for c in PLACES if c in s['message']),previous.get('destination',''))
        sources=knowledge_search(s['message']+' '+city,city)
        results=[]
        if isinstance(extractor,DeepSeekAdapter):
            calls=extractor.select_tools(s['message'],previous,s['session']['messages'],SCHEMAS,sources)
            results=dispatch(calls)
            if any(r['name']=='search_places' and r['status']=='ok' for r in results) and not any(r['name']=='get_route' for r in results) and re.search('多久|路线|路程|怎么去|距离|交通',s['message']):
                # One bounded continuation lets the agent use resolved coordinates instead of guessing.
                followup=extractor.select_tools(s['message'],previous,s['session']['messages'],SCHEMAS,sources,results)
                followup=[c for c in followup if (c.get('function') or {}).get('name')=='get_route']
                results+=dispatch(followup)
            sources=list({d['id']:d for d in sources+tool_sources(results)}.values())[:8]
            progress('answer','正在根据查询证据组织回答')
            reply,patch,ids=extractor.converse(s['message'],previous,s['session']['messages'],sources,results)
        else:
            patch,_=extractor.extract(s['message'],previous)
            ids=[d['id'] for d in sources[:2]]
            reply='可以直接聊旅行，不必先填完整条件。'+('参考资料建议：'+sources[0]['text'] if sources else '你可以问景点、美食或想去的城市，也可以点击生成行程开始规划。')
        patch.update(s.get('patch',{}))
        try:pref=Preferences.model_validate({**previous,**patch}).model_dump(mode='json',exclude_none=True)
        except (ValueError,ValidationError):return {'preferences':previous,'reply':'旅行条件无效，请检查日期、预算和人数；原方案未更改。','citations':[],'trace':['chat']}
        return {'preferences':pref,'reply':reply,'citations':[d for d in sources if d['id'] in ids],'tool_results':results,'trace':['retrieve_knowledge','tools','chat']}

    def understand(s):
        progress('understand','正在理解行程需求')
        previous = s["session"]["preferences"]
        try:
            if isinstance(extractor, DeepSeekAdapter):
                patch, action = extractor.extract(s["message"], previous, s['session']['messages'])
            else:
                patch, action = extractor.extract(s["message"], previous)
            patch.update(s.get("patch", {}))
            if s.get("action", "auto") != "auto":
                action = s["action"]
            pref = Preferences.model_validate({**previous, **patch}).model_dump(mode="json", exclude_none=True)
            return {"preferences": pref, "changed": [k for k in pref if pref[k] != previous.get(k)],
                    "action": action, "trace": ["understand"]}
        except (ValueError, ValidationError):
            return {"preferences": previous, "changed": [], "error": "输入无效，请检查日期、预算、人数（1—10）和天数（1—30）。",
                    "trace": ["understand"]}

    def collect(s):
        missing = [label for key, label in REQUIRED.items() if s["preferences"].get(key) is None]
        if s.get("error"):
            reply = s["error"] + " 原需求与方案未更改。"
        elif missing:
            reply = "还需要：" + "、".join(missing) + "。例如：两个人，预算8000，重庆出发，去杭州，2026-12-01出发，玩5天。"
        elif not s.get('generate',True):
            reply = '旅行需求已补齐，请确认下方条件后点击“生成行程”。'
        elif not s["changed"] and s["action"] == "auto" and s["session"].get("plan") and s['session']['plan']['preferences']==s['preferences']:
            reply = "可以说“酒店换便宜一些”“预算改成6000”“增加美食活动”，或在右侧精确编辑需求。当前方案保持不变。"
        else:
            reply = ""
        return {"missing": missing, "reply": reply, "trace": s["trace"] + ["collect"]}

    def retrieval(s):
        progress('retrieve','正在检索攻略与景点资料')
        pref = s["preferences"]
        sources=knowledge_search(pref['destination']+' '+' '.join(pref.get('interests',[]))+' '+' '.join(pref.get('selected_spots',[])),pref['destination'])
        results=[execute('search_places',{'query':'风景名胜','city':pref['destination']})] if isinstance(extractor,DeepSeekAdapter) else []
        places=results[0]['data'].get('places',[]) if results and results[0]['status']=='ok' else []
        return {"sources": sources,'tool_results':results,'place_context':places,
                "trace": s["trace"] + ["retrieve"]}

    def planning(s):
        progress('plan','正在生成结构化每日路线')
        previous_plan=s['session'].get('plan')
        changes=list(s['changed'])
        if previous_plan:
            changes=list(set(changes)|{k for k,v in s['preferences'].items() if v!=previous_plan['preferences'].get(k)})
        plan, reply = build_plan(s["preferences"], s["sources"], previous_plan, s["action"], changes)
        if s.get('place_context'):plan['place_context']=s['place_context']
        if isinstance(extractor, DeepSeekAdapter):
            target_day = None
            if 'days' in plan['changed_sections']:
                plan = extractor.enrich(plan,s['message'])
                match = re.search(r'第([一二三四五六七八九十两]+|\d+)天',s['message'])
                if match and previous_plan and not set(changes).intersection({'departure_city','destination','days','start_date','num_travelers'}):
                    value=match[1]
                    target_day=number(value)
                    if not 1 <= target_day <= len(plan['days']):
                        raise ModelUnavailable('指定日期超出当前行程，原方案未更改。')
                    plan['days']=[d if d['day']==target_day else deepcopy(previous_plan['days'][i]) for i,d in enumerate(plan['days'])]
            if 'flights' in plan['changed_sections']:
                plan = extractor.estimate(plan)
            elif 'days' in plan['changed_sections']:
                plan = extractor.estimate(plan, scope='daily', target_day=target_day)
            reply = ('已更新行程与AI费用估算，实际价格和可用性请以预订平台为准。'
                     if plan.get('price_metadata') else '已更新原方案，费用沿用原有示例预算。')
            plan['mode'] = 'deepseek'
        return {"plan": plan, "reply": reply, "trace": s["trace"] + ["plan"]}

    def validation(s):
        plan=s['plan']
        plan['feasibility']=verify(plan,live=isinstance(extractor,DeepSeekAdapter))
        plan.pop('repair_proposal',None)
        return {'plan':plan,'trace':s['trace']+['validate']}

    def repair(s):
        plan=s['plan']
        try:proposal=repair_proposal(plan,extractor if isinstance(extractor,DeepSeekAdapter) else None)
        except ModelUnavailable:proposal=None;plan['repair_notice']='自动调整建议暂不可用，已保留原方案与检查结果。'
        if proposal:plan['repair_proposal']=proposal
        return {'plan':plan,'trace':s['trace']+['repair']}

    def respond(s):
        progress('respond','正在整理方案与核验说明')
        plan = s["plan"]
        cost = plan["cost"]
        reply = s["reply"] + f" 已建模总费用¥{cost['total_cents']/100:,.0f}，预算¥{cost['budget_cents']/100:,.0f}。"
        if not cost["within_budget"]:
            reply += " 当前超预算，未将其标为预算达标。"
        if plan["sources"]:
            reply += " 行程依据知识库资料生成，来源见方案引用。"
        else:
            reply += " 该城市无攻略依据，通用安排没有引用。"
        return {"reply": reply, "trace": s["trace"] + ["respond"]}

    graph = StateGraph(GraphState)
    graph.add_node('conversation',conversation)
    for name, node in (("understand", understand), ("collect", collect), ("retrieve", retrieval), ("planning", planning),('validation',validation),('repair',repair), ("respond", respond)):
        graph.add_node(name, node)
    graph.add_conditional_edges(START,lambda s:'plan' if s.get('generate',True) else 'chat',{'plan':'understand','chat':'conversation'})
    graph.add_edge('conversation',END)
    graph.add_edge("understand", "collect")
    graph.add_conditional_edges("collect", lambda s: "done" if s["reply"] else "ready", {"done": END, "ready": "retrieve"})
    graph.add_edge("retrieve", "planning")
    graph.add_edge('planning','validation')
    graph.add_conditional_edges('validation',lambda s:'repair' if s['plan']['feasibility']['blocking_count'] else 'done',{'repair':'repair','done':'respond'})
    graph.add_edge('repair','respond')
    graph.add_edge("respond", END)
    return graph.compile()


GRAPH = build_graph()
DEEPSEEK_GRAPH = build_graph(DeepSeekAdapter())


def run_turn(session, message, patch=None, action="auto",generate=True):
    real = settings.LLM_PROVIDER != 'mock'
    if action=='validate':
        if not session.get('plan'):raise ModelUnavailable('请先生成一份行程，再检查时间和路线。')
        session=deepcopy(session);plan=deepcopy(session['plan'])
        plan['feasibility']=verify(plan,live=real);plan.pop('repair_proposal',None)
        plan['version']=len(session['versions'])+1;plan['changed_sections']=['feasibility']
        session['plan']=plan;session['versions'].append(deepcopy(plan));session['trace']=['validate']
        session['messages'] += [{'role':'user','content':message},{'role':'assistant','content':'已更新行程检查，原每日安排、酒店与报价保留。未知资料仍需核实。'}]
        check();return session
    graph = DEEPSEEK_GRAPH if real else GRAPH
    result = graph.invoke({"session": session, "message": message, "patch": patch or {}, "action": action,'generate':generate})
    session = deepcopy(session)
    session['provider'] = 'deepseek' if real else 'mock'
    session["preferences"] = result["preferences"]
    session["trace"] = result["trace"]
    if result.get("plan"):
        plan = result["plan"]
        plan["version"] = len(session["versions"]) + 1
        if plan.get('repair_proposal'):plan['repair_proposal']['base_version']=plan['version']
        session["plan"] = plan
        session["versions"].append(deepcopy(plan))
        session["title"] = f"{plan['preferences']['destination']} · {plan['preferences']['days']}天"
    check()
    session["messages"] += [{"role": "user", "content": message}, {"role": "assistant", "content": result["reply"], 'sources':result.get('citations',[]),'tools':result.get('tool_results',[])}]
    return session
