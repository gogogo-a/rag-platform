import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch


class FakePromptQuery:
    def __init__(self, items):
        self.items = items
        self._skip = 0
        self._limit = None

    def sort(self, *_args):
        return self

    def skip(self, count):
        self._skip = count
        return self

    def limit(self, count):
        self._limit = count
        return self

    async def to_list(self):
        end = None if self._limit is None else self._skip + self._limit
        return self.items[self._skip:end]

    async def count(self):
        return len(self.items)


class FakePromptModel:
    rows = []

    def __init__(self, **kwargs):
        from uuid import uuid4

        self.id = kwargs.pop("id", None)
        self.uuid = kwargs.pop("uuid", str(uuid4()))
        self.agent_key = kwargs.pop("agent_key")
        self.agent_name = kwargs.pop("agent_name")
        self.category = kwargs.pop("category")
        self.content = kwargs.pop("content")
        self.is_active = kwargs.pop("is_active", True)
        self.is_copy = kwargs.pop("is_copy", False)
        self.source_uuid = kwargs.pop("source_uuid", None)
        self.version_name = kwargs.pop("version_name", "默认版本")
        self.created_at = kwargs.pop("created_at", datetime.now())
        self.updated_at = kwargs.pop("updated_at", datetime.now())

    @classmethod
    def find(cls, *conditions):
        items = cls.rows
        for condition in conditions:
            if callable(condition):
                items = [item for item in items if condition(item)]
        return FakePromptQuery(items)

    @classmethod
    async def find_one(cls, *conditions):
        items = await cls.find(*conditions).to_list()
        return items[0] if items else None

    async def insert(self):
        self.__class__.rows.append(self)
        return self

    async def save(self):
        return self


class PromptManagementTest(unittest.TestCase):
    def setUp(self):
        FakePromptModel.rows = []

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_options_list_fixed_agent_categories_without_file_prompts(self):
        from internal.service.orm.prompt_service import PromptService

        with patch("internal.service.orm.prompt_service.PromptModel", FakePromptModel):
            service = PromptService()
            options = service.get_options()

        agent_keys = {row["agent_key"] for row in options["agents"]}
        self.assertEqual(agent_keys, {"single", "supervisor", "knowledge", "search", "location", "email"})

    def test_update_without_copy_modifies_current_prompt(self):
        from internal.service.orm.prompt_service import PromptService

        with patch("internal.service.orm.prompt_service.PromptModel", FakePromptModel):
            service = PromptService()
            awaitable = FakePromptModel(
                agent_key="single",
                agent_name="普通主 Agent",
                category="普通主 Agent",
                content="旧 Prompt",
            ).insert()
            self.run_async(awaitable)
            row = next(item for item in FakePromptModel.rows if item.agent_key == "single")
            data = self.run_async(service.update_prompt(row.uuid, "新的普通 Prompt", save_copy=False))

        self.assertEqual(len([item for item in FakePromptModel.rows if item.agent_key == "single"]), 1)
        self.assertEqual(row.content, "新的普通 Prompt")
        self.assertEqual(data["content"], "新的普通 Prompt")

    def test_update_with_copy_creates_timestamped_active_copy(self):
        from internal.service.orm.prompt_service import PromptService

        fixed_now = datetime(2026, 6, 24, 15, 30, 5)
        with patch("internal.service.orm.prompt_service.PromptModel", FakePromptModel), patch(
            "internal.service.orm.prompt_service.datetime"
        ) as mocked_datetime:
            mocked_datetime.now.return_value = fixed_now
            mocked_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            service = PromptService()
            self.run_async(
                FakePromptModel(
                    agent_key="knowledge",
                    agent_name="知识专家",
                    category="子 Agent",
                    content="旧知识 Prompt",
                ).insert()
            )
            row = next(item for item in FakePromptModel.rows if item.agent_key == "knowledge")
            data = self.run_async(service.update_prompt(row.uuid, "新版知识专家 Prompt", save_copy=True))

        knowledge_rows = [item for item in FakePromptModel.rows if item.agent_key == "knowledge"]
        self.assertEqual(len(knowledge_rows), 2)
        active_rows = [item for item in knowledge_rows if item.is_active]
        self.assertEqual(len(active_rows), 1)
        self.assertEqual(active_rows[0].content, "新版知识专家 Prompt")
        self.assertTrue(active_rows[0].version_name.startswith("20260624153005-"))
        self.assertEqual(active_rows[0].source_uuid, row.uuid)
        self.assertFalse(row.is_active)
        self.assertEqual(data["uuid"], active_rows[0].uuid)

    def test_activate_prompt_keeps_only_one_active_prompt_per_agent(self):
        from internal.service.orm.prompt_service import PromptService

        with patch("internal.service.orm.prompt_service.PromptModel", FakePromptModel):
            service = PromptService()
            self.run_async(
                FakePromptModel(
                    agent_key="email",
                    agent_name="邮件专家",
                    category="子 Agent",
                    content="旧邮件 Prompt",
                ).insert()
            )
            row = next(item for item in FakePromptModel.rows if item.agent_key == "email")
            copied = self.run_async(service.update_prompt(row.uuid, "邮件新版", save_copy=True))
            self.run_async(service.activate_prompt(row.uuid))

        email_rows = [item for item in FakePromptModel.rows if item.agent_key == "email"]
        active_rows = [item for item in email_rows if item.is_active]
        self.assertEqual(len(active_rows), 1)
        self.assertEqual(active_rows[0].uuid, row.uuid)
        self.assertNotEqual(copied["uuid"], active_rows[0].uuid)

    def test_runtime_prompt_reads_active_mongo_prompt(self):
        from internal.service.orm.prompt_service import PromptService

        with patch("internal.service.orm.prompt_service.PromptModel", FakePromptModel):
            service = PromptService()
            self.run_async(
                FakePromptModel(
                    agent_key="supervisor",
                    agent_name="专家模式主 Agent",
                    category="专家主控 Agent",
                    content="旧主控 Prompt",
                ).insert()
            )
            row = next(item for item in FakePromptModel.rows if item.agent_key == "supervisor")
            self.run_async(service.update_prompt(row.uuid, "主控新版 Prompt", save_copy=False))
            prompt = self.run_async(service.get_active_prompt("supervisor"))

        self.assertEqual(prompt, "主控新版 Prompt")

    def test_missing_active_prompt_raises_error(self):
        from internal.service.orm.prompt_service import PromptService

        with patch("internal.service.orm.prompt_service.PromptModel", FakePromptModel):
            service = PromptService()
            with self.assertRaises(ValueError):
                self.run_async(service.get_active_prompt("single"))


if __name__ == "__main__":
    unittest.main()
