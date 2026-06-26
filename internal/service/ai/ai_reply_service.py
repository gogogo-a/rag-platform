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
import re

from log import logger
from pkg.model_list import DEEPSEEK_CHAT
from pkg.constants.constants import AGENT_TYPE, AGENT_MODE, AGENT_MAX_ITERATIONS, AGENT_MAX_RETRIES

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
            self._agent_mode = AGENT_MODE
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
        skip_cache: bool = False,
        agent_mode: str = "single"
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
            agent_mode: Agent 模式
            
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
                    cached_answer = stream_parser.clean_final_result(similar_result.get("answer", ""))
                    if not cached_answer:
                        similar_result = None
                    else:
                        similar_result["answer"] = cached_answer

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
            
            normalized_agent_mode = self._normalize_agent_mode(agent_mode)
            system_prompt = await self._get_system_prompt(normalized_agent_mode)
            
            # 创建 ChatService
            chat_service = ChatService(
                session_id=session_id,
                user_id=user_id,
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                system_prompt=system_prompt,
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
            usage_data = {}
            
            # 用于收集文档信息
            retrieved_documents = []
            rag_results = []
            
            # 定义回调函数
            def callback(event_type: str, content: Any):
                nonlocal retrieved_documents, rag_results, usage_data
                
                # 收集文档信息
                if event_type == "tool_result" and isinstance(content, dict):
                    documents = content.get("documents", [])
                    results = content.get("results", [])
                    if results:
                        rag_results.extend(results)
                    if documents:
                        existing_uuids = {doc["uuid"] for doc in retrieved_documents}
                        for doc in documents:
                            if doc["uuid"] not in existing_uuids:
                                retrieved_documents.append(doc)
                                existing_uuids.add(doc["uuid"])
                elif event_type == "usage" and isinstance(content, dict):
                    usage_data.update(content)
                
                event_queue.put((event_type, content))
            
            agent = self._create_agent_for_mode(
                agent_mode=normalized_agent_mode,
                llm_service=chat_service.llm_service,
                tools=available_tools,
                history=history,
                callback=callback,
            )
            
            # 启动 Agent 任务
            if hasattr(agent, "run_stream"):
                agent_task = asyncio.create_task(agent.run_stream(user_message))
            else:
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
                    final_result = stream_parser.clean_final_result(result)
                    if final_result:
                        yield {
                            "event": "answer_chunk",
                            "data": {"content": final_result}
                        }
                    else:
                        fallback_result = self._build_observation_fallback_answer(
                            question_for_search,
                            stream_parser.get_observations(),
                            retrieved_documents,
                        )
                        if fallback_result:
                            yield {
                                "event": "answer_chunk",
                                "data": {"content": fallback_result}
                            }
            
            # 发送文档信息
            if retrieved_documents:
                yield {
                    "event": "documents",
                    "data": {"documents": retrieved_documents}
                }
            if rag_results:
                yield {
                    "event": "rag_results",
                    "data": {"results": rag_results}
                }
            if usage_data:
                yield {
                    "event": "usage",
                    "data": usage_data
                }
            
        except Exception as e:
            logger.error(f"生成 AI 回复失败: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": {"content": str(e)}
            }

    def _normalize_agent_mode(self, agent_mode: Optional[str]) -> str:
        mode = (agent_mode or self._agent_mode or "single").lower().strip()
        return mode if mode in {"single", "expert"} else "single"

    async def _get_system_prompt(self, agent_mode: str) -> str:
        from internal.service.orm.prompt_service import prompt_service

        if agent_mode == "expert":
            return await prompt_service.get_active_prompt("supervisor")
        return await prompt_service.get_active_prompt("single")

    def _create_agent_for_mode(
        self,
        agent_mode: str,
        llm_service,
        tools: Dict,
        history: List[Dict[str, Any]],
        callback: Callable,
    ):
        if agent_mode == "expert":
            from internal.agent.expert_orchestrator import ExpertOrchestrator
            return ExpertOrchestrator(
                llm_service=llm_service,
                tool_map=tools,
                history=history,
                callback=callback,
            )
        return self._create_agent(
            llm_service=llm_service,
            tools=tools,
            callback=callback,
        )

    def _build_observation_fallback_answer(
        self,
        question: str,
        observations: List[str],
        documents: List[Dict[str, Any]],
    ) -> Optional[str]:
        useful_observations = []
        for observation in observations:
            text = str(observation or "").strip()
            if not text:
                continue
            if "未找到相关搜索结果" in text or text == "[]":
                continue
            useful_observations.append(text)

        if not useful_observations:
            return None

        source_text = useful_observations[0]
        source_text = re.sub(r"\s+", " ", source_text).strip()
        if len(source_text) > 900:
            source_text = source_text[:900].rstrip() + "..."

        document_names = []
        for document in documents:
            name = str(document.get("name") or document.get("filename") or "").strip()
            if name and name not in document_names:
                document_names.append(name)

        answer_parts = [
            f"关于“{question}”，可以参考已检索到的资料来做：",
            source_text,
        ]
        if document_names:
            answer_parts.append("参考资料：" + "、".join(document_names[:3]))

        return "\n\n".join(answer_parts)
    
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
        last_process_event = None
        while not agent_task.done() or not event_queue.empty():
            try:
                event_type, content = event_queue.get_nowait()
                
                # 处理回调事件
                if event_type == "tool_result" and isinstance(content, dict):
                    documents = content.get("documents") or []
                    results = content.get("results") or []
                    if documents:
                        yield {
                            "event": "documents",
                            "data": {"documents": documents}
                        }
                    if results:
                        yield {
                            "event": "rag_results",
                            "data": {"results": results}
                        }
                    continue

                if event_type in ["action", "observation", "final_answer"]:
                    if event_type in {"action", "observation"}:
                        process_event_key = (event_type, str(content))
                        if process_event_key == last_process_event:
                            continue
                        last_process_event = process_event_key

                    result = stream_parser.handle_callback_event(event_type, content)
                    if result:
                        yield {
                            "event": result["event"],
                            "data": {"content": result["content"]}
                        }

                elif event_type == "expert_manifest" and isinstance(content, dict):
                    yield {
                        "event": "expert_manifest",
                        "data": content
                    }

                elif event_type == "agent_process" and isinstance(content, dict):
                    yield {
                        "event": "agent_process",
                        "data": content
                    }

                elif event_type == "expert_question" and isinstance(content, dict):
                    yield {
                        "event": "expert_question",
                        "data": content
                    }

                elif event_type == "expert_task_status" and isinstance(content, dict):
                    yield {
                        "event": "expert_task_status",
                        "data": content
                    }

                elif event_type == "expert_experience" and isinstance(content, dict):
                    yield {
                        "event": "expert_experience",
                        "data": content
                    }

                elif event_type == "agent_context_usage" and isinstance(content, dict):
                    yield {
                        "event": "agent_context_usage",
                        "data": content
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
