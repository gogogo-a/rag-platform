"""
思维链模型
用于存储 Agent 的完整推理过程
使用 Beanie ODM 映射到 MongoDB
"""
from datetime import datetime
from typing import List, Dict, Optional
from beanie import Document
from pydantic import Field
import uuid as uuid_module


class ThoughtChainModel(Document):
    """
    思维链模型类 - 使用 Beanie ODM
    
    存储 Agent 的完整推理过程，包括：
    - 用户问题
    - 思考步骤（Thought）
    - 动作步骤（Action）
    - 观察结果（Observation）
    - 最终答案
    - 引用的文档
    """
    
    uuid: str = Field(
        default_factory=lambda: str(uuid_module.uuid4()),
        description="唯一ID"
    )
    session_id: str = Field(..., description="会话ID")
    message_id: Optional[str] = Field(None, description="关联的消息ID")
    
    # 问答内容
    question: str = Field(..., description="用户问题原文")
    answer: str = Field(..., description="AI 回答原文")
    
    # 思维链详情
    thought_chain: List[Dict] = Field(
        default=[],
        description="思维链步骤列表 [{step: int, type: str, content: str}]"
    )
    
    # 引用的文档
    documents_used: List[Dict] = Field(
        default=[],
        description="引用的文档列表 [{uuid: str, name: str}]"
    )
    
    # 元数据
    user_id: Optional[str] = Field(None, description="用户ID")
    model_name: Optional[str] = Field(None, description="使用的模型名称")
    total_steps: int = Field(default=0, description="总步骤数")
    
    # 反馈统计
    like_count: int = Field(default=0, description="点赞数")
    dislike_count: int = Field(default=0, description="踩数")
    is_cached: bool = Field(default=False, description="是否已缓存到 Milvus")
    milvus_id: Optional[int] = Field(None, description="Milvus 中的 ID")
    
    # 用户反馈记录（防止重复点赞/踩）
    # 格式: {user_id: "like" | "dislike"}
    user_feedbacks: Dict[str, str] = Field(
        default={},
        description="用户反馈记录，key为用户ID，value为反馈类型(like/dislike)"
    )
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    
    class Settings:
        name = "thought_chains"  # MongoDB 集合名称
