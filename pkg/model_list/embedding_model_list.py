"""
Embedding 模型列表
定义所有可用的文本向量化模型
"""
from .base_model import EmbeddingModelConfig


# ==================== BGE 系列模型 ====================

BGE_LARGE_ZH_V1_5 = EmbeddingModelConfig(
    name="bge-large-zh-v1.5",
    model_path="models/bge-large-zh-v1.5",
    description="本地知识库检索向量模型",
    provider="baai",
    model_type="local",
    dimension=1024,
    max_length=512,
    normalize=True
)

BGE_BASE_ZH_V1_5 = EmbeddingModelConfig(
    name="bge-base-zh-v1.5",
    model_path="BAAI/bge-base-zh-v1.5",
    description="速度快，效果好",
    provider="baai",
    model_type="local",
    dimension=768,
    max_length=512,
    normalize=True
)


# ==================== 其他模型 ====================

TEXT2VEC_BASE_CHINESE = EmbeddingModelConfig(
    name="text2vec-base-chinese",
    model_path="shibing624/text2vec-base-chinese",
    description="轻量级中文模型",
    provider="shibing624",
    model_type="local",
    dimension=768,
    max_length=512,
    normalize=True
)


# ==================== 模型字典（用于查找）====================

EMBEDDING_MODELS = {
    "bge-large-zh-v1.5": BGE_LARGE_ZH_V1_5,
    "bge-base-zh-v1.5": BGE_BASE_ZH_V1_5,
    "text2vec-base-chinese": TEXT2VEC_BASE_CHINESE,
}


# ==================== 辅助函数 ====================

def get_embedding_model(model_name: str) -> EmbeddingModelConfig:
    """
    获取 Embedding 模型配置
    
    Args:
        model_name: 模型名称
        
    Returns:
        EmbeddingModelConfig: 模型配置对象
        
    Raises:
        ValueError: 如果模型不存在
    """
    if model_name not in EMBEDDING_MODELS:
        available = ", ".join(EMBEDDING_MODELS.keys())
        raise ValueError(f"未找到 Embedding 模型 '{model_name}'。可用模型: {available}")
    return EMBEDDING_MODELS[model_name]


def list_embedding_models():
    """列出所有可用的 Embedding 模型"""
    return list(EMBEDDING_MODELS.values())
