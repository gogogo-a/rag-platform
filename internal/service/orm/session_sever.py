"""
会话管理业务逻辑
"""
from typing import Tuple, Optional, Dict, Any, List
from internal.model.session import SessionModel
from internal.model.message import MessageModel
from internal.dto.request import UpdateSessionRequest
from log import logger
from datetime import datetime


class SessionService:
    """会话管理服务（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_session_list(
        self, 
        user_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        """
        获取用户的会话列表
        
        Args:
            user_id: 用户ID
            page: 页码
            page_size: 每页数量
            
        Returns:
            (message, ret, data)
        """
        try:
            logger.info(f"获取会话列表: user_id={user_id}, page={page}, page_size={page_size}")
            
            # 查询用户的所有会话
            query = SessionModel.find(SessionModel.user_id == user_id)
            
            # 排序：按更新时间降序
            query = query.sort(-SessionModel.update_at)
            
            # 分页
            skip = (page - 1) * page_size
            sessions = await query.skip(skip).limit(page_size).to_list()
            
            # 总数
            total = await SessionModel.find(SessionModel.user_id == user_id).count()
            
            # 转换为字典格式
            sessions_data = []
            for session in sessions:
                sessions_data.append({
                    "uuid": session.uuid,
                    "user_id": session.user_id,
                    "name": session.name,
                    "last_message": session.last_message,
                    "create_at": session.create_at.isoformat() if session.create_at else None,
                    "update_at": session.update_at.isoformat() if session.update_at else None
                })
            
            data = {
                "total": total,
                "sessions": sessions_data
            }
            
            logger.info(f"获取会话列表成功: user_id={user_id}, 共 {total} 个会话")
            return "获取成功", 0, data
            
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}", exc_info=True)
            return f"获取失败: {str(e)}", -1, None
    
    async def update_session(
        self, 
        session_id: str,
        req: UpdateSessionRequest
    ) -> Tuple[str, int]:
        """
        更新会话信息
        
        Args:
            session_id: 会话ID
            req: 更新请求
            
        Returns:
            (message, ret)
        """
        try:
            logger.info(f"更新会话: session_id={session_id}")
            
            # 查找会话
            session = await SessionModel.find_one(SessionModel.uuid == session_id)
            
            if not session:
                logger.warning(f"会话不存在: {session_id}")
                return "会话不存在", -2
            
            # 更新字段
            updated = False
            
            if req.name is not None:
                session.name = req.name
                updated = True
                logger.info(f"更新会话名称: {session_id} -> {req.name}")
            
            if req.last_message is not None:
                session.last_message = req.last_message
                updated = True
                logger.info(f"更新最后消息: {session_id}")
            
            if updated:
                session.update_at = datetime.now()
                await session.save()
                logger.info(f"会话更新成功: {session_id}")
                return "更新成功", 0
            else:
                return "没有可更新的字段", -3
            
        except Exception as e:
            logger.error(f"更新会话失败: {e}", exc_info=True)
            return f"更新失败: {str(e)}", -1
    
    async def get_session_detail(self, session_id: str) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        """
        获取会话详情
        
        Args:
            session_id: 会话ID
            
        Returns:
            (message, ret, data)
        """
        try:
            logger.info(f"获取会话详情: session_id={session_id}")
            
            session = await SessionModel.find_one(SessionModel.uuid == session_id)
            
            if not session:
                logger.warning(f"会话不存在: {session_id}")
                return "会话不存在", -2, None
            
            data = {
                "uuid": session.uuid,
                "user_id": session.user_id,
                "name": session.name,
                "last_message": session.last_message,
                "create_at": session.create_at.isoformat() if session.create_at else None,
                "update_at": session.update_at.isoformat() if session.update_at else None
            }
            
            logger.info(f"获取会话详情成功: {session_id}")
            return "获取成功", 0, data
            
        except Exception as e:
            logger.error(f"获取会话详情失败: {e}", exc_info=True)
            return f"获取失败: {str(e)}", -1, None
    
    async def delete_session(self, session_id: str, user_id: str) -> Tuple[str, int]:
        """
        删除会话及其所有消息
        
        Args:
            session_id: 会话ID
            user_id: 用户ID（用于权限验证）
            
        Returns:
            (message, ret)
        """
        try:
            logger.info(f"删除会话: session_id={session_id}, user_id={user_id}")
            
            # 查找会话
            session = await SessionModel.find_one(SessionModel.uuid == session_id)
            
            if not session:
                logger.warning(f"会话不存在: {session_id}")
                return "会话不存在", -2
            
            # 验证权限：只能删除自己的会话
            if session.user_id != user_id:
                logger.warning(f"无权删除会话: session_id={session_id}, owner={session.user_id}, requester={user_id}")
                return "无权删除此会话", -3
            
            # 1. 删除会话下的所有消息
            delete_result = await MessageModel.find(
                MessageModel.session_id == session_id
            ).delete()
            deleted_messages = delete_result.deleted_count if delete_result else 0
            logger.info(f"删除会话消息: session_id={session_id}, 删除了 {deleted_messages} 条消息")
            
            # 2. 删除会话本身
            await session.delete()
            logger.info(f"会话删除成功: {session_id}")
            
            return "删除成功", 0
            
        except Exception as e:
            logger.error(f"删除会话失败: {e}", exc_info=True)
            return f"删除失败: {str(e)}", -1


# 创建单例实例
session_service = SessionService()

