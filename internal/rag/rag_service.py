"""RAG 检索服务。"""
from typing import Any, Dict, List, Optional
import logging

from internal.db.qdrant import qdrant_client
from internal.rag.dedup import deduplicate_results
from internal.embedding.embedding_service import embedding_service
from internal.reranker.reranker_service import reranker_service
from internal.monitor import performance_monitor
from pkg.constants.constants import QDRANT_COLLECTION_NAME
from pkg.model_list import BGE_LARGE_ZH_V1_5, BGE_RERANKER_V2_M3

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 检索服务。"""

    def __init__(
        self,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        reranker_model: Optional[str] = None,
        top_k: int = 5,
        use_reranker: bool = True,
    ):
        self.collection_name = collection_name or QDRANT_COLLECTION_NAME
        self.embedding_model = embedding_model or BGE_LARGE_ZH_V1_5.name
        self.reranker_model = reranker_model or BGE_RERANKER_V2_M3.name
        self.top_k = top_k
        self.use_reranker = use_reranker
        self.reranker = reranker_service if use_reranker else None

    def initialize(self):
        qdrant_client.ensure_collection(self.collection_name)

    def _deduplicate_results(
        self,
        results: List[Dict[str, Any]],
        score_diff_threshold: float = 0.02,
        text_similarity_threshold: float = 0.88,
        target_count: int = 5,
    ) -> List[Dict[str, Any]]:
        return deduplicate_results(
            results=results,
            score_diff_threshold=score_diff_threshold,
            text_similarity_threshold=text_similarity_threshold,
            target_count=target_count,
        )

    @performance_monitor('vector_search', operation_name='向量检索+Rerank', include_args=True, include_result=True)
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        use_reranker: Optional[bool] = None,
        rerank_top_k: Optional[int] = None,
        rerank_score_threshold: float = -100.0,
        user_permission: int = 0,
    ) -> List[Dict[str, Any]]:
        top_k = int(top_k or self.top_k)
        rerank_top_k = int(rerank_top_k or top_k)
        use_reranker = self.use_reranker if use_reranker is None else use_reranker

        query_embedding = embedding_service.encode_query(query, normalize=True)
        results = qdrant_client.search_documents(query_embedding, top_k=top_k * 2, user_permission=user_permission)

        if filter_metadata:
            results = [
                result for result in results
                if all(result.get("metadata", {}).get(key) == value for key, value in filter_metadata.items())
            ]

        if use_reranker and self.reranker and results:
            try:
                reranked = self.reranker.rerank(
                    query=query,
                    documents=results,
                    top_k=rerank_top_k * 2,
                    score_threshold=rerank_score_threshold,
                )
                return self._deduplicate_results(reranked, target_count=rerank_top_k)
            except Exception as exc:
                logger.warning("Reranker 不可用，已使用向量检索结果: %s", exc)

        return self._deduplicate_results(results, target_count=rerank_top_k)

    def get_context_for_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        max_context_length: int = 2000,
        use_reranker: Optional[bool] = None,
        rerank_score_threshold: float = 0.0,
    ) -> str:
        results = self.search(
            query,
            top_k=top_k,
            use_reranker=use_reranker,
            rerank_score_threshold=rerank_score_threshold,
        )
        context_parts = []
        current_length = 0
        for index, result in enumerate(results, 1):
            text = result["text"]
            source = result.get("metadata", {}).get("filename", "未知来源")
            part = f"[文档{index} - {source}]\n{text}\n"
            if current_length + len(part) > max_context_length:
                break
            context_parts.append(part)
            current_length += len(part)
        return "\n".join(context_parts)

    def get_collection_stats(self) -> Dict[str, Any]:
        return {
            "collection_name": self.collection_name,
            "embedding_model": self.embedding_model,
            "reranker_model": self.reranker_model if self.use_reranker else None,
            "top_k": self.top_k,
            "points_count": qdrant_client.get_collection_count(self.collection_name),
        }


_rag_service_instance = None


def get_rag_service():
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService(top_k=5, use_reranker=True)
    return _rag_service_instance


class _RAGServiceProxy:
    def __getattr__(self, name):
        return getattr(get_rag_service(), name)


rag_service = _RAGServiceProxy()
