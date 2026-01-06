"""
全局常量配置
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ==================== HuggingFace 模型配置 ====================
# 需要在导入 transformers/sentence-transformers 之前设置
# 如果模型已下载到本地缓存，设置为 1 可避免联网检查

TRANSFORMERS_OFFLINE = os.getenv("TRANSFORMERS_OFFLINE", "1")
HF_HUB_OFFLINE = os.getenv("HF_HUB_OFFLINE", "1")

# 设置到环境变量中，影响后续导入的库
if TRANSFORMERS_OFFLINE == "1":
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    # 使用 stderr 避免污染 MCP 的 stdout
    import sys
    print("✓ HuggingFace Transformers 离线模式已启用", file=sys.stderr)

if HF_HUB_OFFLINE == "1":
    os.environ["HF_HUB_OFFLINE"] = "1"
    import sys
    print("✓ HuggingFace Hub 离线模式已启用", file=sys.stderr)

# HuggingFace 镜像配置（可选，用于国内访问）
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "")
if HF_ENDPOINT:
    os.environ["HF_ENDPOINT"] = HF_ENDPOINT
    print(f"✓ HuggingFace 镜像已设置: {HF_ENDPOINT}")

# Ollama 配置
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# Token 限制配置
MAX_TOKEN = int(os.getenv("MAX_TOKEN_LIMIT_FOR_SUMMARY", "6400"))

# 触发总结的消息数量阈值
SUMMARY_MESSAGE_THRESHOLD = int(os.getenv("SUMMARY_MESSAGE_THRESHOLD", "10"))

# MongoDB 配置
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://root:rootpassword@localhost:27017/")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "rag_platform")

# Milvus 向量数据库配置
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
MILVUS_USER = os.getenv("MILVUS_USER", "root")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "rootpassword")
MILVUS_DB_NAME = os.getenv("MILVUS_DB_NAME", "rag_platform")
MILVUS_COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME", "documents")

# Redis 缓存配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# 运行模式（设备选择）
def _get_device():
    """
    智能检测并返回合适的设备
    
    支持的配置值：
    - "cpu": 使用 CPU
    - "cuda": 使用 NVIDIA GPU
    - "mps": 使用 Apple Silicon GPU
    - "gpu" 或 "auto": 自动检测最佳 GPU
    
    返回：
    - "cpu", "cuda", 或 "mps"
    """
    mode = os.getenv("RUNNING_MODE", "cpu").lower()
    
    # 如果用户指定了具体设备，直接返回
    if mode in ["cpu", "cuda", "mps"]:
        return mode
    
    # 如果用户设置为 "gpu" 或 "auto"，自动检测
    if mode in ["gpu", "auto"]:
        try:
            import torch
            
            # 优先检测 CUDA (NVIDIA GPU)
            if torch.cuda.is_available():
                return "cuda"
            
            # 检测 MPS (Apple Silicon)
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            
            # 没有 GPU，使用 CPU
            print("⚠️  未检测到可用 GPU，使用 CPU")
            return "cpu"
            
        except ImportError:
            print("⚠️  未安装 PyTorch，无法自动检测 GPU，使用 CPU")
            return "cpu"
    
    # 未知配置，默认使用 CPU
    print(f"⚠️  未知的 RUNNING_MODE 值: {mode}，使用 CPU")
    return "cpu"

RUNNING_MODE = _get_device()

# ==================== 邮件服务配置 ====================
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_HOST_USER)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
EMAIL_VERIFY_SSL = os.getenv("EMAIL_VERIFY_SSL", "False").lower() == "true"

# ==================== 安全配置 ====================
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key_please_change_in_production")

# ==================== 图片识别配置 ====================
# 图片内容识别（使用 Ollama LLaVA）
ENABLE_VISION = os.getenv("ENABLE_VISION", "true").lower() == "true"
VISION_MODEL = os.getenv("VISION_MODEL", "llava:7b")

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

# ==================== 百度千帆配置 ====================
# 百度千帆 API Token（用于网页搜索等服务）
BAIDU_TOKEN = os.getenv("BAIDU_TOKEN", "")

# ==================== 高德地图配置 ====================
# 高德地图 API Key（用于天气查询等服务）
GAODE_API_KEY = os.getenv("GAODE_API_KEY", "")