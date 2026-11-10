"""Replace this bounded extraction adapter when adding an LLM; tools stay deterministic."""
import re
from datetime import date, timedelta
from typing import Protocol


def number(text):
    if text.isdigit():
        return int(text)
    digits = dict(zip("零一二三四五六七八九两", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2]))
    total = current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in "十百千万":
            unit = {"十": 10, "百": 100, "千": 1000, "万": 10000}[char]
            total += (current or 1) * unit
            current = 0
    return total + current


class Extractor(Protocol):
    def extract(self, message: str, preferences: dict) -> tuple[dict, str]: ...


class MockExtractor:
    def extract(self, message, preferences):
        text = message.strip()
        patch = {}
        numeric = r"[0-9零一二三四五六七八九十百千万两]+"
        match = re.search(r"(?:预算|控制在|总共)(?:改成|改为|调整为|为|是|约|：|:|\s)*([0-9]+(?:\.[0-9]+)?|[零一二三四五六七八九十百千万两]+)(万|千)?", text)
        if match:
            value = float(match[1]) if re.match(r"^[0-9]", match[1]) else number(match[1])
            patch["budget"] = value * ({"万": 10000, "千": 1000}.get(match[2], 1))
        match = re.search(rf"({numeric})\s*(?:个)?人", text)
        if match:
            patch["num_travelers"] = number(match[1])
        match = re.search(rf"(?:玩|旅行|待|住)?\s*({numeric})\s*天", text)
        if match:
            patch["days"] = number(match[1])
        match = re.search(r"(?:从)?([\u4e00-\u9fff]{2,6})出发", text)
        if match:
            patch["departure_city"] = match[1]
        match = re.search(r"(?:目的地[是为：:\s]*|想去|去|到)([\u4e00-\u9fff]{2,6}?)(?=[，。\s,！!]|玩|旅行|$)", text)
        if match:
            patch["destination"] = match[1]
        # Accept a bare known city as a follow-up to the first missing city slot.
        if text in {"重庆", "成都", "北京", "上海", "杭州", "西安", "三亚", "南京"}:
            patch["departure_city" if not preferences.get("departure_city") else "destination"] = text
        match = re.search(r"(20\d{2}-\d{1,2}-\d{1,2})", text)
        if match:
            patch["start_date"] = date.fromisoformat(match[1]).isoformat()
        else:
            match = re.search(r"(\d{1,2})月(\d{1,2})[日号]?", text)
            if match:
                today = date.today()
                parsed = date(today.year, int(match[1]), int(match[2]))
                if parsed < today:
                    parsed = parsed.replace(year=today.year + 1)
                patch["start_date"] = parsed.isoformat()
            elif "下周" in text:
                today = date.today()
                weekday = re.search(r"下周([一二三四五六日天])", text)
                offset = "一二三四五六日".find(weekday[1].replace("天", "日")) if weekday else 0
                patch["start_date"] = (today + timedelta(days=7-today.weekday()+offset)).isoformat()
            elif "明天" in text:
                patch["start_date"] = (date.today() + timedelta(days=1)).isoformat()
        interests = [word for word in ("美食", "历史", "艺术", "自然", "购物", "文化", "亲子") if word in text]
        if interests:
            patch["interests"] = interests
        action = "auto"
        if "酒店" in text and any(word in text for word in ("便宜", "经济", "省钱")):
            action = "hotel_cheaper"
        elif "酒店" in text and any(word in text for word in ("更好", "升级", "豪华")):
            action = "hotel_better"
        elif interests or any(word in text for word in ("景点", "活动", "行程换")):
            action = "activity"
        return patch, action
