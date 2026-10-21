"""
LLM 客户端 —— 封装 LLM 调用（DeepSeek / OpenAI 兼容接口），统一 JSON 解析与 mock 降级。

"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from loguru import logger

from config.settings import settings


async def chat(
    messages: list[dict],
    temperature: Optional[float] = None,
    json_mode: bool = False,
) -> str:
    """调用 LLM，返回文本响应。mock 模式返回空字符串。"""
    if settings.LLM_PROVIDER == "mock":
        return ""

    import httpx

    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def chat_json(messages: list[dict], temperature: Optional[float] = None) -> Optional[dict]:
    """调用 LLM 并解析出 JSON 对象。mock 模式或解析失败返回 None。"""
    text = await chat(messages, temperature=temperature, json_mode=True)
    if not text:
        return None
    return extract_json(text)


def extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出中稳健提取 JSON 对象（兼容 markdown 代码块包裹）。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                return None
    return None