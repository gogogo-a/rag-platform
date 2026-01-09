"""
历史记录管理器
负责会话历史消息的加载和管理
"""
from typing import List, Dict, Any

from internal.model.message import MessageModel
from log import logger


class HistoryManager:
    """历史记录管理器（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取会话的历史消息（智能加载）
        
        策略：
        - 如果存在 send_type=2（系统总结），只加载最后一条总结 + 之后的新消息
        - 如果不存在总结，加载所有历史消息
        
        Args:
            session_id: 会话ID
            
        Returns:
            List[Dict]: 格式化的历史消息列表 [{"role": "user/assistant/system", "content": "..."}]
        """
        try:
            # 1. 查找最后一条系统总结消息（send_type=2）
            last_summary = await MessageModel.find(
                MessageModel.session_id == session_id,
                MessageModel.send_type == 2
            ).sort(-MessageModel.created_at).limit(1).to_list()
            
            if last_summary:
                # 有总结：只加载总结 + 之后的消息
                summary_msg = last_summary[0]
                
                # 查询总结之后的所有消息
                messages_after_summary = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.created_at > summary_msg.created_at
                ).sort(MessageModel.created_at).to_list()
                
                # 构建历史记录：总结 + 新消息
                history = []
                
                # 添加总结消息（作为系统消息）
                history.append({
                    "role": "system",
                    "content": f"[历史对话总结]\n{summary_msg.content}"
                })
                
                # 添加总结之后的新消息
                for msg in messages_after_summary:
                    if msg.send_type == 0:  # 用户消息
                        role = "user"
                    elif msg.send_type == 1:  # AI消息
                        role = "assistant"
                    else:  # send_type=2 的总结消息不应该再出现在这里
                        continue
                    
                    history.append({
                        "role": role,
                        "content": msg.content
                    })
                
                logger.debug(f"会话历史: session={session_id}, 总结1条 + 新消息{len(messages_after_summary)}条")
                return history
            else:
                # 没有总结：加载所有历史消息
                messages = await MessageModel.find(
                    MessageModel.session_id == session_id
                ).sort(MessageModel.created_at).to_list()
                
                history = []
                for msg in messages:
                    if msg.send_type == 0:  # 用户消息
                        role = "user"
                    elif msg.send_type == 1:  # AI消息
                        role = "assistant"
                    else:  # send_type=2 的总结消息（理论上不应该存在，但做防御性处理）
                        continue
                    
                    history.append({
                        "role": role,
                        "content": msg.content
                    })
                
                logger.debug(f"会话历史: session={session_id}, 共 {len(history)} 条消息")
                return history
            
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}", exc_info=True)
            return []
    
    async def get_messages_for_summary(self, session_id: str) -> tuple:
        """
        获取需要总结的消息
        
        Args:
            session_id: 会话ID
            
        Returns:
            (messages_to_summarize, base_summary, has_previous_summary)
        """
        try:
            # 查找最后一条系统总结
            last_summary = await MessageModel.find(
                MessageModel.session_id == session_id,
                MessageModel.send_type == 2
            ).sort(-MessageModel.created_at).limit(1).to_list()
            
            if last_summary:
                # 有总结：统计之后的新消息
                new_messages = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.created_at > last_summary[0].created_at,
                    MessageModel.send_type != 2
                ).sort(MessageModel.created_at).to_list()
                
                base_summary = f"[历史对话总结]\n{last_summary[0].content}\n\n[新增对话]\n"
                return new_messages, base_summary, True
            else:
                # 没有总结：统计所有消息
                messages = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.send_type != 2
                ).sort(MessageModel.created_at).to_list()
                
                base_summary = "[对话记录]\n"
                return messages, base_summary, False
                
        except Exception as e:
            logger.error(f"获取需要总结的消息失败: {e}", exc_info=True)
            return [], "", False
    
    async def count_messages_after_summary(self, session_id: str) -> int:
        """
        统计总结之后的消息数量
        
        Args:
            session_id: 会话ID
            
        Returns:
            消息数量
        """
        try:
            # 查找最后一条系统总结
            last_summary = await MessageModel.find(
                MessageModel.session_id == session_id,
                MessageModel.send_type == 2
            ).sort(-MessageModel.created_at).limit(1).to_list()
            
            if last_summary:
                # 统计总结之后的消息
                count = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.created_at > last_summary[0].created_at,
                    MessageModel.send_type != 2
                ).count()
                return count
            else:
                # 没有总结，统计所有消息
                count = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.send_type != 2
                ).count()
                return count
                
        except Exception as e:
            logger.error(f"统计消息数量失败: {e}", exc_info=True)
            return 0


# 创建单例实例
history_manager = HistoryManager()
