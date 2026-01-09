"""
LangGraph Agent 实现
使用 StateGraph 管理状态，支持：
- 条件分支
- 循环
- 错误恢复
- 工具调用（使用文本解析方式，与 ReActAgent 一致）
- 流式输出（与 ReActAgent 一致）
"""
from typing import Dict, List, Callable, Any, Optional, TypedDict, Annotated, Literal
from enum import Enum
import operator
import json
import re
import asyncio

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import StateGraph, END

from log import logger
from internal.monitor import async_performance_monitor


class ErrorType(Enum):
    """错误类型枚举"""
    TOOL_ERROR = "tool_error"
    PARSE_ERROR = "parse_error"
    TIMEOUT_ERROR = "timeout_error"
    LLM_ERROR = "llm_error"
    UNKNOWN_ERROR = "unknown_error"


class AgentState(TypedDict):
    """Agent 状态定义"""
    messages: Annotated[List[BaseMessage], operator.add]
    current_step: int
    max_steps: int
    error_count: int
    last_error: Optional[str]
    error_type: Optional[str]
    tool_results: List[Dict[str, Any]]
    final_answer: Optional[str]
    documents: List[Dict[str, Any]]
    should_end: bool
    agent_scratchpad: str
    pending_action: Optional[Dict]


class StreamingCallbackHandler(BaseCallbackHandler):
    """流式回调处理器 - 用于捕获 LLM 输出"""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.collected_tokens = []
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """LLM 生成新 token 时调用"""
        self.collected_tokens.append(token)
        if self.callback:
            self.callback("llm_chunk", token)
    
    def get_collected_text(self) -> str:
        """获取收集的所有 token"""
        return "".join(self.collected_tokens)
    
    def clear(self):
        """清空收集的 token"""
        self.collected_tokens = []


