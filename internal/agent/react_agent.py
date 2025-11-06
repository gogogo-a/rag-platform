"""
ReAct Agent 实现
基于 Reasoning + Acting 框架的智能代理
"""
import re
from typing import Dict, List, Callable, Any, Optional, Tuple
import logging
from internal.monitor import performance_monitor
from pkg.agent_tools.tool_validator import validate_and_fix_params

logger = logging.getLogger(__name__)


class ReActAgent:
    """ReAct 框架的 Agent 实现"""
    
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
        self.llm = llm_service
        self.tools = tools
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.callback = callback
    
    def _parse_action(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解析 LLM 输出中的 Action（使用括号匹配）
        
        Args:
            text: LLM 输出文本
            
        Returns:
            (action_name, action_params_str) 或 (None, None)
        """
        # 匹配 Action: None
        if re.search(r'Action:\s*None', text, re.IGNORECASE):
            return None, None
        
        # 找到 "Action:" 和工具名
        action_match = re.search(r'Action:\s*(\w+)\s*\(', text)
        if not action_match:
            return None, None
        
        tool_name = action_match.group(1)
        start_pos = action_match.end() - 1  # 左括号的位置
        
        # 使用括号匹配找到对应的右括号
        depth = 0
        i = start_pos
        in_string = False
        string_char = None
        escaped = False
        
        while i < len(text):
            char = text[i]
            
            # 处理转义字符
            if escaped:
                escaped = False
                i += 1
                continue
            
            if char == '\\':
                escaped = True
                i += 1
                continue
            
            # 处理字符串（引号内的括号不计数）
            if char in ('"', "'"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
            
            # 只在字符串外计数括号
            if not in_string:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth == 0:
                        # 找到匹配的右括号
                        params_str = text[start_pos + 1:i].strip()
                        
                        if self.verbose:
                            print(f"[解析] 工具: {tool_name}")
                            print(f"[解析] 参数长度: {len(params_str)} 字符")
                        
                        return tool_name, params_str
            
            i += 1
        
        # 没有找到匹配的右括号
        print(f"\n⚠️  [解析失败] 未找到匹配的右括号")
        print(f"   工具名: {tool_name}")
        print(f"   最终depth: {depth}")
        print(f"   in_string: {in_string}")
        print(f"   文本长度: {len(text)}")
        print(f"   起始位置: {start_pos}, 扫描到位置: {i}")
        if in_string:
            print(f"   ⚠️  仍在字符串中！string_char: {repr(string_char)}")
            print(f"   最后50字符: {text[i-50:i] if i > 50 else text[:i]}")
        return None, None
    
    def _extract_thought(self, text: str) -> str:
        """提取 Thought 内容"""
        match = re.search(r'Thought:\s*(.+?)(?=\n(?:Action|Answer|$))', text, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def _extract_answer(self, text: str) -> Optional[str]:
        """
        提取 Answer 内容
        只提取 Answer: 到下一个 Thought/Action/Observation 之前的内容
        """
        match = re.search(r'Answer:\s*(.+)', text, re.DOTALL)
        if not match:
            return None
        
        answer_text = match.group(1)
        
        # 截断到下一个关键字之前（Answer 后不应该再有这些）
        for keyword in ['Thought:', 'Action:', 'Observation:', '🤔']:
            pos = answer_text.find(keyword)
            if pos >= 0:
                answer_text = answer_text[:pos]
        
        return answer_text.strip() if answer_text.strip() else None
    
    def _parse_named_params(self, params_str: str) -> Dict[str, Any]:
        """
        手动解析命名参数，支持嵌套引号
        
        例如：key1="value1", key2="value with 'quotes'"
        
        Args:
            params_str: 参数字符串
            
        Returns:
            参数字典
        """
        params = {}
        i = 0
        n = len(params_str)
        
        while i < n:
            # 跳过空白和逗号
            while i < n and params_str[i] in ' ,\t\n':
                i += 1
            
            if i >= n:
                break
            
            # 查找参数名
            key_match = re.match(r'(\w+)\s*=\s*', params_str[i:])
            if not key_match:
                break
            
            key = key_match.group(1)
            i += key_match.end()
            
            if i >= n:
                break
            
            # 检查引号类型
            quote = params_str[i]
            if quote not in ('"', "'"):
                # 不是字符串值，可能是数字或其他
                value_match = re.match(r'([^,\)]+)', params_str[i:])
                if value_match:
                    params[key] = value_match.group(1).strip()
                    i += value_match.end()
                continue
            
            # 解析字符串值（支持转义）
            i += 1  # 跳过开始引号
            value_start = i
            escaped = False
            
            while i < n:
                if escaped:
                    escaped = False
                    i += 1
                    continue
                
                if params_str[i] == '\\':
                    escaped = True
                    i += 1
                    continue
                
                if params_str[i] == quote:
                    # 找到匹配的结束引号
                    value = params_str[value_start:i]
                    params[key] = value
                    i += 1  # 跳过结束引号
                    break
                
                i += 1
            else:
                # 没有找到结束引号，将剩余部分作为值
                value = params_str[value_start:]
                params[key] = value
                break
        
        return params
    
    def _parse_tool_params(self, params_str: str) -> Dict[str, Any]:
        """
        解析工具参数字符串为字典
        
        支持格式：
        - 位置参数: "查询内容", 5
        - 命名参数: location="116.73,39.52", extensions="base"
        - 混合: "查询内容", top_k=5
        
        Args:
            params_str: 参数字符串
            
        Returns:
            参数字典
        """
        params = {}
        
        # 改进的参数解析：手动解析以支持嵌套引号
        # 先尝试解析命名参数（key="value" 或 key='value'）
        params = self._parse_named_params(params_str)
        
        if not params:
            # 如果没有命名参数，尝试位置参数
            # 尝试匹配位置参数（兼容旧格式）
            # "query", 5 或 "query"
            positional_pattern = r'["\']([^"\']*)["\'](?:\s*,\s*["\']([^"\']*)["\'])?(?:\s*,\s*(\d+))?'
            match = re.search(positional_pattern, params_str)
            if match:
                # 第一个参数可能是 query 或其他
                first_param = match.group(1)
                second_param = match.group(2)
                third_param = match.group(3)
                
                if second_param:
                    # 有两个字符串参数，可能是 weather_query("北京", "base")
                    params['city'] = first_param
                    params['extensions'] = second_param
                elif third_param:
                    # 有一个字符串 + 一个数字，是 knowledge_search("查询", 5)
                    params['query'] = first_param
                    params['top_k'] = int(third_param)
                else:
                    # 只有一个参数，根据内容推断
                    # 如果是逗号分隔的经纬度，可能是 location
                    if ',' in first_param and all(c.replace('.', '').replace(',', '').replace('-', '').isdigit() for c in first_param.split()):
                        params['location'] = first_param
                    else:
                        # 默认为 query 或 city
                        params['query'] = first_param
        
        # 设置默认值
        if 'query' in params and 'top_k' not in params:
            params['top_k'] = 5
        
        if 'city' in params and 'extensions' not in params:
            params['extensions'] = 'base'
        
        return params
    
    def _execute_tool(self, tool_name: str, tool_input: str) -> str:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            tool_input: 工具参数字符串
            
        Returns:
            工具执行结果（字符串形式的 Observation）
        """
        if tool_name not in self.tools:
            return f"错误: 未知工具 '{tool_name}'"
        
        try:
            # 解析参数
            params = self._parse_tool_params(tool_input)
            
            if self.verbose:
                print(f"[执行] 解析后的参数: {params}")
            
            # 🔥 参数验证和自动修正
            try:
                params = validate_and_fix_params(tool_name, self.tools[tool_name], params)
                if self.verbose:
                    print(f"[执行] 验证后的参数: {params}")
            except ValueError as e:
                logger.error(f"参数验证失败: {e}")
                return f"参数验证失败: {str(e)}"
            
            # 执行工具
            result = self.tools[tool_name](**params)
            
            # 🔥 通过回调发送完整的工具结果（包含 documents 等元信息）
            if self.callback and isinstance(result, dict):
                self.callback("tool_result", result)
            
            # 格式化结果为 Observation 字符串
            if isinstance(result, dict):
                # 🔥 优先使用 summary 字段（如果存在）
                if "summary" in result and result["summary"]:
                    return result["summary"]
                
                # 兼容 knowledge_search 格式
                if result.get("success"):
                    if "context" in result:
                        # knowledge_search / web_search 格式
                        context = result.get("context", "")
                        count = result.get("count", 0)
                        return f"成功检索到 {count} 个相关文档片段：\n\n{context}"
                    else:
                        # 其他工具格式（如 email_sender）
                        return result.get("message", str(result))
                else:
                    message = result.get("message", "执行失败")
                    return f"执行失败: {message}"
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"工具执行失败: {e}", exc_info=True)
            return f"工具执行失败: {str(e)}"
    
    @performance_monitor('agent_total', operation_name='Agent完整推理', include_args=True, include_result=False)
    def run(self, question: str, stream: bool = False) -> str:
        """
        运行 ReAct Agent
        
        Args:
            question: 用户问题
            stream: 是否流式输出
            
        Returns:
            最终答案
        """
        # 🔥 关键修改：明确标记这是当前用户的新问题，与历史记录区分
        current_input = f"""⚠️ 重要：这是用户当前的新问题，请专注于回答这个问题，不要混淆历史对话。

【当前用户问题】: {question}

请按照 Thought-Action 的格式回答（如果需要工具，系统会返回 Observation）。"""
        last_action = None  # 记录上一次的 Action，用于检测重复
        has_observation = False  # 标记是否已经收到 Observation
        thought_only_count = 0  # 连续只有 Thought 没有 Action 的次数
        
        for iteration in range(self.max_iterations):
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"第 {iteration + 1} 轮推理")
                print(f"{'='*60}")
            
            # 1. LLM 生成 Thought 和 Action
            messages = [{"role": "user", "content": current_input}]
            
            response = ""
            if stream:
                print("\n🤔 ", end='', flush=True)
                # 用于检测Action是否完成的状态
                action_started = False
                action_complete = False
                
                for chunk in self.llm.chat(messages, stream=True):
                    # ⚠️ 重要：如果 action_complete 已经设置，不要再处理任何 chunk
                    if action_complete:
                        break
                    
                    # 检查是否包含 "Observation:"，如果有则立即停止
                    if "Observation:" in (response + chunk):
                        # 只保留 Observation: 之前的部分
                        remaining = (response + chunk).split("Observation:")[0]
                        if remaining != response:
                            stop_chunk = remaining[len(response):]
                            print(stop_chunk, end='', flush=True)
                            response += stop_chunk
                            if self.callback:
                                self.callback("llm_chunk", stop_chunk)
                        print()
                        if self.verbose:
                            print("\n⚠️  检测到 LLM 尝试生成 Observation，已停止")
                        break
                    
                    print(chunk, end='', flush=True)
                    if self.callback:
                        self.callback("llm_chunk", chunk)
                    response += chunk
                    
                    # 检测Action是否开始
                    if not action_started and 'Action:' in response:
                        action_started = True
                    
                    # 🔥 新方案：使用括号匹配，一旦Action的括号匹配完成就停止
                    if action_started and not action_complete:
                        # 找到 "Action:" 的位置
                        action_pos = response.find('Action:')
                        if action_pos >= 0:
                            after_action = response[action_pos + len('Action:'):]
                            
                            # 查找第一个左括号
                            first_paren = after_action.find('(')
                            if first_paren >= 0:
                                # 从第一个左括号开始匹配
                                paren_depth = 0
                                in_string = False
                                string_char = None
                                escaped = False
                                
                                for i, char in enumerate(after_action[first_paren:], start=first_paren):
                                    if escaped:
                                        escaped = False
                                        continue
                                    
                                    if char == '\\':
                                        escaped = True
                                        continue
                                    
                                    # 处理字符串
                                    if char in ('"', "'"):
                                        if not in_string:
                                            in_string = True
                                            string_char = char
                                        elif char == string_char:
                                            in_string = False
                                            string_char = None
                                    
                                    # 只在字符串外计数括号
                                    if not in_string:
                                        if char == '(':
                                            paren_depth += 1
                                        elif char == ')':
                                            paren_depth -= 1
                                            if paren_depth == 0:
                                                # 括号匹配完成！立即停止
                                                action_end_pos = action_pos + len('Action:') + i + 1
                                                response = response[:action_end_pos]
                                                action_complete = True
                                                break
                                
                                if action_complete:
                                    break
                    
                    # 旧的检测逻辑作为备用
                    if action_started and not action_complete:
                        # 检查response是否包含完整的Action + 新内容
                        # 策略：如果response中同时有 "Action:" 和后续的 "Thought:"/"Answer:"/"🤔"
                        # 说明Action已经完成，应该停止
                        
                        # 找到Action的位置
                        action_pos = response.find('Action:')
                        if action_pos >= 0:
                            after_action = response[action_pos:]
                            # 检查Action后面是否有新的块（通过查找连续的关键字）
                            # 降低检测门槛到10字符，确保能及时检测到
                            if len(after_action) > 10:  # Action至少要有10字符
                                # 检测模式：查找 ) 后面跟着 换行 + Thought/Answer/🤔
                                import re
                                # 在Action后面查找 ) 后面跟着 Thought: 或 Answer: 或 🤔
                                # 使用更宽松的模式，允许任意空白字符（包括换行）
                                end_patterns = [
                                    r'\)\s+Thought:',        # ) 后面有空白 + Thought:
                                    r'\)\s+🤔',              # ) 后面有空白 + 🤔
                                    r'\)\s+Answer:',         # ) 后面有空白 + Answer:
                                    r'"\)\s+Thought:',       # 带引号版本
                                    r'"\)\s+🤔',
                                    r'"\)\s+Answer:',
                                ]
                                
                                # 额外保护：如果Action后出现这些关键字，强制截断
                                # 即使没有完整匹配到模式，也要截断
                                if not action_complete and ('Thought:' in after_action or '🤔' in after_action or 'Answer:' in after_action):
                                    # 找到关键字的位置，截断到Action的最后一个右括号
                                    thought_pos = after_action.find('Thought:')
                                    emoji_pos = after_action.find('🤔')
                                    answer_pos = after_action.find('Answer:')
                                    
                                    # 找到最早出现的关键字位置
                                    keyword_positions = [p for p in [thought_pos, emoji_pos, answer_pos] if p >= 0]
                                    if keyword_positions:
                                        earliest_keyword = min(keyword_positions)
                                        # 在关键字之前找到最后一个 )
                                        before_keyword = after_action[:earliest_keyword]
                                        last_paren = before_keyword.rfind(')')
                                        if last_paren >= 0:
                                            action_end_pos = action_pos + last_paren + 1
                                            response = response[:action_end_pos]
                                            action_complete = True
                                
                                for pattern in end_patterns:
                                    match = re.search(pattern, after_action)
                                    if match:
                                        # 截断response，只保留到Action的 ) 为止
                                        cut_text = after_action[:match.end()]
                                        last_paren = cut_text.rfind(')')
                                        if last_paren >= 0:
                                            action_end_pos = action_pos + last_paren + 1
                                            response = response[:action_end_pos]
                                        action_complete = True
                                        break
                        
                        if action_complete:
                            break
                else:
                    print()
            else:
                for chunk in self.llm.chat(messages, stream=False):
                    response += chunk
                    # 非流式也要检查
                    if "Observation:" in response:
                        response = response.split("Observation:")[0]
                        break
            
            if self.verbose and not stream:
                print(f"\nLLM 输出:\n{response}")
            
            # 2. 检查是否有 Answer
            answer = self._extract_answer(response)
            if answer:
                if self.verbose:
                    print(f"\n✅ 找到最终答案")
                return answer
            
            # 3. 解析 Action
            tool_name, tool_input = self._parse_action(response)
            
            # 注意：Thought 和 Action 都由 message_sever.py 流式解析
            # 这里只负责工具执行
            
            # 4. 检测重复 Action（防止循环）
            current_action = f"{tool_name}:{tool_input}" if tool_name else None
            if current_action and current_action == last_action and has_observation:
                if self.verbose:
                    print("\n⚠️  检测到重复 Action，强制要求给出 Answer")
                current_input = f"""{response}

⚠️ 警告：你已经执行过这个查询并收到了结果。不要重复查询！
请直接基于之前的 Observation 给出 Answer。

现在请给出最终答案（Answer:）"""
                continue
            
            # 5. 多工具协作支持
            # 注意：不再阻止在有 Observation 后调用新工具
            # 只有重复调用同一个工具才会被上面的逻辑拦截（第570行）
            # 这样允许：web_search → email_sender 这样的多工具协作
            
            # 6. 如果 Action 是 None，要求 LLM 给出答案
            if tool_name is None:
                thought_only_count += 1  # 增加计数器
                thought = self._extract_thought(response)
                
                # 🔥 如果连续 2 次没有 Action，强制要求给出答案或调用工具
                if thought_only_count >= 2:
                    if self.verbose:
                        print(f"\n⚠️  连续 {thought_only_count} 次没有 Action，强制要求给出答案")
                    current_input = f"""{response}

⚠️ 警告：你已经连续 {thought_only_count} 次只有 Thought 没有 Action！

你必须立即做出选择：
1. 如果需要使用工具，立即指定 Action（格式: Action: tool_name(参数)）
2. 如果不需要工具，立即给出 Answer

不要再只输出 Thought！现在就给出 Action 或 Answer！"""
                    continue
                
                if "Action: None" in response or "Action:None" in response:
                    if self.verbose:
                        print("\n📌 LLM 决定不使用工具，直接回答")
                    current_input = f"{response}\n\n请直接给出 Answer。"
                    continue
                else:
                    # 没有找到有效的 Action，提示 LLM
                    if self.verbose:
                        print("\n⚠️  未找到有效的 Action，提示 LLM")
                    current_input = f"{response}\n\n请明确指定 Action（格式: Action: tool_name(param='value') 或 Action: None）"
                    continue
            
            # 7. 执行工具
            # 重置计数器（因为找到了 Action）
            thought_only_count = 0
            
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"🔧 执行工具: {tool_name}")
                print(f"{'='*60}")
                print(f"   参数: {tool_input[:100]}..." if len(tool_input) > 100 else f"   参数: {tool_input}")
            
            observation = self._execute_tool(tool_name, tool_input)
            
            # 🔥 通过回调发送 Observation 事件
            if self.callback:
                self.callback("observation", observation)
            
            # 记录已执行的 Action 和标记已有 Observation
            last_action = current_action
            has_observation = True
            
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"📊 工具执行结果（Observation）")
                print(f"{'='*60}")
                print(f"观察内容总长度: {len(observation)} 字符")
                # 显示前500个字符（增加显示长度）
                if len(observation) > 500:
                    print(f"\n{observation[:500]}...")
                    print(f"\n[... 还有 {len(observation) - 500} 个字符]")
                else:
                    print(f"\n{observation}")
            
            # 8. 构建下一轮输入 - 强制要求只使用 Observation 内容
            current_input = f"""{response}

Observation: {observation}

❗❗❗ 关键指令 - 必须立即回答 ❗❗❗
工具已执行完毕！你已经获得了所需的信息。

**现在你必须做以下事情：**
1. **立即给出 Answer**（使用 Observation 中的内容）
2. **严禁再次重复调用工具**（可以使用别的工具）
3. **不要重复之前的 Thought**

正确格式：
Answer: [直接基于 Observation 中的内容回答用户问题]

现在立即给出最终答案："""
            
            # 调试：显示发送给 LLM 的完整内容长度
            if self.verbose:
                print(f"\n[调试] 发送给 LLM 的内容总长度: {len(current_input)} 字符")
                print(f"[调试] 其中 Observation 长度: {len(observation)} 字符")
                # 显示 Observation 的前200字符，确认内容确实包含了
                obs_preview = observation[:200] if len(observation) > 200 else observation
                print(f"[调试] Observation 前200字符:\n{obs_preview}...")
        
        # 达到最大迭代次数
        return "抱歉，我无法在规定步骤内完成推理。请重新提问或简化问题。"


def create_react_agent(llm_service, tools_dict: Dict[str, Callable]) -> ReActAgent:
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

