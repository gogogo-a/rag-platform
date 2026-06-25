"""Agent prompt model."""
from datetime import datetime
from typing import Optional
import uuid as uuid_module

from beanie import Document
from pydantic import Field


class PromptModel(Document):
    """Prompt stored for one agent role."""

    uuid: str = Field(default_factory=lambda: str(uuid_module.uuid4()), description="Prompt唯一ID")
    agent_key: str = Field(..., description="Agent标识")
    agent_name: str = Field(..., description="Agent名称")
    category: str = Field(..., description="Prompt类别")
    content: str = Field(..., description="Prompt内容")
    is_active: bool = Field(default=True, description="是否当前生效")
    is_copy: bool = Field(default=False, description="是否为副本")
    source_uuid: Optional[str] = Field(default=None, description="来源Prompt ID")
    version_name: str = Field(default="默认版本", description="版本名称")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Settings:
        name = "agent_prompts"
        indexes = [
            "uuid",
            "agent_key",
            "category",
            "is_active",
            [("agent_key", 1), ("is_active", 1)],
        ]
