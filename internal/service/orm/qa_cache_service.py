"""
QA 缓存管理服务
直接从 Milvus 获取 QA 缓存数据
"""
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from pymilvus import Collection, utility

from log import logger
from internal.model.thought_chain import ThoughtChainModel
from internal.db.milvus import milvus_client
from pkg.constants.constants import MILVUS_QA_COLLECTION_NAME


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
        """
        获取 QA 缓存列表（直接从 Milvus 获取）
        
        Args:
            page: 页码
            page_size: 每页数量
            keyword: 搜索关键词
            
        Returns:
            (message, ret, data)
        """
        try:
            # 检查集合是否存在
            if not utility.has_collection(MILVUS_QA_COLLECTION_NAME):
                return "QA 缓存集合不存在", 0, {"total": 0, "items": []}
            
            collection = Collection(MILVUS_QA_COLLECTION_NAME)
            collection.load()
            
            # 查询所有 QA 缓存
            results = collection.query(
                expr="id >= 0",
                output_fields=["id", "text", "metadata"],
                limit=16384
            )
            
            if not results:
                return "暂无 QA 缓存数据", 0, {"total": 0, "items": []}
            
            # 关键词过滤
            filtered = []
            for item in results:
                text = item.get("text", "")
                metadata = item.get("metadata", {})
                answer_preview = metadata.get("answer_preview", "")
                
                if keyword:
                    if keyword.lower() not in text.lower() and keyword.lower() not in answer_preview.lower():
                        continue
                
                filtered.append(item)
            
            total = len(filtered)
            
            # 按创建时间排序（如果有的话）
            filtered.sort(key=lambda x: x.get("metadata", {}).get("created_at", ""), reverse=True)
            
            # 分页
            start = (page - 1) * page_size
            end = start + page_size
            paged = filtered[start:end]
            
            # 构建返回数据
            cache_list = []
            for item in paged:
                metadata = item.get("metadata", {})
                cache_list.append({
                    "thought_chain_id": metadata.get("thought_chain_id", str(item["id"])),
                    "milvus_id": item["id"],
                    "question": item.get("text", ""),
                    "answer_preview": metadata.get("answer_preview", ""),
                    "created_at": metadata.get("created_at")
                })
            
            data = {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": cache_list
            }
            
            return "查询成功", 0, data
            
        except Exception as e:
            logger.error(f"获取 QA 缓存列表失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None
    
    async def get_cache_detail(self, cache_id: str) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        """
        获取 QA 缓存详情
        
        Args:
            cache_id: 思维链 UUID 或 Milvus ID
            
        Returns:
            (message, ret, data)
        """
        try:
            # 先尝试从 MongoDB 获取完整信息
            item = await ThoughtChainModel.find_one(ThoughtChainModel.uuid == cache_id)
            
            if item:
                data = {
                    "thought_chain_id": item.uuid,
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
                    "milvus_id": item.milvus_id,
                    "created_at": item.created_at.isoformat() if item.created_at else None
                }
                return "查询成功", 0, data
            
            # 如果 MongoDB 没有，尝试从 Milvus 获取基本信息
            if not utility.has_collection(MILVUS_QA_COLLECTION_NAME):
                return "缓存不存在", -2, None
            
            collection = Collection(MILVUS_QA_COLLECTION_NAME)
            collection.load()
            
            # 查询 Milvus
            results = collection.query(
                expr="id >= 0",
                output_fields=["id", "text", "metadata"],
                limit=16384
            )
            
            # 查找匹配的记录
            for record in results:
                metadata = record.get("metadata", {})
                if metadata.get("thought_chain_id") == cache_id or str(record["id"]) == cache_id:
                    data = {
                        "thought_chain_id": metadata.get("thought_chain_id", str(record["id"])),
                        "milvus_id": record["id"],
                        "question": record.get("text", ""),
                        "answer": metadata.get("answer_preview", "（完整答案需从 MongoDB 获取）"),
                        "answer_preview": metadata.get("answer_preview", ""),
                        "created_at": metadata.get("created_at"),
                        "references": []
                    }
                    return "查询成功", 0, data
            
            return "缓存不存在", -2, None
            
        except Exception as e:
            logger.error(f"获取 QA 缓存详情失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None
    
    async def delete_cache(self, cache_id: str) -> Tuple[str, int]:
        """
        删除 QA 缓存（同时删除 MongoDB 和 Milvus）
        
        Args:
            cache_id: 思维链 UUID 或 Milvus ID
            
        Returns:
            (message, ret)
        """
        try:
            # 1. 尝试从 MongoDB 获取并更新
            item = await ThoughtChainModel.find_one(ThoughtChainModel.uuid == cache_id)
            
            milvus_id = None
            if item:
                milvus_id = item.milvus_id
                # 更新 MongoDB（标记为未缓存，保留思维链记录）
                item.is_cached = False
                item.milvus_id = None
                await item.save()
            
            # 2. 从 Milvus 删除
            if milvus_id:
                milvus_client.delete_qa_cache(milvus_id)
                logger.info(f"已从 Milvus 删除 QA 缓存: milvus_id={milvus_id}")
            else:
                # 如果没有 milvus_id，尝试通过 thought_chain_id 删除
                deleted = milvus_client.delete_qa_cache_by_thought_chain_id(cache_id)
                if not deleted:
                    # 尝试将 cache_id 作为 milvus_id 删除
                    try:
                        milvus_id_int = int(cache_id)
                        milvus_client.delete_qa_cache(milvus_id_int)
                        logger.info(f"已从 Milvus 删除 QA 缓存: milvus_id={milvus_id_int}")
                    except ValueError:
                        pass
            
            logger.info(f"QA 缓存已删除: {cache_id}")
            return "删除成功", 0
            
        except Exception as e:
            logger.error(f"删除 QA 缓存失败: {e}", exc_info=True)
            return f"删除失败: {str(e)}", -1


# 单例实例
qa_cache_service = QACacheService()
