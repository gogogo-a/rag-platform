"""
AI 回复生成服务
负责调用 Agent 生成 AI 回复（核心模块）
支持两种 Agent 类型：
- ReActAgent: 传统 LangChain ReAct Agent
- LangGraphAgent: 基于 LangGraph 的状态图 Agent（支持错误恢复）
"""
from typing import Dict, Any, List, AsyncGenerator, Optional, Callable
import asyncio
import queue

from log import logger
from pkg.model_list import DEEPSEEK_CHAT
from pkg.agent_prompt.prompt_templates import get_agent_prompt
from pkg.constants.constants import AGENT_TYPE, AGENT_MAX_ITERATIONS, AGENT_MAX_RETRIES

from .stream_parser import StreamParser
from .thought_chain_store import thought_chain_store
from .similar_qa_cache import similar_qa_cache


class AIReplyService:
    """
    AI 回复生成服务（单例模式）
    
    负责：
    - 调用 Agent 生成回复
    - 流式输出处理
    - 收集思维链和文档信息
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._agent_type = AGENT_TYPE
            logger.info(f"AIReplyService 初始化，Agent 类型: {self._agent_type}")
    
    def _create_agent(self, llm_service, tools: Dict, callback: Callable):
        """
        根据配置创建 Agent
        
        Args:
            llm_service: LLM 服务实例
            tools: 工具字典
            callback: 回调函数
            
        Returns:
            Agent 实例
        """
        if self._agent_type == "langgraph":
            from internal.agent.langgraph_agent import LangGraphAgent
            return LangGraphAgent(
                llm_service=llm_service,
                tools=tools,
                max_iterations=AGENT_MAX_ITERATIONS,
                max_retries=AGENT_MAX_RETRIES,
                callback=callback
            )
        else:
            # 默认使用 ReActAgent
            from internal.agent.react_agent import ReActAgent
            return ReActAgent(
                llm_service=llm_service,
                tools=tools,
                max_iterations=AGENT_MAX_ITERATIONS,
                verbose=False,
                callback=callback
            )
    
    async def generate_reply_stream(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        history: List[Dict[str, Any]],
        user_permission: int = 0,
        original_question: str = None,
        skip_cache: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        生成 AI 回复（流式）
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            user_message: 用户消息（可能包含增强内容如位置信息）
            history: 历史消息列表
            user_permission: 用户权限（0=普通用户，1=管理员）
            original_question: 原始问题（用于相似问题检索，不包含增强内容）
            skip_cache: 是否跳过缓存（重新回答时使用）
            
        Yields:
            Dict: 事件字典 {"event": str, "data": dict}
        """
        try:
            # 使用原始问题进行相似问题检索（如果没有提供则使用 user_message）
            question_for_search = original_question or user_message
            
            # 0. 检查相似问题缓存（如果不跳过）
            if similar_qa_cache.is_enabled() and not skip_cache:
                similar_result = await similar_qa_cache.find_similar(question_for_search, user_id)
                if similar_result:
                    # 发送缓存命中提示
                    yield {
                        "event": "cache_hit",
                        "data": {
                            "similarity": similar_result["similarity"],
                            "original_question": similar_result["question"][:100],
                            "thought_chain_id": similar_result.get("thought_chain_id")  # 返回缓存的 thought_chain_id
                        }
                    }
                    
                    # 直接返回缓存的答案
                    yield {
                        "event": "answer_chunk",
                        "data": {"content": similar_result["answer"]}
                    }
                    
                    # 返回文档信息
                    if similar_result.get("documents"):
                        yield {
                            "event": "documents",
                            "data": {"documents": similar_result["documents"]}
                        }
                    
                    return
            
            from internal.chat_service.chat_service import ChatService
            
            # 获取 MCP 工具
            from pkg.agent_tools_mcp import mcp_manager
            available_tools = mcp_manager.get_tool_map()
            tools_list = mcp_manager.get_tools()
            
            # 使用多工具综合 Agent Prompt
            multi_tool_prompt = get_agent_prompt(use_multi_tool=True)
            
            # 创建 ChatService
            chat_service = ChatService(
                session_id=session_id,
                user_id=user_id,
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                system_prompt=multi_tool_prompt,
                tools=tools_list,
                auto_summary=False,
                max_history_count=10
            )
            
            # 加载历史记录
            if len(history) > 1:
                chat_service.add_to_history("system", "--- 以下是历史对话记录---")
                for msg in history[:-1]:
                    chat_service.add_to_history(msg['role'], msg['content'])
                chat_service.add_to_history("system", "--- 以上是历史对话，以下是用户当前的新问题 ---")
            
            # 创建事件队列和流式解析器
            event_queue = queue.Queue()
            stream_parser = StreamParser()
            
            # 用于收集文档信息
            retrieved_documents = []
            
            # 定义回调函数
            def callback(event_type: str, content: Any):
                nonlocal retrieved_documents
                
                # 收集文档信息
                if event_type == "tool_result" and isinstance(content, dict):
                    documents = content.get("documents", [])
                    if documents:
                        existing_uuids = {doc["uuid"] for doc in retrieved_documents}
                        for doc in documents:
                            if doc["uuid"] not in existing_uuids:
                                retrieved_documents.append(doc)
                                existing_uuids.add(doc["uuid"])
                
                event_queue.put((event_type, content))
            
            # 创建 Agent（根据配置选择类型）
            agent = self._create_agent(
                llm_service=chat_service.llm_service,
                tools=available_tools,
                callback=callback
            )
            
            # 启动 Agent 任务
            agent_task = asyncio.create_task(agent.run(user_message, stream=True))
            
            # 实时处理事件队列
            async for event_dict in self._process_event_queue(
                event_queue, agent_task, stream_parser, retrieved_documents
            ):
                yield event_dict
            
            # 等待 Agent 完成
            result = await agent_task
            
            # 处理最终答案
            if not stream_parser.is_answer_sent() and result:
                if not stream_parser.should_skip_duplicate_answer(result):
                    yield {
                        "event": "answer_chunk",
                        "data": {"content": result}
                    }
            
            # 发送文档信息
            if retrieved_documents:
                yield {
                    "event": "documents",
                    "data": {"documents": retrieved_documents}
                }
            
        except Exception as e:
            logger.error(f"生成 AI 回复失败: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": {"content": str(e)}
            }
    
    async def _process_event_queue(
        self,
        event_queue: queue.Queue,
        agent_task: asyncio.Task,
        stream_parser: StreamParser,
        retrieved_documents: List[Dict]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理事件队列
        
        Args:
            event_queue: 事件队列
            agent_task: Agent 任务
            stream_parser: 流式解析器
            retrieved_documents: 文档收集列表
            
        Yields:
            Dict: 事件字典
        """
        while not agent_task.done() or not event_queue.empty():
            try:
                event_type, content = event_queue.get_nowait()
                
                # 处理回调事件
                if event_type in ["action", "observation", "final_answer", "tool_result"]:
                    result = stream_parser.handle_callback_event(event_type, content)
                    if result:
                        yield {
                            "event": result["event"],
                            "data": {"content": result["content"]}
                        }
                
                # 处理 LLM chunk
                elif event_type == "llm_chunk":
                    result = stream_parser.parse_chunk(content)
                    if result:
                        yield {
                            "event": result["event"],
                            "data": {"content": result["content"]}
                        }
                
            except queue.Empty:
                await asyncio.sleep(0.01)
        
        # 检查剩余内容
        remaining = stream_parser.get_remaining_answer()
        if remaining:
            yield {
                "event": "answer_chunk",
                "data": {"content": remaining}
            }


# 创建单例实例
ai_reply_service = AIReplyService()
