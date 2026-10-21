"""
Preference Agent —— 偏好收集 Agent。

职责: 通过对话或结构化输入收集用户偏好（预算/风格/时间/禁忌）。
在 Pipeline 中处于第一个节点，输出 UserPreferences 填入全局状态。


"""

from __future__ import annotations

from loguru import logger

from models.schemas import PlanningState, TravelPlanState, UserPreferences

from .base_agent import BaseAgent
from llm_client import chat_json


class PreferenceAgent(BaseAgent):
    name = "PreferenceAgent"

    async def execute(self, state: TravelPlanState) -> TravelPlanState:
        if state.preferences is None:
            raise ValueError("用户偏好未提供，请先设置 state.preferences")

        pref = state.preferences

        if not pref.interests:
            interests = self._default_interests(pref.travel_style.value)
            if self.use_llm:
                try:
                    llm_i = await self._try_llm_interests(pref.travel_style.value)
                    if llm_i:
                        interests = llm_i
                except Exception as e:
                    logger.warning(f"[{self.name}] LLM 兴趣生成失败，使用默认: {e}")
            pref.interests = interests
            logger.info(f"[{self.name}] 自动补充兴趣标签: {pref.interests}")

        state.preferences = pref
        state.state = PlanningState.RECOMMENDING_DESTINATIONS
        return state

    async def _try_llm_interests(self, style: str) -> list[str] | None:
        prompt = (
            f"旅行风格为 {style}，请推荐 3-5 个兴趣标签（中文），"
            '严格输出 JSON：{"interests":["美食","历史"]}'
        )
        data = await chat_json([
            {"role": "system", "content": "你是旅行偏好分析专家，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ])
        if not data:
            return None
        i = data.get("interests")
        return i if isinstance(i, list) and i else None

    @staticmethod
    def _default_interests(style: str) -> list[str]:
        mapping = {
            "budget": ["免费景点", "街头美食", "步行游览"],
            "comfort": ["经典景点", "当地美食", "文化体验"],
            "luxury": ["米其林餐厅", "私人导游", "SPA"],
            "adventure": ["徒步", "潜水", "极限运动"],
            "cultural": ["博物馆", "历史遗迹", "传统手工艺"],
            "relaxation": ["海滩", "温泉", "瑜伽"],
        }
        return mapping.get(style, ["经典景点", "美食"])
