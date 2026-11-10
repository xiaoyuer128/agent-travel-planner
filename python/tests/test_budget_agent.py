"""
Budget Agent 专项测试 —— 覆盖所有逻辑分支和边界情况。

通过这些测试用例，你可以直观理解 BudgetAgent 的完整行为：
  1. 预算内正常通过
  2. 超预算触发第1轮调整（砍活动费用）
  3. 超预算触发第2轮调整（砍酒店费用）
  4. 超预算触发第3轮调整（砍航班费用）
  5. 达到最大调整次数强制结束
  6. 各种边界条件

运行: cd python && python -m pytest tests/test_budget_agent.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import BudgetAgent
from models.schemas import (
    Activity,
    ActivitySearchResult,
    BudgetBreakdown,
    DayPlan,
    Flight,
    FlightSearchResult,
    Hotel,
    HotelSearchResult,
    PlanningState,
    TravelPlanState,
    TravelStyle,
    UserPreferences,
)


# ━━━━━━━━━━━━━━━━━━ 测试工具函数 ━━━━━━━━━━━━━━━━━━


def _make_prefs(budget: float = 10000, travelers: int = 1) -> UserPreferences:
    """创建测试用的用户偏好对象。"""
    return UserPreferences(
        budget=budget,
        travel_style=TravelStyle.COMFORT,
        departure_city="北京",
        start_date="2026-05-01",
        end_date="2026-05-05",
        num_travelers=travelers,
    )


def _make_flight_result(total: float = 3000) -> FlightSearchResult:
    """创建测试用的航班搜索结果。"""
    return FlightSearchResult(
        outbound_flights=[Flight(
            airline="测试航空",
            flight_no="TEST001",
            departure_city="北京",
            arrival_city="北京",
            departure_time="08:00",
            arrival_time="10:00",
            price=total / 2,
            duration_hours=2.0,
        )],
        return_flights=[Flight(
            airline="测试航空",
            flight_no="TEST002",
            departure_city="北京",
            arrival_city="北京",
            departure_time="18:00",
            arrival_time="20:00",
            price=total / 2,
            duration_hours=2.0,
        )],
        recommended_outbound=Flight(
            airline="测试航空",
            flight_no="TEST001",
            departure_city="北京",
            arrival_city="北京",
            departure_time="08:00",
            arrival_time="10:00",
            price=total / 2,
            duration_hours=2.0,
        ),
        recommended_return=Flight(
            airline="测试航空",
            flight_no="TEST002",
            departure_city="北京",
            arrival_city="北京",
            departure_time="18:00",
            arrival_time="20:00",
            price=total / 2,
            duration_hours=2.0,
        ),
        total_flight_cost=total,
    )


def _make_hotel_result(total: float = 2000, per_night: float = 500) -> HotelSearchResult:
    """创建测试用的酒店搜索结果。"""
    return HotelSearchResult(
        hotels=[Hotel(
            name="测试酒店",
            city="北京",
            star_rating=4.0,
            price_per_night=per_night,
        )],
        recommended=Hotel(
            name="测试酒店",
            city="北京",
            star_rating=4.0,
            price_per_night=per_night,
        ),
        total_nights=4,
        total_hotel_cost=total,
    )


def _make_activity_result(total: float = 1500) -> ActivitySearchResult:
    """创建测试用的活动搜索结果。"""
    return ActivitySearchResult(
        day_plans=[
            DayPlan(
                date=f"2026-05-0{i}",
                activities=[
                    Activity(name="活动A", price=200, time_slot="morning"),
                    Activity(name="活动B", price=150, time_slot="afternoon"),
                    Activity(name="活动C", price=100, time_slot="evening"),
                ],
                day_cost=450,
            )
            for i in range(1, 4)
        ],
        total_activity_cost=total,
    )


def _make_state(
    budget: float = 10000,
    flight_cost: float = 3000,
    hotel_cost: float = 2000,
    activity_cost: float = 1500,
    adjustment_round: int = 0,
    max_adjustments: int = 3,
) -> TravelPlanState:
    """创建完整的测试状态对象。"""
    state = TravelPlanState(
        preferences=_make_prefs(budget),
        flight_result=_make_flight_result(flight_cost),
        hotel_result=_make_hotel_result(hotel_cost),
        activity_result=_make_activity_result(activity_cost),
        adjustment_round=adjustment_round,
        max_adjustments=max_adjustments,
    )
    return state


# ━━━━━━━━━━━━━━━━━━ 测试用例 ━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_01_budget_passes_when_within_budget():
    """场景1: 预算内正常通过
    总费用: 3000 + 2000 + 1500 = 6500
    预算: 10000
    结果: 预算通过，状态变为 COMPLETED
    """
    state = _make_state(budget=10000, flight_cost=3000, hotel_cost=2000, activity_cost=1500)
    agent = BudgetAgent()
    result = await agent.run(state)

    # 验证预算通过
    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is True
    assert result.budget_breakdown.total_cost == 6500
    assert result.budget_breakdown.remaining == 3500
    assert result.state == PlanningState.COMPLETED
    assert result.adjustment_round == 0


@pytest.mark.asyncio
async def test_02_budget_passes_exactly_at_limit():
    """场景2: 刚好等于预算（边界情况）
    总费用: 5000 + 3000 + 2000 = 10000
    预算: 10000
    结果: 预算通过（remaining == 0 也算通过）
    """
    state = _make_state(budget=10000, flight_cost=5000, hotel_cost=3000, activity_cost=2000)
    agent = BudgetAgent()
    result = await agent.run(state)

    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is True
    assert result.budget_breakdown.remaining == 0
    assert result.state == PlanningState.COMPLETED


@pytest.mark.asyncio
async def test_03_over_budget_triggers_round1_cut_activity():
    """场景3: 超预算触发第1轮调整（砍活动费用）
    总费用: 5000 + 3000 + 4000 = 12000
    预算: 10000
    超出: 2000
    预期: 进入第1轮调整，活动费用被砍
    """
    state = _make_state(budget=10000, flight_cost=5000, hotel_cost=3000, activity_cost=4000)
    agent = BudgetAgent()
    result = await agent.run(state)

    # 验证超预算
    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is False
    assert result.budget_breakdown.over_budget_amount == 2000

    # 验证进入调整
    assert result.state == PlanningState.ADJUSTING
    assert result.adjustment_round == 1

    # 验证活动费用被砍
    assert result.activity_result is not None
    assert result.activity_result.total_activity_cost < 4000


@pytest.mark.asyncio
async def test_04_round2_cuts_hotel():
    """场景4: 第2轮调整砍酒店费用
    模拟已经经过1轮调整，仍然超预算
    预期: 进入第2轮调整，酒店费用被砍
    """
    state = _make_state(
        budget=10000,
        flight_cost=5000,
        hotel_cost=3000,
        activity_cost=3000,
        adjustment_round=1,  # 已经调整过1轮
    )
    agent = BudgetAgent()
    result = await agent.run(state)

    # 验证超预算（5000+3000+3000=11000 > 10000）
    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is False

    # 验证进入第2轮调整
    assert result.state == PlanningState.ADJUSTING
    assert result.adjustment_round == 2

    # 验证酒店费用被砍
    assert result.hotel_result is not None
    assert result.hotel_result.total_hotel_cost < 3000


@pytest.mark.asyncio
async def test_05_round3_cuts_flight():
    """场景5: 第3轮调整砍航班费用
    模拟已经经过2轮调整，仍然超预算
    预期: 进入第3轮调整，航班费用被砍
    """
    state = _make_state(
        budget=10000,
        flight_cost=5000,
        hotel_cost=3000,
        activity_cost=3000,
        adjustment_round=2,  # 已经调整过2轮
    )
    agent = BudgetAgent()
    result = await agent.run(state)

    # 验证超预算
    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is False

    # 验证进入第3轮调整
    assert result.state == PlanningState.ADJUSTING
    assert result.adjustment_round == 3

    # 验证航班费用被砍
    assert result.flight_result is not None
    assert result.flight_result.total_flight_cost < 5000


@pytest.mark.asyncio
async def test_06_max_adjustments_reached_force_complete():
    """场景6: 达到最大调整次数，强制完成
    模拟已经调整过3轮（max_adjustments=3），仍然超预算
    预期: 强制转为 COMPLETED，记录错误信息
    """
    state = _make_state(
        budget=10000,
        flight_cost=5000,
        hotel_cost=3000,
        activity_cost=3000,
        adjustment_round=3,  # 已经调整过3轮，达到上限
        max_adjustments=3,
    )
    agent = BudgetAgent()
    result = await agent.run(state)

    # 验证强制完成
    assert result.state == PlanningState.COMPLETED

    # 验证记录了错误信息
    assert len(result.error_messages) > 0
    assert "经过 3 轮调整仍超预算" in result.error_messages[0]


@pytest.mark.asyncio
async def test_07_no_flight_hotel_activity_results():
    """场景7: 没有航班/酒店/活动结果（边界情况）
    预期: 费用全部为0，预算通过
    """
    state = TravelPlanState(preferences=_make_prefs(budget=10000))
    # 不设置 flight_result, hotel_result, activity_result
    agent = BudgetAgent()
    result = await agent.run(state)

    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is True
    assert result.budget_breakdown.total_cost == 0


@pytest.mark.asyncio
async def test_08_missing_preferences_recorded_in_error():
    """场景8: 缺少用户偏好（边界情况）
    预期: 异常被 BaseAgent 捕获，记录到 state.error_messages
    """
    state = TravelPlanState()  # 没有 preferences
    agent = BudgetAgent()
    result = await agent.run(state)

    # BaseAgent 的 run() 模板方法会捕获异常并记录到 error_messages
    assert len(result.error_messages) > 0
    assert "缺少用户偏好" in result.error_messages[0]


@pytest.mark.asyncio
async def test_09_cut_ratio_capped_at_max():
    """场景9: 砍价比例不超过最大阈值
    即使超出金额很大，砍价比例也不能超过 40%/35%/25%
    """
    # 超出金额巨大（10000），但活动费用只有 1000
    # 理论砍价比例 = 10000/1000 = 10（1000%），但应该被 cap 在 40%
    state = _make_state(
        budget=1000,
        flight_cost=5000,
        hotel_cost=3000,
        activity_cost=1000,
    )
    agent = BudgetAgent()
    result = await agent.run(state)

    assert result.activity_result is not None
    # 砍价后活动费用 = 1000 * (1 - 0.4) = 600
    assert abs(result.activity_result.total_activity_cost - 600) < 1


@pytest.mark.asyncio
async def test_10_multiple_travelers():
    """场景10: 多人出行
    验证 BudgetAgent 正确处理多人出行场景
    """
    state = _make_state(
        budget=20000,
        flight_cost=6000,  # 2人往返
        hotel_cost=4000,
        activity_cost=3000,
    )
    state.preferences = _make_prefs(budget=20000, travelers=2)
    agent = BudgetAgent()
    result = await agent.run(state)

    assert result.budget_breakdown is not None
    assert result.budget_breakdown.is_within_budget is True
    assert result.budget_breakdown.total_cost == 13000


@pytest.mark.asyncio
async def test_11_budget_breakdown_structure():
    """场景11: 验证 BudgetBreakdown 对象结构完整性"""
    state = _make_state(budget=10000, flight_cost=3000, hotel_cost=2000, activity_cost=1500)
    agent = BudgetAgent()
    result = await agent.run(state)

    bb = result.budget_breakdown
    assert bb is not None
    assert bb.flight_cost == 3000
    assert bb.hotel_cost == 2000
    assert bb.activity_cost == 1500
    assert bb.total_cost == 6500
    assert bb.budget == 10000
    assert bb.remaining == 3500
    assert bb.is_within_budget is True
    assert bb.over_budget_amount == 0
    assert isinstance(bb.suggestions, list)


@pytest.mark.asyncio
async def test_12_suggestions_generated_for_over_budget():
    """场景12: 超预算时生成调整建议"""
    state = _make_state(budget=10000, flight_cost=5000, hotel_cost=3000, activity_cost=4000)
    agent = BudgetAgent()
    result = await agent.run(state)

    assert result.budget_breakdown is not None
    assert len(result.budget_breakdown.suggestions) > 0
    # 第0轮应该建议减少活动开支
    assert any("活动" in s for s in result.budget_breakdown.suggestions)


@pytest.mark.asyncio
async def test_13_state_transitions_complete_flow():
    """场景13: 完整的状态转换流程测试
    模拟从超预算到最终完成的完整流程
    使用极低预算确保每一轮调整后仍然超预算
    """
    # 初始状态：严重超预算（总费用12000，预算5000）
    state = _make_state(
        budget=5000,
        flight_cost=5000,
        hotel_cost=3000,
        activity_cost=4000,
    )
    agent = BudgetAgent()

    # 第1轮：砍活动
    result = await agent.run(state)
    assert result.state == PlanningState.ADJUSTING
    assert result.adjustment_round == 1

    # 第2轮：砍酒店
    result = await agent.run(result)
    assert result.state == PlanningState.ADJUSTING
    assert result.adjustment_round == 2

    # 第3轮：砍航班
    result = await agent.run(result)
    assert result.state == PlanningState.ADJUSTING
    assert result.adjustment_round == 3

    # 第4轮：达到上限，强制完成
    result = await agent.run(result)
    assert result.state == PlanningState.COMPLETED
    assert len(result.error_messages) > 0
