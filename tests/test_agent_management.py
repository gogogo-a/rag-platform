import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch


class FakeAgentConfigQuery:
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


class FakeAgentConfigModel:
    rows = []

    def __init__(self, **kwargs):
        from uuid import uuid4

        self.id = kwargs.pop("id", None)
        self.uuid = kwargs.pop("uuid", str(uuid4()))
        self.agent_key = kwargs.pop("agent_key")
        self.agent_name = kwargs.pop("agent_name")
        self.description = kwargs.pop("description")
        self.mcp_tools = kwargs.pop("mcp_tools", [])
        self.prompt_key = kwargs.pop("prompt_key")
        self.enabled = kwargs.pop("enabled", True)
        self.sort_order = kwargs.pop("sort_order", 0)
        self.created_at = kwargs.pop("created_at", datetime.now())
        self.updated_at = kwargs.pop("updated_at", datetime.now())

    @classmethod
    def find(cls, *conditions):
        items = cls.rows
        for condition in conditions:
            if callable(condition):
                items = [item for item in items if condition(item)]
        return FakeAgentConfigQuery(items)

    @classmethod
    async def find_one(cls, *conditions):
        items = await cls.find(*conditions).to_list()
        return items[0] if items else None

    async def insert(self):
        self.__class__.rows.append(self)
        return self

    async def save(self):
        return self


class FakePromptService:
    def __init__(self):
        self.created = []

    async def ensure_prompt_for_agent(self, agent_key, agent_name, content=""):
        self.created.append((agent_key, agent_name, content))

    async def get_agent_options(self):
        return [
            {"agent_key": "knowledge", "agent_name": "知识专家", "category": "子 Agent"},
            {"agent_key": "search", "agent_name": "搜索专家", "category": "子 Agent"},
            {"agent_key": "travel", "agent_name": "旅行专家", "category": "子 Agent"},
        ]


class AgentManagementTest(unittest.TestCase):
    def setUp(self):
        FakeAgentConfigModel.rows = []

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_default_agents_are_seeded_as_config_rows(self):
        from internal.service.orm.agent_config_service import AgentConfigService

        with patch("internal.service.orm.agent_config_service.AgentConfigModel", FakeAgentConfigModel):
            service = AgentConfigService(available_tool_names=["knowledge_search", "web_search", "email_sender"])
            self.run_async(service.ensure_defaults())

        agent_keys = [row.agent_key for row in FakeAgentConfigModel.rows]
        self.assertEqual(["knowledge", "search", "email"], agent_keys)
        self.assertEqual(["knowledge_search"], FakeAgentConfigModel.rows[0].mcp_tools)
        self.assertTrue(all(row.enabled for row in FakeAgentConfigModel.rows))

    def test_create_agent_rejects_unknown_mcp_tools(self):
        from internal.service.orm.agent_config_service import AgentConfigService

        with patch("internal.service.orm.agent_config_service.AgentConfigModel", FakeAgentConfigModel):
            service = AgentConfigService(available_tool_names=["web_search"])
            with self.assertRaises(ValueError) as ctx:
                self.run_async(service.create_agent({
                    "agent_key": "travel",
                    "agent_name": "旅行专家",
                    "description": "查询旅行信息",
                    "mcp_tools": ["web_search", "unknown_tool"],
                    "prompt_key": "travel",
                    "enabled": True,
                }))

        self.assertIn("MCP工具不存在", str(ctx.exception))

    def test_create_agent_creates_prompt_and_returns_row(self):
        from internal.service.orm.agent_config_service import AgentConfigService

        fake_prompt_service = FakePromptService()
        with patch("internal.service.orm.agent_config_service.AgentConfigModel", FakeAgentConfigModel), patch(
            "internal.service.orm.agent_config_service.prompt_service", fake_prompt_service
        ):
            service = AgentConfigService(available_tool_names=["web_search"])
            data = self.run_async(service.create_agent({
                "agent_key": "travel",
                "agent_name": "旅行专家",
                "description": "查询旅行信息",
                "mcp_tools": ["web_search"],
                "prompt_key": "travel",
                "enabled": True,
            }))

        self.assertEqual("travel", data["agent_key"])
        self.assertEqual(["web_search"], data["mcp_tools"])
        self.assertEqual([("travel", "旅行专家", "")], fake_prompt_service.created)

    def test_disabled_agent_is_not_available_at_runtime(self):
        from internal.service.orm.agent_config_service import AgentConfigService

        with patch("internal.service.orm.agent_config_service.AgentConfigModel", FakeAgentConfigModel):
            service = AgentConfigService(available_tool_names=["web_search"])
            self.run_async(FakeAgentConfigModel(
                agent_key="search",
                agent_name="搜索专家",
                description="查询公开资料",
                mcp_tools=["web_search"],
                prompt_key="search",
                enabled=False,
            ).insert())
            configs = self.run_async(service.list_runtime_agents({"web_search": object()}))

        self.assertEqual([], configs)

    def test_runtime_agent_requires_at_least_one_available_tool(self):
        from internal.service.orm.agent_config_service import AgentConfigService

        with patch("internal.service.orm.agent_config_service.AgentConfigModel", FakeAgentConfigModel):
            service = AgentConfigService(available_tool_names=["web_search"])
            self.run_async(FakeAgentConfigModel(
                agent_key="search",
                agent_name="搜索专家",
                description="查询公开资料",
                mcp_tools=["web_search"],
                prompt_key="search",
                enabled=True,
            ).insert())
            configs = self.run_async(service.list_runtime_agents({}))

        self.assertEqual([], configs)

    def test_options_include_available_tools_and_prompt_rows(self):
        from internal.service.orm.agent_config_service import AgentConfigService

        fake_prompt_service = FakePromptService()
        with patch("internal.service.orm.agent_config_service.prompt_service", fake_prompt_service):
            service = AgentConfigService(available_tool_names=["web_search"])
            options = self.run_async(service.get_options())

        self.assertEqual([{"name": "web_search", "description": "网页搜索工具"}], options["tools"])
        self.assertEqual("travel", options["prompts"][2]["agent_key"])


if __name__ == "__main__":
    unittest.main()
