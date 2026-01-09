"""
思维链存储
负责存储和检索 Agent 的完整推理过程
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid as uuid_module

from log import logger
from internal.model.thought_chain import ThoughtChainModel
from internal.db.milvus import milvus_client
from internal.embedding.embedding_service import embedding_service
from pkg.constants.constants import ENABLE_QA_CACHE


class ThoughtChainStore:
    """
    思维链存储（单例模式）
    
    负责存储 Agent 的完整推理过程，包括：
    - 问题
    - 思考步骤（Thought）
    - 动作步骤（Action）
    - 观察结果（Observation）
    - 最终答案
    - 引用的文档
    
    同时将问题的 embedding 存储到 Milvus，用于相似问题检索
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
    
    def build_thought_chain(
        self,
        thoughts: List[str],
        actions: List[str],
        observations: List[str]
    ) -> List[Dict[str, Any]]:
        """
        构建思维链数据结构
        
        Args:
            thoughts: 思考步骤列表
            actions: 动作步骤列表
            observations: 观察结果列表
            
        Returns:
            格式化的思维链列表
        """
        chain = []
        step = 1
        
        # 交错合并 thought, action, observation
        max_len = max(len(thoughts), len(actions), len(observations))
        
        for i in range(max_len):
            if i < len(thoughts) and thoughts[i]:
                chain.append({
                    "step": step,
                    "type": "thought",
                    "content": thoughts[i]
                })
                step += 1
            
            if i < len(actions) and actions[i]:
                chain.append({
                    "step": step,
                    "type": "action",
                    "content": actions[i]
                })
                step += 1
            
            if i < len(observations) and observations[i]:
                chain.append({
                    "step": step,
                    "type": "observation",
                    "content": observations[i]
                })
                step += 1
        
        return chain
    
    async def save_chain(
        self,
        session_id: str,
        question: str,
        answer: str,
        thoughts: List[str],
        actions: List[str],
        observations: List[str],
        documents_used: List[Dict[str, str]],
        user_id: Optional[str] = None,
        message_id: Optional[str] = None,
        model_name: Optional[str] = None,
        should_cache: Optional[bool] = None
    ) -> Optional[str]:
        """
        保存思维链到 MongoDB 和 Milvus
        
        Args:
            session_id: 会话ID
            question: 用户问题
            answer: AI 回答
            thoughts: 思考步骤列表
            actions: 动作步骤列表
            observations: 观察结果列表
            documents_used: 引用的文档列表 [{uuid, name}]
            user_id: 用户ID
            message_id: 关联的消息ID
            model_name: 使用的模型名称
            should_cache: 是否缓存到 QA 库（由评估 AI 决定）
            
        Returns:
            保存的思维链UUID，失败返回 None
        """
        try:
            # 1. 构建思维链
            chain = self.build_thought_chain(thoughts, actions, observations)
            
            # 2. 保存到 MongoDB（思维链始终保存）
            thought_chain_model = ThoughtChainModel(
                uuid=str(uuid_module.uuid4()),
                session_id=session_id,
                message_id=message_id,
                question=question,
                answer=answer,
                thought_chain=chain,
                documents_used=documents_used,
                user_id=user_id,
                model_name=model_name,
                total_steps=len(chain),
                created_at=datetime.now()
            )
            
            await thought_chain_model.insert()
            
            # 3. 根据评估结果决定是否保存到 Milvus QA 缓存
            if ENABLE_QA_CACHE and should_cache:
                milvus_id = await self._save_to_milvus(
                    thought_chain_id=thought_chain_model.uuid,
                    question=question,
                    answer=answer,
                    session_id=session_id,
                    user_id=user_id
                )
                
                # 更新 MongoDB 中的缓存状态
                if milvus_id:
                    thought_chain_model.is_cached = True
                    thought_chain_model.milvus_id = milvus_id
                    await thought_chain_model.save()
                    logger.debug(f"问答已缓存到 Milvus: {question[:30]}...")
            elif ENABLE_QA_CACHE and should_cache is False:
                logger.debug(f"问答评估为不缓存: {question[:30]}...")
            
            # 4. 更新关联消息的 extra_data，添加 thought_chain_id
            if message_id:
                await self._update_message_thought_chain_id(
                    message_id=message_id,
                    thought_chain_id=thought_chain_model.uuid,
                    like_count=thought_chain_model.like_count,
                    dislike_count=thought_chain_model.dislike_count
                )
            
            return thought_chain_model.uuid
            
        except Exception as e:
            logger.error(f"保存思维链失败: {e}", exc_info=True)
            return None
    
    async def _update_message_thought_chain_id(
        self,
        message_id: str,
        thought_chain_id: str,
        like_count: int = 0,
        dislike_count: int = 0
    ):
        """
        更新消息的 extra_data，添加 thought_chain_id
        
        Args:
            message_id: 消息ID
            thought_chain_id: 思维链ID
            like_count: 点赞数
            dislike_count: 踩数
        """
        try:
            from internal.model.message import MessageModel
            
            message = await MessageModel.find_one(MessageModel.uuid == message_id)
            if message:
                if not message.extra_data:
                    message.extra_data = {}
                
                message.extra_data["thought_chain_id"] = thought_chain_id
                message.extra_data["like_count"] = like_count
                message.extra_data["dislike_count"] = dislike_count
                
                await message.save()
                logger.debug(f"已更新消息的 thought_chain_id: {message_id}")
        except Exception as e:
            logger.error(f"更新消息 thought_chain_id 失败: {e}", exc_info=True)
    
    async def _save_to_milvus(
        self,
        thought_chain_id: str,
        question: str,
        answer: str,
        session_id: str,
        user_id: Optional[str]
    ) -> Optional[int]:
        """
        保存问题 embedding 到 Milvus（用于相似问题检索）
        
        Returns:
            Milvus 中的 ID，失败返回 None
        """
        try:
            # 生成问题的 embedding
            question_embedding = embedding_service.encode_query(question)
            
            # 构建元数据
            metadata = {
                "thought_chain_id": thought_chain_id,
                "session_id": session_id,
                "user_id": user_id or "",
                "answer_preview": answer[:200] if len(answer) > 200 else answer,
                "created_at": datetime.now().isoformat()
            }
            
            # 插入到 Milvus
            milvus_id = milvus_client.insert_qa_cache(
                question_embedding=question_embedding,
                question_text=question,
                metadata=metadata
            )
            
            return milvus_id
                
        except Exception as e:
            logger.error(f"保存问题 embedding 到 Milvus 失败: {e}")
            return None
    
    async def get_chain(self, chain_id: str) -> Optional[Dict[str, Any]]:
        """
        获取思维链
        
        Args:
            chain_id: 思维链UUID
            
        Returns:
            思维链数据，或 None
        """
        try:
            chain = await ThoughtChainModel.find_one(ThoughtChainModel.uuid == chain_id)
            if chain:
                return {
                    "uuid": chain.uuid,
                    "session_id": chain.session_id,
                    "message_id": chain.message_id,
                    "question": chain.question,
                    "answer": chain.answer,
                    "thought_chain": chain.thought_chain,
                    "documents_used": chain.documents_used,
                    "user_id": chain.user_id,
                    "model_name": chain.model_name,
                    "total_steps": chain.total_steps,
                    "created_at": chain.created_at.isoformat() if chain.created_at else None
                }
            return None
        except Exception as e:
            logger.error(f"获取思维链失败: {e}", exc_info=True)
            return None
    
    async def get_chains_by_session(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取会话的所有思维链
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
            
        Returns:
            思维链列表
        """
        try:
            chains = await ThoughtChainModel.find(
                ThoughtChainModel.session_id == session_id
            ).sort(-ThoughtChainModel.created_at).limit(limit).to_list()
            
            return [
                {
                    "uuid": chain.uuid,
                    "question": chain.question,
                    "answer": chain.answer[:100] + "..." if len(chain.answer) > 100 else chain.answer,
                    "total_steps": chain.total_steps,
                    "documents_count": len(chain.documents_used),
                    "created_at": chain.created_at.isoformat() if chain.created_at else None
                }
                for chain in chains
            ]
        except Exception as e:
            logger.error(f"获取会话思维链失败: {e}", exc_info=True)
            return []


# 创建单例实例
thought_chain_store = ThoughtChainStore()
