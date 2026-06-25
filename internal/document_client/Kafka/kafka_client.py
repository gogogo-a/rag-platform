"""
Kafka 模式客户端 - 使用 kafka-python 实现分布式消息队列
"""
import json
import threading
from typing import Callable, Dict, Any, Optional, List
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
from log import logger


class KafkaClient:
    """Kafka 客户端（单例模式）"""
    
    _instance: Optional['KafkaClient'] = None
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        bootstrap_servers: List[str],
        producer_config: Optional[Dict[str, Any]] = None,
        consumer_config: Optional[Dict[str, Any]] = None
    ):
        if self._initialized:
            return
        
        self.bootstrap_servers = bootstrap_servers
        self.producer_config = producer_config or {}
        self.consumer_config = consumer_config or {}
        
        # 生产者
        self.producer: Optional[KafkaProducer] = None
        
        # 消费者
        self.consumers: Dict[str, KafkaConsumer] = {}
        self.consumer_threads: List[threading.Thread] = []
        self.running = False
        
        self._init_producer()
        self._initialized = True
        
        logger.info(f"Kafka 客户端已初始化，服务器: {bootstrap_servers}")
    
    def _init_producer(self):
        """初始化生产者"""
        try:
            # 默认配置
            default_config = {
                'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
                'key_serializer': lambda k: k.encode('utf-8') if k else None,
                'acks': 'all',
                'retries': 3,
                'compression_type': 'gzip'
            }
            
            # 合并用户配置
            config = {**default_config, **self.producer_config}
            
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                **config
            )
            
            logger.info("Kafka 生产者初始化成功")
            
        except Exception as e:
            logger.error(f"Kafka 生产者初始化失败: {e}", exc_info=True)
            raise
    
    def send_message(
        self,
        topic: str,
        message: Dict[str, Any],
        key: Optional[str] = None,
        partition: Optional[int] = None
    ) -> bool:
        """
        发送消息到 Kafka
        
        Args:
            topic: 主题名称
            message: 消息字典
            key: 消息键（可选，用于分区）
            partition: 指定分区（可选）
        
        Returns:
            bool: 是否发送成功
        """
        if not self.producer:
            logger.error("Kafka 生产者未初始化")
            return False
        
        try:
            future = self.producer.send(
                topic=topic,
                value=message,
                key=key,
                partition=partition
            )
            
            # 等待发送完成（可选，同步发送）
            record_metadata = future.get(timeout=10)
            
            logger.debug(
                f"消息已发送到 Kafka，主题: {topic}, "
                f"分区: {record_metadata.partition}, "
                f"偏移量: {record_metadata.offset}"
            )
            return True
            
        except KafkaError as e:
            logger.error(f"Kafka 发送失败: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"消息发送异常: {e}", exc_info=True)
            return False
    
    def start_consumer(
        self,
        topic: str,
        handler: Callable[[Dict[str, Any]], None],
        consumer_group: Optional[str] = None
    ):
        """
        启动消费者
        
        Args:
            topic: 主题名称
            handler: 消息处理函数
            consumer_group: 消费者组ID
        """
        consumer_key = f"{topic}:{consumer_group or ''}"
        if consumer_key in self.consumers:
            logger.warning(f"主题 {topic} 的消费者已存在")
            return
        
        try:
            # 默认配置
            default_config = {
                'value_deserializer': lambda m: json.loads(m.decode('utf-8')),
                'key_deserializer': lambda k: k.decode('utf-8') if k else None,
                'auto_offset_reset': 'latest',
                'enable_auto_commit': True,
                'session_timeout_ms': 30000
            }
            
            # 合并用户配置
            config = {**default_config, **self.consumer_config}
            
            if consumer_group:
                config['group_id'] = consumer_group
            
            # 创建消费者
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                **config
            )
            
            self.consumers[consumer_key] = consumer
            
            # 启动消费者线程
            self.running = True
            consumer_thread = threading.Thread(
                target=self._consume_loop,
                args=(consumer_key, topic, handler),
                daemon=True,
                name=f"KafkaConsumer-{topic}"
            )
            consumer_thread.start()
            self.consumer_threads.append(consumer_thread)
            
            logger.info(f"Kafka 消费者已启动，主题: {topic}, 组: {consumer_group}")
            
        except Exception as e:
            logger.error(f"Kafka 消费者启动失败: {e}", exc_info=True)
            raise
    
    def _consume_loop(self, consumer_key: str, topic: str, handler: Callable[[Dict[str, Any]], None]):
        """
        消费者循环
        
        Args:
            topic: 主题名称
            handler: 消息处理函数
        """
        consumer = self.consumers[consumer_key]
        logger.info(f"消费者循环已启动: {topic}")
        
        try:
            while self.running:
                # 批量拉取消息
                message_batch = consumer.poll(timeout_ms=1000, max_records=100)
                
                for topic_partition, messages in message_batch.items():
                    for message in messages:
                        try:
                            # 处理消息
                            handler(message.value)
                            logger.debug(
                                f"消费消息成功，主题: {topic}, "
                                f"分区: {message.partition}, "
                                f"偏移量: {message.offset}"
                            )
                        except Exception as e:
                            logger.error(f"消息处理失败: {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"消费者循环异常: {e}", exc_info=True)
        finally:
            logger.info(f"消费者循环已停止: {topic}")
    
    def stop(self):
        """停止所有消费者和生产者"""
        logger.info("正在停止 Kafka 客户端...")
        self.running = False
        
        # 关闭消费者
        for consumer_key, consumer in self.consumers.items():
            try:
                consumer.close()
                logger.info(f"消费者已关闭: {consumer_key}")
            except Exception as e:
                logger.error(f"关闭消费者失败: {e}", exc_info=True)
        
        # 等待消费者线程结束
        for thread in self.consumer_threads:
            thread.join(timeout=5)
        
        # 关闭生产者
        if self.producer:
            try:
                self.producer.flush()
                self.producer.close()
                logger.info("生产者已关闭")
            except Exception as e:
                logger.error(f"关闭生产者失败: {e}", exc_info=True)
        
        logger.info("Kafka 客户端已停止")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "mode": "kafka",
            "bootstrap_servers": self.bootstrap_servers,
            "num_consumers": len(self.consumers),
            "topics": list(self.consumers.keys()),
            "running": self.running
        }


# 创建全局实例（延迟初始化）
kafka_client: Optional[KafkaClient] = None


def get_kafka_client(
    bootstrap_servers: List[str],
    producer_config: Optional[Dict[str, Any]] = None,
    consumer_config: Optional[Dict[str, Any]] = None
) -> KafkaClient:
    """获取 Kafka 客户端实例"""
    global kafka_client
    if kafka_client is None:
        kafka_client = KafkaClient(bootstrap_servers, producer_config, consumer_config)
    return kafka_client
