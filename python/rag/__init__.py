"""
RAG 知识库包 —— 把目的地攻略 / 景点资料向量化并封装为可检索工具。

设计目标:
  - Mock 优先、真实组件可选: 默认使用零依赖的字符 n-gram 向量化 + 内存检索，
    无需安装任何重依赖即可运行演示；通过环境变量切换到 BGE-M3 + Milvus。
  - 面向 Agent 的工具接口: `rag_search()` 供各 Agent 直接调用，检索结果
    拼入 `TravelPlanState.rag_context` 作为上下文补充。
"""

from .knowledge_base import RAGRetriever, RAGTool, get_retriever, has_guide, rag_search

__all__ = ["RAGRetriever", "RAGTool", "get_retriever", "rag_search", "has_guide"]