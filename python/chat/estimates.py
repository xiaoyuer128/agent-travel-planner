"""Validated AI budget estimates with explicit planning assumptions for omissions."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .planner import calculate


class EstimatedItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='', max_length=120)
    price_cents: int | None = Field(default=None, ge=0, le=5_000_000, strict=True)
    basis: str = Field(default='', max_length=300)


class EstimatedDay(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: int = Field(ge=1, le=30, strict=True)
    tickets_cents: int | None = Field(default=None, ge=0, le=500_000, strict=True)
    meals_cents: int | None = Field(default=None, ge=0, le=500_000, strict=True)
    local_transport_cents: int | None = Field(default=None, ge=0, le=500_000, strict=True)
    basis: str = Field(default='', max_length=300)


class BudgetEstimate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    flights: list[EstimatedItem] = Field(default_factory=list, max_length=2)
    hotels: list[EstimatedItem] = Field(default_factory=list, max_length=3)
    daily_costs: list[EstimatedDay] = Field(default_factory=list, max_length=30)


ASSUMPTION = '缺失项按通用旅行规划假设补足，未查询历史价格数据库。'
NOTICE = '航班、酒店及费用为AI预算估算，非实时报价；实际价格与可用性以预订平台为准。'


def apply_estimate(plan, output: BudgetEstimate, scope='full', target_day=None):
    """Apply only requested sections; never accept model-computed totals."""
    preferences = plan['preferences']
    destination = preferences['destination']
    premium_city = destination in {'北京', '上海', '深圳', '三亚'}
    hotel_base = 32000 if premium_city else 24000
    flight_base = 80000
    if preferences['departure_city'] == destination:
        flight_base = 0
    fallback_fields = []

    def amount(value, fallback, path):
        if value is None:
            fallback_fields.append(path)
            return fallback
        return value

    if scope == 'full':
        flights = []
        for index, direction in enumerate(('去程', '返程')):
            item = output.flights[index] if index < len(output.flights) else EstimatedItem()
            price = amount(item.price_cents, flight_base, f'flights.{index}.price_cents')
            flights.append({
                'id': f'ai-flight-{index}', 'label': f'{direction}交通预算',
                'suggestion': item.name, 'price_cents': price,
                'basis': item.basis or '按出发地、目的地与出行日期估算单人单程费用。',
                'source_kind': 'planning_assumption' if item.price_cents is None else 'ai_estimate',
            })
        hotels = []
        for index, (tier, multiplier, stars) in enumerate(
                [('经济型', 0.65, 2), ('舒适型', 1, 3), ('品质型', 1.6, 4)]):
            item = output.hotels[index] if index < len(output.hotels) else EstimatedItem()
            # An overnight room with zero cost is not a usable hotel estimate.
            if item.price_cents == 0:
                raise ValueError('住宿估算必须大于零')
            price = amount(item.price_cents, round(hotel_base * multiplier), f'hotels.{index}.price_cents')
            hotels.append({
                'id': f'ai-hotel-{index}', 'name': item.name or f'{destination}{tier}住宿建议',
                'price_cents': price, 'stars': stars, 'tier': tier,
                'basis': item.basis or '按城市消费水平估算每房每晚费用，具体酒店与房型待核实。',
                'source_kind': 'planning_assumption' if item.price_cents is None else 'ai_estimate',
            })
        hotels.sort(key=lambda hotel: hotel['price_cents'])
        plan['flights'] = flights
        plan['hotel_options'] = hotels
        plan['hotel'] = dict(hotels[1])

    daily = {row.day: row for row in output.daily_costs}
    if len(daily) != len(output.daily_costs) or any(day > preferences['days'] for day in daily):
        raise ValueError('每日费用序号重复或超出行程')
    for day in plan['days']:
        if target_day is not None and day['day'] != target_day:
            continue
        row = daily.get(day['day'], EstimatedDay(day=day['day']))
        expenses = {
            'tickets_cents': amount(row.tickets_cents, 8000, f'days.{day["day"]}.tickets_cents'),
            'meals_cents': amount(row.meals_cents, 12000 if premium_city else 10000, f'days.{day["day"]}.meals_cents'),
            'local_transport_cents': amount(row.local_transport_cents, 4000, f'days.{day["day"]}.local_transport_cents'),
        }
        day['expense_estimate'] = {
            **expenses, 'basis': row.basis or '按门票、三餐与市内出行的通用日预算估算。',
            'source_kind': 'planning_assumption' if any(
                getattr(row, key) is None for key in expenses) else 'ai_estimate',
        }
        day['cost_per_person_cents'] = sum(expenses.values())

    previous_fallbacks = plan.get('price_metadata', {}).get('fallback_fields', [])
    if scope == 'daily':
        # Keep provenance for untouched sections, replace it for regenerated days.
        updated_prefixes = [f'days.{day["day"]}.' for day in plan['days']
                            if target_day is None or day['day'] == target_day]
        previous_fallbacks = [field for field in previous_fallbacks
                              if not any(field.startswith(prefix) for prefix in updated_prefixes)]
    else:
        previous_fallbacks = []
    mixed = scope == 'daily' and (
        any('expense_estimate' not in day for day in plan['days'])
        or 'source_kind' not in plan['hotel']
        or any('source_kind' not in flight for flight in plan['flights']))
    plan['price_metadata'] = {
        'kind': 'mixed_estimate' if mixed else 'ai_estimate', 'provider': 'deepseek', 'currency': 'CNY',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'notice': ('本次修改使用AI费用估算，未修改部分沿用原方案示例预算；实际价格与可用性以预订平台为准。' if mixed else NOTICE),
        'fallback_note': ASSUMPTION,
        'fallback_fields': previous_fallbacks + fallback_fields,
    }
    return calculate(plan)
