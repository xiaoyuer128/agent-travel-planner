"""
RAG 知识库单元测试 —— 覆盖 Mock 向量化、内存检索、工具封装与 Agent 接入。

运行: cd python && python -m pytest tests/test_rag.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag import get_retriever, rag_search
from rag.embeddings import MockEmbedder
from rag.vector_store import InMemoryVectorStore, SearchHit


# ━━━━━━ Embedding ━━━━━━


def test_mock_embedder_is_deterministic():
    emb = MockEmbedder()
    v1 = emb.embed("杭州 西湖 美食")
    v2 = emb.embed("杭州 西湖 美食")
    assert len(v1) == MockEmbedder.dim
    assert v1 == v2


def test_mock_embedder_normalized():
    emb = MockEmbedder()
    vec = emb.embed("杭州旅游攻略")
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6


# ━━━━━━ VectorStore ━━━━━━


def test_inmemory_store_search_topk():
    emb = MockEmbedder()
    store = InMemoryVectorStore()
    store.add(
        ids=["a", "b"],
        vectors=emb.embed_many(["杭州西湖攻略", "三亚水上市场攻略"]),
        texts=["杭州的西湖", "三亚的水上市场"],
    )
    hits = store.search(emb.embed("杭州 西湖"), top_k=1)
    assert len(hits) == 1
    assert hits[0].id == "a"
    assert "西湖" in hits[0].text


# ━━━━━━ RAG 检索门面 ━━━━━━


def test_rag_search_returns_relevant_hits():
    hits = rag_search("杭州 西湖 美食")
    assert hits
    assert any("西湖" in h or "杭州" in h for h in hits)


def test_rag_retriever_singleton():
    assert get_retriever() is get_retriever()


# ━━━━━━ Agent 接入 ━━━━━━


@pytest.mark.asyncio
async def test_destination_agent_fills_rag_context():
    from agents import DestinationAgent
    from models.schemas import PlanningState, TravelPlanState, TravelStyle, UserPreferences

    prefs = UserPreferences(
        budget=15000,
        travel_style=TravelStyle.COMFORT,
        departure_city="北京",
        start_date="2026-05-01",
        end_date="2026-05-05",
    )
    state = TravelPlanState(preferences=prefs, state=PlanningState.RECOMMENDING_DESTINATIONS)
    result = await DestinationAgent().run(state)
    assert result.rag_context, "目的地 Agent 应通过 RAG 检索到攻略上下文"
    assert all(isinstance(c, str) for c in result.rag_context)