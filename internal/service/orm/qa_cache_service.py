"""
QA 缓存管理服务
"""
from typing import Tuple, Optional, Dict, Any

from log import logger
from internal.model.qa_cache import QACacheModel
from internal.model.thought_chain import ThoughtChainModel
from internal.db.qdrant import qa_qdrant_client


class QACacheService:
    """QA 缓存管理服务（单例模式）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_cache_list(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None
    ) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        try:
            query: Dict[str, Any] = {"is_cached": True}
            if keyword:
                query["$or"] = [
                    {"question": {"$regex": keyword, "$options": "i"}},
                    {"answer": {"$regex": keyword, "$options": "i"}},
                ]

            total = await ThoughtChainModel.find(query).count()
            rows = (
                await ThoughtChainModel.find(query)
                .sort(-ThoughtChainModel.created_at)
                .skip((page - 1) * page_size)
                .limit(page_size)
                .to_list()
            )

            items = []
            for row in rows:
                items.append({
                    "thought_chain_id": row.uuid,
                    "vector_id": row.vector_id or row.uuid,
                    "question": row.question,
                    "answer_preview": row.answer[:160],
                    "created_at": row.created_at.isoformat() if row.created_at else None
                })

            if total == 0:
                return await self._get_cache_list_from_mongodb(page, page_size, keyword)

            return "查询成功", 0, {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items
            }

        except Exception as e:
            logger.error(f"获取 QA 缓存列表失败: {e}", exc_info=True)
            return await self._get_cache_list_from_mongodb(page, page_size, keyword)

    async def _get_cache_list_from_mongodb(
        self,
        page: int,
        page_size: int,
        keyword: Optional[str]
    ) -> Tuple[str, int, Dict[str, Any]]:
        query: Dict[str, Any] = {"is_active": True}
        if keyword:
            query["$or"] = [
                {"question": {"$regex": keyword, "$options": "i"}},
                {"answer": {"$regex": keyword, "$options": "i"}},
            ]

        total = await QACacheModel.find(query).count()
        rows = (
            await QACacheModel.find(query)
            .sort(-QACacheModel.update_at)
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list()
        )

        items = []
        for row in rows:
            thought_chain_id = row.metadata.get("thought_chain_id") if row.metadata else None
            items.append({
                "thought_chain_id": thought_chain_id or row.uuid,
                "vector_id": row.uuid,
                "question": row.question,
                "answer_preview": row.answer[:160],
                "created_at": row.create_at.isoformat() if row.create_at else None
            })

        return "查询成功", 0, {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items
        }

    async def get_cache_detail(self, cache_id: str) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        try:
            item = await ThoughtChainModel.find_one(ThoughtChainModel.uuid == cache_id)
            if not item:
                item = await ThoughtChainModel.find_one(ThoughtChainModel.vector_id == cache_id)

            if not item:
                return "缓存不存在", -2, None

            data = {
                "thought_chain_id": item.uuid,
                "vector_id": item.vector_id or item.uuid,
                "session_id": item.session_id,
                "message_id": item.message_id,
                "question": item.question,
                "answer": item.answer,
                "thought_chain": item.thought_chain,
                "references": item.documents_used,
                "user_id": item.user_id,
                "model_name": item.model_name,
                "total_steps": item.total_steps,
                "like_count": item.like_count,
                "dislike_count": item.dislike_count,
                "is_cached": item.is_cached,
                "created_at": item.created_at.isoformat() if item.created_at else None
            }
            return "查询成功", 0, data

        except Exception as e:
            logger.error(f"获取 QA 缓存详情失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None

    async def delete_cache(self, cache_id: str) -> Tuple[str, int]:
        try:
            item = await ThoughtChainModel.find_one(ThoughtChainModel.uuid == cache_id)
            if not item:
                item = await ThoughtChainModel.find_one(ThoughtChainModel.vector_id == cache_id)

            delete_ids = [cache_id]
            if item:
                delete_ids.append(item.uuid)
                if item.vector_id:
                    delete_ids.append(item.vector_id)
                item.is_cached = False
                item.vector_id = None
                await item.save()

            qa_qdrant_client.delete_points(list(dict.fromkeys(delete_ids)))
            logger.info(f"QA 缓存已删除: {cache_id}")
            return "删除成功", 0

        except Exception as e:
            logger.error(f"删除 QA 缓存失败: {e}", exc_info=True)
            return f"删除失败: {str(e)}", -1


qa_cache_service = QACacheService()
