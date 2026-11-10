"""
酒店搜索工具 —— 模拟 Booking.com / 携程酒店 API。

在生产环境中，这里会对接真实酒店预订 API。
Mock 模式下根据城市和旅行风格生成合理的酒店数据。
"""

from __future__ import annotations

import random

from models.schemas import Hotel


CITY_HOTEL_DATA: dict[str, list[dict]] = {'杭州': [{'name': '杭州舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '杭州经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '南京': [{'name': '南京舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '南京经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '北京': [{'name': '北京舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '北京经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '西安': [{'name': '西安舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '西安经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '成都': [{'name': '成都舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '成都经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '重庆': [{'name': '重庆舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '重庆经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '上海': [{'name': '上海舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '上海经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], '三亚': [{'name': '三亚舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '三亚经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}], 'default': [{'name': '杭州舒适型示例酒店', 'star': 3.0, 'base_price': 220, 'amenities': ['WiFi', '早餐']}, {'name': '杭州经济型示例酒店', 'star': 2.0, 'base_price': 120, 'amenities': ['WiFi']}]}


def search_hotels(city: str, check_in: str, check_out: str, style: str = "comfort") -> list[Hotel]:
    """搜索酒店（Mock 实现）。"""
    templates = CITY_HOTEL_DATA.get(city, [{**h, "name": city + "示例酒店"} for h in CITY_HOTEL_DATA["default"]])
    style_mult = {"budget": 0.7, "comfort": 1.0, "luxury": 1.5,
                  "adventure": 0.6, "cultural": 0.9, "relaxation": 1.2}
    mult = style_mult.get(style, 1.0)

    results: list[Hotel] = []
    for tmpl in templates:
        noise = random.uniform(0.85, 1.15)
        results.append(Hotel(
            name=tmpl["name"],
            city=city,
            address=f"{city}市中心",
            star_rating=tmpl["star"],
            user_rating=round(random.uniform(7.0, 9.8), 1),
            price_per_night=round(tmpl["base_price"] * mult * noise),
            amenities=tmpl["amenities"],
            distance_to_center_km=round(random.uniform(0.3, 5.0), 1),
        ))

    return sorted(results, key=lambda h: h.price_per_night)
