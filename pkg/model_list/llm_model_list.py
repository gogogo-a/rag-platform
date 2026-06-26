"""
LLM 模型列表
定义所有可用的大语言模型
"""
import os

from .base_model import LLMModelConfig


# ==================== 本地模型 ====================

LLAMA_3_2 = LLMModelConfig(
    name="llama3.2",
    model_path="llama3.2",
    description="Llama 3.2 本地模型",
    provider="ollama",
    model_type="local",
    temperature=0.3,
    max_tokens=2048,
    context_window=int(os.getenv("LLAMA_CONTEXT_WINDOW", os.getenv("OLLAMA_NUM_CTX", "8192"))),
    timeout=120
)


# ==================== 云端模型 ====================

DEEPSEEK_CHAT = LLMModelConfig(
    name="deepseek-chat",
    model_path="deepseek-chat",
    description="DeepSeek Chat 云端模型",
    provider="deepseek",
    model_type="cloud",
    temperature=0.3,
    max_tokens=4096,
    context_window=int(os.getenv("DEEPSEEK_CONTEXT_WINDOW", "1000000")),
    timeout=30  # 🔥 调整为 30 秒，避免长时间等待
)


# ==================== 模型字典（用于查找）====================

LLM_MODELS = {
    # 本地模型
    "llama3.2": LLAMA_3_2,
    
    # 云端模型
    "deepseek-chat": DEEPSEEK_CHAT,
}


# ==================== 辅助函数 ====================

def get_llm_model(model_name: str) -> LLMModelConfig:
    """
    获取 LLM 模型配置
    
    Args:
        model_name: 模型名称
        
    Returns:
        LLMModelConfig: 模型配置对象
        
    Raises:
        ValueError: 如果模型不存在
    """
    if model_name not in LLM_MODELS:
        available = ", ".join(LLM_MODELS.keys())
        raise ValueError(f"未找到 LLM 模型 '{model_name}'。可用模型: {available}")
    return LLM_MODELS[model_name]


def list_llm_models():
    """列出所有可用的 LLM 模型"""
    return list(LLM_MODELS.values())
