"""
Destination Agent —— 目的地推荐 Agent。

职责: 根据用户偏好推荐目的地，考虑季节、签证、安全性、性价比。
在 Pipeline 中处于第二个节点，接收 preferences，输出 DestinationRecommendation。

面试考点:
  - 推荐算法: 基于多维加权评分（预算匹配度、季节适宜度、安全评分）
  - 为什么不直接让用户选城市？ —— 提升用户体验，发现长尾目的地
  - Mock 数据库 vs 真实 API: 演示用 mock，生产环境接 Amadeus / Google Places
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from models.schemas import (
    Destination,
    DestinationRecommendation,
    PlanningState,
    TravelPlanState,
    UserPreferences,
)

from .base_agent import BaseAgent
from llm_client import chat_json
from rag import has_guide, rag_search

MOCK_DESTINATIONS: list[dict] = [
    {
        "city": "东京",
        "country": "日本",
        "description": "传统与现代的完美融合，美食天堂",
        "best_season": "spring,autumn",
        "visa_required": True,
        "safety_score": 9.5,
        "cost_level": "high",
        "highlights": ["浅草寺", "涩谷十字路口", "筑地市场", "东京塔"],
    },
    {
        "city": "曼谷",
        "country": "泰国",
        "description": "热带风情，物美价廉的旅游胜地",
        "best_season": "winter",
        "visa_required": False,
        "safety_score": 7.5,
        "cost_level": "low",
        "highlights": ["大皇宫", "卧佛寺", "考山路", "暹罗广场"],
    },
    {
        "city": "巴黎",
        "country": "法国",
        "description": "浪漫之都，艺术与美食的殿堂",
        "best_season": "spring,summer",
        "visa_required": True,
        "safety_score": 8.0,
        "cost_level": "high",
        "highlights": ["埃菲尔铁塔", "卢浮宫", "香榭丽舍大街", "蒙马特高地"],
    },
    {
        "city": "清迈",
        "country": "泰国",
        "description": "宁静的兰纳古城，适合文化与休闲",
        "best_season": "winter",
        "visa_required": False,
        "safety_score": 8.5,
        "cost_level": "low",
        "highlights": ["双龙寺", "古城", "夜间动物园", "周末夜市"],
    },
    {
        "city": "首尔",
        "country": "韩国",
        "description": "潮流时尚与历史文化交汇",
        "best_season": "spring,autumn",
        "visa_required": False,
        "safety_score": 9.0,
        "cost_level": "medium",
        "highlights": ["景福宫", "明洞", "北村韩屋村", "南山塔"],
    },
    {
        "city": "大阪",
        "country": "日本",
        "description": "日本的厨房，环球影城所在地",
        "best_season": "spring,autumn",
        "visa_required": True,
        "safety_score": 9.5,
        "cost_level": "medium",
        "highlights": ["大阪城", "道顿堀", "环球影城", "黑门市场"],
    },
]


class DestinationAgent(BaseAgent):
    name = "DestinationAgent"

    async def execute(self, state: TravelPlanState) -> TravelPlanState:
        pref = state.preferences
        if pref is None:
            raise ValueError("缺少用户偏好")

        if pref.destination and await self._apply_destination_override(state, pref, pref.destination):
            return state

        if self.use_llm:
            try:
                if await self._try_llm(state):
                    self._attach_rag_context(state)
                    return state
            except Exception as e:
                logger.warning(f"[{self.name}] LLM 调用异常，降级 mock: {e}")

        scored = []
        for d_data in MOCK_DESTINATIONS:
            dest = Destination(**d_data)
            score = self._score_destination(dest, pref.budget, pref.travel_style.value, pref.start_date)
            scored.append((score, dest))

        scored.sort(key=lambda x: x[0], reverse=True)
        top3 = [d for _, d in scored[:3]]
        selected = top3[0]

        state.destination_rec = DestinationRecommendation(
            destinations=top3,
            selected=selected,
            reasoning=f"根据您 ¥{pref.budget} 的预算和 {pref.travel_style.value} 风格，推荐 {selected.city}",
        )
        state.state = PlanningState.SEARCHING_PARALLEL
        self._attach_rag_context(state)

        logger.info(f"[{self.name}] 推荐目的地: {selected.city}, {selected.country}")
        return state

    async def _apply_destination_override(
        self, state: TravelPlanState, pref: UserPreferences, city: str
    ) -> bool:
        """使用用户指定的目的地；支持任意城市自由输入，找不到匹配则为其构建定制目的地。"""
        match = next((d for d in MOCK_DESTINATIONS if d["city"] == city), None)
        if match:
            selected = Destination(**match)

            scored: list[tuple[float, Destination]] = []
            for d_data in MOCK_DESTINATIONS:
                dest = Destination(**d_data)
                score = self._score_destination(dest, pref.budget, pref.travel_style.value, pref.start_date)
                scored.append((score, dest))
            scored.sort(key=lambda x: x[0], reverse=True)
            others = [d for _, d in scored if d.city != selected.city][:2]
        else:
            selected = await self._build_custom_destination(city)
            others: list[Destination] = []

        state.destination_rec = DestinationRecommendation(
            destinations=[selected] + others,
            selected=selected,
            reasoning=f"根据你指定的目的地 {selected.city}，已为你规划行程",
        )
        state.state = PlanningState.SEARCHING_PARALLEL
        self._attach_rag_context(state)
        logger.info(f"[{self.name}] 使用用户指定目的地: {selected.city}, {selected.country}")
        return True

    async def _build_custom_destination(self, city: str) -> Destination:
        """为不在 MOCK_DESTINATIONS 中的任意城市构建目的地信息。优先 LLM 补全，失败则用默认模板。"""
        if self.use_llm:
            try:
                prompt = (
                    f"请补全目的地「{city}」的旅游信息。严格输出如下 JSON（无多余字段）：\n"
                    f'{{"city":"{city}","country":"国家","description":"一句话简介",'
                    '"best_season":"spring,autumn","visa_required":false,"safety_score":8.0,'
                    '"cost_level":"medium","highlights":["景点1","景点2","景点3"]}'
                )
                data = await chat_json([
                    {"role": "system", "content": "你是旅行目的地百科，只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ])
                if isinstance(data, dict) and data:
                    data["city"] = city
                    data.setdefault("country", "")
                    return Destination(**data)
            except Exception as e:
                logger.warning(f"[{self.name}] LLM 补全 {city} 失败，降级默认模板: {e}")
        return Destination(
            city=city,
            country="",
            description=f"{city} 定制行程",
            safety_score=8.0,
            cost_level="medium",
        )

    def _attach_rag_context(self, state: TravelPlanState) -> None:
        """RAG 检索目的地攻略，补充到共享 state，供后续 Agent 与前端参考（LLM/mock 共用）。"""
        dest = state.selected_destination
        if dest is None:
            return
        if not has_guide(dest.city):
            logger.info(f"[{self.name}] {dest.city} 无内置攻略，跳过 RAG 检索")
            return
        hits = rag_search(f"{dest.city} {dest.country} 旅游攻略 景点 美食")
        if hits:
            state.rag_context = hits
            logger.info(f"[{self.name}] RAG 检索到 {len(hits)} 条攻略上下文")

    async def _try_llm(self, state: TravelPlanState) -> bool:
        pref = state.preferences
        prompt = (
            f"预算 ¥{pref.budget:.0f}，出发城市 {pref.departure_city}，出发日期 {pref.start_date}，"
            f"旅行风格 {pref.travel_style.value}，兴趣 {pref.interests or ['美食']}。\n"
            "请推荐 3 个目的地，严格输出如下 JSON（无多余字段）：\n"
            '{"destinations":[{"city":"东京","country":"日本","description":"...","best_season":"spring,autumn",'
            '"visa_required":true,"safety_score":9.5,"cost_level":"high","highlights":["浅草寺","涩谷"]}],'
            '"reasoning":"推荐理由"}'
        )
        data = await chat_json([
            {"role": "system", "content": "你是资深旅行规划师，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ])
        if not data:
            return False
        raw = data.get("destinations")
        if not isinstance(raw, list) or not raw:
            return False
        try:
            destinations = [Destination(**d) for d in raw[:3]]
        except Exception as e:
            logger.warning(f"[{self.name}] LLM 结果解析失败: {e}")
            return False
        if not destinations:
            return False
        state.destination_rec = DestinationRecommendation(
            destinations=destinations,
            selected=destinations[0],
            reasoning=data.get("reasoning", f"推荐 {destinations[0].city}, {destinations[0].country}"),
        )
        state.state = PlanningState.SEARCHING_PARALLEL
        logger.info(f"[{self.name}](LLM) 推荐目的地: {destinations[0].city}, {destinations[0].country}")
        return True

    @staticmethod
    def _score_destination(dest: Destination, budget: float, style: str, start_date: str) -> float:
        score = 0.0

        cost_budget_map = {"low": 8000, "medium": 15000, "high": 25000}
        est_cost = cost_budget_map.get(dest.cost_level, 15000)
        if budget >= est_cost:
            score += 30
        elif budget >= est_cost * 0.7:
            score += 15

        score += dest.safety_score * 3

        try:
            month = datetime.strptime(start_date, "%Y-%m-%d").month
        except (ValueError, TypeError):
            month = 6

        season_map = {12: "winter", 1: "winter", 2: "winter",
                      3: "spring", 4: "spring", 5: "spring",
                      6: "summer", 7: "summer", 8: "summer",
                      9: "autumn", 10: "autumn", 11: "autumn"}
        current_season = season_map.get(month, "summer")
        if current_season in dest.best_season:
            score += 20

        style_cost_pref = {"budget": "low", "comfort": "medium", "luxury": "high",
                           "adventure": "low", "cultural": "medium", "relaxation": "medium"}
        if style_cost_pref.get(style) == dest.cost_level:
            score += 15

        if not dest.visa_required:
            score += 10

        return score
