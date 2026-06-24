"""RAG 检索服务。"""
from typing import Any, Dict, List, Optional
import logging
import re

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

    def _tokenize_for_bm25(self, text: str) -> List[str]:
        return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+", (text or "").lower())

    def _result_key(self, result: Dict[str, Any]) -> Any:
        metadata = result.get("metadata") or {}
        document_uuid = metadata.get("document_uuid")
        chunk_index = metadata.get("chunk_index")
        if document_uuid is not None and chunk_index is not None:
            return document_uuid, chunk_index
        return result.get("text", "")

    def _matches_metadata(self, result: Dict[str, Any], filter_metadata: Optional[Dict[str, Any]]) -> bool:
        if not filter_metadata:
            return True
        metadata = result.get("metadata") or {}
        return all(metadata.get(key) == value for key, value in filter_metadata.items())

    def _keyword_search(
        self,
        query: str,
        top_k: int,
        filter_metadata: Optional[Dict[str, Any]] = None,
        user_permission: int = 0,
    ) -> List[Dict[str, Any]]:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25 未安装，已跳过关键词检索")
            return []

        try:
            points = qdrant_client.scroll_all(collection_name=self.collection_name)
        except Exception as exc:
            logger.warning("关键词检索读取文档失败，已跳过 BM25: %s", exc)
            return []
        documents: List[Dict[str, Any]] = []
        tokenized_corpus: List[List[str]] = []
        for point in points:
            payload = point.payload or {}
            metadata = payload.get("metadata") or {}
            if user_permission == 0 and metadata.get("permission", 0) == 1:
                continue
            result = {
                "text": payload.get("text", ""),
                "metadata": metadata,
            }
            if not self._matches_metadata(result, filter_metadata):
                continue
            tokens = self._tokenize_for_bm25(result["text"])
            if not tokens:
                continue
            documents.append(result)
            tokenized_corpus.append(tokens)

        query_tokens = self._tokenize_for_bm25(query)
        if not documents or not query_tokens:
            return []

        scores = BM25Okapi(tokenized_corpus).get_scores(query_tokens)
        query_token_set = set(query_tokens)
        ranked_indexes = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        results: List[Dict[str, Any]] = []
        for index in ranked_indexes[:top_k]:
            if not query_token_set.intersection(tokenized_corpus[index]):
                continue
            item = dict(documents[index])
            item["bm25_score"] = float(scores[index])
            results.append(item)
        return results

    def _rrf_fuse(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not keyword_results:
            return vector_results

        fused: Dict[Any, Dict[str, Any]] = {}
        for source_results in (vector_results, keyword_results):
            for rank, result in enumerate(source_results, 1):
                key = self._result_key(result)
                item = fused.setdefault(key, dict(result))
                item["rrf_score"] = item.get("rrf_score", 0.0) + 1.0 / (60 + rank)
                if "vector_score" in result:
                    item["vector_score"] = result["vector_score"]
                    item["score"] = result.get("score", result["vector_score"])
                if "bm25_score" in result:
                    item["bm25_score"] = result["bm25_score"]

        return sorted(fused.values(), key=lambda item: item.get("rrf_score", 0.0), reverse=True)

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
        vector_results = qdrant_client.search_documents(query_embedding, top_k=top_k * 2, user_permission=user_permission)
        vector_results = [
            result for result in vector_results
            if self._matches_metadata(result, filter_metadata)
        ]
        keyword_results = self._keyword_search(
            query=query,
            top_k=top_k * 2,
            filter_metadata=filter_metadata,
            user_permission=user_permission,
        )
        results = self._rrf_fuse(vector_results, keyword_results)

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
