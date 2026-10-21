"""
并行执行器 —— 同时运行多个 Agent，等待全部完成后合并结果。

"""

from __future__ import annotations

import asyncio
from typing import Sequence

from loguru import logger

from agents.base_agent import BaseAgent
from config.settings import settings
from models.schemas import TravelPlanState


class ParallelExecutor:
    """并行执行一组 Agent，将各自输出合并到同一 state 对象。"""

    def __init__(self, agents: Sequence[BaseAgent], timeout: int | None = None):
        self.agents = list(agents)
        self.timeout = timeout or settings.PARALLEL_TIMEOUT

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        logger.info(f"[ParallelExecutor] 启动 {len(self.agents)} 个 Agent 并行执行...")

        tasks = [
            asyncio.wait_for(agent.run(state), timeout=self.timeout)
            for agent in self.agents
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                err_msg = f"{agent.name} 并行执行失败: {result}"
                logger.error(err_msg)
                state.error_messages.append(err_msg)

        logger.info("[ParallelExecutor] 并行执行完成")
        return state
