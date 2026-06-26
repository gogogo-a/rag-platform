"""
流式解析器
负责解析 LLM 输出的流式内容，识别 Thought/Action/Observation/Answer
"""
from typing import Dict, Any, Optional, List
from enum import Enum
import re
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

    _MARKERS = ("Thought:", "Action:", "Action Input:", "Observation:", "Answer:", "Final Answer:")
    _CONTROL_MARKERS = ("Action:", "Action Input:", "Observation:", "Answer:", "Final Answer:")
    _MARKER_PATTERN = re.compile(r"(\*\*)?\s*(Thought|Action Input|Action|Observation|Final Answer|Answer)\s*:\s*(\*\*)?")
    _MARKER_ONLY_LINE_PATTERN = re.compile(r"(?im)^\s*(Thought|Action Input|Action|Observation|Final Answer|Answer)\s*$")
    
    def reset(self):
        """重置解析器状态"""
        self.state = ParseState.IDLE
        self.buffer = ""
        self.current_content = ""
        self.in_answer = False
        self.last_observation = None
        self.observations: List[str] = []
        self._answer_started_without_content = False
        self._strip_next_answer_chunk = False
        self._pending_events: List[Dict[str, Any]] = []
        self._state_changed = False
    
    def parse_chunk(self, chunk: str) -> Optional[Dict[str, Any]]:
        """
        解析单个 chunk
        
        Args:
            chunk: LLM 输出的单个 chunk
            
        Returns:
            解析结果字典，包含 event 和 content，或 None
        """
        self.buffer += chunk

        if self._pending_events:
            return self._pending_events.pop(0)

        if self.state == ParseState.ANSWER:
            if self._strip_next_answer_chunk:
                self._strip_next_answer_chunk = False
                chunk = chunk.lstrip()
                if not chunk:
                    return None
            return self._process_current_state(chunk)
        
        # 检测状态转换
        while True:
            self._state_changed = False
            result = self._detect_state_change()
            if result:
                return result
            if self._pending_events:
                return self._pending_events.pop(0)
            if not self._state_changed:
                break

        if self._answer_started_without_content:
            self._answer_started_without_content = False
            return None

        if self.state == ParseState.IDLE and self._is_plain_answer_buffer():
            if self._looks_like_unmarked_reasoning(self.buffer) or self._looks_like_react_trace(self.buffer):
                self.state = ParseState.THOUGHT
                event_type = "thought"
            else:
                self.state = ParseState.ANSWER
                self.in_answer = True
                event_type = "answer_chunk"

            answer_content = self.buffer.lstrip()
            self.buffer = ""
            if answer_content:
                if event_type == "thought" and self._looks_like_react_trace(answer_content):
                    return None
                return {
                    "event": event_type,
                    "content": answer_content
                }

        # 根据当前状态处理内容
        return self._process_current_state(chunk)

    def _is_plain_answer_buffer(self) -> bool:
        stripped = self.buffer.lstrip()
        if not stripped:
            return False
        return not self._could_be_marker_prefix(stripped)

    def _looks_like_unmarked_reasoning(self, text: str) -> bool:
        stripped = text.lstrip()
        reasoning_phrases = (
            "好的",
            "需要检索",
            "需要先检索",
            "需要查询",
            "需要先查询",
            "需要搜索",
            "需要先搜索",
            "需要整理",
            "我需要检索",
            "我需要查询",
            "我需要搜索",
            "我需要先检索",
            "我需要先查询",
            "我需要先搜索",
            "需要从知识库",
            "需要从网络",
            "需要从知识库或网络",
            "我需要从知识库",
            "我需要从网络",
            "我需要从知识库或网络",
            "可以先搜索",
            "我可以先搜索",
            "可以进行网页搜索",
            "搜索知识库",
            "搜索网页",
            "获取最新资料",
            "需要提供系统性的指导",
            "这是一个技术性较强的问题",
            "同时也可以进行网页搜索",
        )
        return any(phrase in stripped for phrase in reasoning_phrases)

    def _looks_like_react_trace(self, text: str) -> bool:
        return (
            any(marker in text for marker in ("Thought:", "Action:", "Action Input:", "Observation:"))
            or bool(self._MARKER_ONLY_LINE_PATTERN.search(text))
        )

    def _split_process_prefix_answer(self, text: str) -> tuple[str, str]:
        if not self._looks_like_unmarked_reasoning(text):
            return "", text
        answer_starters = (
            "要自制一个",
            "可以参考以下",
            "建议按",
            "你可以按",
            "具体可以",
            "核心步骤",
        )
        indexes = [text.find(starter) for starter in answer_starters if text.find(starter) > 0]
        if not indexes:
            return text, ""
        split_at = min(indexes)
        return text[:split_at], text[split_at:]

    def _could_be_marker_prefix(self, text: str) -> bool:
        return any(marker.startswith(text) for marker in self._MARKERS)

    def _find_next_marker(self) -> Optional[tuple[int, str]]:
        match = self._MARKER_PATTERN.search(self.buffer)
        if not match:
            return None
        return match.start(), f"{match.group(2)}:"

    def _consume_marker(self, marker_name: str) -> None:
        match = self._MARKER_PATTERN.match(self.buffer)
        if match and match.group(2) == marker_name:
            self.buffer = self.buffer[match.end():]
            return
        marker = f"{marker_name}:"
        if self.buffer.startswith(marker):
            self.buffer = self.buffer[len(marker):]

    def _take_thought_before_marker(self, marker_index: int) -> Optional[Dict[str, Any]]:
        thought = self.buffer[:marker_index].strip()
        if thought:
            return {
                "event": "thought",
                "content": thought
            }
        return None

    def _split_trailing_control_prefix(self) -> tuple[str, str]:
        for index in range(len(self.buffer)):
            suffix = self.buffer[index:].lstrip()
            if suffix and any(marker.startswith(suffix) for marker in self._CONTROL_MARKERS):
                return self.buffer[:index], self.buffer[index:]
        return self.buffer, ""

    def _is_control_residue(self, text: str) -> bool:
        stripped = text.strip()
        return bool(stripped) and any(marker.startswith(stripped) for marker in self._CONTROL_MARKERS)
    
    def _detect_state_change(self) -> Optional[Dict[str, Any]]:
        """检测状态转换"""
        
        marker_match = self._find_next_marker()
        if not marker_match:
            return None

        marker_index, marker = marker_match

        if marker_index > 0:
            thought_event = self._take_thought_before_marker(marker_index)
            self.buffer = self.buffer[marker_index:]
            self.current_content = ""
            if thought_event and self.state in {ParseState.IDLE, ParseState.THOUGHT}:
                return thought_event

        # 检测 Thought:
        if marker == "Thought:":
            self.state = ParseState.THOUGHT
            self._consume_marker("Thought")
            self.current_content = ""
            self._state_changed = True
            return None

        # 检测 Action 或 Action Input:
        if marker in {"Action:", "Action Input:"}:
            self.state = ParseState.ACTION
            self._consume_marker(marker.rstrip(":"))
            self.current_content = ""
            self._state_changed = True
            return None

        # 检测 Observation:
        if marker == "Observation:":
            self.state = ParseState.OBSERVATION
            self._consume_marker("Observation")
            self.current_content = ""
            self._state_changed = True
            return None

        # 检测 Answer: 或 Final Answer:
        if not self.in_answer and marker in {"Answer:", "Final Answer:"}:
            self.state = ParseState.ANSWER
            self.in_answer = True
            self._state_changed = True
            
            # 提取 Answer: 后面的内容
            self._consume_marker(marker.rstrip(":"))
            answer_content = self.buffer.lstrip()
            self.buffer = ""
            self.current_content = ""
            
            if answer_content:
                return {
                    "event": "answer_chunk",
                    "content": answer_content
                }
            self._answer_started_without_content = True
            self._strip_next_answer_chunk = True
            return None
        
        return None
    
    def _process_current_state(self, chunk: str) -> Optional[Dict[str, Any]]:
        """根据当前状态处理内容"""
        
        # 过滤换行符
        if chunk in ['\n', '\r\n']:
            return None
        
        if self.state == ParseState.THOUGHT:
            # 检查是否遇到下一个关键字
            marker_match = self._find_next_marker()
            if marker_match:
                result = self._detect_state_change()
                if result:
                    return result
                if self._pending_events:
                    return self._pending_events.pop(0)
                return None  # 让状态转换处理

            stable_content, pending_prefix = self._split_trailing_control_prefix()
            if stable_content:
                _, answer_suffix = self._split_process_prefix_answer(stable_content)
                if answer_suffix:
                    self.state = ParseState.ANSWER
                    self.in_answer = True
                    self.buffer = pending_prefix
                    self.current_content = answer_suffix
                    return {
                        "event": "answer_chunk",
                        "content": answer_suffix
                    }
                content = stable_content.lstrip() if not self.current_content else stable_content
                self.buffer = pending_prefix
                self.current_content += content
                return {
                    "event": "thought",
                    "content": content
                }

            stripped_buffer = self.buffer.lstrip()
            if any(marker.startswith(stripped_buffer) for marker in self._CONTROL_MARKERS):
                return None

            content = self.buffer.lstrip() if not self.current_content else self.buffer
            _, answer_suffix = self._split_process_prefix_answer(content)
            if answer_suffix:
                self.buffer = ""
                self.state = ParseState.ANSWER
                self.in_answer = True
                self.current_content = answer_suffix
                return {
                    "event": "answer_chunk",
                    "content": answer_suffix
                }
            self.buffer = ""
            self.current_content += content
            return {
                "event": "thought",
                "content": content
            }
        
        elif self.state == ParseState.ACTION:
            # Action 内容通过回调获取，这里跳过
            return None
        
        elif self.state == ParseState.OBSERVATION:
            # Observation 内容通过回调获取，这里跳过
            return None
        
        elif self.state == ParseState.ANSWER:
            if self._looks_like_unmarked_reasoning(chunk):
                _, answer_suffix = self._split_process_prefix_answer(chunk)
                if answer_suffix:
                    self.current_content += answer_suffix
                    return {
                        "event": "answer_chunk",
                        "content": answer_suffix
                    }
                self.state = ParseState.THOUGHT
                self.in_answer = False
                return {
                    "event": "thought",
                    "content": chunk
                }
            marker_match = self._find_next_marker()
            if marker_match and marker_match[1] in {"Thought:", "Action:", "Action Input:", "Observation:"}:
                stable_content = self.buffer[:marker_match[0]]
                self.buffer = self.buffer[marker_match[0]:]
                self.state = ParseState.ACTION if marker_match[1] in {"Action:", "Action Input:"} else ParseState.OBSERVATION
                self.current_content = ""
                if stable_content and not self._is_control_residue(stable_content):
                    self.current_content += stable_content
                    return {
                        "event": "answer_chunk",
                        "content": stable_content
                    }
                return None
            stable_content, pending_prefix = self._split_trailing_control_prefix()
            if pending_prefix:
                self.buffer = pending_prefix
                if stable_content and not self._is_control_residue(stable_content):
                    self.current_content += stable_content
                    return {
                        "event": "answer_chunk",
                        "content": stable_content
                    }
                return None
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
            if content:
                self.observations.append(str(content))
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

    def get_observations(self) -> List[str]:
        return list(self.observations)
    
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

    def clean_final_result(self, result: str) -> Optional[str]:
        """
        从 Agent 最终返回里提取可展示答案。
        """
        if not result:
            return None

        answer_markers = [
            match for match in self._MARKER_PATTERN.finditer(result)
            if match.group(2) in {"Answer", "Final Answer"}
        ]
        if answer_markers:
            parser = StreamParser()
            answer_parts: List[str] = []
            for chunk in result[answer_markers[-1].start():].splitlines(keepends=True):
                parsed = parser.parse_chunk(chunk)
                if parsed and parsed["event"] == "answer_chunk":
                    answer_parts.append(parsed["content"])
            cleaned = "".join(answer_parts).strip()
            return cleaned or None

        if self._looks_like_react_trace(result) or self._looks_like_unmarked_reasoning(result):
            return None

        return result.strip() or None
