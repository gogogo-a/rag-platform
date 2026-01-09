"""
总结服务
负责对话历史的自动总结
"""
from typing import Optional

from log import logger
from pkg.model_list import DEEPSEEK_CHAT
from pkg.agent_prompt.prompt_templates import SUMMARY_PROMPT
from pkg.constants.constants import SUMMARY_MESSAGE_THRESHOLD

from internal.service.message.history_manager import history_manager
from internal.service.message.message_service import message_crud_service


class SummaryService:
    """总结服务（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
    
    async def check_and_save_summary(self, session_id: str, threshold: int = None):
        """
        检查是否需要生成总结并保存到数据库
        
        策略：
        - 如果有历史总结，统计之后的新消息数
        - 如果新消息超过阈值，利用底层 LLMService 生成总结并保存
        - 如果没有总结且总消息数超过阈值，生成第一次总结
        
        Args:
            session_id: 会话ID
            threshold: 触发总结的消息数量阈值（默认从环境变量读取）
        """
        if threshold is None:
            threshold = SUMMARY_MESSAGE_THRESHOLD
        
        try:
            # 获取需要总结的消息
            messages_to_summarize, base_summary, has_previous_summary = \
                await history_manager.get_messages_for_summary(session_id)
            
            # 检查是否超过阈值
            if len(messages_to_summarize) < threshold:
                return
            
            logger.debug(f"消息数{len(messages_to_summarize)}条，超过阈值{threshold}，开始生成总结")
            
            # 构建对话文本
            dialog_text = base_summary
            for msg in messages_to_summarize:
                role = "用户" if msg.send_type == 0 else "AI助手"
                dialog_text += f"{role}：{msg.content}\n"
            
            # 调用 LLM 生成总结
            summary = await self._generate_summary(dialog_text)
            
            if summary:
                # 保存总结到数据库
                await message_crud_service.save_summary_message(session_id, summary)
            
        except Exception as e:
            logger.error(f"检查并保存总结失败: {e}", exc_info=True)
    
    async def _generate_summary(self, dialog_text: str) -> Optional[str]:
        """
        调用 LLM 生成总结
        
        Args:
            dialog_text: 对话文本
            
        Returns:
            总结内容，或 None
        """
        try:
            from internal.llm.llm_service import LLMService
            
            llm_service = LLMService(
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                auto_summary=False
            )
            
            summary_messages = [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": f"请总结以下对话：\n\n{dialog_text}"}
            ]
            
            summary = llm_service.chat(messages=summary_messages, stream=False, use_history=False)
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"生成总结失败: {e}", exc_info=True)
            return None
    
    async def auto_generate_session_name(
        self, 
        session_id: str, 
        user_question: str, 
        ai_answer: str
    ):
        """
        自动生成会话名称（第1轮对话后触发）
        
        Args:
            session_id: 会话ID
            user_question: 用户问题
            ai_answer: AI回答
        """
        try:
            from internal.llm.llm_service import LLMService
            
            llm_service = LLMService(
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                auto_summary=False
            )
            
            # 提示词：要求生成8-15字的简短标题
            prompt = f"""请根据以下对话，生成一个简短的会话标题（8-15个字）。
只返回标题本身，不要有任何其他内容。

用户问题：{user_question}
AI回答：{ai_answer[:200]}...

标题："""
            
            # 调用 LLM 生成标题
            response = llm_service.chat(user_message=prompt, stream=False, use_history=False)
            title = response.strip().strip('"').strip("'")
            
            # 限制长度
            if len(title) > 20:
                title = title[:20]
            
            # 更新会话名称
            from internal.service.message.session_manager import session_manager
            await session_manager.update_session_name(session_id, title)
                
        except Exception as e:
            logger.error(f"自动生成会话名称失败: {e}", exc_info=True)


# 创建单例实例
summary_service = SummaryService()
