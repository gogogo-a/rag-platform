"""
RAG 评估与评分模型
用于量化系统生成的回答质量
"""
from datetime import datetime
from typing import Optional, Dict, Any
from beanie import Document
from pydantic import Field


class EvaluationModel(Document):
    """RAG 效果评估模型"""
    
    # 关联对象
    target_id: str = Field(..., description="关联的消息ID或思维链ID")
    target_type: str = Field(..., description="关联类型 (message/thought_chain)")
    
    # RAGAS 维度评分
    faithfulness: float = Field(default=0.0, description="忠实度：回答是否基于检索内容")
    answer_relevance: float = Field(default=0.0, description="回答相关度：回答是否直接解决了问题")
    context_precision: float = Field(default=0.0, description="上下文精准度：检索出的内容是否有用")
    context_recall: float = Field(default=0.0, description="上下文召回率：是否找齐了关键信息")
    
    # 综合评价
    overall_score: float = Field(default=0.0, description="综合得分")
    evaluator: str = Field(default="llm", description="评估者类型 (llm/human/ragas)")
    comment: Optional[str] = Field(None, description="详细评语/改进建议")
    
    # 数据流向
    dataset_type: str = Field(default="production", description="数据集类型 (production/benchmark)")
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "evaluations"
        indexes = [
            "target_id",
            "dataset_type",
            "overall_score"
        ]
