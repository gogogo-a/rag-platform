"""
ReAct Agent 实现 - LangChain 版本
使用 LangChain 的 create_react_agent 和 AgentExecutor
"""
from typing import Dict, List, Callable, Any, Optional
import re
from datetime import datetime, timedelta

from langchain.agents import create_react_agent, AgentExecutor
from langchain.agents.output_parsers import ReActSingleInputOutputParser
from langchain_core.agents import AgentAction
from langchain_core.agents import AgentFinish
from langchain_core.exceptions import OutputParserException
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate
from langchain_core.callbacks import BaseCallbackHandler

from log import logger
from internal.monitor import async_performance_monitor


class TolerantReActOutputParser(ReActSingleInputOutputParser):
    """Clean light formatting around tool names before execution."""

    @staticmethod
    def _clean_tool_name(tool_name: str) -> str:
        cleaned = tool_name.strip()
        cleaned = cleaned.strip("`*_ \n\t\r")
        cleaned = re.sub(r"\s+", "", cleaned)
        cleaned = cleaned.strip(":：")
        return cleaned

    def parse(self, text: str):
        try:
            parsed = super().parse(text)
        except OutputParserException:
            if not re.search(r"(^|\n)\s*(Thought|Action|Action Input|Observation)\s*:", text):
                answer = text.strip()
                if answer:
                    return AgentFinish({"output": answer}, text)
            raise
        if isinstance(parsed, AgentAction):
            cleaned_tool = self._clean_tool_name(parsed.tool)
            if cleaned_tool != parsed.tool:
                return AgentAction(cleaned_tool, parsed.tool_input, parsed.log)
        return parsed


class StreamingCallbackHandler(BaseCallbackHandler):
    """流式回调处理器 - 用于捕获 LLM 输出和工具执行"""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """LLM 生成新 token 时调用"""
        if self.callback:
            self.callback("llm_chunk", token)
    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """工具开始执行时调用"""
        if self.callback:
            tool_name = serialized.get("name", "unknown")
            # 🔥 过滤掉异常工具调用（LangChain 的错误处理机制）
            if tool_name.startswith("_Exception"):
                return
            self.callback("action", f"{tool_name}({input_str})")
    
    def on_tool_end(self, output: str, **kwargs) -> None:
        """工具执行结束时调用"""
        if self.callback:
            # 过滤掉错误处理的 observation
            if output and (output.startswith("请按照正确的格式") or "Invalid Format" in output):
                return
            
            # 尝试从工具结果中提取文档信息
            try:
                import json
                parsed = json.loads(output)
                if isinstance(parsed, dict) and "documents" in parsed:
                    documents = parsed.get("documents", [])
                    if documents:
                        self.callback("tool_result", {
                            "tool_name": "knowledge_search",
                            "documents": documents,
                            "results": parsed.get("results", []),
                        })
                    # 使用 context 作为 observation
                    output = parsed.get("context", output)
            except (json.JSONDecodeError, TypeError):
                pass
            
            self.callback("observation", output)


