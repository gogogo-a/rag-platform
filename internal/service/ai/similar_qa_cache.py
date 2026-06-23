"""
相似问答缓存
负责检索相似问题的历史回答，避免重复推理
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from log import logger
from internal.db.qdrant import qa_qdrant_client
from internal.embedding.embedding_service import embedding_service
from internal.model.thought_chain import ThoughtChainModel
from pkg.constants.constants import (
    ENABLE_QA_CACHE,
    QA_SIMILARITY_THRESHOLD,
    QA_CACHE_TTL
)


class SimilarQACache:
    """
    相似问答缓存（单例模式）
    
    负责：
    - 检索相似问题的历史回答
    - 避免对相同/相似问题重复调用 Agent
    - 节省 Token 和响应时间
    - 支持时间过滤和多结果选择
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化相似问答缓存"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.similarity_threshold = QA_SIMILARITY_THRESHOLD
            self.cache_ttl = QA_CACHE_TTL  # 缓存有效期（秒）
    
    def is_enabled(self) -> bool:
        """
        检查缓存功能是否启用
        
        Returns:
            是否启用
        """
        return ENABLE_QA_CACHE
    
    async def find_similar(
        self,
        question: str,
        user_id: Optional[str] = None,
        skip_cache: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        检索相似问题的历史回答
        
        Args:
            question: 用户问题
            user_id: 用户ID（可选，用于个性化检索）
            skip_cache: 是否跳过缓存（重新回答时使用）
            
        Returns:
            如果找到相似问题，返回：
            {
                "question": 原始问题,
                "answer": 历史答案,
                "thought_chain_id": 思维链ID,
                "similarity": 相似度分数,
                "documents": 引用的文档
            }
            否则返回 None
        """
        if not self.is_enabled() or skip_cache:
            return None
        
        try:
            # 1. 生成问题的 embedding
            question_embedding = embedding_service.encode_query(question)
            
            # 2. 在向量库中检索相似问题
            similar_results = qa_qdrant_client.search_qa_cache(
                embedding=question_embedding,
                top_k=5,
                score_threshold=self.similarity_threshold
            )
            
            if not similar_results:
                return None
            
            # 3. 从多个结果中选择最佳的（考虑时间、点赞数等）
            best_match = await self._select_best_match(similar_results)
            
            if not best_match:
                return None
            
            thought_chain_id = best_match.get("metadata", {}).get("thought_chain_id")
            
            if not thought_chain_id:
                logger.warning("相似问题缺少 thought_chain_id")
                return None
            
            # 4. 从 MongoDB 获取完整的思维链和答案
            thought_chain = await ThoughtChainModel.find_one(
                ThoughtChainModel.uuid == thought_chain_id
            )
            
            if not thought_chain:
                logger.warning(f"思维链不存在: {thought_chain_id}")
                return None
            
            # 5. 检查是否过期
            if self._is_expired(thought_chain.created_at):
                logger.debug(f"缓存已过期: {thought_chain_id}")
                return None
            
            logger.info(f"🎯 命中相似问题缓存: similarity={best_match['score']:.4f}, likes={thought_chain.like_count}")
            
            return {
                "question": best_match["text"],
                "answer": thought_chain.answer,
                "thought_chain_id": thought_chain_id,
                "thought_chain": thought_chain.thought_chain,
                "similarity": best_match["score"],
                "documents": thought_chain.documents_used,
                "like_count": thought_chain.like_count,
                "dislike_count": thought_chain.dislike_count
            }
            
        except Exception as e:
            logger.error(f"检索相似问题失败: {e}", exc_info=True)
            return None
    
    async def _select_best_match(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        从多个相似结果中选择最佳的
        
        选择策略：
        1. 过滤掉过期的
        2. 过滤掉踩数过多的
        3. 按 (相似度 * 0.6 + 点赞权重 * 0.4) 排序
        
        Args:
            results: 向量检索结果列表
            
        Returns:
            最佳匹配结果
        """
        if not results:
            return None
        
        valid_results = []
        
        for result in results:
            thought_chain_id = result.get("metadata", {}).get("thought_chain_id")
            if not thought_chain_id:
                continue
            
            # 从 MongoDB 获取思维链信息
            thought_chain = await ThoughtChainModel.find_one(
                ThoughtChainModel.uuid == thought_chain_id
            )
            
            if not thought_chain:
                continue
            
            # 过滤过期的
            if self._is_expired(thought_chain.created_at):
                continue
            
            # 过滤净踩数过多的（踩数 - 赞数 >= 3 则不使用）
            net_dislike = thought_chain.dislike_count - thought_chain.like_count
            if net_dislike >= 3:
                continue
            
            # 计算综合得分
            similarity_score = result["score"]
            like_weight = min(thought_chain.like_count * 0.05, 0.2)  # 点赞加分，最多 0.2
            dislike_penalty = thought_chain.dislike_count * 0.1  # 踩减分
            
            combined_score = similarity_score * 0.6 + like_weight - dislike_penalty
            
            valid_results.append({
                **result,
                "combined_score": combined_score,
                "thought_chain": thought_chain
            })
        
        if not valid_results:
            return None
        
        # 按综合得分排序
        valid_results.sort(key=lambda x: x["combined_score"], reverse=True)
        
        return valid_results[0]
    
    def _is_expired(self, created_at: datetime) -> bool:
        """
        检查缓存是否过期
        
        Args:
            created_at: 创建时间
            
        Returns:
            是否过期
        """
        if self.cache_ttl <= 0:
            return False  # TTL <= 0 表示永不过期
        
        expiry_time = created_at + timedelta(seconds=self.cache_ttl)
        return datetime.now() > expiry_time
    
    async def delete_cache(self, thought_chain_id: str) -> bool:
        """
        删除指定的 QA 缓存
        
        Args:
            thought_chain_id: 思维链 UUID
            
        Returns:
            是否删除成功
        """
        try:
            # 1. 从向量库删除
            qa_qdrant_client.delete_points([thought_chain_id])
            
            # 2. 更新 MongoDB 中的缓存状态
            thought_chain = await ThoughtChainModel.find_one(
                ThoughtChainModel.uuid == thought_chain_id
            )
            if thought_chain:
                thought_chain.is_cached = False
                thought_chain.vector_id = None
                await thought_chain.save()
            
            logger.info(f"✓ 已删除 QA 缓存: {thought_chain_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除 QA 缓存失败: {e}", exc_info=True)
            return False
    
    async def update_feedback(
        self,
        thought_chain_id: str,
        feedback_type: str,  # "like" 或 "dislike"
        user_id: str = None  # 用户ID，用于防止重复操作
    ) -> Dict[str, Any]:
        """
        更新反馈（点赞/踩）
        
        Args:
            thought_chain_id: 思维链 UUID
            feedback_type: 反馈类型 ("like" 或 "dislike")
            user_id: 用户ID（用于防止重复操作）
            
        Returns:
            更新后的统计信息
        """
        try:
            thought_chain = await ThoughtChainModel.find_one(
                ThoughtChainModel.uuid == thought_chain_id
            )
            
            if not thought_chain:
                return {"success": False, "message": "思维链不存在"}
            
            # 检查用户是否已经反馈过
            if user_id:
                previous_feedback = thought_chain.user_feedbacks.get(user_id)
                
                if previous_feedback == feedback_type:
                    # 相同操作，不允许重复
                    return {
                        "success": False, 
                        "message": "您已经提交过相同的反馈",
                        "like_count": thought_chain.like_count,
                        "dislike_count": thought_chain.dislike_count,
                        "is_cached": thought_chain.is_cached
                    }
                
                if previous_feedback:
                    # 切换反馈：先撤销之前的
                    if previous_feedback == "like":
                        thought_chain.like_count = max(0, thought_chain.like_count - 1)
                    elif previous_feedback == "dislike":
                        thought_chain.dislike_count = max(0, thought_chain.dislike_count - 1)
            
            # 更新新的反馈
            if feedback_type == "like":
                thought_chain.like_count += 1
            elif feedback_type == "dislike":
                thought_chain.dislike_count += 1
            
            # 记录缓存删除状态
            was_cached = thought_chain.is_cached
            cache_deleted = False
            
            # 检查是否需要删除缓存：踩数 - 赞数 >= 3 时自动删除
            net_dislike = thought_chain.dislike_count - thought_chain.like_count
            if net_dislike >= 3 and thought_chain.is_cached:
                await self.delete_cache(thought_chain_id)
                cache_deleted = True
                logger.info(f"⚠️ 净踩数达到阈值({net_dislike})，已自动删除缓存: {thought_chain_id}")
            
            # 记录用户反馈
            if user_id:
                thought_chain.user_feedbacks[user_id] = feedback_type
            
            await thought_chain.save()
            
            return {
                "success": True,
                "like_count": thought_chain.like_count,
                "dislike_count": thought_chain.dislike_count,
                "is_cached": thought_chain.is_cached,
                "was_cached": was_cached,  # 操作前是否已缓存
                "cache_deleted": cache_deleted  # 本次操作是否删除了缓存
            }
            
        except Exception as e:
            logger.error(f"更新反馈失败: {e}", exc_info=True)
            return {"success": False, "message": str(e)}
    
    async def find_similar_batch(
        self,
        questions: List[str],
        user_id: Optional[str] = None
    ) -> List[Optional[Dict[str, Any]]]:
        """
        批量检索相似问题
        
        Args:
            questions: 问题列表
            user_id: 用户ID
            
        Returns:
            相似问题结果列表（与输入顺序对应）
        """
        results = []
        for question in questions:
            result = await self.find_similar(question, user_id)
            results.append(result)
        return results


# 创建单例实例
similar_qa_cache = SimilarQACache()
