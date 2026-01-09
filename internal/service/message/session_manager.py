"""
会话管理器
负责会话的创建、获取、更新
"""
from typing import Tuple, Optional
from datetime import datetime
import uuid as uuid_module

from internal.model.session import SessionModel
from log import logger


class SessionManager:
    """会话管理器（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def create_or_get_session(
        self, 
        session_id: Optional[str], 
        user_id: str, 
        content: str
    ) -> Tuple[str, str]:
        """
        创建或获取会话
        
        Args:
            session_id: 会话ID（可选）
            user_id: 用户ID
            content: 消息内容（用于生成会话名称）
            
        Returns:
            (session_id, session_name)
        """
        try:
            if session_id:
                # 查找现有会话
                session = await SessionModel.find_one(SessionModel.uuid == session_id)
                if session:
                    logger.info(f"使用现有会话: {session_id}")
                    return session.uuid, session.name
                else:
                    logger.warning(f"会话不存在，将创建新会话: {session_id}")
            
            # 创建新会话
            # 会话名称：消息前10个字符，超过则加"..."
            session_name = content[:10] + ("..." if len(content) > 10 else "")
            
            new_session = SessionModel(
                uuid=str(uuid_module.uuid4()),
                user_id=user_id,
                name=session_name,
                last_message=content
            )
            await new_session.insert()
            
            logger.info(f"创建新会话: {new_session.uuid}, 名称: {session_name}")
            return new_session.uuid, session_name
            
        except Exception as e:
            logger.error(f"创建/获取会话失败: {e}", exc_info=True)
            raise
    
    async def update_last_message(self, session_id: str, message: str):
        """
        更新会话的最后一条消息
        
        Args:
            session_id: 会话ID
            message: 最后一条消息内容
        """
        try:
            session = await SessionModel.find_one(SessionModel.uuid == session_id)
            if session:
                session.last_message = message
                session.update_at = datetime.now()
                await session.save()
                logger.info(f"会话最后消息已更新: {session_id}")
            else:
                logger.warning(f"会话不存在，无法更新: {session_id}")
                
        except Exception as e:
            logger.error(f"更新会话最后消息失败: {e}", exc_info=True)
    
    async def update_session_name(self, session_id: str, name: str):
        """
        更新会话名称
        
        Args:
            session_id: 会话ID
            name: 新的会话名称
        """
        try:
            session = await SessionModel.find_one(SessionModel.uuid == session_id)
            if session:
                session.name = name
                session.update_at = datetime.now()
                await session.save()
                logger.info(f"会话名称已更新: {session_id} -> {name}")
            else:
                logger.warning(f"会话不存在，无法更新名称: {session_id}")
                
        except Exception as e:
            logger.error(f"更新会话名称失败: {e}", exc_info=True)
    
    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """
        获取会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            SessionModel 或 None
        """
        try:
            return await SessionModel.find_one(SessionModel.uuid == session_id)
        except Exception as e:
            logger.error(f"获取会话失败: {e}", exc_info=True)
            return None


# 创建单例实例
session_manager = SessionManager()