class ReActAgent:
    """ReAct Agent - LangChain 版本"""
    
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Callable],
        max_iterations: int = 5,
        verbose: bool = True,
        callback: Optional[Callable] = None
    ):
        """
        初始化 ReAct Agent
        
        Args:
            llm_service: LLM 服务实例
            tools: 工具字典 {tool_name: tool_function}
            max_iterations: 最大迭代次数
            verbose: 是否打印详细信息
            callback: 回调函数，用于实时推送事件 callback(event_type, content)
        """
        self.llm_service = llm_service
        self.llm = llm_service.llm  # LangChain LLM 实例
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.callback = callback
        
        # 🔥 转换工具为 LangChain Tool 格式
        self.langchain_tools = self._convert_tools(tools)
        
        # 🔥 创建 ReAct Agent
        self.agent = self._create_agent()
        
        # 🔥 创建 AgentExecutor
        # 自定义错误处理：不将解析错误暴露给用户
        def handle_parsing_error(error) -> str:
            """处理解析错误，返回提示信息而不是错误详情"""
            logger.warning(f"Agent 解析错误: {error}")
            return "请按照正确的格式输出：Thought -> Action -> Action Input"
        
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.langchain_tools,
            max_iterations=max_iterations,
            verbose=verbose,
            handle_parsing_errors=handle_parsing_error,  # 🔥 使用自定义错误处理
            return_intermediate_steps=True
        )

    @staticmethod
    def _chunk_to_text(chunk: Any) -> str:
        if chunk is None:
            return ""
        if isinstance(chunk, str):
            return chunk
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
            return "".join(parts)
        if isinstance(chunk, dict):
            return str(chunk.get("text") or chunk.get("content") or "")
        return ""

    def _emit_usage(self, chunk: Any) -> None:
        if not self.callback or chunk is None:
            return

        usage = None
        response_metadata = getattr(chunk, "response_metadata", None) or {}
        usage_metadata = getattr(chunk, "usage_metadata", None) or {}
        if isinstance(usage_metadata, dict) and usage_metadata:
            usage = {
                "prompt_tokens": usage_metadata.get("input_tokens"),
                "completion_tokens": usage_metadata.get("output_tokens"),
                "total_tokens": usage_metadata.get("total_tokens"),
            }
        token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
        if isinstance(token_usage, dict):
            usage = {
                "prompt_tokens": token_usage.get("prompt_tokens"),
                "completion_tokens": token_usage.get("completion_tokens"),
                "total_tokens": token_usage.get("total_tokens"),
            }

        if usage:
            clean_usage = {key: value for key, value in usage.items() if isinstance(value, int)}
            if clean_usage:
                self.callback("usage", clean_usage)

    def _emit_tool_end(self, output: Any) -> None:
        if not self.callback:
            return

        output_text = output if isinstance(output, str) else str(output)
        if output_text and (output_text.startswith("请按照正确的格式") or "Invalid Format" in output_text):
            return

        try:
            import json
            parsed = json.loads(output_text)
            if isinstance(parsed, dict) and "documents" in parsed:
                documents = parsed.get("documents", [])
                if documents:
                    self.callback("tool_result", {
                        "tool_name": "knowledge_search",
                        "documents": documents,
                        "results": parsed.get("results", []),
                    })
                output_text = parsed.get("context", output_text)
        except (json.JSONDecodeError, TypeError):
            pass

        self.callback("observation", output_text)
    
    def _get_history_text(self) -> str:
        """
        从 llm_service 获取历史记录文本
        
        Returns:
            格式化的历史记录文本
        """
        history_messages = self.llm_service.get_history()
        if not history_messages:
            return ""
        
        history_parts = []
        for msg in history_messages:
            role = msg.type if hasattr(msg, 'type') else 'unknown'
            content = msg.content if hasattr(msg, 'content') else str(msg)
            
            if role == 'human':
                history_parts.append(f"用户: {content}")
            elif role == 'ai':
                history_parts.append(f"AI: {content}")
            elif role == 'system':
                history_parts.append(f"系统: {content}")
        
        return "\n".join(history_parts)
    
    def _convert_tools(self, tools: Dict[str, Callable]) -> List[Tool]:
        """
        转换工具为 LangChain Tool 格式
        支持普通函数和 LangChain MCP 工具
        
        Args:
            tools: 工具字典 {tool_name: tool_function}
            
        Returns:
            LangChain Tool 列表
        """
        langchain_tools = []
        for name, func in tools.items():
            # 🔥 检查是否已经是 LangChain Tool
            if isinstance(func, Tool):
                langchain_tools.append(func)
            else:
                # 普通函数，包装为 Tool
                tool = Tool(
                    name=name,
                    func=func,
                    description=getattr(func, 'description', f"工具: {name}")
                )
                langchain_tools.append(tool)
        
        return langchain_tools
    
    def _create_agent(self):
        """创建 LangChain ReAct Agent"""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        # 🔥 优化的 ReAct prompt 模板（中文友好，支持历史记录）
        template = """尽你所能回答以下问题。你可以使用以下工具：

{tools}

严格按照以下格式输出：

Question: 需要回答的问题
Thought: 思考应该做什么
Action: 要执行的动作，必须是以下之一 [{tool_names}]
Action Input: 动作的输入参数
Observation: 动作的执行结果
... (Thought/Action/Action Input/Observation 可以重复N次)
Thought: 我现在知道最终答案了
Final Answer: 对原始问题的最终答案

重要提示：
1. 每次只能执行一个 Action
2. Action 和 Action Input 必须在同一轮输出
3. 看到 Observation 后，必须先输出 Thought 再决定下一步
4. 确定答案后，直接输出 Final Answer
5. 如果有历史对话，请结合历史上下文理解用户问题
6. 今天是 {today}，明天是 {tomorrow}；回答相对日期时必须使用这个日期，不要编造其他日期
7. Final Answer 后只输出给用户看的答案，不要再输出 Thought、Action、Action Input、Observation

{chat_history}

开始！

Question: {input}
Thought:{agent_scratchpad}"""
        template = template.replace("{today}", today.isoformat()).replace("{tomorrow}", tomorrow.isoformat())
        
        prompt = PromptTemplate.from_template(template)
        
        return create_react_agent(
            llm=self.llm,
            tools=self.langchain_tools,
            prompt=prompt,
            output_parser=TolerantReActOutputParser()
        )
    
    @async_performance_monitor('agent_total', operation_name='Agent完整推理', include_args=True, include_result=False)
    async def run(self, question: str, stream: bool = False) -> str:
        """
        运行 ReAct Agent - LangChain 版本（异步）
        
        Args:
            question: 用户问题
            stream: 是否流式输出（通过回调实现）
            
        Returns:
            最终答案
        """
        try:
            # 🔥 设置回调处理器
            callbacks = []
            if self.callback:
                callbacks.append(StreamingCallbackHandler(self.callback))
            
            # 🔥 获取历史记录
            chat_history = self._get_history_text()
            if chat_history:
                chat_history = f"历史对话记录：\n{chat_history}\n"
            
            # 🔥 执行 Agent（异步），传入历史记录
            result = await self.agent_executor.ainvoke(
                {
                    "input": question,
                    "chat_history": chat_history
                },
                config={"callbacks": callbacks}
            )
            
            # 返回最终答案
            return result.get("output", "抱歉，我无法回答这个问题。")
            
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}", exc_info=True)
            return f"抱歉，处理过程中出现错误: {str(e)}"

    async def run_stream(self, question: str) -> str:
        """
        运行 ReAct Agent，并把模型 token 和工具事件实时推送到 callback。
        """
        try:
            chat_history = self._get_history_text()
            if chat_history:
                chat_history = f"历史对话记录：\n{chat_history}\n"

            inputs = {
                "input": question,
                "chat_history": chat_history
            }
            final_output = ""

            async for event in self.agent_executor.astream_events(inputs, version="v2"):
                event_type = event.get("event")
                data = event.get("data") or {}

                if event_type in {"on_chat_model_stream", "on_llm_stream"}:
                    chunk = data.get("chunk")
                    self._emit_usage(chunk)
                    token = self._chunk_to_text(chunk)
                    if token and self.callback:
                        self.callback("llm_chunk", token)

                elif event_type == "on_tool_start" and self.callback:
                    tool_name = event.get("name") or "unknown"
                    if str(tool_name).startswith("_Exception"):
                        continue
                    tool_input = data.get("input", "")
                    self.callback("action", f"{tool_name}({tool_input})")

                elif event_type == "on_tool_end":
                    self._emit_tool_end(data.get("output", ""))

                elif event_type == "on_chain_end":
                    output = data.get("output")
                    if isinstance(output, dict) and output.get("output"):
                        final_output = output["output"]

            return final_output or "抱歉，我无法回答这个问题。"

        except Exception as e:
            logger.error(f"Agent 流式执行失败: {e}", exc_info=True)
            return await self.run(question, stream=False)


def create_react_agent_wrapper(llm_service, tools_dict: Dict[str, Callable]) -> ReActAgent:
    """
    创建 ReAct Agent
    
    Args:
        llm_service: LLM 服务实例
        tools_dict: 工具字典
        
    Returns:
        ReActAgent 实例
    """
    return ReActAgent(
        llm_service=llm_service,
        tools=tools_dict,
        max_iterations=5,
        verbose=True
    )
