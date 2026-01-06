"""
聊天服务（上层封装）
负责：
1. Session 和 User 管理
2. 调用底层 LLMService
3. 封装 Agent 交互（统一入口）

Note: 历史记录持久化（Redis/MongoDB）应在 API Server 层实现
"""
from typing import Optional, List, Dict, Any, Callable
from internal.llm.llm_service import LLMService
from pkg.constants.constants import MAX_TOKEN


class ChatService:
    """
    聊天服务 - 上层封装
    管理会话、用户、封装 LLM 和 Agent 调用
    """
    
    def __init__(
        self,
        session_id: str,
        user_id: str,
        model_name: Optional[str] = None,
        model_type: Optional[str] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Callable]] = None,
        auto_summary: bool = True,
        max_history_count: int = 10,
        max_history_tokens: int = MAX_TOKEN
    ):
        """
        初始化聊天服务
        
        Args:
            session_id: 会话ID（必填）
            user_id: 用户ID（必填）
            model_name: 模型名称
            model_type: 模型类型 (local/cloud)
            system_prompt: 系统提示词
            tools: 工具列表
            auto_summary: 是否自动总结
            max_history_count: 最大历史记录条数
            max_history_tokens: 最大历史记录token数
        """
        self.session_id = session_id
        self.user_id = user_id
        
        # 初始化底层 LLM 服务（纯粹的 LLM 调用）
        self.llm_service = LLMService(
            model_name=model_name,
            model_type=model_type,
            system_prompt=system_prompt,
            tools=tools,
            auto_summary=auto_summary,
            max_history_count=max_history_count,
            max_history_tokens=max_history_tokens
        )
        
        print(f"✓ ChatService 已初始化")
        print(f"  Session: {self.session_id}")
        print(f"  User: {self.user_id}")
    
    def _chat_with_agent(
        self,
        question: str,
        agent_tools: Dict[str, Callable],
        save_only_answer: bool = True,
        max_iterations: int = 5,
        verbose: bool = True
    ) -> str:
        """
        使用 Agent 进行对话（ReAct 框架）- LangChain 版本
        
        Args:
            question: 用户问题
            agent_tools: Agent 可用的工具字典
            save_only_answer: 是否只保存最终答案
            max_iterations: Agent 最大推理轮数
            verbose: 是否打印详细的推理过程
            
        Returns:
            最终答案
        """
        
        # 导入 ReActAgent（延迟导入避免循环依赖）
        from internal.agent.react_agent import ReActAgent
        
        # 🔥 记录历史长度（LangChain 版本）
        history_start_length = len(self.llm_service.chat_history.messages)
        
        # 创建 Agent
        agent = ReActAgent(
            llm_service=self.llm_service,
            tools=agent_tools,
            max_iterations=max_iterations,
            verbose=verbose
        )
        
        # 运行 Agent
        answer = agent.run(question, stream=verbose)
        
        # 🔥 ChatService 统一处理历史记录（LangChain 版本）
        if save_only_answer:
            # ✅ 只保存问答（清除所有中间过程）
            # 获取当前历史长度
            current_length = len(self.llm_service.chat_history.messages)
            
            # 删除中间过程（从 history_start_length 到 current_length）
            messages_to_keep = self.llm_service.chat_history.messages[:history_start_length]
            
            # 清空并重新添加
            self.llm_service.chat_history.clear()
            for msg in messages_to_keep:
                self.llm_service.chat_history.add_message(msg)
            
            # 添加简洁的问答对
            self.add_to_history("user", question)
            self.add_to_history("assistant", answer)
            
            if verbose:
                cleaned_count = current_length - history_start_length
                print(f"\n💾 ChatService：只保存问答（清除了 {cleaned_count} 条中间过程）")
        else:
            # ❌ 保留所有思考过程
            self.add_to_history("user", question)
            self.add_to_history("assistant", answer)
            
            if verbose:
                total_count = len(self.llm_service.chat_history.messages) - history_start_length
                print(f"\n💾 ChatService：保留完整思考过程（共 {total_count} 条）")
        
        return answer


    def chat(
        self,
        user_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        stream: bool = True,
        auto_add_to_history: bool = True,
        use_agent: bool = False,
        agent_tools: Optional[Dict[str, Callable]] = None,
        save_only_answer: bool = True,
        max_iterations: int = 5,
        verbose: bool = True,
        **kwargs
    ):
        """
        对话（自动管理历史记录）
        
        🔥 优化：完全自动化的对话流程
        1. 自动使用内部历史记录
        2. 自动添加用户消息和 AI 回复到历史
        3. 自动处理总结
        4. 支持 ReAct Agent（工具调用）🆕
        
        Args:
            user_message: 用户消息（简化用法，推荐）
            messages: 消息列表（高级用法，用于完全控制）
            context: 额外上下文
            stream: 是否流式返回（use_agent=True 时忽略，总是返回 str）
            auto_add_to_history: 是否自动添加到历史记录（默认 True）
            
            use_agent: 是否使用 ReAct Agent 进行工具调用（默认 False）🆕
            agent_tools: Agent 可用的工具字典 {tool_name: tool_function}（use_agent=True 时必需）🆕
            save_only_answer: Agent 模式下，是否只保存最终答案（默认 True，推荐）🆕
                            True: 只保存 question 和 answer
                            False: 保存所有 Thought、Action、Observation
            max_iterations: Agent 最大推理轮数（默认 5）🆕
            verbose: 是否打印详细的推理过程（默认 True）🆕
            
            **kwargs: 其他参数
            
        Yields/Returns:
            - 普通模式（use_agent=False）：
                - stream=True: Generator[str]（流式回复）
                - stream=False: str（完整回复）
            - Agent 模式（use_agent=True）：str（总是返回完整回复）
            
        示例:
            # ✅ 普通对话（流式）
            for chunk in chat_service.chat("你好"):
                print(chunk, end="")
            
            # ✅ Agent 对话（工具调用）🆕
            from pkg.agent_tools import knowledge_search
            
            answer = chat_service.chat(
                user_message="奖学金评定标准是什么？",
                use_agent=True,
                agent_tools={"knowledge_search": knowledge_search}
            )
            print(answer)
            
            # ✅ 高级用法（完全控制，不自动添加历史）
            response = chat_service.chat(
                messages=[{"role": "user", "content": "你好"}],
                auto_add_to_history=False
            )
        
        Note:
            - Agent 模式总是非流式返回
            - Agent 模式需要提供 agent_tools
            - 推荐使用 save_only_answer=True 保持历史简洁
        """
        # 🆕 Agent 模式：使用 ReAct Agent 进行工具调用
        if use_agent:
            if not user_message:
                raise ValueError("Agent 模式需要提供 user_message")
            if not agent_tools:
                raise ValueError("Agent 模式需要提供 agent_tools")
            
            return self._chat_with_agent(
                question=user_message,
                agent_tools=agent_tools,
                save_only_answer=save_only_answer,
                max_iterations=max_iterations,
                verbose=verbose
            )
        
        # 普通模式：直接 LLM 对话
        # 提取用户消息（用于历史记录）
        extracted_user_message = None
        if user_message:
            extracted_user_message = user_message
        elif messages and auto_add_to_history:
            # 从 messages 中提取最后一条用户消息
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    extracted_user_message = msg.get("content")
                    break
        
        # 🔥 关键优化：只传递其中一个参数给底层 LLM
        # 避免参数冲突
        if user_message:
            # 简化用法：只传 user_message
            result_generator = self.llm_service.chat(
                user_message=user_message,
                context=context,
                stream=stream,
                use_history=True,  # 🔥 自动使用内部历史
                **kwargs
            )
        else:
            # 高级用法：传 messages（不传 user_message）
            result_generator = self.llm_service.chat(
                messages=messages,
                context=context,
                stream=stream,
                use_history=True,  # 🔥 自动使用内部历史
                **kwargs
            )
        
        # 如果需要自动添加到历史
        if auto_add_to_history and extracted_user_message:
            # 先添加用户消息
            self.add_to_history("user", extracted_user_message)
            
            if stream:
                # 流式返回：需要收集完整回复后再添加
                def response_generator():
                    full_response = ""
                    try:
                        for chunk in result_generator:
                            full_response += chunk
                            yield chunk
                    finally:
                        # 添加 AI 回复到历史（即使出错也会执行）
                        if full_response:
                            self.add_to_history("assistant", full_response)
                
                return response_generator()
            else:
                # 非流式：直接添加完整回复
                response = result_generator
                self.add_to_history("assistant", response)
                return response
        else:
            # 不自动添加历史，直接返回
            return result_generator
    
    def add_to_history(self, role: str, content: str):
        """
        添加消息到历史记录
        
        🔥 优化：只会标记是否需要总结，不会立即执行
        真正的总结发生在下次 chat() 调用时
        
        Args:
            role: 角色 (user/assistant/system)
            content: 内容
        """
        self.llm_service.add_to_history(role, content)
    
    def get_history(self):
        """获取历史记录 - LangChain 版本"""
        return self.llm_service.get_history()
    
    def clear_history(self):
        """清空历史记录"""
        self.llm_service.clear_history()
        print("✓ 历史记录已清空")
    
    def get_history_stats(self) -> Dict[str, Any]:
        """获取历史记录统计信息"""
        stats = self.llm_service.get_history_stats()
        
        # 添加会话信息
        stats["session_id"] = self.session_id
        stats["user_id"] = self.user_id
        
        return stats
    
    def get_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        info = self.llm_service.get_info()
        
        # 添加 ChatService 层的信息
        info["chat_service"] = {
            "session_id": self.session_id,
            "user_id": self.user_id
        }
        
        return info