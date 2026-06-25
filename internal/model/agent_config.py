"""Dynamic sub agent configuration model."""
from datetime import datetime
from typing import List
import uuid as uuid_module

from beanie import Document
from pydantic import Field


class AgentConfigModel(Document):
    """Configurable sub agent stored in MongoDB."""

    uuid: str = Field(default_factory=lambda: str(uuid_module.uuid4()), description="Agent配置唯一ID")
    agent_key: str = Field(..., description="Agent标识")
    agent_name: str = Field(..., description="Agent名称")
    description: str = Field(..., description="Agent描述")
    mcp_tools: List[str] = Field(default_factory=list, description="关联MCP工具")
    prompt_key: str = Field(..., description="关联Prompt标识")
    enabled: bool = Field(default=True, description="是否启用")
    sort_order: int = Field(default=0, description="排序")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Settings:
        name = "agent_configs"
        indexes = [
            "uuid",
            "agent_key",
            "enabled",
            "sort_order",
            [("enabled", 1), ("sort_order", 1)],
        ]
