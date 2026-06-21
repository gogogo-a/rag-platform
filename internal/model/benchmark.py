"""
RAG 基准测试集模型 (Golden Dataset)
用于离线测试系统的准确率
"""
from datetime import datetime
from typing import Optional, List
from beanie import Document
from pydantic import Field


class BenchmarkModel(Document):
    """RAG 基准测试集模型"""
    
    question: str = Field(..., description="基准问题")
    ground_truth: str = Field(..., description="标准答案 (Ground Truth)")
    
    expected_doc_uuids: List[str] = Field(default=[], description="预期应该被检索到的文档ID")
    category: str = Field(default="general", description="分类：如'常见病'、'急救场景'")
    difficulty: int = Field(default=1, description="难度等级 (1-5)")
    
    is_active: bool = Field(default=True, description="是否参与当前测试轮次")
    
    created_at: datetime = Field(default_factory=datetime.now)
    update_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "benchmarks"
        indexes = [
            "category",
            "difficulty"
        ]
