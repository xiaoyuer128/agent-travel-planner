"""Deterministic tools: immutable fixture offers, retrieval BEFORE generation."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from rag.embeddings import MockEmbedder

from domestic import GUIDES

HOTELS = [
    {"id": "hotel-economy", "name": "经济型示例酒店", "price_cents": 12000, "stars": 2},
    {"id": "hotel-comfort", "name": "舒适型示例酒店", "price_cents": 22000, "stars": 3},
    {"id": "hotel-premium", "name": "品质型示例酒店", "price_cents": 36000, "stars": 4},
]


def retrieve(city, interests):
    embedder = MockEmbedder()
    query = embedder.embed(city + " " + " ".join(interests))
    hits = []
    for doc in GUIDES:
        if doc["city"] != city:
            continue
        score = sum(a*b for a, b in zip(query, embedder.embed(doc["city"] + doc["text"])))
        hits.append({**doc, "score": round(score, 4), "source": "本地示例攻略 v1",
                     "uri": "mock://guides/" + doc["id"], "version": "v1"})
    return sorted(hits, key=lambda x: -x["score"])[:3]


def itinerary(pref, sources):
    days = []
    for i in range(pref["days"]):
        source = sources[i % len(sources)] if sources else None
        days.append({"day": i+1, "date": (date.fromisoformat(pref["start_date"]) + timedelta(days=i)).isoformat(),
                     "title": source["title"] if source else "自由探索（无攻略依据）",
                     "description": source["text"] if source else "暂无该城市知识资料，请自行核实当地活动。",
                     "source_ids": [source["id"]] if source else [],
                     "cost_per_person_cents": 8000})
    return days


def calculate(plan):
    pref = plan["preferences"]
    rooms = (pref["num_travelers"] + 1) // 2
    flight = sum(x["price_cents"] for x in plan["flights"]) * pref["num_travelers"]
    hotel = plan["hotel"]["price_cents"] * max(pref["days"]-1, 0) * rooms
    activity = sum(d["cost_per_person_cents"] for d in plan["days"]) * pref["num_travelers"]
    total = flight + hotel + activity
    budget = int(Decimal(str(pref["budget"])) * 100)
    plan["cost"] = {"flight_cents": flight, "hotel_cents": hotel, "activity_cents": activity,
                    "total_cents": total, "budget_cents": budget, "within_budget": total <= budget,
                    "remaining_cents": budget-total, "rooms": rooms, "nights": max(pref["days"]-1, 0)}
    plan["warnings"] = ["全部航班、酒店与费用均为Mock示例，不可直接预订；攻略不是实时旅游资讯。"]
    if not plan["sources"]:
        plan["warnings"].append("该城市暂无本地攻略：未伪造来源，仅提供通用安排。")
    if total > budget:
        plan["warnings"].append("当前方案超预算，未修改原始报价；请降低酒店档次、减少天数或提高预算。")
    return plan


def build_plan(pref, sources, previous=None, action="auto", changed=()):
    # Local edits preserve unrelated sections byte-for-byte.
    local = previous is not None and not set(changed).intersection(
        {"departure_city", "destination", "start_date", "days", "num_travelers"})
    if local:
        plan = deepcopy(previous)
        plan["preferences"] = deepcopy(pref)
        plan["changed_sections"] = []
    else:
        plan = {"preferences": deepcopy(pref), "mode": "mock", "sources": sources,
                "flights": [{"id": "mock-outbound", "label": "去程示例航班", "price_cents": 60000},
                            {"id": "mock-return", "label": "返程示例航班", "price_cents": 60000}],
                "hotel": deepcopy(HOTELS[1]), "days": itinerary(pref, sources),
                "changed_sections": ["flights", "hotel", "days", "sources"]}
    note = "已生成示例方案。"
    if action in {"hotel_cheaper", "hotel_better"}:
        current = next(i for i, h in enumerate(HOTELS) if h["id"] == plan["hotel"]["id"])
        target = max(0, current-1) if action == "hotel_cheaper" else min(len(HOTELS)-1, current+1)
        plan["hotel"] = deepcopy(HOTELS[target])
        plan["changed_sections"] = list(dict.fromkeys(plan["changed_sections"] + ["hotel", "cost"]))
        note = "酒店已替换，其余航班和行程保留。" if target != current else "已是当前候选的最低／最高档酒店，保留原方案。"
    if local and (action == "activity" or set(changed).intersection({'interests','pace','walking','needs','selected_spots','transport'})):
        plan["sources"] = sources
        plan["days"] = itinerary(pref, sources)
        plan["changed_sections"] += ["days", "sources", "cost"]
        note = "已更新活动与攻略引用，航班和酒店保留。"
    if local and "budget" in changed:
        plan["changed_sections"] += ["cost"]
        note = "已更新预算并重新核算，保留原有候选及报价。"
    return calculate(plan), note
