"""
Embedding 抽象层 —— 文本转向量。


"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """向量化器抽象基类。"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """单条文本 -> 向量。"""
        ...

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，默认逐条调用。"""
        return [self.embed(t) for t in texts]


class MockEmbedder(BaseEmbedder):
    """
    零依赖的向量化器: 基于字符 n-gram 的 MD5 哈希特征。

    原理:
      - 对中英文分词 token，取 1-gram、2-gram；
      - 每个 n-gram 哈希到固定维度向量中的一个桶并累加；
      - 最后 L2 归一化，使余弦相似度可用。
    这样「浅草寺」「东京美食」等文本在无真实模型时也能按字符重叠检索，
    结果可复现，适合测试与演示。维度固定 256。
    """

    dim = 256

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        for tok in tokens:
            for n in (1, 2):
                for i in range(len(tok) - n + 1):
                    gram = tok[i : i + n]
                    idx = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16) % self.dim
                    vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class BGEM3Embedder(BaseEmbedder):
    """
    真实 BGE-M3 多语言向量化（可选）。

    需要: pip install FlagEmbedding，首次运行会下载 BAAI/bge-m3 权重。
    仅在接受 RAG_EMBEDDING=bge-m3 时懒加载，避免拖慢 Mock 演示。
    """

    dim = 1024  # BGE-M3 dense 向量维度

    def __init__(self) -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover - 依赖未安装
            raise ImportError(
                "使用 BGE-M3 需先安装: pip install FlagEmbedding"
            ) from exc

        self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

    def embed(self, text: str) -> list[float]:
        output = self._model.encode([text])
        # BGEM3 返回 dense_vecs(sparse/dense/colbert 三视图)，此处用 dense 向量
        return output["dense_vecs"][0].tolist()


def get_embedder(name: str) -> BaseEmbedder:
    """工厂函数: 按配置名返回向量化器实例。"""
    if name == "bge-m3":
        return BGEM3Embedder()
    return MockEmbedder()