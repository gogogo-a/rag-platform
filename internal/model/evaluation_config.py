"""RAG 评估配置模型。"""
from datetime import datetime
from beanie import Document
from pydantic import Field


class EvaluationConfigModel(Document):
    """RAGAS 评估配置。"""

    key: str = Field(default="ragas", description="配置键")
    ragas_enabled: bool = Field(default=True, description="是否启用 RAGAS 评估")
    ragas_queue_enabled: bool = Field(default=True, description="是否加入 Kafka 队列")
    ragas_sample_rate: float = Field(default=1.0, description="评估抽样比例")
    ragas_max_chunks_per_question: int = Field(default=3, description="每个问题最多评估片段数")
    ragas_min_retrieval_score: float = Field(default=0.0, description="最低检索分数")
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "evaluation_configs"
        indexes = ["key"]
