"""Context shaping for expert mode."""

from typing import Any, Dict, List


class ExpertContextBuilder:
    def __init__(self, max_history_count: int = 5):
        self.max_history_count = max_history_count

    def build_supervisor_input(self, user_message: str, history: List[Dict[str, Any]]) -> str:
        history_text = self._format_history(history)
        if not history_text:
            return user_message
        return f"历史对话：\n{history_text}\n\n当前问题：\n{user_message}"

    def build_expert_input(
        self,
        expert_name: str,
        task: str,
        original_question: str,
        history: List[Dict[str, Any]],
    ) -> str:
        history_text = self._format_history(history)
        parts = [
            f"专家类型：{expert_name}",
            f"用户原始问题：{original_question}",
            f"当前分配任务：{task}",
        ]
        if history_text:
            parts.append(f"必要历史：\n{history_text}")
        return "\n\n".join(parts)

    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return ""

        selected = history[-self.max_history_count :]
        lines = []
        for message in selected:
            role = message.get("role") or message.get("send_type") or "unknown"
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
