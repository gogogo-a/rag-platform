"""
配置文件加载器
从 config.toml 读取配置
"""
import os
import toml
from pathlib import Path
from typing import Dict, Any, Optional
from log import logger


class ConfigLoader:
    """配置加载器（单例模式）"""
    
    _instance: Optional['ConfigLoader'] = None
    _config: Optional[Dict[str, Any]] = None
    _config_path: Optional[Path] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        # 获取配置文件路径
        current_dir = Path(__file__).parent
        self._config_path = current_dir / "config.toml"
        
        if not self._config_path.exists():
            logger.error(f"配置文件不存在: {self._config_path}")
            raise FileNotFoundError(f"配置文件不存在: {self._config_path}")
        
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config = toml.load(f)
            logger.info(f"配置文件加载成功: {self._config_path}")
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}", exc_info=True)
            raise
    
    def reload(self):
        """重新加载配置"""
        self._config = None
        self._load_config()
        logger.info("配置文件已重新加载")
    
    @property
    def message_mode(self) -> str:
        """获取消息模式 (channel/kafka)"""
        return self._config.get('message', {}).get('mode', 'channel')
    
    @property
    def channel_config(self) -> Dict[str, Any]:
        """获取 Channel 模式配置"""
        return self._config.get('channel', {})
    
    @property
    def kafka_config(self) -> Dict[str, Any]:
        """获取 Kafka 模式配置"""
        return self._config.get('kafka', {})
    
    @property
    def embedding_config(self) -> Dict[str, Any]:
        """获取 Embedding 配置"""
        return self._config.get('embedding', {})
    
    @property
    def vector_config(self) -> Dict[str, Any]:
        """获取向量库配置"""
        return self._config.get('vector', {})
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取指定配置项"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value


# 创建全局配置实例
config = ConfigLoader()


if __name__ == "__main__":
    # 测试配置加载
    print("=" * 80)
    print("配置文件测试")
    print("=" * 80)
    
    print(f"\n消息模式: {config.message_mode}")
    print(f"Channel 配置: {config.channel_config}")
    print(f"Kafka 配置: {config.kafka_config}")
    print(f"Embedding 配置: {config.embedding_config}")
    print(f"向量库配置: {config.vector_config}")
    
    print(f"\n单项配置:")
    print(f"  kafka.topics.document_embedding: {config.get('kafka.topics.document_embedding')}")
    print(f"  channel.max_size: {config.get('channel.max_size')}")
    print(f"  embedding.batch_size: {config.get('embedding.batch_size')}")
