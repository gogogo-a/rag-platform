"""
文档分块模型
支持父子文档层级结构 (Small-to-Big Retrieval)
"""
from datetime import datetime
from typing import Optional, Dict, Any
from beanie import Document
from pydantic import Field
import uuid as uuid_module


class ChunkModel(Document):
    """文档分块模型 - 用于存储更细粒度的文本块"""
    
    uuid: str = Field(default_factory=lambda: str(uuid_module.uuid4()), description="分块唯一ID")
    document_uuid: str = Field(..., description="所属文档UUID")
    parent_chunk_uuid: Optional[str] = Field(None, description="父级分块UUID（支持层级结构）")
    
    content: str = Field(..., description="分块文本内容")
    full_content: Optional[str] = Field(None, description="完整上下文内容（用于召回给LLM）")
    
    index: int = Field(default=0, description="在文档中的原始顺序")
    page_number: Optional[int] = Field(None, description="所在页码")
    
    # 向量数据库关联
    vector_id: Optional[int] = Field(None, description="Milvus 中的记录 ID")
    embedding_model: Optional[str] = Field(None, description="使用的 Embedding 模型名称")
    
    metadata: Dict[str, Any] = Field(default={}, description="扩展元数据")
    
    create_at: datetime = Field(default_factory=datetime.now)
    update_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "chunks"
        indexes = [
            "uuid",
            "document_uuid",
            "parent_chunk_uuid"
        ]
