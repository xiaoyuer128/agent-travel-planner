"""
全局配置管理 —— 通过环境变量加载，绝不硬编码密钥。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    BUDGET_MAX_RETRIES: int = int(os.getenv("BUDGET_MAX_RETRIES", "3"))
    PARALLEL_TIMEOUT: int = int(os.getenv("PARALLEL_TIMEOUT", "30"))

    # ── RAG 知识库 ──
    # RAG_EMBEDDING: mock(零依赖字符n-gram) | bge-m3(需 pip install FlagEmbedding)
    RAG_EMBEDDING: str = os.getenv("RAG_EMBEDDING", "mock")
    # RAG_STORE: memory(内存向量检索) | milvus(需本机运行 Milvus 服务)
    RAG_STORE: str = os.getenv("RAG_STORE", "memory")
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "3"))
    MILVUS_URI: str = os.getenv("MILVUS_URI", "http://localhost:19530")
    MILVUS_COLLECTION: str = os.getenv("MILVUS_COLLECTION", "travel_guide")

    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
