"""
流式解析器
负责解析 LLM 输出的流式内容，识别 Thought/Action/Observation/Answer
"""
from typing import Dict, Any, Optional, Generator
from enum import Enum
from log import logger


class ParseState(Enum):
    """解析状态枚举"""
    IDLE = "idle"           # 空闲状态
    THOUGHT = "thought"     # 正在解析 Thought
    ACTION = "action"       # 正在解析 Action
    OBSERVATION = "observation"  # 正在解析 Observation
    ANSWER = "answer"       # 正在解析 Answer


class StreamParser:
    """
    流式解析器（状态机模式）
    
    负责解析 LLM 输出的流式内容，识别：
    - Thought: 思考过程
    - Action: 工具调用
    - Observation: 工具返回结果
    - Answer: 最终答案
    """
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """重置解析器状态"""
        self.state = ParseState.IDLE
        self.buffer = ""
        self.current_content = ""
        self.in_answer = False
        self.last_observation = None
    
    def parse_chunk(self, chunk: str) -> Optional[Dict[str, Any]]:
        """
        解析单个 chunk
        
        Args:
            chunk: LLM 输出的单个 chunk
            
        Returns:
            解析结果字典，包含 event 和 content，或 None
        """
        self.buffer += chunk
        
        # 检测状态转换
        result = self._detect_state_change()
        if result:
            return result
        
        # 根据当前状态处理内容
        return self._process_current_state(chunk)
    
    def _detect_state_change(self) -> Optional[Dict[str, Any]]:
        """检测状态转换"""
        
        # 检测 Thought:
        if self.state != ParseState.THOUGHT and 'Thought:' in self.buffer:
            self.state = ParseState.THOUGHT
            # 提取 Thought: 后面的内容
            parts = self.buffer.split('Thought:', 1)
            self.buffer = parts[1] if len(parts) > 1 else ""
            self.current_content = ""
            return None  # 状态转换，不立即返回内容
        
        # 检测 Action:
        if self.state != ParseState.ACTION and 'Action:' in self.buffer:
            old_state = self.state
            self.state = ParseState.ACTION
            # 提取 Action: 后面的内容
            parts = self.buffer.split('Action:', 1)
            self.buffer = parts[1] if len(parts) > 1 else ""
            self.current_content = ""
            return None
        
        # 检测 Observation:
        if self.state != ParseState.OBSERVATION and 'Observation:' in self.buffer:
            self.state = ParseState.OBSERVATION
            parts = self.buffer.split('Observation:', 1)
            self.buffer = parts[1] if len(parts) > 1 else ""
            self.current_content = ""
            return None
        
        # 检测 Answer: 或 Final Answer:
        if not self.in_answer and ('Answer:' in self.buffer or 'Final Answer:' in self.buffer):
            self.state = ParseState.ANSWER
            self.in_answer = True
            
            # 提取 Answer: 后面的内容
            if 'Final Answer:' in self.buffer:
                parts = self.buffer.split('Final Answer:', 1)
            else:
                parts = self.buffer.split('Answer:', 1)
            
            answer_content = parts[1].strip() if len(parts) > 1 else ""
            self.buffer = ""
            self.current_content = ""
            
            if answer_content:
                return {
                    "event": "answer_chunk",
                    "content": answer_content
                }
            return None
        
        return None
    
    def _process_current_state(self, chunk: str) -> Optional[Dict[str, Any]]:
        """根据当前状态处理内容"""
        
        # 过滤换行符
        if chunk in ['\n', '\r\n']:
            return None
        
        if self.state == ParseState.THOUGHT:
            # 检查是否遇到下一个关键字
            if 'Action:' in self.buffer or 'Answer:' in self.buffer:
                return None  # 让状态转换处理
            
            self.current_content += chunk
            return {
                "event": "thought",
                "content": chunk
            }
        
        elif self.state == ParseState.ACTION:
            # Action 内容通过回调获取，这里跳过
            return None
        
        elif self.state == ParseState.OBSERVATION:
            # Observation 内容通过回调获取，这里跳过
            return None
        
        elif self.state == ParseState.ANSWER:
            self.current_content += chunk
            return {
                "event": "answer_chunk",
                "content": chunk
            }
        
        return None
    
    def handle_callback_event(self, event_type: str, content: Any) -> Optional[Dict[str, Any]]:
        """
        处理来自 Agent 回调的事件
        
        Args:
            event_type: 事件类型（action, observation, tool_result, final_answer）
            content: 事件内容
            
        Returns:
            格式化的事件字典
        """
        if event_type == "action":
            return {
                "event": "action",
                "content": content
            }
        
        elif event_type == "observation":
            self.last_observation = content
            return {
                "event": "observation",
                "content": content
            }
        
        elif event_type == "final_answer":
            self.in_answer = True
            return {
                "event": "answer_chunk",
                "content": content
            }
        
        elif event_type == "tool_result":
            # tool_result 用于收集文档信息，不直接输出
            return None
        
        return None
    
    def get_remaining_answer(self) -> Optional[str]:
        """
        获取缓冲区中剩余的 Answer 内容
        
        Returns:
            剩余的 Answer 内容，或 None
        """
        if self.buffer.strip() and not self.in_answer:
            if 'Answer:' in self.buffer:
                parts = self.buffer.split('Answer:', 1)
                return parts[1].strip() if len(parts) > 1 else None
            elif 'Final Answer:' in self.buffer:
                parts = self.buffer.split('Final Answer:', 1)
                return parts[1].strip() if len(parts) > 1 else None
        return None
    
    def is_answer_sent(self) -> bool:
        """检查是否已发送答案"""
        return self.in_answer
    
    def should_skip_duplicate_answer(self, result: str) -> bool:
        """
        检查是否应该跳过重复的答案
        
        Args:
            result: Agent 返回的最终结果
            
        Returns:
            是否应该跳过
        """
        if self.last_observation and self.last_observation == result:
            logger.info("⚠️ 最终答案已作为 observation 发送，跳过重复发送")
            return True
        return False
