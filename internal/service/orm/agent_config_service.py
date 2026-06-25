"""Agent configuration management service."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from internal.model.agent_config import AgentConfigModel
from internal.service.orm.prompt_service import prompt_service
from pkg.agent_tools_mcp.mcp_config import MCP_TOOLS


DEFAULT_AGENT_CONFIGS: List[Dict[str, Any]] = [
    {
        "agent_key": "knowledge",
        "agent_name": "知识专家",
        "description": "查询知识库、文档和内部资料。",
        "mcp_tools": ["knowledge_search"],
        "prompt_key": "knowledge",
        "enabled": True,
        "sort_order": 10,
    },
    {
        "agent_key": "search",
        "agent_name": "搜索专家",
        "description": "查询网页、实时信息和公开资料。",
        "mcp_tools": ["web_search"],
        "prompt_key": "search",
        "enabled": True,
        "sort_order": 20,
    },
    {
        "agent_key": "location",
        "agent_name": "位置专家",
        "description": "处理天气、地理编码、地点搜索、路线规划和 IP 定位。",
        "mcp_tools": ["geocode", "ip_location", "poi_search", "route_planning", "weather_query"],
        "prompt_key": "location",
        "enabled": True,
        "sort_order": 30,
    },
    {
        "agent_key": "email",
        "agent_name": "邮件专家",
        "description": "处理邮件发送。",
        "mcp_tools": ["email_sender"],
        "prompt_key": "email",
        "enabled": True,
        "sort_order": 40,
    },
]


def _fake_equals(field_name: str, expected: Any):
    return lambda item: getattr(item, field_name, None) == expected


def _fake_contains_any(field_names: List[str], keyword: str):
    lowered = keyword.lower()
    return lambda item: any(lowered in str(getattr(item, field_name, "") or "").lower() for field_name in field_names)


class AgentConfigService:
    """Read and update dynamic sub agent configurations."""

    def __init__(self, available_tool_names: Optional[List[str]] = None):
        self._available_tool_names = available_tool_names

    def available_tool_names(self) -> List[str]:
        if self._available_tool_names is not None:
            return list(self._available_tool_names)
        return [item["name"] for item in MCP_TOOLS]

    def available_tools(self) -> List[Dict[str, str]]:
        available_names = set(self.available_tool_names())
        return [
            {
                "name": item["name"],
                "description": item.get("description", item["name"]),
            }
            for item in MCP_TOOLS
            if item["name"] in available_names
        ]

    async def ensure_defaults(self) -> None:
        available = set(self.available_tool_names())
        for seed in DEFAULT_AGENT_CONFIGS:
            if not any(tool in available for tool in seed["mcp_tools"]):
                continue
            existing = await self._find_one_by(agent_key=seed["agent_key"])
            if existing:
                continue
            await AgentConfigModel(**seed).insert()

    async def list_agents(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        await self.ensure_defaults()
        conditions = []
        if enabled is not None:
            conditions.append(self._condition("enabled", enabled))
        if keyword:
            conditions.append(self._text_condition(["agent_key", "agent_name", "description", "prompt_key"], keyword))

        query = AgentConfigModel.find(*conditions).sort("sort_order", "-updated_at")
        total = await query.count()
        rows = await query.skip((page - 1) * page_size).limit(page_size).to_list()
        return {
            "items": [self._to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def create_agent(self, data: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_defaults()
        payload = self._normalize_payload(data, is_create=True)
        existing = await self._find_one_by(agent_key=payload["agent_key"])
        if existing:
            raise ValueError("Agent标识已存在")
        row = AgentConfigModel(**payload)
        await row.insert()
        await prompt_service.ensure_prompt_for_agent(row.prompt_key, row.agent_name, "")
        return self._to_dict(row)

    async def update_agent(self, agent_uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        row = await self._get_by_uuid(agent_uuid)
        payload = self._normalize_payload(data, is_create=False)
        if "agent_key" in payload and payload["agent_key"] != row.agent_key:
            existing = await self._find_one_by(agent_key=payload["agent_key"])
            if existing:
                raise ValueError("Agent标识已存在")

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = datetime.now()
        await row.save()
        await prompt_service.ensure_prompt_for_agent(row.prompt_key, row.agent_name, "")
        return self._to_dict(row)

    async def set_enabled(self, agent_uuid: str, enabled: bool) -> Dict[str, Any]:
        row = await self._get_by_uuid(agent_uuid)
        row.enabled = bool(enabled)
        row.updated_at = datetime.now()
        await row.save()
        return self._to_dict(row)

    async def list_runtime_agents(self, tool_map: Dict[str, Any]) -> List[Dict[str, Any]]:
        await self.ensure_defaults()
        rows = await AgentConfigModel.find(self._condition("enabled", True)).sort("sort_order", "-updated_at").to_list()
        runtime_agents = []
        for row in rows:
            tools = [tool for tool in row.mcp_tools if tool in tool_map]
            if not tools:
                continue
            runtime_agents.append({**self._to_dict(row), "mcp_tools": tools})
        return runtime_agents

    async def get_options(self) -> Dict[str, Any]:
        return {
            "tools": self.available_tools(),
            "prompts": await prompt_service.get_agent_options(),
        }

    async def _get_by_uuid(self, agent_uuid: str):
        row = await self._find_one_by(uuid=agent_uuid)
        if not row:
            raise ValueError("Agent不存在")
        return row

    def _normalize_payload(self, data: Dict[str, Any], is_create: bool) -> Dict[str, Any]:
        payload = {}
        for key in ["agent_key", "agent_name", "description", "prompt_key"]:
            value = str(data.get(key, "") or "").strip()
            if is_create or value:
                if not value:
                    raise ValueError("Agent信息不能为空")
                payload[key] = value

        if "mcp_tools" in data or is_create:
            tools = data.get("mcp_tools") or []
            if not isinstance(tools, list) or not tools:
                raise ValueError("MCP工具不能为空")
            payload["mcp_tools"] = self._validate_tools(tools)

        if "enabled" in data:
            payload["enabled"] = bool(data.get("enabled"))
        elif is_create:
            payload["enabled"] = True

        if "sort_order" in data:
            payload["sort_order"] = int(data.get("sort_order") or 0)
        elif is_create:
            payload["sort_order"] = 0

        return payload

    def _validate_tools(self, tools: List[str]) -> List[str]:
        available = set(self.available_tool_names())
        cleaned = []
        for tool in tools:
            name = str(tool or "").strip()
            if not name:
                continue
            if name not in available:
                raise ValueError(f"MCP工具不存在: {name}")
            if name not in cleaned:
                cleaned.append(name)
        if not cleaned:
            raise ValueError("MCP工具不能为空")
        return cleaned

    def _condition(self, field_name: str, expected: Any):
        field = getattr(AgentConfigModel, field_name, None)
        if field is None:
            return _fake_equals(field_name, expected)
        try:
            return field == expected
        except Exception:
            return _fake_equals(field_name, expected)

    def _text_condition(self, field_names: List[str], keyword: str):
        if not hasattr(AgentConfigModel, field_names[0]):
            return _fake_contains_any(field_names, keyword)
        return {
            "$or": [
                {field_name: {"$regex": keyword, "$options": "i"}}
                for field_name in field_names
            ]
        }

    async def _find_one_by(self, **kwargs):
        conditions = [self._condition(field_name, expected) for field_name, expected in kwargs.items()]
        return await AgentConfigModel.find_one(*conditions)

    def _to_dict(self, row) -> Dict[str, Any]:
        return {
            "id": str(getattr(row, "id", "") or ""),
            "uuid": row.uuid,
            "agent_key": row.agent_key,
            "agent_name": row.agent_name,
            "description": row.description,
            "mcp_tools": list(row.mcp_tools or []),
            "prompt_key": row.prompt_key,
            "enabled": bool(row.enabled),
            "sort_order": int(row.sort_order or 0),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


agent_config_service = AgentConfigService()
