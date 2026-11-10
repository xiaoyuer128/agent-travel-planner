from copy import deepcopy
from typing import TypedDict
from pydantic import ValidationError
from langgraph.graph import StateGraph, START, END
from .models import Preferences, REQUIRED
from .provider import MockExtractor,number
from .planner import retrieve, build_plan
from config.settings import settings
from .deepseek import DeepSeekAdapter
import re
from rag.library import search as knowledge_search


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


def build_graph(extractor=None):
    extractor = extractor or MockExtractor()

    def conversation(s):
        previous=s['session']['preferences']
        sources=knowledge_search(s['message']+' '+previous.get('destination',''),previous.get('destination',''))
        if isinstance(extractor,DeepSeekAdapter):
            reply,patch,ids=extractor.converse(s['message'],previous,s['session']['messages'],sources)
        else:
            patch,_=extractor.extract(s['message'],previous)
            ids=[d['id'] for d in sources[:2]]
            reply='可以直接聊旅行，不必先填完整条件。'+('参考资料建议：'+sources[0]['text'] if sources else '你可以问景点、美食或想去的城市，也可以点击生成行程开始规划。')
        patch.update(s.get('patch',{}))
        try:pref=Preferences.model_validate({**previous,**patch}).model_dump(mode='json',exclude_none=True)
        except (ValueError,ValidationError):return {'preferences':previous,'reply':'旅行条件无效，请检查日期、预算和人数；原方案未更改。','citations':[],'trace':['chat']}
        return {'preferences':pref,'reply':reply,'citations':[d for d in sources if d['id'] in ids],'trace':['retrieve_knowledge','chat']}

    def understand(s):
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
        pref = s["preferences"]
        sources=knowledge_search(pref['destination']+' '+' '.join(pref.get('interests',[]))+' '+' '.join(pref.get('selected_spots',[])),pref['destination'])
        return {"sources": sources or retrieve(pref["destination"], pref.get("interests", [])),
                "trace": s["trace"] + ["retrieve"]}

    def planning(s):
        previous_plan=s['session'].get('plan')
        changes=list(s['changed'])
        if previous_plan:
            changes=list(set(changes)|{k for k,v in s['preferences'].items() if v!=previous_plan['preferences'].get(k)})
        plan, reply = build_plan(s["preferences"], s["sources"], previous_plan, s["action"], changes)
        if isinstance(extractor, DeepSeekAdapter):
            if 'days' in plan['changed_sections']:
                original = deepcopy(plan['days'])
                plan = extractor.enrich(plan,s['message'])
                match = re.search(r'第([一二三四五六七八九十两]+|\d+)天',s['message'])
                if match and s['session'].get('plan') and not set(s['changed']).intersection({'destination','days','start_date'}):
                    value=match[1]
                    target=number(value)
                    plan['days']=[d if d['day']==target else original[i] for i,d in enumerate(plan['days'])]
                reply = "已由 DeepSeek 生成行程，航班、酒店与费用仍为示例。"
            plan['mode'] = 'deepseek'
        return {"plan": plan, "reply": reply, "trace": s["trace"] + ["plan"]}

    def respond(s):
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
    for name, node in (("understand", understand), ("collect", collect), ("retrieve", retrieval), ("planning", planning), ("respond", respond)):
        graph.add_node(name, node)
    graph.add_conditional_edges(START,lambda s:'plan' if s.get('generate',True) else 'chat',{'plan':'understand','chat':'conversation'})
    graph.add_edge('conversation',END)
    graph.add_edge("understand", "collect")
    graph.add_conditional_edges("collect", lambda s: "done" if s["reply"] else "ready", {"done": END, "ready": "retrieve"})
    graph.add_edge("retrieve", "planning")
    graph.add_edge("planning", "respond")
    graph.add_edge("respond", END)
    return graph.compile()


GRAPH = build_graph()
DEEPSEEK_GRAPH = build_graph(DeepSeekAdapter())


def run_turn(session, message, patch=None, action="auto",generate=True):
    real = settings.LLM_PROVIDER != 'mock'
    graph = DEEPSEEK_GRAPH if real else GRAPH
    result = graph.invoke({"session": session, "message": message, "patch": patch or {}, "action": action,'generate':generate})
    session = deepcopy(session)
    session['provider'] = 'deepseek' if real else 'mock'
    session["preferences"] = result["preferences"]
    session["trace"] = result["trace"]
    if result.get("plan"):
        plan = result["plan"]
        plan["version"] = len(session["versions"]) + 1
        session["plan"] = plan
        session["versions"].append(deepcopy(plan))
        session["title"] = f"{plan['preferences']['destination']} · {plan['preferences']['days']}天"
    session["messages"] += [{"role": "user", "content": message}, {"role": "assistant", "content": result["reply"], 'sources':result.get('citations',[])}]
    return session
