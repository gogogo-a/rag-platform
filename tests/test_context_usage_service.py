import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from internal.service.message.context_usage_service import context_usage_service


class FakeMessageQuery:
    def __init__(self, messages):
        self.messages = list(messages)

    def sort(self, *args):
        reverse = bool(args and isinstance(args[0], int) and args[0] < 0)
        self.messages.sort(key=lambda item: item.created_at, reverse=reverse)
        return self

    def limit(self, count):
        self.messages = self.messages[:count]
        return self

    async def to_list(self):
        return self.messages


class FakeField:
    def __init__(self, name):
        self.name = name

    def __neg__(self):
        return ("desc", self.name)

    def __eq__(self, other):
        return (self.name, "eq", other)

    def __ne__(self, other):
        return (self.name, "ne", other)

    def __gt__(self, other):
        return (self.name, "gt", other)


class FakeMessageModel:
    session_id = FakeField("session_id")
    send_type = FakeField("send_type")
    created_at = FakeField("created_at")
    messages = []

    @classmethod
    def find(cls, *conditions):
        items = list(cls.messages)
        for condition in conditions:
            if condition == ("send_type", "eq", 2):
                items = [item for item in items if item.send_type == 2]
            elif condition == ("send_type", "ne", 2):
                items = [item for item in items if item.send_type != 2]
            elif isinstance(condition, tuple) and condition[:2] == ("created_at", "gt"):
                items = [item for item in items if item.created_at > condition[2]]
        return FakeMessageQuery(items)


