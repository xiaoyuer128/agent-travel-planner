"""
活动搜索工具 —— 模拟 Google Maps Places API / 大众点评 API。

在生产环境中，这里会对接 Google Places API / TripAdvisor API 等。
Mock 模式下返回各城市的景点、餐厅、体验活动数据。
"""

from __future__ import annotations

import random

from models.schemas import Activity


CITY_ACTIVITIES: dict[str, list[dict]] = {'杭州': [{'name': '西湖', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '灵隐飞来峰', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '南京': [{'name': '栖霞山', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '夫子庙秦淮风光带', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '北京': [{'name': '颐和园', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '香山公园', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '西安': [{'name': '大雁塔', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '西安城墙', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '成都': [{'name': '人民公园', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '宽窄巷子', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '重庆': [{'name': '洪崖洞', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '解放碑', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '上海': [{'name': '外滩', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '豫园', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], '三亚': [{'name': '亚龙湾', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}, {'name': '鹿回头风景区', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'afternoon'}], 'default': [{'name': '当地街区自由探索（示例）', 'cat': 'sightseeing', 'price': 0, 'hours': 2.0, 'slot': 'morning'}]}


def search_activities(city: str, interests: list[str] | None = None) -> list[Activity]:
    """搜索目的地活动（Mock 实现）。"""
    templates = CITY_ACTIVITIES.get(city, CITY_ACTIVITIES["default"])
    interests = interests or []

    results: list[Activity] = []
    for tmpl in templates:
        bonus = sum(1 for tag in interests if tag.lower() in tmpl["name"].lower())
        rating = round(random.uniform(7.5, 9.5) + bonus * 0.3, 1)
        results.append(Activity(
            name=tmpl["name"],
            category=tmpl["cat"],
            location=city,
            duration_hours=tmpl["hours"],
            price=float(tmpl["price"]),
            rating=min(rating, 10.0),
            description=f"{city} - {tmpl['name']}",
            time_slot=tmpl["slot"],
        ))

    return results
