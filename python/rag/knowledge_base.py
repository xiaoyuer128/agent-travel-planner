"""
RAG 知识库 —— 目的地攻略 / 景点资料的门面（Facade）。

职责:
  - 内置若干目的地攻略文档（Mock 数据源，对应推荐候选城市）；
  - `RAGRetriever` 串起 Embedder + VectorStore，完成「文档 → 向量 → 入库 → 检索」；
  - `rag_search()` 是对外统一检索入口，供各 Agent 当作工具调用；
  - `RAGTool` 是面向多 Agent 的标准工具封装，描述字段可用于 Function Calling。

"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from loguru import logger

from config.settings import settings

from .embeddings import get_embedder
from .vector_store import get_vector_store


@dataclass
class KnowledgeDoc:
    """知识库中的一个文档切片。"""

    id: str
    city: str
    title: str
    content: str


# ── Mock 知识源: 目的地攻略 / 景点资料 ──────────────────────
# 生产环境中这些文档通常来自数据库 / 爬虫 / 内容平台。
from domestic import GUIDES
KB_DOCUMENTS = [KnowledgeDoc(id=d["id"], city=d["city"], title=d["title"], content=d["text"]) for d in GUIDES]


KNOWN_CITIES: frozenset[str] = frozenset(doc.city for doc in KB_DOCUMENTS)


def has_guide(city: str) -> bool:
    """判断知识库是否内置该城市的攻略文档。"""
    return city in KNOWN_CITIES


class RAGRetriever:
    """RAG 检索器: 文档向量化入库 + Top-K 相似度检索。"""

    def __init__(self) -> None:
        self.embedder = get_embedder(settings.RAG_EMBEDDING)
        self.top_k = settings.RAG_TOP_K
        dim = getattr(self.embedder, "dim", 256)
        self.store = get_vector_store(
            settings.RAG_STORE,
            dim=dim,
            uri=settings.MILVUS_URI,
            collection=settings.MILVUS_COLLECTION,
        )
        self._index()

    def _index(self) -> None:
        """把内置文档向量化并写入向量库。"""
        ids = [doc.id for doc in KB_DOCUMENTS]
        texts = [f"{doc.city} | {doc.title} | {doc.content}" for doc in KB_DOCUMENTS]
        vectors = self.embedder.embed_many(texts)
        self.store.add(ids, vectors, [doc.content for doc in KB_DOCUMENTS])
        logger.info(f"[RAG] 已索引 {len(KB_DOCUMENTS)} 篇目的地攻略文档")

    def retrieve(self, query: str, top_k: int | None = None) -> list[str]:
        """按自然语言查询返回 Top-K 攻略片段（纯文本）。"""
        query_vector = self.embedder.embed(query)
        hits = self.store.search(query_vector, top_k or self.top_k)
        return [hit.text for hit in hits]


@lru_cache(maxsize=1)
def get_retriever() -> RAGRetriever:
    """懒加载单例: 全局共享同一份索引，避免重复向量化。"""
    return RAGRetriever()


def rag_search(query: str, top_k: int | None = None) -> list[str]:
    """
    Agent 工具入口: 检索目的地攻略 / 景点资料。

    检索失败时优雅降级返回空列表，不影响主流程。
    """
    try:
        return get_retriever().retrieve(query, top_k)
    except Exception as exc:  # noqa: BLE001 - 降级兜底
        logger.warning(f"[RAG] 检索失败，降级返回空: {exc}")
        return []


class RAGTool:
    """
    标准工具封装: 把 RAG 知识库暴露给多 Agent。
    name / description 字段可直接映射到 Function Calling / Tool 定义。
    """

    name = "destination_knowledge_search"
    description = "检索目的地攻略与景点资料，为行程规划补充上下文"

    def __call__(self, query: str, top_k: int | None = None) -> list[str]:
        return rag_search(query, top_k)