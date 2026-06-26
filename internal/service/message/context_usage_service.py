"""
会话上下文占用统计
"""
from typing import Any, Dict, List, Optional

from internal.model.message import MessageModel
from internal.service.message.context_builder import context_builder
from pkg.model_list import DEEPSEEK_CHAT


OFFICIAL_DEEPSEEK_CONTEXT_WINDOWS = {
    "deepseek-chat": 1_000_000,
}


class ContextUsageService:
    """统计当前会话计入上下文的内容占用"""

    def __init__(self):
        self._tokenizer = None
        self._tokenizer_checked = False

    def get_context_window(self) -> int:
        official_window = OFFICIAL_DEEPSEEK_CONTEXT_WINDOWS.get(DEEPSEEK_CHAT.name)
        if official_window:
            return official_window
        return int(DEEPSEEK_CHAT.context_window or 64000)

    def get_context_window_source(self) -> str:
        if DEEPSEEK_CHAT.name in OFFICIAL_DEEPSEEK_CONTEXT_WINDOWS:
            return "official"
        return "fallback"

    def _load_deepseek_tokenizer(self):
        if self._tokenizer_checked:
            return self._tokenizer

        self._tokenizer_checked = True
        try:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                "deepseek-ai/DeepSeek-V3",
                trust_remote_code=True,
                local_files_only=True,
            )
        except Exception:
            self._tokenizer = None
        return self._tokenizer

    def count_tokens(self, text: str) -> int:
        tokenizer = self._load_deepseek_tokenizer()
        if tokenizer is not None:
            return len(tokenizer.encode(text or ""))
        return self._estimate_tokens(text or "")

    def get_count_type(self) -> str:
        return "official" if self._load_deepseek_tokenizer() is not None else "estimated"

    def _estimate_tokens(self, text: str) -> int:
        chinese_chars = len([char for char in text if "\u4e00" <= char <= "\u9fff"])
        other_chars = len(text) - chinese_chars
        return max(0, int(chinese_chars * 1.5 + other_chars / 4))

    def _get_tools_snapshot(self):
        return context_builder.get_tools_snapshot()

    async def _find_latest_ai_messages(self, session_id: str):
        messages = await MessageModel.find(
            MessageModel.session_id == session_id,
            MessageModel.send_type == 1,
        ).sort(-MessageModel.created_at).limit(10).to_list()
        return messages

    async def _find_latest_actual_usage(self, session_id: str) -> Optional[int]:
        messages = await MessageModel.find(
            MessageModel.session_id == session_id,
            MessageModel.send_type == 1,
        ).sort(-MessageModel.created_at).limit(10).to_list()

        for msg in messages:
            prompt_tokens = self._extract_prompt_tokens(getattr(msg, "extra_data", None) or {})
            if prompt_tokens is not None:
                return prompt_tokens
        return None

    @staticmethod
    def _extract_prompt_tokens(extra_data: Dict[str, Any]) -> Optional[int]:
        usage = extra_data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
            return prompt_tokens
        return None

    def _with_section_tokens(self, sections):
        enriched = []
        total = 0
        context_window = self.get_context_window()
        for section in sections:
            tokens = self.count_tokens(section.get("content", ""))
            total += tokens
            item = dict(section)
            item["tokens"] = tokens
            item["percent"] = self._calculate_percent(tokens, context_window)
            enriched.append(item)
        return enriched, total

    @staticmethod
    def _calculate_percent(tokens: int, context_window: int) -> float:
        if context_window <= 0:
            return 0
        percent = min(100, round((tokens / context_window) * 100, 2))
        return percent

    def build_usage_snapshot(
        self,
        agent_key: str,
        agent_name: str,
        sections: List[Dict[str, Any]],
        used_tokens: Optional[int] = None,
        source: str = "preview",
        count_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        context_window = self.get_context_window()
        enriched, estimated_tokens = self._with_section_tokens(sections)
        actual_tokens = used_tokens if isinstance(used_tokens, int) and used_tokens >= 0 else None
        final_used_tokens = max(estimated_tokens, actual_tokens) if actual_tokens is not None else estimated_tokens
        final_count_type = count_type or self.get_count_type()
        percent = self._calculate_percent(final_used_tokens, context_window)
        result = {
            "agent_key": agent_key,
            "agent_name": agent_name,
            "model_name": DEEPSEEK_CHAT.name,
            "context_window": context_window,
            "context_window_source": self.get_context_window_source(),
            "used_tokens": final_used_tokens,
            "remaining_tokens": context_window - final_used_tokens,
            "percent": percent,
            "estimated_tokens": estimated_tokens,
            "count_type": final_count_type,
            "source": source,
            "sections": enriched,
        }
        if actual_tokens is not None:
            result["actual_tokens"] = actual_tokens
        return result

    def build_text_section_usage(
        self,
        agent_key: str,
        agent_name: str,
        title: str,
        content: str,
        section_type: str = "context",
        used_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.build_usage_snapshot(
            agent_key=agent_key,
            agent_name=agent_name,
            sections=[{
                "type": section_type,
                "title": title,
                "content": content or "",
                "estimated": used_tokens is None,
            }],
            used_tokens=used_tokens,
            source="preview" if used_tokens is None else "actual",
            count_type=None if used_tokens is None else "official",
        )

    @staticmethod
    def _get_saved_child_agent_usages(extra_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        saved = extra_data.get("agent_context_usage") or {}
        child_usages = saved.get("child_agent_usages") or []
        return child_usages if isinstance(child_usages, list) else []

    async def get_session_context_usage(self, session_id: str) -> Dict[str, Any]:
        context_window = self.get_context_window()
        preview = await context_builder.build_session_preview(session_id)
        sections, estimated_tokens = self._with_section_tokens(preview["sections"])
        latest_ai_messages = await self._find_latest_ai_messages(session_id)
        latest_extra_data = {}
        actual_prompt_tokens = None
        child_agent_usages = []
        for message in latest_ai_messages:
            extra_data = getattr(message, "extra_data", None) or {}
            if actual_prompt_tokens is None:
                actual_prompt_tokens = self._extract_prompt_tokens(extra_data)
                if actual_prompt_tokens is not None:
                    latest_extra_data = extra_data
            if not child_agent_usages:
                child_agent_usages = self._get_saved_child_agent_usages(extra_data)

        if actual_prompt_tokens is not None:
            used_tokens = max(estimated_tokens, actual_prompt_tokens)
            count_type = "official"
            source = "actual"
        else:
            used_tokens = estimated_tokens
            count_type = self.get_count_type()
            source = "preview"

        percent = self._calculate_percent(used_tokens, context_window)
        primary_agent_usage = {
            "agent_key": "supervisor",
            "agent_name": "主助手",
            "model_name": DEEPSEEK_CHAT.name,
            "context_window": context_window,
            "context_window_source": self.get_context_window_source(),
            "used_tokens": used_tokens,
            "remaining_tokens": context_window - used_tokens,
            "percent": percent,
            "estimated_tokens": estimated_tokens,
            "count_type": count_type,
            "source": source,
            "sections": sections,
        }
        if actual_prompt_tokens is not None:
            primary_agent_usage["actual_tokens"] = actual_prompt_tokens

        return {
            "model_name": DEEPSEEK_CHAT.name,
            "context_window": context_window,
            "context_window_source": self.get_context_window_source(),
            "used_tokens": used_tokens,
            "remaining_tokens": context_window - used_tokens,
            "percent": percent,
            "estimated_tokens": estimated_tokens,
            "actual_tokens": actual_prompt_tokens,
            "count_type": count_type,
            "source": source,
            "primary_agent_usage": primary_agent_usage,
            "child_agent_usages": child_agent_usages,
            "sections": sections,
            "items": sections,
        }


context_usage_service = ContextUsageService()
