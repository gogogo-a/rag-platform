"""固定对话测试集模型。"""
from datetime import datetime
from typing import Any, Dict, List

from beanie import Document
from pydantic import Field


class EvaluationCaseModel(Document):
    """固定对话测试集。"""

    case_id: str = Field(..., description="测试集标识")
    name: str = Field(..., description="测试集名称")
    suite_type: str = Field(default="mcp", description="测试集类型 mcp/agent/flow")
    agent_mode: str = Field(default="single", description="运行模式 single/expert")
    target_agent: str = Field(default="", description="目标专家")
    required_tools: List[str] = Field(default_factory=list, description="必须覆盖的能力")
    blocked_terms: List[str] = Field(default_factory=list, description="回答内容拦截词")
    turns: List[Dict[str, Any]] = Field(default_factory=list, description="多轮测试问题")
    min_score: float = Field(default=0.8, description="最低通过分")
    enabled: bool = Field(default=True, description="是否启用")
    description: str = Field(default="", description="测试集说明")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "evaluation_cases"
        indexes = ["case_id", "suite_type", "agent_mode", "enabled", "created_at"]
