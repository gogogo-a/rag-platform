"""
统一的消息客户端接口
根据配置自动选择 Channel 或 Kafka 模式
"""
from typing import Callable, Dict, Any, Optional
from log import logger
from internal.document_client.config_loader import config
from internal.document_client.channel.channel_client import channel_client
from internal.document_client.Kafka.kafka_client import get_kafka_client


class MessageClient:
    """
    统一消息客户端
    
    根据 config.toml 中的 message.mode 配置自动选择实现策略：
    - "channel": 使用内存队列（单机模式）
    - "kafka": 使用 Kafka 消息队列（分布式模式）
    """
    
    def __init__(self):
        self.mode = config.message_mode
        self.client = None
        self._init_client()
        logger.info(f"消息客户端已初始化，模式: {self.mode}")
    
    def _init_client(self):
        """根据配置初始化客户端"""
        if self.mode == "channel":
            self._init_channel_client()
        elif self.mode == "kafka":
            self._init_kafka_client()
        else:
            raise ValueError(f"不支持的消息模式: {self.mode}")
    
    def _init_channel_client(self):
        """初始化 Channel 客户端"""
        channel_config = config.channel_config
        
        # 配置已在 ChannelClient 单例中
        channel_client.max_size = channel_config.get('max_size', 1000)
        channel_client.timeout = channel_config.get('timeout', 5)
        
        self.client = channel_client
        logger.info(f"Channel 客户端配置: {channel_config}")
    
    def _init_kafka_client(self):
        """初始化 Kafka 客户端"""
        kafka_config = config.kafka_config
        
        bootstrap_servers = kafka_config.get('bootstrap_servers', ['8.140.245.242:9092'])
        producer_config = kafka_config.get('producer', {})
        consumer_config = kafka_config.get('consumer', {})
        
        self.client = get_kafka_client(
            bootstrap_servers=bootstrap_servers,
            producer_config=producer_config,
            consumer_config=consumer_config
        )
        logger.info(f"Kafka 客户端配置: 服务器={bootstrap_servers}")
    
    def send_message(
        self,
        message: Dict[str, Any],
        topic: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        发送消息
        
        Args:
            message: 消息字典
            topic: 主题名称（仅 Kafka 模式需要）
            **kwargs: 额外参数
        
        Returns:
            bool: 是否发送成功
        """
        try:
            if self.mode == "channel":
                return self.client.send_message(
                    message=message,
                    block=kwargs.get('block', True),
                    timeout=kwargs.get('timeout')
                )
            elif self.mode == "kafka":
                if not topic:
                    # 使用默认主题
                    topic = config.get('kafka.topics.document_embedding', 'document_embedding')
                
                return self.client.send_message(
                    topic=topic,
                    message=message,
                    key=kwargs.get('key'),
                    partition=kwargs.get('partition')
                )
            else:
                logger.error(f"不支持的消息模式: {self.mode}")
                return False
                
        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
            return False
    
    def start_consumer(
        self,
        handler: Callable[[Dict[str, Any]], None],
        topic: Optional[str] = None,
        num_consumers: Optional[int] = None
    ):
        """
        启动消费者
        
        Args:
            handler: 消息处理函数
            topic: 主题名称（仅 Kafka 模式需要）
            num_consumers: 消费者数量（仅 Channel 模式需要）
        """
        try:
            if self.mode == "channel":
                if num_consumers is None:
                    num_consumers = config.get('channel.num_consumers', 3)
                
                self.client.start_consumer(
                    handler=handler,
                    num_consumers=num_consumers
                )
                logger.info(f"Channel 消费者已启动，数量: {num_consumers}")
                
            elif self.mode == "kafka":
                if not topic:
                    # 使用默认主题
                    topic = config.get('kafka.topics.document_embedding', 'document_embedding')
                
                consumer_group = config.get('kafka.consumer.group_id', 'brainwave_embedding_group')
                
                self.client.start_consumer(
                    topic=topic,
                    handler=handler,
                    consumer_group=consumer_group
                )
                logger.info(f"Kafka 消费者已启动，主题: {topic}, 组: {consumer_group}")
            
        except Exception as e:
            logger.error(f"启动消费者失败: {e}", exc_info=True)
            raise
    
    def stop(self):
        """停止客户端"""
        if self.client:
            self.client.stop()
            logger.info(f"消息客户端已停止，模式: {self.mode}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if self.client:
            return self.client.get_stats()
        return {"mode": self.mode, "status": "not_initialized"}


# 创建全局实例
message_client = MessageClient()


if __name__ == "__main__":
    # 测试代码
    print("=" * 80)
    print(f"消息客户端模式: {message_client.mode}")
    print("=" * 80)
    
    # 测试发送消息
    test_message = {
        "task_type": "embedding",
        "document_id": "test_doc_001",
        "content": "这是一个测试文档"
    }
    
    success = message_client.send_message(test_message)
    print(f"\n发送消息: {success}")
    
    # 测试统计信息
    stats = message_client.get_stats()
    print(f"\n统计信息: {stats}")
