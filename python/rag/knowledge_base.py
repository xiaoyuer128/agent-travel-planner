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
KB_DOCUMENTS: list[KnowledgeDoc] = [
    KnowledgeDoc(
        id="tokyo-1",
        city="东京",
        title="东京景点攻略",
        content="浅草寺是东京最古老的寺庙，雷门与仲见世商店街值得一逛；涩谷十字路口是世界最繁忙路口，"
        "晚上可去新宿歌舞伎町感受夜生活；明治神宫适合清晨散步，门票免费。",
    ),
    KnowledgeDoc(
        id="tokyo-2",
        city="东京",
        title="东京美食推荐",
        content="筑地市场适合海鲜早餐，寿司与海胆饭是招牌；居酒屋体验可品尝烧鸟和清酒；"
        "秋叶原动漫街上能找到主题咖啡店。预算方面，东京整体消费偏高，属高价目的地。",
    ),
    KnowledgeDoc(
        id="bangkok-1",
        city="曼谷",
        title="曼谷景点攻略",
        content="大皇宫与卧佛寺是曼谷必去的文化地标，注意着装要求；水上市场适合体验当地水上贸易；"
        "湄南河夜游可欣赏河畔夜景。曼谷消费低廉，是性价比极高的目的地。",
    ),
    KnowledgeDoc(
        id="bangkok-2",
        city="曼谷",
        title="曼谷美食推荐",
        content="考山路是背包客聚集地，小吃物美价廉；路边摊美食之旅可品尝冬阴功、芒果糯米饭；"
        "泰式按摩价格亲民，适合行程中穿插放松。",
    ),
    KnowledgeDoc(
        id="paris-1",
        city="巴黎",
        title="巴黎景点攻略",
        content="埃菲尔铁塔与卢浮宫是巴黎标志，卢浮宫周二闭馆需提前预约；香榭丽舍大街适合购物，"
        "蒙马特高地可俯瞰巴黎全景。巴黎为高价目的地，安全评分中等。",
    ),
    KnowledgeDoc(
        id="chiangmai-1",
        city="清迈",
        title="清迈景点攻略",
        content="清迈是兰纳文化古城，双龙寺坐落于素贴山可俯瞰全城；古城内寺庙密集适合徒步；"
        "周末夜市与夜间动物园是亲子与休闲的好选择。消费低廉，节奏宁静。",
    ),
    KnowledgeDoc(
        id="seoul-1",
        city="首尔",
        title="首尔景点攻略",
        content="景福宫与北村韩屋村展现传统韩国；明洞是购物与美妆天堂；南山塔适合看夜景，"
        "挂同心锁是经典体验。首尔消费中等，无需签证可免签入境。",
    ),
    KnowledgeDoc(
        id="osaka-1",
        city="大阪",
        title="大阪景点攻略",
        content="大阪城是地标性城堡，樱花季尤其壮观；道顿堀是美食与招牌文化的代表，可品尝章鱼烧；"
        "环球影城适合家庭游；黑门市场是海鲜爱好者的天堂。大阪被誉为日本的厨房。",
    ),
]


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