class ContextUsageServiceTest(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 6, 24, 10, 0, 0)
        self.user_msg = SimpleNamespace(
            uuid="user-msg",
            send_type=0,
            content="用户问题",
            send_name="我",
            created_at=base,
            send_at=base,
            extra_data={},
        )
        self.ai_msg = SimpleNamespace(
            uuid="ai-msg",
            send_type=1,
            content="AI 回答",
            send_name="AI助手",
            created_at=base + timedelta(seconds=1),
            send_at=base + timedelta(seconds=1),
            extra_data={},
        )
        self.summary_msg = SimpleNamespace(
            uuid="summary-msg",
            send_type=2,
            content="历史总结",
            send_name="系统",
            created_at=base + timedelta(seconds=2),
            send_at=base + timedelta(seconds=2),
            extra_data={},
        )
        self.new_msg = SimpleNamespace(
            uuid="new-msg",
            send_type=0,
            content="新的问题",
            send_name="我",
            created_at=base + timedelta(seconds=3),
            send_at=base + timedelta(seconds=3),
            extra_data={},
        )

    def test_context_usage_without_summary_counts_prompt_tools_and_messages(self):
        FakeMessageModel.messages = [self.user_msg, self.ai_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", side_effect=lambda text: len(text)), \
             patch.object(context_usage_service, "_get_tools_snapshot", return_value=("工具A说明", "tool_a")):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        self.assertEqual(result["model_name"], "deepseek-chat")
        section_titles = [section["title"] for section in result["sections"]]
        self.assertIn("系统提示词", section_titles)
        self.assertIn("ReAct 模板", section_titles)
        self.assertIn("工具列表", section_titles)
        self.assertIn("历史消息", section_titles)
        self.assertGreater(result["used_tokens"], len("用户问题") + len("AI 回答"))
        self.assertEqual(result["remaining_tokens"], result["context_window"] - result["used_tokens"])
        self.assertEqual(result["count_type"], "estimated")

    def test_deepseek_chat_uses_official_context_window_metadata(self):
        FakeMessageModel.messages = [self.user_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", return_value=1), \
             patch.object(context_usage_service, "_get_tools_snapshot", return_value=("", "")):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        self.assertEqual(result["context_window"], 1_000_000)
        self.assertEqual(result["context_window_source"], "official")
        self.assertEqual(result["primary_agent_usage"]["context_window"], 1_000_000)

    def test_deepseek_model_default_window_matches_official_metadata(self):
        from pkg.model_list import DEEPSEEK_CHAT

        self.assertEqual(DEEPSEEK_CHAT.context_window, 1_000_000)

    def test_section_percent_uses_context_window_not_used_tokens(self):
        self.ai_msg.extra_data = {"usage": {"prompt_tokens": 100}}
        FakeMessageModel.messages = [self.user_msg, self.ai_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", return_value=500), \
             patch.object(context_usage_service, "get_context_window", return_value=1000):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        self.assertEqual(result["used_tokens"], 3000)
        self.assertEqual(result["actual_tokens"], 100)
        self.assertEqual(result["estimated_tokens"], 3000)
        self.assertTrue(result["sections"])
        self.assertTrue(all(section["percent"] == 50 for section in result["sections"]))
        self.assertEqual(result["primary_agent_usage"]["percent"], 100)

    def test_context_usage_with_summary_counts_latest_summary_and_new_messages(self):
        FakeMessageModel.messages = [self.user_msg, self.ai_msg, self.summary_msg, self.new_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", side_effect=lambda text: len(text)), \
             patch.object(context_usage_service, "_get_tools_snapshot", return_value=("", "")):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        summary_section = next(section for section in result["sections"] if section["type"] == "summary")
        question_section = next(section for section in result["sections"] if section["type"] == "current_question")
        self.assertIn("历史总结", summary_section["content"])
        self.assertIn("新的问题", question_section["content"])
        self.assertNotIn("用户问题", question_section["content"])
        self.assertNotIn("AI 回答", question_section["content"])

    def test_context_usage_keeps_section_total_when_saved_prompt_tokens_are_lower(self):
        self.ai_msg.extra_data = {"usage": {"prompt_tokens": 1234}}
        FakeMessageModel.messages = [self.user_msg, self.ai_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", return_value=1):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        self.assertEqual(result["used_tokens"], 1234)
        self.assertEqual(result["actual_tokens"], 1234)
        self.assertEqual(result["source"], "actual")
        self.assertEqual(result["count_type"], "official")

    def test_context_usage_never_reports_less_than_section_total(self):
        self.ai_msg.extra_data = {"usage": {"prompt_tokens": 10}}
        FakeMessageModel.messages = [self.user_msg, self.ai_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", return_value=100), \
             patch.object(context_usage_service, "get_context_window", return_value=1000):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        section_total = sum(section["tokens"] for section in result["sections"])
        self.assertEqual(result["used_tokens"], section_total)
        self.assertEqual(result["primary_agent_usage"]["used_tokens"], section_total)
        self.assertEqual(result["actual_tokens"], 10)

    def test_context_usage_restores_child_agent_usages_from_latest_message(self):
        self.ai_msg.extra_data = {
            "usage": {"prompt_tokens": 120},
            "agent_context_usage": {
                "child_agent_usages": [
                    {
                        "agent_key": "search",
                        "agent_name": "搜索专家",
                        "used_tokens": 40,
                        "context_window": 1000,
                        "percent": 4,
                        "sections": [{"type": "current_task", "title": "当前任务", "tokens": 40, "percent": 4, "content": "北京天气"}],
                    }
                ]
            }
        }
        FakeMessageModel.messages = [self.user_msg, self.ai_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", return_value=1), \
             patch.object(context_usage_service, "get_context_window", return_value=1000):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        self.assertEqual(result["child_agent_usages"][0]["agent_key"], "search")
        self.assertEqual(result["child_agent_usages"][0]["agent_name"], "搜索专家")
        self.assertEqual(result["primary_agent_usage"]["used_tokens"], 120)

    def test_percentage_is_capped_at_100(self):
        FakeMessageModel.messages = [self.user_msg]

        with patch("internal.service.message.context_usage_service.MessageModel", FakeMessageModel), \
             patch("internal.service.message.context_builder.MessageModel", FakeMessageModel), \
             patch.object(context_usage_service, "_load_deepseek_tokenizer", return_value=None), \
             patch.object(context_usage_service, "count_tokens", return_value=999999), \
             patch.object(context_usage_service, "get_context_window", return_value=100), \
             patch.object(context_usage_service, "_get_tools_snapshot", return_value=("", "")):
            result = asyncio.run(context_usage_service.get_session_context_usage("session-1"))

        self.assertEqual(result["percent"], 100)
        self.assertLess(result["remaining_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
