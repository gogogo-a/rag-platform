"""
Qdrant 向量数据库连接
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from log import logger
from pkg.constants.constants import (
    QDRANT_COLLECTION_NAME,
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_QA_COLLECTION_NAME,
    VECTOR_DIMENSION,
)


class QdrantVectorClient:
    """统一的 Qdrant 向量客户端。"""

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        collection_name: str = QDRANT_COLLECTION_NAME,
        dimension: int = VECTOR_DIMENSION,
    ):
        self.client = client or QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.collection_name = collection_name
        self.dimension = dimension

    def ensure_collection(self, collection_name: Optional[str] = None, dimension: Optional[int] = None) -> None:
        name = collection_name or self.collection_name
        size = dimension or self.dimension
        collections = {item.name for item in self.client.get_collections().collections}
        if name not in collections:
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
            )

    def _document_point_id(self, metadata: Dict[str, Any], index: int) -> str:
        document_uuid = metadata.get("document_uuid") or str(uuid.uuid4())
        chunk_index = metadata.get("chunk_index", index)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"document:{document_uuid}:{chunk_index}"))

    def upsert_documents(
        self,
        embeddings: Iterable[Any],
        texts: List[str],
        metadata: List[Dict[str, Any]],
        collection_name: Optional[str] = None,
    ) -> List[str]:
        name = collection_name or self.collection_name
        self.ensure_collection(name)

        points: List[PointStruct] = []
        point_ids: List[str] = []
        for index, embedding in enumerate(embeddings):
            meta = metadata[index]
            point_id = self._document_point_id(meta, index)
            vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": texts[index],
                        "metadata": meta,
                    },
                )
            )
            point_ids.append(point_id)

        if points:
            self.client.upsert(collection_name=name, points=points)
        return point_ids

    def upsert_qa_cache(
        self,
        embedding: Any,
        question: str,
        metadata: Dict[str, Any],
        collection_name: str = QDRANT_QA_COLLECTION_NAME,
    ) -> str:
        self.ensure_collection(collection_name)
        point_id = metadata.get("thought_chain_id") or str(uuid.uuid4())
        vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        self.client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"text": question, "metadata": metadata},
                )
            ],
        )
        return point_id

    def search(
        self,
        embedding: Any,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        query_filter: Optional[Filter] = None,
        score_threshold: Optional[float] = None,
    ):
        name = collection_name or self.collection_name
        vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        limit = max(int(top_k), 1)
        if hasattr(self.client, "search"):
            return self.client.search(
                collection_name=name,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=score_threshold,
            )
        response = self.client.query_points(
            collection_name=name,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            score_threshold=score_threshold,
        )
        return response.points

    def search_documents(self, embedding: Any, top_k: int = 5, user_permission: int = 0):
        limit = max(top_k * 3, top_k)
        hits = self.search(embedding, top_k=limit)
        results = []
        for hit in hits:
            payload = hit.payload or {}
            metadata = payload.get("metadata") or {}
            if user_permission == 0 and metadata.get("permission", 0) == 1:
                continue
            results.append({
                "text": payload.get("text", ""),
                "metadata": metadata,
                "vector_score": float(hit.score),
                "score": float(hit.score),
            })
            if len(results) >= top_k:
                break
        return results

    def search_qa_cache(self, embedding: Any, top_k: int = 5, score_threshold: Optional[float] = None):
        try:
            hits = self.search(
                embedding,
                top_k=top_k,
                collection_name=QDRANT_QA_COLLECTION_NAME,
                score_threshold=score_threshold,
            )
        except Exception as e:
            logger.warning(f"问答缓存检索失败: {e}")
            return []

        return [
            {
                "id": str(hit.id),
                "text": (hit.payload or {}).get("text", ""),
                "metadata": (hit.payload or {}).get("metadata", {}),
                "score": float(hit.score),
            }
            for hit in hits
        ]

    def count_by_document_uuid(self, document_uuid: str, collection_name: Optional[str] = None) -> int:
        name = collection_name or self.collection_name
        count = 0
        offset = None
        flt = Filter(
            must=[
                FieldCondition(
                    key="metadata.document_uuid",
                    match=MatchValue(value=document_uuid),
                )
            ]
        )
        while True:
            points, offset = self.client.scroll(
                collection_name=name,
                scroll_filter=flt,
                limit=256,
                with_payload=False,
                with_vectors=False,
                offset=offset,
            )
            count += len(points)
            if offset is None:
                return count

    def delete_by_document_uuid(self, document_uuid: str, collection_name: Optional[str] = None) -> None:
        name = collection_name or self.collection_name
        self.client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="metadata.document_uuid",
                        match=MatchValue(value=document_uuid),
                    )
                ]
            ),
        )

    def delete_points(self, ids: List[str], collection_name: Optional[str] = None) -> None:
        if not ids:
            return
        name = collection_name or self.collection_name
        self.client.delete(collection_name=name, points_selector=PointIdsList(points=ids))

    def scroll_all(
        self,
        collection_name: Optional[str] = None,
        limit: int = 16384,
        with_vectors: bool = False,
    ):
        name = collection_name or self.collection_name
        points, _ = self.client.scroll(
            collection_name=name,
            limit=limit,
            with_payload=True,
            with_vectors=with_vectors,
        )
        return points

    def get_collection_count(self, collection_name: Optional[str] = None) -> int:
        name = collection_name or self.collection_name
        try:
            info = self.client.get_collection(name)
            return int(info.points_count or 0)
        except Exception:
            return 0


qdrant_client = QdrantVectorClient()
qa_qdrant_client = QdrantVectorClient(collection_name=QDRANT_QA_COLLECTION_NAME)