class LangGraphAgent:
    """
    LangGraph Agent - 基于状态图的智能代理
    
    特性：
    - 使用 StateGraph 管理复杂工作流
    - 使用文本解析方式调用工具（与 ReActAgent 一致）
    - 支持错误恢复（重试、换工具、降级）
    - 流式输出支持（与 ReActAgent 一致）
    """
    
    REACT_PROMPT = """尽你所能回答以下问题。你可以使用以下工具：

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

{chat_history}

开始！

Question: {input}
Thought:{agent_scratchpad}"""
    
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Callable],
        max_iterations: int = 5,
        max_retries: int = 2,
        callback: Optional[Callable] = None
    ):
        self.llm_service = llm_service
        self.llm = llm_service.llm
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        self.callback = callback
        
        # 流式回调处理器
        self.streaming_handler = StreamingCallbackHandler(callback)
        
        # 转换工具
        self.tools = self._convert_tools(tools)
        self.tool_map = {t.name: t for t in self.tools}
        
        # 生成工具描述
        self.tools_description = self._get_tools_description()
        self.tool_names = ", ".join([t.name for t in self.tools])
        
        # 构建状态图
        self.graph = self._build_graph()
        self.app = self.graph.compile()
    
    def _convert_tools(self, tools: Dict[str, Callable]) -> List[Tool]:
        """转换工具为 LangChain Tool 格式"""
        langchain_tools = []
        for name, func in tools.items():
            if isinstance(func, Tool):
                langchain_tools.append(func)
            else:
                tool = Tool(
                    name=name,
                    func=func,
                    description=getattr(func, 'description', f"工具: {name}")
                )
                langchain_tools.append(tool)
        return langchain_tools
    
    def _get_tools_description(self) -> str:
        """生成工具描述文本"""
        descriptions = []
        for tool in self.tools:
            descriptions.append(f"{tool.name}: {tool.description}")
        return "\n".join(descriptions)
    
    def _build_graph(self) -> StateGraph:
        """构建状态图"""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("think", self._think_node)
        workflow.add_node("act", self._act_node)
        workflow.add_node("error_recovery", self._error_recovery_node)
        workflow.add_node("finalize", self._finalize_node)
        
        workflow.set_entry_point("think")
        
        workflow.add_conditional_edges(
            "think",
            self._route_after_think,
            {"act": "act", "finalize": "finalize", "end": END}
        )
        
        workflow.add_conditional_edges(
            "act",
            self._route_after_act,
            {"think": "think", "error_recovery": "error_recovery", "finalize": "finalize"}
        )
        
        workflow.add_conditional_edges(
            "error_recovery",
            self._route_after_recovery,
            {"think": "think", "finalize": "finalize"}
        )
        
        workflow.add_edge("finalize", END)
        
        return workflow
    
    def _parse_llm_output(self, text: str) -> Dict[str, Any]:
        """解析 LLM 输出，提取 Action、Action Input 或 Final Answer"""
        result = {"thought": ""}
        
        # 提取 Thought
        thought_match = re.search(r'Thought:\s*(.+?)(?=Action:|Final Answer:|$)', text, re.DOTALL)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()
        
        # 检查是否有 Final Answer
        final_answer_match = re.search(r'Final Answer:\s*(.+?)$', text, re.DOTALL)
        if final_answer_match:
            result["type"] = "final_answer"
            result["answer"] = final_answer_match.group(1).strip()
            return result
        
        # 检查是否有 Action
        action_match = re.search(r'Action:\s*(.+?)(?:\n|$)', text)
        action_input_match = re.search(r'Action Input:\s*(.+?)(?=\nObservation:|$)', text, re.DOTALL)
        
        if action_match:
            tool_name = action_match.group(1).strip()
            tool_input = action_input_match.group(1).strip() if action_input_match else ""
            
            if tool_name in self.tool_map:
                result["type"] = "action"
                result["tool_name"] = tool_name
                result["tool_input"] = tool_input
                return result
            else:
                result["type"] = "error"
                result["error"] = f"未知工具: {tool_name}，可用工具: {self.tool_names}"
                return result
        
        # 如果没有明确的格式，检查是否是直接回答
        if text.strip() and not action_match and not final_answer_match:
            result["type"] = "final_answer"
            result["answer"] = text.strip()
            return result
        
        result["type"] = "error"
        result["error"] = "无法解析 LLM 输出格式"
        return result
    
    async def _stream_llm_call(self, prompt: str) -> str:
        """流式调用 LLM，通过回调发送每个 token"""
        self.streaming_handler.clear()
        
        try:
            # 使用流式调用
            response = await self.llm.ainvoke(
                prompt,
                config={"callbacks": [self.streaming_handler]}
            )
            
            # 返回完整响应
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"流式 LLM 调用失败: {e}")
            raise
    
    async def _think_node(self, state: AgentState) -> AgentState:
        """思考节点 - 调用 LLM 决定下一步行动（流式输出）"""
        try:
            # 获取历史记录
            chat_history = self._get_history_text()
            if chat_history:
                chat_history = f"历史对话记录：\n{chat_history}\n"
            
            # 获取用户问题
            question = ""
            for msg in reversed(state["messages"]):
                if isinstance(msg, HumanMessage):
                    question = msg.content
                    break
            
            # 构建 prompt
            prompt = self.REACT_PROMPT.format(
                tools=self.tools_description,
                tool_names=self.tool_names,
                chat_history=chat_history,
                input=question,
                agent_scratchpad=state["agent_scratchpad"]
            )
            
            # 流式调用 LLM
            llm_output = await self._stream_llm_call(prompt)
            
            # 解析 LLM 输出
            parsed = self._parse_llm_output(llm_output)
            
            new_state = {
                "current_step": state["current_step"] + 1,
                "last_error": None,
                "error_type": None
            }
            
            if parsed["type"] == "final_answer":
                new_state["final_answer"] = parsed["answer"]
            
            elif parsed["type"] == "action":
                new_state["pending_action"] = {
                    "tool_name": parsed["tool_name"],
                    "tool_input": parsed["tool_input"]
                }
            
            elif parsed["type"] == "error":
                new_state["last_error"] = parsed["error"]
                new_state["error_type"] = ErrorType.PARSE_ERROR.value
                new_state["error_count"] = state["error_count"] + 1
            
            return new_state
            
        except Exception as e:
            logger.error(f"思考节点错误: {e}")
            return {
                "last_error": str(e),
                "error_type": ErrorType.LLM_ERROR.value,
                "error_count": state["error_count"] + 1
            }
    
    async def _act_node(self, state: AgentState) -> AgentState:
        """行动节点 - 执行工具调用"""
        try:
            pending_action = state.get("pending_action")
            if not pending_action:
                return {
                    "last_error": "没有待执行的动作",
                    "error_type": ErrorType.PARSE_ERROR.value
                }
            
            tool_name = pending_action["tool_name"]
            tool_input = pending_action["tool_input"]
            
            # 发送 action 事件
            if self.callback:
                self.callback("action", f"{tool_name}({tool_input})")
            
            if tool_name not in self.tool_map:
                return {
                    "last_error": f"工具 {tool_name} 不存在",
                    "error_type": ErrorType.TOOL_ERROR.value,
                    "error_count": state["error_count"] + 1
                }
            
            tool = self.tool_map[tool_name]
            
            # 执行工具
            if hasattr(tool, 'coroutine') and tool.coroutine:
                result = await tool.coroutine(tool_input)
            else:
                result = tool.func(tool_input)
            
            # 发送 observation 事件
            if self.callback:
                self.callback("observation", str(result)[:500])
            
            # 解析工具结果，提取文档信息
            documents = []
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                if isinstance(parsed, dict) and "documents" in parsed:
                    documents = parsed.get("documents", [])
                    if self.callback:
                        self.callback("tool_result", {"documents": documents})
                    result = parsed.get("context", result)
            except (json.JSONDecodeError, TypeError):
                pass
            
            # 更新 agent_scratchpad
            new_scratchpad = state["agent_scratchpad"]
            new_scratchpad += f" 我需要使用 {tool_name} 工具\n"
            new_scratchpad += f"Action: {tool_name}\n"
            new_scratchpad += f"Action Input: {tool_input}\n"
            new_scratchpad += f"Observation: {str(result)[:1000]}\n"
            new_scratchpad += "Thought:"
            
            # 合并文档（去重）
            existing_uuids = {d["uuid"] for d in state["documents"] if d.get("uuid")}
            new_docs = [d for d in documents if d.get("uuid") and d["uuid"] not in existing_uuids]
            
            return {
                "agent_scratchpad": new_scratchpad,
                "tool_results": state["tool_results"] + [{"tool": tool_name, "result": str(result)[:200]}],
                "documents": state["documents"] + new_docs,
                "pending_action": None,
                "last_error": None,
                "error_type": None
            }
            
        except asyncio.TimeoutError:
            logger.error("工具执行超时")
            return {
                "last_error": "工具执行超时",
                "error_type": ErrorType.TIMEOUT_ERROR.value,
                "error_count": state["error_count"] + 1,
                "pending_action": None
            }
        except Exception as e:
            logger.error(f"行动节点错误: {e}")
            new_scratchpad = state["agent_scratchpad"]
            if state.get("pending_action"):
                tool_name = state["pending_action"]["tool_name"]
                tool_input = state["pending_action"]["tool_input"]
                new_scratchpad += f" 我需要使用 {tool_name} 工具\n"
                new_scratchpad += f"Action: {tool_name}\n"
                new_scratchpad += f"Action Input: {tool_input}\n"
                new_scratchpad += f"Observation: 工具执行失败: {str(e)}\n"
                new_scratchpad += "Thought:"
            
            return {
                "agent_scratchpad": new_scratchpad,
                "last_error": str(e),
                "error_type": ErrorType.TOOL_ERROR.value,
                "error_count": state["error_count"] + 1,
                "pending_action": None
            }

    async def _error_recovery_node(self, state: AgentState) -> AgentState:
        """错误恢复节点"""
        error_type = state.get("error_type", ErrorType.UNKNOWN_ERROR.value)
        error_count = state.get("error_count", 0)
        last_error = state.get("last_error", "未知错误")
        
        if error_count >= self.max_retries:
            logger.warning(f"错误次数超过限制 ({error_count}/{self.max_retries})，降级处理")
            return {
                "final_answer": f"抱歉，处理过程中遇到了一些问题。根据已有信息，我尝试为您解答。",
                "should_end": True
            }
        
        recovery_hint = self._get_recovery_message(error_type, last_error)
        new_scratchpad = state["agent_scratchpad"]
        new_scratchpad += f" {recovery_hint}\nThought:"
        
        return {
            "agent_scratchpad": new_scratchpad,
            "last_error": None,
            "error_type": None
        }
    
    def _get_recovery_message(self, error_type: str, error_detail: str) -> str:
        """根据错误类型生成恢复提示"""
        if error_type == ErrorType.TOOL_ERROR.value:
            return f"工具调用出错: {error_detail}。请尝试使用其他工具或简化参数，或直接基于已有信息回答。"
        elif error_type == ErrorType.PARSE_ERROR.value:
            return f"格式错误: {error_detail}。请按照正确格式输出。"
        elif error_type == ErrorType.TIMEOUT_ERROR.value:
            return f"操作超时: {error_detail}。请尝试简化请求。"
        elif error_type == ErrorType.LLM_ERROR.value:
            return f"处理出错: {error_detail}。请重新思考。"
        else:
            return f"遇到错误: {error_detail}。请尝试其他方式。"
    
    async def _finalize_node(self, state: AgentState) -> AgentState:
        """最终化节点 - 生成最终答案（流式输出）"""
        if state.get("final_answer"):
            # final_answer 已经通过流式输出发送了
            return {"should_end": True}
        
        # 如果没有最终答案，基于工具结果生成
        if state["tool_results"]:
            # 获取用户问题
            question = ""
            for msg in reversed(state["messages"]):
                if isinstance(msg, HumanMessage):
                    question = msg.content
                    break
            
            # 构建总结 prompt
            summary_prompt = f"""根据以下工具调用结果，给出简洁明了的最终答案。

用户问题: {question}

工具调用结果:
{state['agent_scratchpad']}

请直接给出最终答案，不需要再调用工具。"""
            
            # 流式调用 LLM 生成最终答案
            final_answer = await self._stream_llm_call(summary_prompt)
            
            # 清理答案格式
            if "Final Answer:" in final_answer:
                final_answer = final_answer.split("Final Answer:")[-1].strip()
            
            return {
                "final_answer": final_answer,
                "should_end": True
            }
        
        # 没有工具结果，返回默认答案
        default_answer = "抱歉，我无法找到相关信息来回答您的问题。"
        if self.callback:
            self.callback("llm_chunk", default_answer)
        
        return {
            "final_answer": default_answer,
            "should_end": True
        }
    
    def _route_after_think(self, state: AgentState) -> Literal["act", "finalize", "end"]:
        """思考后的路由决策"""
        if state["current_step"] >= state["max_steps"]:
            return "finalize"
        if state.get("last_error"):
            return "finalize"
        if state.get("final_answer"):
            return "finalize"
        if state.get("pending_action"):
            return "act"
        return "finalize"
    
    def _route_after_act(self, state: AgentState) -> Literal["think", "error_recovery", "finalize"]:
        """行动后的路由决策"""
        if state.get("last_error"):
            return "error_recovery"
        if state["current_step"] >= state["max_steps"]:
            return "finalize"
        return "think"
    
    def _route_after_recovery(self, state: AgentState) -> Literal["think", "finalize"]:
        """恢复后的路由决策"""
        if state.get("should_end"):
            return "finalize"
        return "think"
    
    def _get_history_text(self) -> str:
        """从 llm_service 获取历史记录文本"""
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
    
    @async_performance_monitor('agent_total', operation_name='LangGraph Agent推理', include_args=True, include_result=False)
    async def run(self, question: str, stream: bool = False) -> str:
        """运行 LangGraph Agent"""
        try:
            initial_state: AgentState = {
                "messages": [HumanMessage(content=question)],
                "current_step": 0,
                "max_steps": self.max_iterations,
                "error_count": 0,
                "last_error": None,
                "error_type": None,
                "tool_results": [],
                "final_answer": None,
                "documents": [],
                "should_end": False,
                "agent_scratchpad": "",
                "pending_action": None
            }
            
            final_state = await self.app.ainvoke(initial_state)
            
            return final_state.get("final_answer", "抱歉，我无法回答这个问题。")
            
        except Exception as e:
            logger.error(f"LangGraph Agent 执行失败: {e}", exc_info=True)
            return f"抱歉，处理过程中出现错误: {str(e)}"
    
    def get_collected_documents(self) -> List[Dict[str, Any]]:
        """获取收集的文档"""
        return []


def create_langgraph_agent(
    llm_service,
    tools_dict: Dict[str, Callable],
    max_iterations: int = 5,
    callback: Optional[Callable] = None
) -> LangGraphAgent:
    """创建 LangGraph Agent"""
    return LangGraphAgent(
        llm_service=llm_service,
        tools=tools_dict,
        max_iterations=max_iterations,
        callback=callback
    )
