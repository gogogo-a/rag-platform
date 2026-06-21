"""
企业级问答缓存模型
具备 AI 判断准入、人工审计与纠错能力
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from beanie import Document
from pydantic import Field
import uuid as uuid_module


class QACacheModel(Document):
    """问答缓存模型"""
    
    uuid: str = Field(default_factory=lambda: str(uuid_module.uuid4()), description="缓存唯一ID")
    
    # 核心问答对
    question: str = Field(..., description="用户问题原文")
    answer: str = Field(..., description="标准/缓存回答")
    
    # AI & 人工验证状态
    is_ai_verified: bool = Field(default=False, description="是否通过 AI 准入评估")
    ai_evaluation_score: float = Field(default=0.0, description="AI 质量评分")
    
    is_human_verified: bool = Field(default=False, description="是否经过人工审核（金牌答案）")
    human_auditor_id: Optional[str] = Field(None, description="审核人ID")
    
    # 统计与反馈
    hit_count: int = Field(default=0, description="缓存命中次数")
    like_count: int = Field(default=0, description="点赞数")
    dislike_count: int = Field(default=0, description="点踩数（达到阈值自动失效缓存）")
    
    # 一致性保护
    source_doc_uuids: List[str] = Field(default=[], description="该问答依赖的源文档列表")
    is_active: bool = Field(default=True, description="缓存是否生效")
    
    # 元数据
    category: Optional[str] = Field(None, description="业务分类")
    metadata: Dict[str, Any] = Field(default={}, description="扩展信息")
    
    create_at: datetime = Field(default_factory=datetime.now)
    update_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "qa_caches"
        indexes = [
            "uuid",
            "is_active",
            "hit_count"
        ]
