"""
模型基类定义
所有模型配置的基础类
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class BaseModelConfig:
    """模型配置基类"""
    name: str                    # 模型名称
    model_path: str             # 模型路径（HuggingFace 路径或 API 名称）
    description: str            # 模型描述
    provider: str               # 提供商（ollama/openai/baai 等）
    model_type: str             # 模型类型（local/cloud）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "model_path": self.model_path,
            "description": self.description,
            "provider": self.provider,
            "model_type": self.model_type
        }


@dataclass
class LLMModelConfig(BaseModelConfig):
    """LLM 模型配置"""
    temperature: float = 0.3
    max_tokens: Optional[int] = None
    context_window: Optional[int] = None
    timeout: int = 120
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "context_window": self.context_window,
            "timeout": self.timeout
        })
        return data


@dataclass
class EmbeddingModelConfig(BaseModelConfig):
    """Embedding 模型配置"""
    dimension: int              # 向量维度
    max_length: int             # 最大序列长度
    normalize: bool = True      # 是否归一化
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "dimension": self.dimension,
            "max_length": self.max_length,
            "normalize": self.normalize
        })
        return data


@dataclass
class RerankerModelConfig(BaseModelConfig):
    """Reranker 模型配置"""
    max_length: int             # 最大序列长度
    use_fp16: bool = False      # 是否使用半精度
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "max_length": self.max_length,
            "use_fp16": self.use_fp16
        })
        return data
