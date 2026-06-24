"""
聊天上下文构造
"""
from typing import Any, Dict, List, Tuple

from internal.model.message import MessageModel
from pkg.agent_prompt.prompt_templates import get_agent_prompt


REACT_PROMPT_TEMPLATE = """尽你所能回答以下问题。你可以使用以下工具：

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


class ContextBuilder:
    """构造聊天模型请求预览"""

    async def build_session_preview(self, session_id: str) -> Dict[str, Any]:
        messages = await self._get_context_messages(session_id)
        latest_user_message = self._latest_user_message(messages)
        history_messages = messages[:-1] if latest_user_message else messages
        question = latest_user_message.content if latest_user_message else ""
        tools_text, tool_names = self.get_tools_snapshot()

        sections = [
            self._section("system_prompt", "系统提示词", get_agent_prompt(use_multi_tool=True)),
            self._section(
                "react_template",
                "ReAct 模板",
                REACT_PROMPT_TEMPLATE
                .replace("{tools}", tools_text)
                .replace("{tool_names}", tool_names)
                .replace("{chat_history}", "{历史消息}")
                .replace("{input}", "{当前问题}")
                .replace("{agent_scratchpad}", "{运行时工具轨迹}"),
            ),
            self._section("tools", "工具列表", self._format_tools_section(tools_text, tool_names)),
        ]

        summary_text = self._format_summary(messages)
        if summary_text:
            sections.append(self._section("summary", "历史总结", summary_text))

        history_text = self._format_history(history_messages)
        if history_text:
            sections.append(self._section("history", "历史消息", history_text))

        if question:
            sections.append(self._section("current_question", "当前问题", question))

        runtime_text = "本区内容会随本轮工具调用和观察结果增长；有官方实际用量时以实际用量为准。"
        sections.append(self._section("runtime", "运行时工具轨迹", runtime_text, estimated=False))

        return {
            "messages": messages,
            "sections": sections,
            "current_question": question,
            "tools_text": tools_text,
            "tool_names": tool_names,
        }

    async def _get_latest_summary(self, session_id: str):
        summaries = await MessageModel.find(
            MessageModel.session_id == session_id,
            MessageModel.send_type == 2,
        ).sort(-MessageModel.created_at).limit(1).to_list()
        return summaries[0] if summaries else None

    async def _get_context_messages(self, session_id: str) -> List[MessageModel]:
        latest_summary = await self._get_latest_summary(session_id)
        if latest_summary:
            messages_after_summary = await MessageModel.find(
                MessageModel.session_id == session_id,
                MessageModel.created_at > latest_summary.created_at,
                MessageModel.send_type != 2,
            ).sort(MessageModel.created_at).to_list()
            return [latest_summary, *messages_after_summary]

        return await MessageModel.find(
            MessageModel.session_id == session_id,
            MessageModel.send_type != 2,
        ).sort(MessageModel.created_at).to_list()

    def get_tools_snapshot(self) -> Tuple[str, str]:
        try:
            from pkg.agent_tools_mcp import mcp_manager

            tools = mcp_manager.get_tools()
        except Exception:
            tools = []

        tool_lines = []
        tool_names = []
        for tool in tools:
            name = getattr(tool, "name", "")
            description = getattr(tool, "description", "") or ""
            if name:
                tool_names.append(name)
                tool_lines.append(f"{name}: {description}")

        return "\n".join(tool_lines), ", ".join(tool_names)

    def _section(self, section_type: str, title: str, content: str, estimated: bool = True) -> Dict[str, Any]:
        return {
            "type": section_type,
            "title": title,
            "content": content or "",
            "estimated": estimated,
        }

    def _latest_user_message(self, messages: List[MessageModel]):
        for msg in reversed(messages):
            if getattr(msg, "send_type", None) == 0:
                return msg
        return None

    def _format_summary(self, messages: List[MessageModel]) -> str:
        for msg in messages:
            if getattr(msg, "send_type", None) == 2:
                return f"[历史对话总结]\n{msg.content or ''}"
        return ""

    def _format_history(self, messages: List[MessageModel]) -> str:
        parts = []
        for msg in messages:
            send_type = getattr(msg, "send_type", None)
            if send_type == 2:
                continue
            if send_type == 0:
                role = "用户"
            elif send_type == 1:
                role = "AI"
            else:
                role = "系统"
            parts.append(f"{role}: {msg.content or ''}")
        if not parts:
            return ""
        return "--- 以下是历史对话记录---\n" + "\n".join(parts) + "\n--- 以上是历史对话，以下是用户当前的新问题 ---"

    def _format_tools_section(self, tools_text: str, tool_names: str) -> str:
        if not tools_text and not tool_names:
            return "当前没有可用工具。"
        return f"可用工具：{tool_names}\n\n{tools_text}"


context_builder = ContextBuilder()
