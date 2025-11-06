"""
消息管理业务逻辑（模块化设计）
参考 test_full_rag_qa.py 的 AI 回答流程
集成 Agent + RAG 检索
"""
from typing import Tuple, Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime
import uuid as uuid_module
import time
import os
from pathlib import Path as PathlibPath

from internal.model.message import MessageModel
from internal.model.session import SessionModel
from internal.db.redis import redis_client
from internal.db.milvus import milvus_client
from internal.rag.rag_service import rag_service
from pkg.model_list import DEEPSEEK_CHAT
from pkg.agent_prompt.prompt_templates import get_agent_prompt
from pkg.agent_tools import get_available_tools
from log import logger
from pkg.constants.constants import MILVUS_COLLECTION_NAME, SUMMARY_MESSAGE_THRESHOLD, SUPPORTED_IMAGE_FORMATS
from internal.monitor import record_performance

# 文件上传配置
MESSAGE_FILES_DIR = "uploads/message_files"  # 消息文件上传目录
os.makedirs(MESSAGE_FILES_DIR, exist_ok=True)  # 确保目录存在

class MessageService:
    """消息管理服务（单例模式）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化 RAG 服务"""
        if self._initialized:
            return
        
        # 初始化 RAG 服务
        self._init_rag_service()
        self._initialized = True
    
    def _init_rag_service(self):
        """初始化 RAG 检索服务"""
        try:
            # 连接 Milvus（如果还没连接）
            from pymilvus import connections
            if not connections.has_connection("default"):
                logger.info("连接 Milvus...")
                milvus_client.connect()
            
            # 设置 collection name
            collection_name = MILVUS_COLLECTION_NAME  # 默认集合名
            rag_service.collection_name = collection_name
            
            # 初始化 RAG 服务
            logger.info(f"初始化 RAG 检索服务: collection={collection_name}")
            rag_service.initialize()
            
            logger.info("✓ RAG 服务初始化成功")
            
        except Exception as e:
            logger.warning(f"RAG 服务初始化失败: {e}，将在没有 RAG 的情况下运行")
    
    # ==================== 私有辅助函数（模块化）====================
    
    async def _create_or_get_session(
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
    
    async def _save_user_message(
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
            file_content: 文件解析后的文本内容（用于 AI 分析）
            file_bytes: 文件原始字节流（用于保存文件）
            location: 用户位置信息（JSON 字符串，包含经纬度等）
        
        Returns:
            MessageModel: 保存的消息对象
        """
        try:
            # 🔥 如果有文件字节流，保存文件并生成 URL
            extra_data = None
            if file_bytes and file_name:
                # 保存文件到服务器
                file_url = self._save_file_to_server(file_bytes, file_name)
                
                extra_data = {
                    "file_url": file_url,  # 文件访问 URL
                    "file_type": file_type,
                    "file_name": file_name,
                    "file_size": file_size
                }
                
                # 如果有解析内容（文档），也保存到 extra_data
                if file_content:
                    extra_data["parsed_content"] = file_content
                
                logger.info(f"用户上传了文件: {file_name}, URL: {file_url}, 有解析内容: {file_content is not None}")
                
            elif file_content:
                # 向后兼容：如果只有 file_content 没有 file_bytes
                extra_data = {
                    "file_content": file_content,
                    "file_type": file_type,
                    "file_name": file_name
                }
                logger.info(f"用户上传了文件（仅内容）: {file_name}, 内容长度: {len(file_content)}")
            
            # 🔥 如果有位置信息，添加到 extra_data
            if location:
                if extra_data is None:
                    extra_data = {}
                try:
                    import json
                    location_data = json.loads(location)
                    extra_data["location"] = location_data
                    logger.info(f"用户位置信息已保存: {location_data}")
                except Exception as e:
                    logger.warning(f"解析位置信息失败: {e}")
                    extra_data["location"] = location  # 保存原始字符串
            
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
                extra_data=extra_data,  # 🔥 保存文件 URL 到 extra_data
                status=1,  # 1.已发送
                send_at=datetime.now()
            )
            await message.insert()
            
            logger.info(f"用户消息已保存: {message.uuid}, session: {session_id}, has_file={file_bytes is not None or file_content is not None}")
            return message
            
        except Exception as e:
            logger.error(f"保存用户消息失败: {e}", exc_info=True)
            raise
    
    def _save_file_to_server(self, file_bytes: bytes, original_filename: str) -> str:
        """
        保存文件到服务器，并返回访问 URL
        
        Args:
            file_bytes: 文件字节流
            original_filename: 原始文件名
        
        Returns:
            文件访问 URL（相对路径）
        """
        try:
            # 生成唯一文件名（保留原始扩展名）
            extension = PathlibPath(original_filename).suffix
            saved_filename = f"{uuid_module.uuid4()}{extension}"
            file_path = os.path.join(MESSAGE_FILES_DIR, saved_filename)
            
            # 保存文件
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            # 构建访问 URL（相对路径）
            file_url = f"/uploads/message_files/{saved_filename}"
            
            logger.info(f"文件已保存: {file_path} ({len(file_bytes)} 字节) -> URL: {file_url}")
            
            return file_url
            
        except Exception as e:
            logger.error(f"保存文件失败: {original_filename}, error={e}", exc_info=True)
            raise
    
    async def _get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取会话的历史消息（智能加载）
        
        策略：
        - 如果存在 send_type=2（系统总结），只加载最后一条总结 + 之后的新消息
        - 如果不存在总结，加载所有历史消息
        
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
                logger.info(f"找到系统总结消息: {summary_msg.uuid}, 时间: {summary_msg.created_at}")
                
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
                
                logger.info(f"获取会话历史（智能加载）: session={session_id}, 总结1条 + 新消息{len(messages_after_summary)}条")
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
                
                logger.info(f"获取会话历史（全量加载）: session={session_id}, 共 {len(history)} 条消息")
                return history
            
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}", exc_info=True)
            return []
    
    async def _analyze_image_stream(
        self,
        image_bytes: bytes,
        filename: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式分析图片内容（OCR + LLaVA）
        
        Args:
            image_bytes: 图片字节流
            filename: 文件名
        
        Yields:
            Dict: 分析进度事件
                - event: 事件类型
                - data: 事件数据
        """
        try:
            from internal.service.image_service import image_service
            from PIL import Image
            import io
            
            # 获取图片基本信息
            image = Image.open(io.BytesIO(image_bytes))
            image_info = {
                "width": image.width,
                "height": image.height,
                "format": image.format or "Unknown"
            }
            
            result = {
                "ocr_text": "",
                "vision_description": "",
                "image_info": image_info,
                "combined_content": ""
            }
            
            # 1. OCR 文字识别
            yield {
                "event": "thought",
                "data": {
                    "content": "📝 正在识别图片中的文字（OCR）...\n"
                }
            }
            
            try:
                ocr_text = image_service._ocr_image(image_bytes, filename)
                result["ocr_text"] = ocr_text
                
                if ocr_text and ocr_text != "（图片中未识别到文字内容）":
                    # 输出识别到的文字内容
                    yield {
                        "event": "thought",
                        "data": {
                            "content": f"✅ OCR 识别完成，识别到文字：\n```\n{ocr_text}\n```\n\n"
                        }
                    }
                else:
                    yield {
                        "event": "thought",
                        "data": {
                            "content": "⚠️ 图片中未识别到文字内容\n\n"
                        }
                    }
            except Exception as e:
                logger.error(f"OCR 识别失败: {e}")
                yield {
                    "event": "thought",
                    "data": {
                        "content": f"⚠️ OCR 识别失败: {str(e)}\n\n"
                    }
                }
            
            # 2. LLaVA 多模态图片内容识别（流式输出）
            yield {
                "event": "thought",
                "data": {
                    "content": "🤖 正在使用 LLaVA 分析图片内容（物体、场景识别）...\n\n"
                }
            }
            
            try:
                vision_desc_full = ""
                
                # 流式输出 LLaVA 分析结果
                for chunk in image_service._llava_analyze_stream(image_bytes, filename):
                    vision_desc_full += chunk
                    # 将 LLaVA 的实际描述内容流式输出
                    yield {
                        "event": "thought",
                        "data": {
                            "content": chunk
                        }
                    }
                
                result["vision_description"] = vision_desc_full
                
                # 分析完成提示
                yield {
                    "event": "thought",
                    "data": {
                        "content": f"\n\n✅ 图片分析完成\n\n"
                    }
                }
                
            except Exception as e:
                logger.error(f"LLaVA 分析失败: {e}")
                yield {
                    "event": "thought",
                    "data": {
                        "content": f"⚠️ 图片内容识别失败: {str(e)}\n\n"
                    }
                }
            
            # 3. 综合内容描述
            combined_parts = []
            
            if result["vision_description"]:
                combined_parts.append(f"【图片内容 - LLaVA 分析】\n{result['vision_description']}")
            
            if result["ocr_text"] and result["ocr_text"] != "（图片中未识别到文字内容）":
                combined_parts.append(f"【图片中的文字 - OCR 识别】\n{result['ocr_text']}")
            
            if not combined_parts:
                combined_parts.append("（图片分析未得到有效信息）")
            
            result["combined_content"] = "\n\n".join(combined_parts)
            
            logger.info(f"图片分析完成: OCR={len(result['ocr_text'])} 字符, LLaVA={len(result['vision_description'])} 字符")
            
            # 返回完整结果
            yield {
                "event": "image_analysis_complete",
                "data": result
            }
            
        except Exception as e:
            logger.error(f"图片分析失败: {filename}, error={e}", exc_info=True)
            yield {
                "event": "thought",
                "data": {
                    "content": f"❌ 图片分析失败：{str(e)}"
                }
            }
            yield {
                "event": "image_analysis_complete",
                "data": {
                    "combined_content": f"（图片分析失败：{str(e)}）"
                }
            }
    
    async def _generate_ai_reply_stream(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        history: List[Dict[str, Any]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """生成 AI 回复（真正的流式）- 使用回调机制"""
        import asyncio
        import queue
        
        try:
            from internal.chat_service.chat_service import ChatService
            from internal.agent.react_agent import ReActAgent
            from internal.model.user_info import UserInfoModel
            
            # 🔥 获取用户权限信息
            user_info = await UserInfoModel.find_one(UserInfoModel.uuid == user_id)
            is_admin = user_info.is_admin if user_info else False
            user_permission = 1 if is_admin else 0
            logger.info(f"用户权限: user_id={user_id}, is_admin={is_admin}, permission={user_permission}")
            
            # 🔥 从工具层获取用户可用的工具（自动处理权限过滤和参数绑定）
            available_tools = get_available_tools(is_admin=is_admin, user_permission=user_permission)
            tools_list = list(available_tools.values())
            
            # 🎯 使用多工具综合 Agent Prompt
            multi_tool_prompt = get_agent_prompt(use_multi_tool=True)
            
            # 注意：auto_summary=False，因为我们在数据库层面实现了持久化总结（send_type=2）
            chat_service = ChatService(
                session_id=session_id,
                user_id=user_id,
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                system_prompt=multi_tool_prompt,  # 🔥 使用多工具 Agent prompt
                tools=tools_list,  # 🔥 使用工具层提供的工具列表（7个工具）
                auto_summary=False,  # 关闭底层自动总结，避免与数据库总结重复
                max_history_count=10
            )
            
            # 🔥 加载历史记录时添加上下文分隔
            if len(history) > 1:
                # 添加历史对话标记
                chat_service.add_to_history("system", "--- 以下是历史对话记录---")
                for msg in history[:-1]:
                    chat_service.add_to_history(msg['role'], msg['content'])
                # 添加当前问题标记
                chat_service.add_to_history("system", "--- 以上是历史对话，以下是用户当前的新问题 ---")
            
            # 创建事件队列
            event_queue = queue.Queue()
            
            # 用于收集文档信息
            retrieved_documents = []
            
            # 定义回调函数
            def callback(event_type, content):
                nonlocal retrieved_documents
                
                # 如果是工具结果，收集文档信息
                if event_type == "tool_result" and isinstance(content, dict):
                    documents = content.get("documents", [])
                    logger.info(f"🔍 工具返回文档数量: {len(documents)}")
                    if documents:
                        # 去重合并文档
                        existing_uuids = {doc["uuid"] for doc in retrieved_documents}
                        for doc in documents:
                            if doc["uuid"] not in existing_uuids:
                                retrieved_documents.append(doc)
                                existing_uuids.add(doc["uuid"])
                                logger.info(f"📄 添加文档: {doc['name']} ({doc['uuid']})")
                
                event_queue.put((event_type, content))
            
            # 创建 Agent 并传入回调（使用工具层提供的工具字典）
            agent = ReActAgent(
                llm_service=chat_service.llm_service,
                tools=available_tools,  # 🔥 使用工具层提供的工具字典
                max_iterations=5,
                verbose=False,
                callback=callback
            )
            
            # 在后台线程运行 Agent
            async def run_agent():
                return await asyncio.to_thread(lambda: agent.run(user_message, stream=True))
            
            # 启动 Agent 任务
            agent_task = asyncio.create_task(run_agent())
            
            # 实时读取队列并yield事件
            current_line = ""
            in_answer = False
            in_thought = False  # 新增：标记是否在 Thought 部分
            in_action = False   # 新增：标记是否在 Action 部分
            action_paren_depth = 0  # 跟踪Action中的括号深度
            in_action_string = False  # 跟踪是否在Action的字符串内
            action_string_char = None  # 字符串的引号类型
            action_escaped = False  # 跟踪是否在转义字符后
            
            while not agent_task.done() or not event_queue.empty():
                try:
                    event_type, content = event_queue.get_nowait()
                    
                    # 🔥 处理 tool_result 事件（已在 callback 中收集文档，这里只需要跳过）
                    if event_type == "tool_result":
                        logger.debug(f"收到工具结果，已收集文档信息")
                        continue
                    
                    # 🔥 处理 Observation 事件
                    elif event_type == "observation":
                        yield {
                            "event": "observation",
                            "data": {"content": content}
                        }
                    
                    elif event_type == "llm_chunk":
                        current_line += content
                        
                        # 🔥 流式检测 Thought:
                        if not in_thought and not in_answer and 'Thought:' in current_line:
                            in_thought = True
                            # 提取并立即输出 Thought: 后面的内容
                            thought_part = current_line.split('Thought:', 1)[1]
                            # 分割成已输出的部分和未输出的部分
                            if '\n' in thought_part:
                                # 有换行符，只输出第一行
                                to_output = thought_part.split('\n')[0]
                                remaining = '\n' + '\n'.join(thought_part.split('\n')[1:])
                                current_line = remaining
                            else:
                                # 没有换行符，全部输出
                                to_output = thought_part
                                current_line = ""
                            
                            # 输出 Thought 内容（去掉换行符）
                            if to_output and to_output not in ['\n', '\r\n']:
                                yield {
                                    "event": "thought",
                                    "data": {"content": to_output}
                                }
                        
                        # 如果在 Thought 部分，继续实时输出
                        elif in_thought and not in_answer and not in_action:
                            # 检查是否遇到 Action: 或 Answer:
                            if 'Action:' in current_line or 'Answer:' in current_line:
                                in_thought = False
                                # 不清空 current_line，让后续逻辑处理
                            else:
                                # 实时输出当前 chunk（除了换行符）
                                if content not in ['\n', '\r\n']:
                                    yield {
                                        "event": "thought",
                                        "data": {"content": content}
                                    }
                        
                        # 流式检测 Action:
                        if not in_action and not in_answer and 'Action:' in current_line:
                            in_action = True
                            in_thought = False  # 退出 Thought 模式
                            action_paren_depth = 0
                            in_action_string = False
                            action_string_char = None
                            action_escaped = False
                            
                            # 提取并立即输出 Action: 后面的内容
                            action_part = current_line.split('Action:', 1)[1]
                            # 立即输出 "Action:" 之后的内容
                            if action_part and action_part not in ['\n', '\r\n']:
                                yield {
                                    "event": "action",
                                    "data": {"content": action_part}
                                }
                                # 更新括号深度
                                for char in action_part:
                                    if action_escaped:
                                        action_escaped = False
                                        continue
                                    if char == '\\':
                                        action_escaped = True
                                        continue
                                    if not in_action_string:
                                        if char in ('"', "'"):
                                            in_action_string = True
                                            action_string_char = char
                                        elif char == '(':
                                            action_paren_depth += 1
                                        elif char == ')':
                                            action_paren_depth -= 1
                                            if action_paren_depth == 0:
                                                in_action = False
                                                break
                                    elif char == action_string_char:
                                        in_action_string = False
                                        action_string_char = None
                            current_line = ""
                        
                        # 如果在 Action 部分，继续实时输出并跟踪括号
                        elif in_action and not in_answer:
                            # 检查是否遇到 Observation: 或其他关键字
                            if 'Observation:' in content or 'Answer:' in content or 'Thought:' in content:
                                in_action = False
                                # 不清空 current_line，让后续逻辑处理
                            else:
                                # 实时输出当前 chunk
                                if content not in ['\r']:
                                    yield {
                                        "event": "action",
                                        "data": {"content": content}
                                    }
                                    
                                    # 更新括号深度（用于判断Action是否结束）
                                    for char in content:
                                        if action_escaped:
                                            action_escaped = False
                                            continue
                                        if char == '\\':
                                            action_escaped = True
                                            continue
                                        if not in_action_string:
                                            if char in ('"', "'"):
                                                in_action_string = True
                                                action_string_char = char
                                            elif char == '(':
                                                action_paren_depth += 1
                                            elif char == ')':
                                                action_paren_depth -= 1
                                                if action_paren_depth == 0:
                                                    # 括号匹配完成，Action结束
                                                    in_action = False
                                                    break
                                        elif char == action_string_char:
                                            in_action_string = False
                                            action_string_char = None
                        
                        # 🔥 流式检测 Answer:
                        if not in_answer and 'Answer:' in current_line:
                            in_answer = True
                            in_thought = False  # 退出 Thought 模式
                            in_action = False   # 退出 Action 模式
                            # 提取 Answer: 后面的内容
                            answer_part = current_line.split('Answer:', 1)[1]
                            if answer_part.strip():
                                yield {
                                    "event": "answer_chunk",
                                    "data": {"content": answer_part}
                                }
                            current_line = ""  # 清空已处理的内容
                        # 如果在 Answer 部分，实时输出
                        elif in_answer and content not in ['\n', '\r\n']:
                            yield {
                                "event": "answer_chunk",
                                "data": {"content": content}
                            }
                
                except queue.Empty:
                    await asyncio.sleep(0.01)  # 等待新事件
            
            # 🔥 循环结束后，检查是否有遗留的 Answer 内容
            if current_line.strip() and not in_answer:
                if 'Answer:' in current_line:
                    answer_part = current_line.split('Answer:', 1)[1].strip()
                    if answer_part:
                        yield {
                            "event": "answer_chunk",
                            "data": {"content": answer_part}
                        }
            
            # 等待 Agent 完成
            result = await agent_task
            logger.info(f"Agent 完成: {len(result)} 字符")
            
            # 🔥 发送检索到的文档信息
            logger.info(f"📚 准备发送文档列表，当前收集到 {len(retrieved_documents)} 个文档")
            if retrieved_documents:
                logger.info(f"✅ 发送检索文档信息: {retrieved_documents}")
                yield {
                    "event": "documents",
                    "data": {"documents": retrieved_documents}
                }
            else:
                logger.warning("⚠️ 没有收集到文档信息")
            
        except Exception as e:
            logger.error(f"生成 AI 回复失败: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": {"content": str(e)}
            }
    
    async def _save_ai_message(
        self,
        session_id: str,
        content: str,
        receive_id: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> MessageModel:
        """
        保存 AI 消息到数据库
        
        Args:
            extra_data: 额外数据（思考过程、文档等）
        
        Returns:
            MessageModel: 保存的消息对象
        """
        try:
            logger.debug(f"_save_ai_message收到extra_data: type={type(extra_data)}, value={extra_data}")
            
            message = MessageModel(
                uuid=str(uuid_module.uuid4()),
                session_id=session_id,
                content=content,
                send_type=1,  # 1.AI
                send_id="system",
                send_name="AI助手",
                send_avatar="",
                receive_id=receive_id,
                extra_data=extra_data,  # 🔥 存储额外数据
                status=1,  # 1.已发送
                send_at=datetime.now()
            )
            
            logger.debug(f"MessageModel创建后extra_data: {message.extra_data}")
            
            await message.insert()
            
            logger.info(f"AI 消息已保存: {message.uuid}, session: {session_id}, extra_data有{len(extra_data.get('documents', []) if extra_data else [])}个文档")
            
            # 同时保存到 Redis（缓存最后一条 AI 消息）
            try:
                key = f"session:{session_id}:last_ai_message"
                redis_client.set(key, content, ex=3600)  # 1小时过期
                logger.info(f"AI 消息已缓存到 Redis: {key}")
            except Exception as e:
                logger.warning(f"缓存 AI 消息到 Redis 失败: {e}")
            
            return message
            
        except Exception as e:
            logger.error(f"保存 AI 消息失败: {e}", exc_info=True)
            raise
    
    async def _update_session_last_message(self, session_id: str, message: str):
        """
        更新会话的最后一条消息
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
    
    async def _check_and_save_summary(self, session_id: str, threshold: int = None):
        """
        检查是否需要生成总结并保存到数据库
        
        策略：
        - 如果有历史总结，统计之后的新消息数
        - 如果新消息超过阈值，利用底层 LLMService 生成总结并保存
        - 如果没有总结且总消息数超过阈值，生成第一次总结
        
        Args:
            session_id: 会话ID
            threshold: 触发总结的消息数量阈值（默认从环境变量读取 SUMMARY_MESSAGE_THRESHOLD）
        """
        # 使用全局配置的阈值
        if threshold is None:
            threshold = SUMMARY_MESSAGE_THRESHOLD
        
        logger.info(f"🔍 检查会话是否需要总结: session={session_id}, 阈值={threshold}")
        
        try:
            # 查找最后一条系统总结
            last_summary = await MessageModel.find(
                MessageModel.session_id == session_id,
                MessageModel.send_type == 2
            ).sort(-MessageModel.created_at).limit(1).to_list()
            
            # 统计需要总结的消息
            if last_summary:
                # 有总结：统计之后的新消息
                new_messages = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.created_at > last_summary[0].created_at,
                    MessageModel.send_type != 2
                ).sort(MessageModel.created_at).to_list()
                
                messages_to_summarize = new_messages
                base_summary = f"[历史对话总结]\n{last_summary[0].content}\n\n[新增对话]\n"
                logger.info(f"📊 找到历史总结，新消息数: {len(messages_to_summarize)}")
            else:
                # 没有总结：统计所有消息
                messages_to_summarize = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.send_type != 2
                ).sort(MessageModel.created_at).to_list()
                
                base_summary = "[对话记录]\n"
                logger.info(f"📊 未找到历史总结，总消息数: {len(messages_to_summarize)}")
            
            # 检查是否超过阈值
            if len(messages_to_summarize) < threshold:
                logger.info(f"⏸️  消息数{len(messages_to_summarize)}条，未达到阈值{threshold}，暂不总结")
                return
            
            logger.info(f"✅ 消息数{len(messages_to_summarize)}条，超过阈值{threshold}，开始生成总结...")
            
            # 构建对话文本（利用已有消息数据）
            dialog_text = base_summary
            for msg in messages_to_summarize:
                role = "用户" if msg.send_type == 0 else "AI助手"
                dialog_text += f"{role}：{msg.content}\n"
            
            logger.info(f"📝 对话文本构建完成，准备调用 LLM 生成总结...")
            
            # 🔥 利用底层 LLMService 的总结能力（通过 SUMMARY_PROMPT）
            from internal.llm.llm_service import LLMService
            from pkg.agent_prompt.prompt_templates import SUMMARY_PROMPT
            
            llm_service = LLMService(
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                auto_summary=False  # 这里不需要自动总结
            )
            
            summary_messages = [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": f"请总结以下对话：\n\n{dialog_text}"}
            ]
            
            # 生成总结
            logger.info(f"🤖 正在调用 LLM 生成总结...")
            summary = llm_service.chat(messages=summary_messages, stream=False, use_history=False)
            logger.info(f"✨ LLM 总结生成完成，长度: {len(summary)} 字符")
            
            # 保存总结到数据库
            message = MessageModel(
                uuid=str(uuid_module.uuid4()),
                session_id=session_id,
                content=summary.strip(),
                send_type=2,  # 2.系统总结
                send_id="system",
                send_name="系统",
                send_avatar="",
                receive_id="system",
                status=1,
                send_at=datetime.now()
            )
            
            await message.insert()
            logger.info(f"💾 总结已保存到数据库: message_id={message.uuid}, send_type=2")
            
        except Exception as e:
            logger.error(f"检查并保存总结失败: {e}", exc_info=True)
    
    async def _auto_generate_session_name(
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
            logger.info(f"开始自动生成会话名称: session={session_id}")
            
            # 使用 LLMService 生成简短标题
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
            
            logger.info(f"生成的会话标题: {title}")
            
            # 使用 UpdateSessionRequest 更新会话名称
            from internal.dto.request import UpdateSessionRequest
            from internal.service.orm.session_sever import session_service
            
            req = UpdateSessionRequest(uuid=session_id, name=title)
            message, ret = await session_service.update_session(session_id, req)
            
            if ret == 0:
                logger.info(f"会话名称自动更新成功: {session_id} -> {title}")
            else:
                logger.warning(f"会话名称自动更新失败: {message}")
                
        except Exception as e:
            logger.error(f"自动生成会话名称失败: {e}", exc_info=True)
    
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
        location: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送消息（统一流式返回，支持文件内容）
        
        Args:
            content: 用户的原始问题（保存到数据库）
            file_content: 文档文件内容（已解析，用于保存到 extra_data）
            file_bytes: 图片文件字节流（未解析，将在此方法中流式处理）
            show_thinking: 是否显示思考过程（Thought/Action/Observation）
            location: 用户位置信息（JSON 字符串，包含经纬度，用于 POI 搜索、天气查询、路线规划等）
        
        Yields:
            Dict: 包含事件类型和数据的字典
                - event: 事件类型
                - data: 事件数据
        
        事件类型：
            - session_created: 会话创建
            - user_message_saved: 用户消息保存完成
            - image_analysis: 图片分析进度（流式输出）
            - thought: Agent 思考（仅当 show_thinking=True）
            - action: Agent 动作（仅当 show_thinking=True）
            - observation: 观察结果（仅当 show_thinking=True）
            - answer_chunk: 最终答案片段
            - ai_message_saved: AI 消息保存完成
            - done: 完成
            - error: 错误
        """
        try:
            logger.info(f"收到消息发送请求（流式）: user={user_id}, session={session_id}, show_thinking={show_thinking}")
            
            # 1. 创建或获取会话
            logger.debug(f"开始创建或获取会话...")
            session_id, session_name = await self._create_or_get_session(
                session_id, user_id, content
            )
            logger.debug(f"会话已准备: session_id={session_id}, session_name={session_name}")
            
            yield {
                "event": "session_created",
                "data": {
                    "session_id": session_id,
                    "session_name": session_name
                }
            }
            
            # 2. 🖼️ 如果是图片文件，先流式分析图片内容
            enhanced_content = content  # 默认使用原始问题
            
            if file_bytes and file_name:
                from pathlib import Path as PathlibPath
                extension = PathlibPath(file_name).suffix.lower()
                
                if extension in SUPPORTED_IMAGE_FORMATS:
                    # 图片文件：流式分析
                    logger.info(f"🖼️ 开始流式分析图片: {file_name}")
                    
                    # 流式输出：开始分析
                    yield {
                        "event": "thought",
                        "data": {
                            "content": f"🖼️ 正在分析上传的图片：{file_name}"
                        }
                    }
                    
                    # 执行图片分析（使用异步迭代器流式输出）
                    image_analysis_result = None
                    async for analysis_event in self._analyze_image_stream(file_bytes, file_name):
                        # 流式输出分析进度
                        yield analysis_event
                        # 最后一个事件包含完整结果
                        if analysis_event.get("event") == "image_analysis_complete":
                            image_analysis_result = analysis_event.get("data", {}).get("combined_content", "")
                    
                    # 分析完成后，构建增强内容
                    if image_analysis_result:
                        from PIL import Image
                        import io
                        image = Image.open(io.BytesIO(file_bytes))
                        enhanced_content = f"""这是我上传的图片（文件名：{file_name}，尺寸：{image.width}x{image.height}）：

{image_analysis_result}

---

我的问题：{content}"""
                        logger.info(f"✅ 图片分析完成，增强内容长度: {len(enhanced_content)}")
                        
                        # 更新 file_content 用于保存到数据库
                        file_content = image_analysis_result
                else:
                    # 文档文件：已在 Controller 层解析，直接构建增强内容
                    if file_content:
                        logger.info(f"📄 检测到文档文件: {file_name}，内容长度: {len(file_content)}")
                        enhanced_content = f"""这是我上传的 {file_type.upper()} 文件（文件名：{file_name}）：

{file_content}

---

我的问题：{content}"""
                        logger.info(f"✅ 文档内容已加入增强内容，长度: {len(enhanced_content)}")
            elif file_content:
                # 如果没有 file_bytes 但有 file_content（向后兼容）
                logger.info(f"📄 检测到文档内容（无 file_bytes），内容长度: {len(file_content)}")
                enhanced_content = f"""这是我上传的文件：

{file_content}

---

我的问题：{content}"""
            
            # 3. 保存用户消息（包含文件内容，如果是图片则包含分析结果）
            user_msg = await self._save_user_message(
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
            history = await self._get_session_history(session_id)
            
            # 5. 流式生成 AI 回复（收集额外数据）
            ai_reply_full = ""
            extra_data = {
                "thoughts": [],
                "actions": [],
                "observations": [],
                "documents": []
            }
            
            # ⏱️ 性能监控：记录各阶段时间
            llm_total_start = time.time()
            current_thought_start = None
            current_action_start = None
            answer_start = None
            
            # 🔥 使用 enhanced_content（包含文件内容）或原始 content
            ai_input_content = enhanced_content
            
            # 🌐 如果有用户位置信息，添加到消息中（用于 POI 搜索、天气查询、路线规划等功能）
            if location:
                ai_input_content = f"{ai_input_content}\n\n[系统信息]\n用户位置: {location}"
                logger.info(f"已添加用户位置到 AI 输入: {location}")
            
            logger.info(f"发送给 AI 的内容长度: {len(ai_input_content)}, 原始问题长度: {len(content)}")
            
            async for event_dict in self._generate_ai_reply_stream(session_id, user_id, ai_input_content, history):
                event_type = event_dict.get("event", "message")
                event_data = event_dict.get("data", {})
                event_content = event_data.get("content", "")
                
                # 根据 show_thinking 参数决定是否输出思考过程，同时收集到 extra_data
                if event_type == "thought":
                    # ⏱️ 记录 thought 开始时间
                    if current_thought_start is None:
                        current_thought_start = time.time()
                    
                    extra_data["thoughts"].append(event_content)
                    if show_thinking:  # 只有启用时才输出
                        yield event_dict
                        
                elif event_type == "action":
                    # ⏱️ thought 结束，记录时间
                    if current_thought_start is not None:
                        think_duration = time.time() - current_thought_start
                        record_performance('llm_think', f'思考步骤{len(extra_data["thoughts"])}', think_duration, 
                                         thought_content=extra_data["thoughts"][-1][:100] if extra_data["thoughts"] else "")
                        current_thought_start = None
                    
                    # ⏱️ 记录 action 开始时间
                    current_action_start = time.time()
                    
                    extra_data["actions"].append(event_content)
                    if show_thinking:  # 只有启用时才输出
                        yield event_dict
                        
                elif event_type == "observation":
                    # ⏱️ action 结束（包含工具执行），记录时间
                    if current_action_start is not None:
                        action_duration = time.time() - current_action_start
                        record_performance('llm_action', f'动作步骤{len(extra_data["actions"])}', action_duration,
                                         action_content=extra_data["actions"][-1][:100] if extra_data["actions"] else "")
                        current_action_start = None
                    
                    extra_data["observations"].append(event_content)
                    if show_thinking:  # 只有启用时才输出
                        yield event_dict
                        
                elif event_type == "answer_chunk":
                    # ⏱️ 开始生成答案，记录开始时间
                    if answer_start is None:
                        answer_start = time.time()
                    
                    ai_reply_full += event_content
                    yield event_dict
                    
                elif event_type == "documents":
                    # 🔥 收集文档信息到 extra_data（始终收集）
                    extra_data["documents"] = event_data.get("documents", [])
                    # 传递文档信息给前端（始终发送）
                    yield event_dict
                elif event_type == "debug":
                    if show_thinking:  # 只有启用时才输出
                        yield event_dict
                elif event_type == "error":
                    yield event_dict
            
            # ⏱️ 答案生成结束，记录时间
            if answer_start is not None:
                answer_duration = time.time() - answer_start
                record_performance('llm_answer', '生成最终答案', answer_duration,
                                 answer_length=len(ai_reply_full))
            
            # ⏱️ LLM 总时间
            llm_total_duration = time.time() - llm_total_start
            record_performance('llm_total', 'LLM完整对话', llm_total_duration,
                             total_thoughts=len(extra_data["thoughts"]),
                             total_actions=len(extra_data["actions"]),
                             total_observations=len(extra_data["observations"]),
                             total_documents=len(extra_data["documents"]),
                             answer_length=len(ai_reply_full))
            
            # 5. 保存 AI 消息（包含 extra_data）
            if ai_reply_full:
                # 🔥 根据 show_thinking 决定保存哪些额外数据
                final_extra_data = {"documents": extra_data["documents"]}
                
                if show_thinking:
                    # 显示思考过程：保存所有数据
                    final_extra_data.update({
                        "thoughts": extra_data["thoughts"],
                        "actions": extra_data["actions"],
                        "observations": extra_data["observations"]
                    })
                
                logger.debug(f"准备保存extra_data: {final_extra_data}")
                logger.debug(f"extra_data类型: {type(final_extra_data)}, documents数量: {len(final_extra_data.get('documents', []))}")
                
                ai_msg = await self._save_ai_message(
                    session_id, 
                    ai_reply_full, 
                    user_id,
                    extra_data=final_extra_data
                )
                
                yield {
                    "event": "ai_message_saved",
                    "data": {
                        "uuid": ai_msg.uuid,
                        "content": ai_msg.content
                    }
                }
                
                # 6. 更新会话最后消息
                await self._update_session_last_message(session_id, ai_reply_full)
                
                # 7. 🔥 检查是否需要生成总结并保存到数据库
                await self._check_and_save_summary(session_id)
                
                # 8. 🔥 第1轮对话后自动生成会话名称
                total_messages = await MessageModel.find(
                    MessageModel.session_id == session_id,
                    MessageModel.send_type != 2  # 排除总结消息
                ).count()
                
                if total_messages == 2:  # 用户1条 + AI1条
                    logger.info(f"检测到第1轮对话完成，触发自动生成会话名称: session={session_id}")
                    # 异步执行，不阻塞流式返回
                    import asyncio
                    asyncio.create_task(
                        self._auto_generate_session_name(session_id, content, ai_reply_full)
                    )
            
            yield {
                "event": "done",
                "data": {
                    "session_id": session_id
                }
            }
            
        except Exception as e:
            logger.error(f"发送消息失败（流式）: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": {
                    "message": f"发送失败: {str(e)}"
                }
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
        try:
            logger.info(f"获取会话消息: session={session_id}, page={page}, page_size={page_size}")
            
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
                    "extra_data": msg.extra_data,  # 🔥 返回额外数据（思考过程、文档等）
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "send_at": msg.send_at.isoformat() if msg.send_at else None
                })
            
            data = {
                "total": total,
                "messages": messages_data
            }
            
            logger.info(f"获取会话消息成功: session={session_id}, 共 {total} 条消息")
            return "获取成功", 0, data
            
        except Exception as e:
            logger.error(f"获取会话消息失败: {e}", exc_info=True)
            return f"获取失败: {str(e)}", -1, None


# 创建单例实例
message_service = MessageService()
