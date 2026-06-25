"""Stored expert workflow experience."""

from datetime import datetime
from typing import Dict, List, Optional
import uuid as uuid_module

from beanie import Document
from pydantic import Field


class ExpertExperienceModel(Document):
    uuid: str = Field(default_factory=lambda: str(uuid_module.uuid4()), description="唯一ID")
    question_id: str = Field(..., description="问题编号")
    question: str = Field(..., description="用户问题")
    answer: str = Field(default="", description="最终回答")
    expert_results: List[Dict] = Field(default=[], description="专家结果")
    failed_tasks: List[Dict] = Field(default=[], description="失败任务")
    lesson: str = Field(default="", description="可复用经验")
    vector_id: Optional[str] = Field(None, description="向量记录 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    class Settings:
        name = "expert_experiences"
