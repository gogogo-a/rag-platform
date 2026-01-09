"""
消息管理业务逻辑（汇总入口）
整合各个模块：
- message: 消息 CRUD、会话管理、文件处理、历史管理
- ai: AI 回复生成、流式解析
- image: 图片分析
- summary: 对话总结

保持原有接口不变，内部调用模块化的服务
"""
from typing import Tuple, Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime
import time
import asyncio

from internal.db.milvus import milvus_client
from internal.rag.rag_service import rag_service
from log import logger
from pkg.constants.constants import MILVUS_COLLECTION_NAME, SUPPORTED_IMAGE_FORMATS
from internal.monitor import record_performance

# 导入模块化服务
from internal.service.message import (
    message_crud_service,
    session_manager,
    file_handler,
    history_manager
)
from internal.service.ai import ai_reply_service, thought_chain_store
from internal.service.ai.qa_evaluator import qa_evaluator
from internal.service.image import image_analyzer
from internal.service.summary import summary_service


class MessageService:
    """消息管理服务（单例模式）- 汇总入口"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化服务"""
        if self._initialized:
            return
        
        self._init_rag_service()
        self._initialized = True
        logger.info("✅ MessageService 初始化完成")
    
    def _init_rag_service(self):
        """初始化 RAG 检索服务"""
        try:
            from pymilvus import connections
            if not connections.has_connection("default"):
                milvus_client.connect()
            
            rag_service.collection_name = MILVUS_COLLECTION_NAME
            rag_service.initialize()
            
        except Exception as e:
            logger.warning(f"RAG 服务初始化失败: {e}")
    
    # ==================== 公共接口 ====================
    
    async def send_message_stream(
        self,
        content: str,
        user_id: str,
        send_name: str,
        send_avatar: str,
        session_id: Optional[str] = None,
        file_type: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size: Optional[str] = None,
        file_content: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        show_thinking: bool = False,
        location: Optional[str] = None,
        skip_cache: bool = False,
        regenerate_message_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送消息（统一流式返回，支持文件内容）
        
        Args:
            content: 用户的原始问题（保存到数据库）
            user_id: 用户ID
            send_name: 发送者昵称
            send_avatar: 发送者头像
            session_id: 会话ID（可选）
            file_type: 文件类型
            file_name: 文件名
            file_size: 文件大小
            file_content: 文档文件内容（已解析）
            file_bytes: 图片文件字节流（未解析）
            show_thinking: 是否显示思考过程
            location: 用户位置信息
            skip_cache: 是否跳过缓存（重新回答时使用）
            regenerate_message_id: 重新生成时的原消息ID（用于删除旧缓存）
        
        Yields:
            Dict: 包含事件类型和数据的字典
        """
        try:
            logger.debug(f"消息请求: user={user_id}, session={session_id}")
            
            # 1. 创建或获取会话
            session_id, session_name = await session_manager.create_or_get_session(
                session_id, user_id, content
            )
            
            yield {
                "event": "session_created",
                "data": {
                    "session_id": session_id,
                    "session_name": session_name
                }
            }
            
            # 2. 处理图片文件（流式分析）
            enhanced_content = content
            
            if file_bytes and file_name:
                if file_handler.is_image_file(file_name):
                    # 图片文件：流式分析
                    logger.debug(f"分析图片: {file_name}")
                    
                    yield {
                        "event": "thought",
                        "data": {"content": f"🖼️ 正在分析上传的图片：{file_name}"}
                    }
                    
                    # 执行图片分析
                    image_analysis_result = None
                    async for analysis_event in image_analyzer.analyze_image_stream(file_bytes, file_name):
                        yield analysis_event
                        if analysis_event.get("event") == "image_analysis_complete":
                            image_analysis_result = analysis_event.get("data", {}).get("combined_content", "")
                    
                    # 构建增强内容
                    if image_analysis_result:
                        from PIL import Image
                        import io
                        image = Image.open(io.BytesIO(file_bytes))
                        enhanced_content = f"""这是我上传的图片（文件名：{file_name}，尺寸：{image.width}x{image.height}）：

{image_analysis_result}

---

我的问题：{content}"""
                        file_content = image_analysis_result
                else:
                    # 文档文件：已在 Controller 层解析
                    if file_content:
                        logger.debug(f"文档文件: {file_name}, 长度: {len(file_content)}")
                        enhanced_content = f"""这是我上传的 {file_type.upper()} 文件（文件名：{file_name}）：

{file_content}

---

我的问题：{content}"""
            elif file_content:
                # 向后兼容
                enhanced_content = f"""这是我上传的文件：

{file_content}

---

我的问题：{content}"""
            
            # 3. 保存用户消息
            user_msg = await message_crud_service.save_user_message(
                session_id, content, user_id, send_name, send_avatar,
                file_type, file_name, file_size, file_content, file_bytes, location
            )
            
            yield {
                "event": "user_message_saved",
                "data": {
                    "uuid": user_msg.uuid,
                    "content": user_msg.content
                }
            }
            
            # 4. 获取会话历史
            history = await history_manager.get_session_history(session_id)
            
            # 5. 获取用户权限
            from internal.model.user_info import UserInfoModel
            user_info = await UserInfoModel.find_one(UserInfoModel.uuid == user_id)
            is_admin = user_info.is_admin if user_info else False
            user_permission = 1 if is_admin else 0
            
            # 5.1 启动异步问答评估（不阻塞主流程）
            evaluation_id = f"{session_id}:{user_msg.uuid}"
            qa_evaluator.start_evaluation(content, evaluation_id)
            
            # 5.2 如果是重新回答，删除旧的缓存
            if skip_cache and regenerate_message_id:
                from internal.model.thought_chain import ThoughtChainModel
                from internal.service.ai.similar_qa_cache import similar_qa_cache
                
                # 查找关联的思维链
                old_chain = await ThoughtChainModel.find_one(
                    ThoughtChainModel.message_id == regenerate_message_id
                )
                if old_chain and old_chain.is_cached:
                    await similar_qa_cache.delete_cache(old_chain.uuid)
                    logger.debug(f"已删除旧缓存: {old_chain.uuid}")
            
            # 6. 流式生成 AI 回复
            ai_reply_full = ""
            extra_data = {
                "thoughts": [],
                "actions": [],
                "observations": [],
                "documents": []
            }
            
            # 性能监控
            llm_total_start = time.time()
            current_thought_start = None
            current_action_start = None
            answer_start = None
            
            # 添加位置信息
            ai_input_content = enhanced_content
            if location:
                ai_input_content = f"{ai_input_content}\n\n[系统信息]\n用户位置: {location}"
            
            # 调用 AI 回复服务
            # 用于缓存命中时保存 thought_chain_id
            cached_thought_chain_id = None
            
            async for event_dict in ai_reply_service.generate_reply_stream(
                session_id, user_id, ai_input_content, history, user_permission,
                original_question=content,  # 传递原始问题用于相似问题检索
                skip_cache=skip_cache  # 传递跳过缓存标志
            ):
                event_type = event_dict.get("event", "message")
                event_data = event_dict.get("data", {})
                event_content = event_data.get("content", "")
                
                # 处理缓存命中事件
                if event_type == "cache_hit":
                    cached_thought_chain_id = event_data.get("thought_chain_id")
                    logger.info(f"缓存命中: thought_chain_id={cached_thought_chain_id}")
                    # 不向前端发送 cache_hit 事件，只记录
                    continue
                
                # 根据 show_thinking 参数决定是否输出思考过程
                elif event_type == "thought":
                    if current_thought_start is None:
                        current_thought_start = time.time()
                    extra_data["thoughts"].append(event_content)
                    if show_thinking:
                        yield event_dict
                        
                elif event_type == "action":
                    if current_thought_start is not None:
                        think_duration = time.time() - current_thought_start
                        record_performance('llm_think', f'思考步骤{len(extra_data["thoughts"])}', think_duration,
                                         thought_content=extra_data["thoughts"][-1][:100] if extra_data["thoughts"] else "")
                        current_thought_start = None
                    current_action_start = time.time()
                    extra_data["actions"].append(event_content)
                    if show_thinking:
                        yield event_dict
                        
                elif event_type == "observation":
                    if current_action_start is not None:
                        action_duration = time.time() - current_action_start
                        record_performance('llm_action', f'动作步骤{len(extra_data["actions"])}', action_duration,
                                         action_content=extra_data["actions"][-1][:100] if extra_data["actions"] else "")
                        current_action_start = None
                    extra_data["observations"].append(event_content)
                    if show_thinking:
                        yield event_dict
                        
                elif event_type == "answer_chunk":
                    if answer_start is None:
                        answer_start = time.time()
                    ai_reply_full += event_content
                    yield event_dict
                    
                elif event_type == "documents":
                    extra_data["documents"] = event_data.get("documents", [])
                    yield event_dict
                    
                elif event_type == "debug":
                    if show_thinking:
                        yield event_dict
                        
                elif event_type == "error":
                    yield event_dict
            
            # 性能监控记录
            if answer_start is not None:
                answer_duration = time.time() - answer_start
                record_performance('llm_answer', '生成最终答案', answer_duration,
                                 answer_length=len(ai_reply_full))
            
            llm_total_duration = time.time() - llm_total_start
            record_performance('llm_total', 'LLM完整对话', llm_total_duration,
                             total_thoughts=len(extra_data["thoughts"]),
                             total_actions=len(extra_data["actions"]),
                             total_observations=len(extra_data["observations"]),
                             total_documents=len(extra_data["documents"]),
                             answer_length=len(ai_reply_full))
            
            # 7. 保存 AI 消息
            if ai_reply_full:
                final_extra_data = {"documents": extra_data["documents"]}
                
                if show_thinking:
                    final_extra_data.update({
                        "thoughts": extra_data["thoughts"],
                        "actions": extra_data["actions"],
                        "observations": extra_data["observations"]
                    })
                
                ai_msg = await message_crud_service.save_ai_message(
                    session_id, 
                    ai_reply_full, 
                    user_id,
                    extra_data=final_extra_data
                )
                
                # 7.1 处理 thought_chain_id
                thought_chain_id = None
                
                # 如果是缓存命中，直接使用缓存的 thought_chain_id
                if cached_thought_chain_id:
                    thought_chain_id = cached_thought_chain_id
                    logger.info(f"使用缓存的 thought_chain_id: {thought_chain_id}")
                else:
                    # 保存新的思维链
                    # 构建文档引用列表
                    documents_used = [
                        {"uuid": doc.get("uuid", ""), "name": doc.get("name", "")}
                        for doc in extra_data["documents"]
                    ]
                    
                    # 获取问答评估结果（等待异步评估完成）
                    evaluation_id = f"{session_id}:{user_msg.uuid}"
                    should_cache = await qa_evaluator.get_evaluation_result(evaluation_id, timeout=3.0)
                    
                    # 同步保存思维链，获取 thought_chain_id（始终保存，即使没有 thoughts/actions）
                    thought_chain_id = await thought_chain_store.save_chain(
                        session_id=session_id,
                        question=content,  # 使用原始问题，不是增强后的内容
                        answer=ai_reply_full,
                        thoughts=extra_data["thoughts"],
                        actions=extra_data["actions"],
                        observations=extra_data["observations"],
                        documents_used=documents_used,
                        user_id=user_id,
                        message_id=ai_msg.uuid,
                        should_cache=should_cache
                    )
                    logger.info(f"新思维链已保存: thought_chain_id={thought_chain_id}")
                
                yield {
                    "event": "ai_message_saved",
                    "data": {
                        "uuid": ai_msg.uuid,
                        "content": ai_msg.content,
                        "thought_chain_id": thought_chain_id  # 返回 thought_chain_id
                    }
                }
                
                # 8. 更新会话最后消息
                await session_manager.update_last_message(session_id, ai_reply_full)
                
                # 9. 检查是否需要生成总结
                await summary_service.check_and_save_summary(session_id)
                
                # 10. 第1轮对话后自动生成会话名称
                total_messages = await message_crud_service.count_session_messages(session_id)
                
                if total_messages == 2:  # 用户1条 + AI1条
                    asyncio.create_task(
                        summary_service.auto_generate_session_name(session_id, content, ai_reply_full)
                    )
            
            yield {
                "event": "done",
                "data": {"session_id": session_id}
            }
            
        except Exception as e:
            logger.error(f"发送消息失败（流式）: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": {"message": f"发送失败: {str(e)}"}
            }
    
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
        return await message_crud_service.get_session_messages(session_id, page, page_size)


# 创建单例实例
message_service = MessageService()
