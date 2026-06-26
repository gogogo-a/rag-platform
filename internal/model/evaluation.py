"""
RAG 评估与评分模型
用于量化系统生成的回答质量
"""
from datetime import datetime
from typing import Any, Dict, Optional
from beanie import Document
from pydantic import Field


class EvaluationModel(Document):
    """RAG 效果评估模型"""
    
    # 关联对象
    target_id: str = Field(..., description="关联的消息ID或思维链ID")
    target_type: str = Field(..., description="关联类型 (message/thought_chain)")

    question: Optional[str] = Field(None, description="用户问题")
    answer: Optional[str] = Field(None, description="AI 回答")
    session_id: Optional[str] = Field(None, description="会话ID")
    user_id: Optional[str] = Field(None, description="用户ID")
    message_id: Optional[str] = Field(None, description="AI 消息ID")
    tool_name: Optional[str] = Field(None, description="工具名称")
    document_uuid: Optional[str] = Field(None, description="文档ID")
    filename: Optional[str] = Field(None, description="文档名称")
    chunk_index: int = Field(default=0, description="文本块序号")
    retrieved_text: Optional[str] = Field(None, description="检索返回文本")
    vector_score: float = Field(default=0.0, description="向量检索分数")
    rerank_score: float = Field(default=0.0, description="重排分数")
    ragas_status: str = Field(default="not_started", description="RAGAS 评估状态")
    ragas_error: Optional[str] = Field(None, description="RAGAS 评估错误")
    queue_status: str = Field(default="not_queued", description="评估队列状态")
    queued_at: Optional[datetime] = Field(None, description="入队时间")
    started_at: Optional[datetime] = Field(None, description="开始评估时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    retry_count: int = Field(default=0, description="重试次数")
    
    # RAGAS 维度评分
    faithfulness: float = Field(default=0.0, description="忠实度：回答是否基于检索内容")
    answer_relevance: float = Field(default=0.0, description="回答相关度：回答是否直接解决了问题")
    context_precision: float = Field(default=0.0, description="上下文精准度：检索出的内容是否有用")
    context_recall: float = Field(default=0.0, description="上下文召回率：是否找齐了关键信息")
    
    # 综合评价
    evaluation_type: str = Field(default="rag", description="评估类型 (rag/normal_reply/long_context/tool_call/multi_agent)")
    llm_score: float = Field(default=0.0, description="LLM 质量评分，0-1")
    rule_score: float = Field(default=0.0, description="规则评分，0-1")
    score_reason: Optional[str] = Field(None, description="LLM 评分原因")
    score_breakdown: Dict[str, Any] = Field(default_factory=dict, description="评分构成")
    overall_score: float = Field(default=0.0, description="综合得分")
    evaluator: str = Field(default="llm", description="评估者类型 (llm/human/ragas)")
    comment: Optional[str] = Field(None, description="详细评语/改进建议")

    # 固定测试集
    case_id: Optional[str] = Field(None, description="固定测试集ID")
    case_name: Optional[str] = Field(None, description="固定测试集名称")
    suite_type: Optional[str] = Field(None, description="测试集类型 (mcp/agent/flow)")
    turn_index: Optional[int] = Field(None, description="测试轮次")
    agent_mode: Optional[str] = Field(None, description="Agent 模式")
    target_agent: Optional[str] = Field(None, description="目标专家")
    required_tools: list[str] = Field(default_factory=list, description="必须覆盖的能力")
    triggered_tools: list[str] = Field(default_factory=list, description="本轮覆盖到的能力")
    
    # 数据流向
    dataset_type: str = Field(default="production", description="数据集类型 (production/benchmark)")
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "evaluations"
        indexes = [
            "target_id",
            "target_type",
            "evaluation_type",
            "dataset_type",
            "overall_score",
            "case_id",
            "suite_type",
            "ragas_status",
            "queue_status",
            "created_at"
        ]
