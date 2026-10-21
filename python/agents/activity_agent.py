"""
Activity Agent —— 活动/景点推荐 Agent。

职责: 推荐景点/餐厅/体验，生成每日行程安排。
在并行阶段执行，与 Flight Agent / Hotel Agent 同时运行。

"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from loguru import logger

from models.schemas import Activity, ActivitySearchResult, DayPlan, TravelPlanState

from .base_agent import BaseAgent
from llm_client import chat_json
from rag import has_guide, rag_search

MOCK_ACTIVITIES_DB: dict[str, list[dict]] = {
    "default": [
        {"name": "城市地标打卡", "category": "sightseeing", "duration_hours": 2.0, "price": 0, "rating": 8.5, "time_slot": "morning"},
        {"name": "当地市场探索", "category": "food", "duration_hours": 1.5, "price": 100, "rating": 8.0, "time_slot": "morning"},
        {"name": "博物馆参观", "category": "sightseeing", "duration_hours": 3.0, "price": 80, "rating": 8.8, "time_slot": "morning"},
        {"name": "特色午餐", "category": "food", "duration_hours": 1.5, "price": 150, "rating": 9.0, "time_slot": "afternoon"},
        {"name": "历史街区漫步", "category": "sightseeing", "duration_hours": 2.0, "price": 0, "rating": 7.5, "time_slot": "afternoon"},
        {"name": "手工艺体验", "category": "experience", "duration_hours": 2.0, "price": 200, "rating": 8.5, "time_slot": "afternoon"},
        {"name": "日落观景", "category": "sightseeing", "duration_hours": 1.0, "price": 50, "rating": 9.0, "time_slot": "evening"},
        {"name": "当地夜市美食", "category": "food", "duration_hours": 2.0, "price": 120, "rating": 8.5, "time_slot": "evening"},
        {"name": "文化演出", "category": "experience", "duration_hours": 2.0, "price": 300, "rating": 9.2, "time_slot": "evening"},
        {"name": "温泉/SPA体验", "category": "experience", "duration_hours": 2.0, "price": 350, "rating": 9.0, "time_slot": "afternoon"},
        {"name": "公园休闲", "category": "sightseeing", "duration_hours": 1.5, "price": 0, "rating": 7.0, "time_slot": "morning"},
        {"name": "购物街逛逛", "category": "experience", "duration_hours": 2.0, "price": 0, "rating": 7.5, "time_slot": "afternoon"},
    ],
}


class ActivityAgent(BaseAgent):
    name = "ActivityAgent"

    async def execute(self, state: TravelPlanState) -> TravelPlanState:
        pref = state.preferences
        dest = state.selected_destination
        if pref is None or dest is None:
            raise ValueError("缺少偏好或目的地信息")

        if self.use_llm:
            try:
                if await self._try_llm(state):
                    self._attach_rag_context(state)
                    return state
            except Exception as e:
                logger.warning(f"[{self.name}] LLM 调用异常，降级 mock: {e}")

        days = self._get_travel_days(pref.start_date, pref.end_date)
        daily_budget = (pref.budget * 0.25) / max(len(days), 1) / pref.num_travelers

        # RAG 检索当地景点/玩法资料，作为活动推荐上下文补充（去重追加）
        self._attach_rag_context(state)

        pool = self._get_activity_pool(dest.city)
        day_plans: list[DayPlan] = []
        total_cost = 0.0

        for date_str in days:
            plan = self._plan_one_day(date_str, pool, daily_budget, pref.interests)
            day_cost = sum(a.price for a in plan.activities) * pref.num_travelers
            plan.day_cost = day_cost
            total_cost += day_cost
            day_plans.append(plan)

        state.activity_result = ActivitySearchResult(
            day_plans=day_plans,
            total_activity_cost=total_cost,
        )
        logger.info(f"[{self.name}] 生成 {len(day_plans)} 天行程, 活动总费用: ¥{total_cost:.0f}")
        return state

    def _attach_rag_context(self, state: TravelPlanState) -> None:
        """RAG 检索当地景点/玩法资料，去重追加到共享 state（LLM/mock 共用）。"""
        dest = state.selected_destination
        if dest is None:
            return
        if not has_guide(dest.city):
            return
        hits = rag_search(f"{dest.city} 景点 玩法 美食 体验")
        for hit in hits:
            if hit not in state.rag_context:
                state.rag_context.append(hit)

    async def _try_llm(self, state: TravelPlanState) -> bool:
        pref = state.preferences
        dest = state.selected_destination
        days = self._get_travel_days(pref.start_date, pref.end_date)
        prompt = (
            f"为 {dest.city} 生成 {len(days)} 天行程（{days[0]} 至 {days[-1]}），"
            f"兴趣 {pref.interests or ['美食', '文化']}，每日活动预算约 ¥{pref.budget * 0.25 / max(len(days), 1):.0f}。\n"
            "严格输出如下 JSON（无多余字段）：\n"
            '{"day_plans":[{"date":"2026-05-01","activities":[{"name":"博物馆参观","category":"sightseeing",'
            '"location":"","duration_hours":2.0,"price":80,"rating":8.5,"description":"","time_slot":"morning"}]}]}\n'
            "要求：每天包含 morning/afternoon/evening 三个时段的 2-3 个活动；category 只能是 sightseeing/food/experience/transport；time_slot 只能是 morning/afternoon/evening。"
        )
        data = await chat_json([
            {"role": "system", "content": "你是行程规划师，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ])
        if not data:
            return False
        raw = data.get("day_plans")
        if not isinstance(raw, list) or not raw:
            return False
        day_plans: list[DayPlan] = []
        total = 0.0
        try:
            for i, dp in enumerate(raw):
                acts = [Activity(**a) for a in dp.get("activities", [])]
                date_str = days[i] if i < len(days) else dp.get("date", days[0])
                plan = DayPlan(date=date_str, activities=acts)
                dc = sum(a.price for a in acts) * pref.num_travelers
                plan.day_cost = dc
                total += dc
                day_plans.append(plan)
        except Exception as e:
            logger.warning(f"[{self.name}] LLM 结果解析失败: {e}")
            return False
        if not day_plans:
            return False
        state.activity_result = ActivitySearchResult(
            day_plans=day_plans,
            total_activity_cost=total,
        )
        logger.info(f"[{self.name}](LLM) 生成 {len(day_plans)} 天行程, 活动总费用 ¥{total:.0f}")
        return True

    @staticmethod
    def _get_travel_days(start: str, end: str) -> list[str]:
        try:
            d1 = datetime.strptime(start, "%Y-%m-%d")
            d2 = datetime.strptime(end, "%Y-%m-%d")
            days_count = max((d2 - d1).days, 1)
            return [(d1 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_count)]
        except (ValueError, TypeError):
            return ["2026-01-01", "2026-03-02", "2026-03-03"]

    @staticmethod
    def _get_activity_pool(city: str) -> list[dict]:
        pool = MOCK_ACTIVITIES_DB.get(city, MOCK_ACTIVITIES_DB["default"])
        return [dict(a, location=city) for a in pool]

    @staticmethod
    def _plan_one_day(date: str, pool: list[dict], daily_budget: float, interests: list[str]) -> DayPlan:
        slots = ["morning", "afternoon", "evening"]
        activities: list[Activity] = []

        for slot in slots:
            candidates = [a for a in pool if a["time_slot"] == slot]
            if not candidates:
                continue

            for c in candidates:
                bonus = sum(2 for tag in interests if tag in c["name"] or tag in c["category"])
                c["_score"] = c["rating"] + bonus + random.uniform(0, 1)

            candidates.sort(key=lambda x: x["_score"], reverse=True)
            best = candidates[0]
            activities.append(Activity(
                name=best["name"],
                category=best["category"],
                location=best.get("location", ""),
                duration_hours=best["duration_hours"],
                price=float(best["price"]),
                rating=best["rating"],
                description=f"{date} {slot} - {best['name']}",
                time_slot=slot,
            ))

        return DayPlan(date=date, activities=activities)
