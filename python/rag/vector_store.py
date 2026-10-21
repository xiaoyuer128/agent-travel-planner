"""
向量存储抽象层 —— 保存向量并支持 Top-K 相似度检索。


"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchHit:
    """一次检索命中的片段。"""

    id: str
    score: float
    text: str


class BaseVectorStore(ABC):
    """向量存储抽象基类。"""

    @abstractmethod
    def add(self, ids: list[str], vectors: list[list[float]], texts: list[str]) -> None:
        """批量写入 (id, 向量, 原文)。"""
        ...

    @abstractmethod
    def search(self, query_vector: list[float], top_k: int) -> list[SearchHit]:
        """按相似度检索 Top-K。"""
        ...


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度。向量已 L2 归一化，点积即余弦值（∈[-1,1]）。"""
    return sum(x * y for x, y in zip(a, b))


class InMemoryVectorStore(BaseVectorStore):
    """内存向量存储（默认，零依赖）。"""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._texts: list[str] = []

    def add(self, ids: list[str], vectors: list[list[float]], texts: list[str]) -> None:
        for i, v, t in zip(ids, vectors, texts):
            self._ids.append(i)
            self._vectors.append(v)
            self._texts.append(t)

    def search(self, query_vector: list[float], top_k: int) -> list[SearchHit]:
        scored = [(self._cosine_against(query_vector, i), i) for i in range(len(self._ids))]
        scored.sort(key=lambda x: -x[0])
        return [
            SearchHit(id=self._ids[i], score=round(sim, 4), text=self._texts[i])
            for sim, i in scored[:top_k]
        ]

    def _cosine_against(self, vec: list[float], idx: int) -> float:
        stored = self._vectors[idx]
        return sum(a * b for a, b in zip(vec, stored))


class MilvusVectorStore(BaseVectorStore):
    """
    Milvus 向量库实现（可选，生产级）。

    需要: 本机运行 Milvus 服务（RAG_STORE=milvus），且安装 pymilvus。
    pip install pymilvus==2.4.x
    """

    def __init__(self, uri: str, collection: str, dim: int) -> None:
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
        except ImportError as exc:  # pragma: no cover - 依赖未安装
            raise ImportError(
                "使用 Milvus 需先安装: pip install pymilvus"
            ) from exc

        self._uri = uri
        self._collection_name = collection
        self._dim = dim
        self._pc = connections.connect(alias="default", uri=uri)

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2048),
        ]
        schema = CollectionSchema(fields, description="travel guide knowledge")
        if not utility.has_collection(collection):
            self._collection = Collection(collection, schema=schema)
            self._collection.create_index(
                field_name="vector",
                index_params={"index_type": "IVF_FLAT", "metric_type": "IP", "params": {"nlist": 128}},
            )
        else:
            self._collection = Collection(collection)
        self._collection.load()

    def add(self, ids: list[str], vectors: list[list[float]], texts: list[str]) -> None:
        self._collection.insert([ids, vectors, texts])
        self._collection.flush()

    def search(self, query_vector: list[float], top_k: int) -> list[SearchHit]:
        res = self._collection.search(
            data=[query_vector],
            anns_field="vector",
            param={"metric_type": "IP", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=["id", "text"],
        )
        hits: list[SearchHit] = []
        for r in res[0]:
            hits.append(
                SearchHit(id=r.entity.get("id"), score=round(float(r.distance), 4), text=r.entity.get("text"))
            )
        return hits


def get_vector_store(name: str, dim: int = 256, uri: str = "", collection: str = "") -> BaseVectorStore:
    """工厂函数: 按配置名返回向量存储实例。"""
    if name == "milvus":
        return MilvusVectorStore(uri=uri, collection=collection, dim=dim)
    return InMemoryVectorStore()