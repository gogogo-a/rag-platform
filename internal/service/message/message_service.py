"""
消息 CRUD 服务
负责消息的创建、读取、更新、删除
"""
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
import uuid as uuid_module

from internal.model.message import MessageModel
from internal.db.redis import redis_client
from log import logger

from .file_handler import file_handler


class MessageCRUDService:
    """消息 CRUD 服务（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def save_user_message(
        self,
        session_id: str,
        content: str,
        user_id: str,
        send_name: str,
        send_avatar: str,
        file_type: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size: Optional[str] = None,
        file_content: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        location: Optional[str] = None
    ) -> MessageModel:
        """
        保存用户消息到数据库
        
        Args:
            session_id: 会话ID
            content: 消息内容
            user_id: 用户ID
            send_name: 发送者昵称
            send_avatar: 发送者头像
            file_type: 文件类型
            file_name: 文件名
            file_size: 文件大小
            file_content: 文件解析后的文本内容（用于 AI 分析）
            file_bytes: 文件原始字节流（用于保存文件）
            location: 用户位置信息（JSON 字符串，包含经纬度等）
        
        Returns:
            MessageModel: 保存的消息对象
        """
        try:
            # 构建 extra_data
            extra_data = file_handler.build_extra_data(
                file_bytes, file_name, file_type, file_size, file_content, location
            )
            
            message = MessageModel(
                uuid=str(uuid_module.uuid4()),
                session_id=session_id,
                content=content,
                send_type=0,  # 0.用户
                send_id=user_id,
                send_name=send_name,
                send_avatar=send_avatar,
                receive_id="system",  # AI系统
                file_type=file_type,
                file_name=file_name,
                file_size=file_size,
                extra_data=extra_data,
                status=1,  # 1.已发送
                send_at=datetime.now()
            )
            await message.insert()
            
            logger.debug(f"用户消息已保存: {message.uuid}")
            return message
            
        except Exception as e:
            logger.error(f"保存用户消息失败: {e}", exc_info=True)
            raise
    
    async def save_ai_message(
        self,
        session_id: str,
        content: str,
        receive_id: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> MessageModel:
        """
        保存 AI 消息到数据库
        
        Args:
            session_id: 会话ID
            content: 消息内容
            receive_id: 接收者ID
            extra_data: 额外数据（思考过程、文档等）
        
        Returns:
            MessageModel: 保存的消息对象
        """
        try:
            message = MessageModel(
                uuid=str(uuid_module.uuid4()),
                session_id=session_id,
                content=content,
                send_type=1,  # 1.AI
                send_id="system",
                send_name="AI助手",
                send_avatar="",
                receive_id=receive_id,
                extra_data=extra_data,
                status=1,  # 1.已发送
                send_at=datetime.now()
            )
            
            await message.insert()
            
            doc_count = len(extra_data.get('documents', []) if extra_data else [])
            logger.debug(f"AI 消息已保存: {message.uuid}, 文档数: {doc_count}")
            
            # 同时保存到 Redis（缓存最后一条 AI 消息）
            try:
                key = f"session:{session_id}:last_ai_message"
                redis_client.set(key, content, ex=3600)  # 1小时过期
            except Exception as e:
                logger.warning(f"缓存 AI 消息到 Redis 失败: {e}")
            
            return message
            
        except Exception as e:
            logger.error(f"保存 AI 消息失败: {e}", exc_info=True)
            raise
    
    async def save_summary_message(
        self,
        session_id: str,
        content: str
    ) -> MessageModel:
        """
        保存总结消息到数据库
        
        Args:
            session_id: 会话ID
            content: 总结内容
        
        Returns:
            MessageModel: 保存的消息对象
        """
        try:
            message = MessageModel(
                uuid=str(uuid_module.uuid4()),
                session_id=session_id,
                content=content.strip(),
                send_type=2,  # 2.系统总结
                send_id="system",
                send_name="系统",
                send_avatar="",
                receive_id="system",
                status=1,
                send_at=datetime.now()
            )
            
            await message.insert()
            logger.debug(f"总结已保存: {message.uuid}")
            
            return message
            
        except Exception as e:
            logger.error(f"保存总结消息失败: {e}", exc_info=True)
            raise
    
    async def get_session_messages(
        self,
        session_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        """
        获取会话的所有消息
        
        Args:
            session_id: 会话ID
            page: 页码
            page_size: 每页数量
            
        Returns:
            (message, ret, data)
        """
        try:
            # 查询消息
            query = MessageModel.find(MessageModel.session_id == session_id)
            
            # 排序：按创建时间升序
            query = query.sort(MessageModel.created_at)
            
            # 分页
            skip = (page - 1) * page_size
            messages = await query.skip(skip).limit(page_size).to_list()
            
            # 总数
            total = await MessageModel.find(MessageModel.session_id == session_id).count()
            
            # 转换为字典格式
            messages_data = []
            for msg in messages:
                messages_data.append({
                    "uuid": msg.uuid,
                    "session_id": msg.session_id,
                    "content": msg.content,
                    "send_type": msg.send_type,
                    "send_id": msg.send_id,
                    "send_name": msg.send_name,
                    "send_avatar": msg.send_avatar,
                    "receive_id": msg.receive_id,
                    "file_type": msg.file_type,
                    "file_name": msg.file_name,
                    "file_size": msg.file_size,
                    "status": msg.status,
                    "extra_data": msg.extra_data,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "send_at": msg.send_at.isoformat() if msg.send_at else None
                })
            
            data = {
                "total": total,
                "messages": messages_data
            }
            
            return "获取成功", 0, data
            
        except Exception as e:
            logger.error(f"获取会话消息失败: {e}", exc_info=True)
            return f"获取失败: {str(e)}", -1, None
    
    async def count_session_messages(self, session_id: str, exclude_summary: bool = True) -> int:
        """
        统计会话消息数量
        
        Args:
            session_id: 会话ID
            exclude_summary: 是否排除总结消息
            
        Returns:
            消息数量
        """
        try:
            if exclude_summary:
                count = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.send_type != 2
                ).count()
            else:
                count = await MessageModel.find(
                    MessageModel.session_id == session_id
                ).count()
            return count
        except Exception as e:
            logger.error(f"统计会话消息数量失败: {e}", exc_info=True)
            return 0


# 创建单例实例
message_crud_service = MessageCRUDService()
