"""Dynamic expert definitions and MCP tool grouping."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ExpertDefinition:
    name: str
    display_name: str
    tool_name: str
    description: str
    mcp_tools: List[str]
    prompt_name: str
    enabled: bool = True
    sort_order: int = 0


EXPERT_DEFINITIONS: Dict[str, ExpertDefinition] = {
    "knowledge": ExpertDefinition(
        name="knowledge",
        display_name="知识库专家",
        tool_name="ask_knowledge_expert",
        description="查询知识库、文档和内部资料。",
        mcp_tools=["knowledge_search"],
        prompt_name="knowledge",
    ),
    "search": ExpertDefinition(
        name="search",
        display_name="搜索专家",
        tool_name="ask_search_expert",
        description="查询网页、实时信息和公开资料。",
        mcp_tools=["web_search"],
        prompt_name="search",
    ),
    "location": ExpertDefinition(
        name="location",
        display_name="位置专家",
        tool_name="ask_location_expert",
        description="处理天气、地理编码、地点搜索、路线规划和 IP 定位。",
        mcp_tools=["geocode", "ip_location", "poi_search", "route_planning", "weather_query"],
        prompt_name="location",
    ),
    "email": ExpertDefinition(
        name="email",
        display_name="邮件专家",
        tool_name="ask_email_expert",
        description="处理邮件发送。",
        mcp_tools=["email_sender"],
        prompt_name="email",
    ),
}


class ExpertAgentRegistry:
    def __init__(self, tool_map: Dict[str, Any]):
        self.tool_map = tool_map
        self._definitions: Dict[str, ExpertDefinition] = {}
        self._loaded = False

    async def load(self) -> None:
        if self._loaded:
            return
        from internal.service.orm.agent_config_service import agent_config_service

        configs = await agent_config_service.list_runtime_agents(self.tool_map)
        self._definitions = {
            config["agent_key"]: ExpertDefinition(
                name=config["agent_key"],
                display_name=config["agent_name"],
                tool_name=f"ask_{config['agent_key']}_expert",
                description=config["description"],
                mcp_tools=config["mcp_tools"],
                prompt_name=config["prompt_key"],
                enabled=config["enabled"],
                sort_order=config["sort_order"],
            )
            for config in configs
        }
        self._loaded = True

    def get_definition(self, expert_name: str) -> ExpertDefinition:
        definitions = self._definitions if self._loaded else EXPERT_DEFINITIONS
        return definitions[expert_name]

    def get_tools_for_expert(self, expert_name: str) -> Dict[str, Any]:
        definition = self.get_definition(expert_name)
        return self.get_tools_for_definition(definition)

    def get_tools_for_definition(self, definition: ExpertDefinition) -> Dict[str, Any]:
        return {
            tool_name: self.tool_map[tool_name]
            for tool_name in definition.mcp_tools
            if tool_name in self.tool_map
        }

    async def get_prompt_for_expert(self, expert_name: str) -> str:
        from internal.service.orm.prompt_service import prompt_service

        await self.load()
        prompt_name = self.get_definition(expert_name).prompt_name
        return await prompt_service.get_active_prompt(prompt_name)

    async def available_experts(self) -> List[ExpertDefinition]:
        await self.load()
        return [
            definition
            for definition in self._definitions.values()
            if definition.enabled and self.get_tools_for_expert(definition.name)
        ]

    async def get_manifest(self) -> List[Dict[str, Any]]:
        manifest = []
        for definition in await self.available_experts():
            manifest.append(
                {
                    "agent_key": definition.name,
                    "agent_name": definition.display_name,
                    "tool_name": definition.tool_name,
                    "description": definition.description,
                    "tools": list(self.get_tools_for_expert(definition.name).keys()),
                    "enabled": definition.enabled,
                }
            )
        return manifest
