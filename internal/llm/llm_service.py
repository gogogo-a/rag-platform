"""
LLM 服务层 - LangChain 版本
使用 LangChain 标准组件：
- ChatMessageHistory: 历史记录管理
- SystemMessage/HumanMessage/AIMessage: 消息类型
- 支持自动总结历史记录
"""
from typing import Optional, List, Dict, Any, Callable
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from pkg.model_list import ModelManager, LLAMA_3_2  # 默认模型配置
from pkg.agent_tools import (
    get_tools_info,
    get_prompt_for_tools
)
from pkg.constants.constants import MAX_TOKEN


DEFAULT_SYSTEM_PROMPT = "你是一个智能助手，回答要准确、简洁、清晰。"
SUMMARY_SYSTEM_PROMPT = "你是一个对话总结助手，请保留关键事实、用户意图和未完成事项。"


class LLMService:
    """LLM 服务类 - 精简版"""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        model_type: Optional[str] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Callable]] = None,
        auto_summary: bool = True,
        max_history_count: int = 10,
        max_history_tokens: int = MAX_TOKEN
    ):
        """
        初始化 LLM 服务
        
        Args:
            model_name: 模型名称，如果为 None 则使用 LLAMA_3_2
            model_type: 模型类型 (local/cloud)，如果为 None 则使用默认模型的类型
            system_prompt: 自定义系统提示词（可选）
            tools: 使用的工具函数列表（可选），可以直接点击跳转
                   例如: [knowledge_search, document_analyzer]
            auto_summary: 是否自动总结历史记录
            max_history_count: 历史记录最大条数（默认10条）
            max_history_tokens: 历史记录最大token数（默认从配置读取）
        """
        # 如果没有指定模型，使用默认配置
        if model_name is None:
            model_name = LLAMA_3_2.name
            model_type = LLAMA_3_2.model_type
        elif model_type is None:
            # 如果只指定了 model_name，从配置中获取 model_type
            from pkg.model_list import get_llm_model
            config = get_llm_model(model_name)
            model_type = config.model_type
        
        self.model_name = model_name
        self.model_type = model_type
        
        # 工具配置
        self.tools = tools or []
        
        # 设置系统提示词
        if system_prompt:
            self.system_prompt = system_prompt
        elif self.tools:
            tool_names = get_prompt_for_tools(self.tools)
            self.system_prompt = f"{DEFAULT_SYSTEM_PROMPT}\n可用工具类型：{tool_names}"
        else:
            self.system_prompt = DEFAULT_SYSTEM_PROMPT
        
        # 🔥 使用 LangChain 的历史记录管理
        self.chat_history: BaseChatMessageHistory = InMemoryChatMessageHistory()
        self.auto_summary = auto_summary
        self.max_history_count = max_history_count
        self.max_history_tokens = max_history_tokens
        self._is_summarizing = False  # 总结状态标志
        self._need_summary = False  # 是否需要在下次对话前总结
        
        # 初始化模型
        self.llm = None
        self._initialize()
    
    def _initialize(self):
        """初始化模型"""
        try:
            self.llm = ModelManager.select_llm_model(self.model_name, self.model_type)
            print(f"✓ 模型已加载: {self.model_name} (type: {self.model_type})")
            if self.tools:
                # 兼容 LangChain Tool 对象和普通函数
                from langchain_core.tools import Tool
                tool_names = []
                for t in self.tools:
                    if isinstance(t, Tool):
                        tool_names.append(t.name)
                    else:
                        tool_names.append(t.__name__)
                print(f"✓ 已启用工具: {tool_names}")
        except Exception as e:
            print(f"✗ 模型初始化失败: {e}")
            raise
    
    def chat(
        self,
        user_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        stream: bool = True,
        use_history: bool = True,
        **kwargs
    ):
        """
        对话方法 - LangChain 版本
        
        Args:
            user_message: 用户消息（简化用法）
            messages: 消息列表（高级用法）
            context: 额外的上下文信息（如知识库检索结果）
            stream: 是否流式返回
            use_history: 是否自动使用内部历史记录（默认 True）
            **kwargs: 其他参数
        
        Yields (stream=True):
            回复片段
            
        Returns (stream=False):
            完整回复
        """
        # 🔥 在 AI 回答前，如果需要总结，先执行总结
        if self._need_summary and not self._is_summarizing:
            print("\n⚡ 检测到需要总结历史记录，正在总结...")
            self.summarize_history()
            self._need_summary = False
        
        # 🔥 构建 LangChain 消息列表
        langchain_messages: List[BaseMessage] = []
        
        # 添加系统提示词
        if self.system_prompt:
            langchain_messages.append(SystemMessage(content=self.system_prompt))
        
        # 添加上下文
        if context:
            langchain_messages.append(SystemMessage(content=f"参考信息：\n{context}"))
        
        # 🔥 自动添加历史记录（LangChain 格式）
        if use_history:
            langchain_messages.extend(self.chat_history.messages)
        
        # 添加用户消息
        if user_message and messages:
            raise ValueError("不能同时提供 user_message 和 messages 参数")
        elif user_message:
            langchain_messages.append(HumanMessage(content=user_message))
        elif messages:
            # 转换为 LangChain 消息格式
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    langchain_messages.append(SystemMessage(content=content))
                elif role == "user":
                    langchain_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    langchain_messages.append(AIMessage(content=content))
        else:
            raise ValueError("必须提供 user_message 或 messages 参数")
        
        # 🔥 使用 LangChain 的 stream 方法
        if stream:
            return self._stream_generate(langchain_messages, **kwargs)
        else:
            return self._generate(langchain_messages, **kwargs)
    
    def _normalize_chunk(self, chunk) -> str:
        """
        标准化不同模型返回的 chunk 格式
        
        Args:
            chunk: 原始 chunk（可能是 str 或 AIMessageChunk）
            
        Returns:
            标准化后的字符串
        """
        # Ollama 返回字符串，ChatOpenAI 返回 AIMessageChunk
        if isinstance(chunk, str):
            return chunk
        else:
            # AIMessageChunk 对象，提取 content
            return chunk.content if hasattr(chunk, 'content') else str(chunk)
    
    def _stream_generate(self, messages: List[BaseMessage], **kwargs):
        """流式生成 - LangChain 版本"""
        try:
            # 🔥 直接传递 LangChain 消息列表
            for chunk in self.llm.stream(messages):
                yield self._normalize_chunk(chunk)
        except Exception as e:
            raise Exception(f"生成失败: {e}")
    
    def _generate(self, messages: List[BaseMessage], **kwargs) -> str:
        """非流式生成 - LangChain 版本"""
        try:
            # 🔥 使用 invoke 方法
            response = self.llm.invoke(messages)
            return self._normalize_chunk(response)
        except Exception as e:
            raise Exception(f"生成失败: {e}")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量
        简单估算：中文1字约1.5token，英文1词约1token
        
        Args:
            text: 文本内容
            
        Returns:
            估算的 token 数
        """
        # 简单估算方法
        chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars / 4)
    
    def _calculate_history_tokens(self) -> int:
        """计算历史记录的总 token 数 - LangChain 版本"""
        total_tokens = 0
        for msg in self.chat_history.messages:
            content = msg.content if hasattr(msg, 'content') else str(msg)
            total_tokens += self._estimate_tokens(content)
        return total_tokens
    
    def _should_summarize(self) -> bool:
        """
        判断是否需要总结历史记录
        
        Returns:
            是否需要总结
        """
        # 如果正在总结中，不再触发
        if self._is_summarizing:
            return False
        
        # 检查条数
        if len(self.chat_history) >= self.max_history_count:
            return True
        
        # 检查 token 数
        total_tokens = self._calculate_history_tokens()
        if total_tokens >= self.max_history_tokens:
            return True
        
        return False
    
    def _do_summarize(self) -> str:
        """
        执行总结的核心逻辑 - LangChain 版本
        
        Returns:
            总结内容
        """
        # 🔥 构建总结 prompt（LangChain 格式）
        history_text = "\n\n".join([
            f"{msg.type}: {msg.content}"
            for msg in self.chat_history.messages
        ])
        
        summary_messages = [
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=f"请总结以下对话：\n\n{history_text}")
        ]
        
        # 生成总结
        summary_chunks = [
            self._normalize_chunk(chunk) 
            for chunk in self.llm.stream(summary_messages)
        ]
        
        return "".join(summary_chunks)
    
    async def _summarize_history_async(self):
        """
        异步总结历史记录 - LangChain 版本
        """
        if not self.chat_history.messages or self._is_summarizing:
            return
        
        self._is_summarizing = True
        
        try:
            old_count = len(self.chat_history.messages)
            summary = self._do_summarize()
            
            # 🔥 清空并添加总结（LangChain 格式）
            self.chat_history.clear()
            self.chat_history.add_message(
                AIMessage(content=f"[历史对话总结] {summary}")
            )
            
            print(f"\n✓ 历史记录已总结（原 {old_count} 条 -> 1 条）")
            
        except Exception as e:
            print(f"✗ 总结历史记录失败: {e}")
        finally:
            self._is_summarizing = False
    
    def summarize_history(self):
        """
        同步方式总结历史记录 - LangChain 版本
        """
        if not self.chat_history.messages or self._is_summarizing:
            return
        
        self._is_summarizing = True
        
        try:
            old_count = len(self.chat_history.messages)
            summary = self._do_summarize()
            
            # 🔥 清空并添加总结（LangChain 格式）
            self.chat_history.clear()
            self.chat_history.add_message(
                AIMessage(content=f"[历史对话总结] {summary}")
            )
            
            print(f"\n✓ 历史记录已总结（原 {old_count} 条 -> 1 条）")
            
        except Exception as e:
            print(f"✗ 总结历史记录失败: {e}")
        finally:
            self._is_summarizing = False
    
    def add_to_history(self, role: str, content: str):
        """
        添加消息到历史记录 - LangChain 版本
        
        Args:
            role: 角色 (user/assistant/system)
            content: 内容
        """
        # 🔥 使用 LangChain 的 add_message 方法
        if role == "user":
            self.chat_history.add_message(HumanMessage(content=content))
        elif role == "assistant":
            self.chat_history.add_message(AIMessage(content=content))
        elif role == "system":
            self.chat_history.add_message(SystemMessage(content=content))
        
        # 检查是否需要总结
        if self.auto_summary and self._should_summarize() and not self._need_summary:
            self._need_summary = True
            print(f"📌 历史记录已达到限制（{len(self.chat_history.messages)}条），将在下次对话前自动总结")
    
    def get_history(self) -> List[BaseMessage]:
        """获取当前历史记录 - LangChain 版本"""
        return self.chat_history.messages.copy()
    
    def clear_history(self):
        """清空历史记录 - LangChain 版本"""
        self.chat_history.clear()
        print("✓ 历史记录已清空")
    
    def get_history_stats(self) -> Dict[str, Any]:
        """获取历史记录统计信息 - LangChain 版本"""
        return {
            "count": len(self.chat_history.messages),
            "total_tokens": self._calculate_history_tokens(),
            "max_count": self.max_history_count,
            "max_tokens": self.max_history_tokens,
            "is_summarizing": self._is_summarizing
        }
    
    def get_info(self) -> Dict[str, Any]:
        """获取服务信息 - LangChain 版本"""
        tool_info = get_tools_info(self.tools) if self.tools else []
        return {
            "model_name": self.model_name,
            "model_type": self.model_type,
            "system_prompt": self.system_prompt[:100] + "..." if len(self.system_prompt) > 100 else self.system_prompt,
            "tools": [t["name"] for t in tool_info],
            "tool_count": len(self.tools),
            "auto_summary": self.auto_summary,
            "history_count": len(self.chat_history.messages)
        }
